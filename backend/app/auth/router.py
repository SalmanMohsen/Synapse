import urllib.parse
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth.dependencies import get_auth_service, get_current_user
from app.auth.models import User
from app.auth.schemas import LoginRequest, RegisterRequest, UserRead
from app.auth.service import AuthService
from app.core.config import settings # Assuming you moved config to core based on previous steps

# Specification: All routes prefixed with /api/v1/
router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


# ------------------------------------------------------------------ #
# Cookie helpers                                                     #
# ------------------------------------------------------------------ #

def _set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    # Use settings.DEBUG to toggle secure cookies for local dev
    is_secure = not settings.DEBUG if hasattr(settings, "DEBUG") else True
    base = dict(httponly=True, samesite="lax", secure=is_secure)
    
    response.set_cookie(
        "access_token", access_token,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/",
        **base,
    )
    # refresh_token path is scoped to only reach /auth/refresh
    response.set_cookie(
        "refresh_token", refresh_token,
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 86400,
        path="/api/v1/auth/refresh",
        **base,
    )

def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/api/v1/auth/refresh")


# ------------------------------------------------------------------ #
# Popup OAuth HTML responses                                         #
# ------------------------------------------------------------------ #

def _success_html() -> str:
    # Requires FRONTEND_URL in settings (e.g., http://localhost:3000)
    origin = settings.FRONTEND_URL 
    return f"""<!DOCTYPE html><html><body><script>
if(window.opener){{window.opener.postMessage({{type:'oauth_success'}},'{origin}');}}
window.close();
</script></body></html>"""

def _error_html(reason: str) -> str:
    origin = settings.FRONTEND_URL
    safe = reason.replace("'", "\\'")
    return f"""<!DOCTYPE html><html><body><script>
if(window.opener){{window.opener.postMessage({{type:'oauth_error',reason:'{safe}'}},'{origin}');}}
window.close();
</script></body></html>"""


# ------------------------------------------------------------------ #
# Email / password routes                                            #
# ------------------------------------------------------------------ #

@router.post("/register", response_model=UserRead, status_code=201)
async def register(
    data: RegisterRequest,
    response: Response,
    service: AuthService = Depends(get_auth_service),
):
    user, access_token, refresh_token = await service.register(data)
    _set_auth_cookies(response, access_token, refresh_token)
    return user


@router.post("/login", response_model=UserRead)
async def login(
    data: LoginRequest,
    response: Response,
    service: AuthService = Depends(get_auth_service),
):
    user, access_token, refresh_token = await service.login(data)
    _set_auth_cookies(response, access_token, refresh_token)
    return user


# ------------------------------------------------------------------ #
# GitHub OAuth (popup flow)                                          #
# ------------------------------------------------------------------ #

@router.get("/github")
async def github_oauth_start():
    """Redirect to GitHub — this URL is what the popup window opens."""
    params = urllib.parse.urlencode({
        "client_id": settings.GITHUB_CLIENT_ID,
        "scope": "user:email",
        "allow_signup": "true",
    })
    return RedirectResponse(f"https://github.com/login/oauth/authorize?{params}")


@router.get("/github/callback")
async def github_oauth_callback(
    code: str,
    service: AuthService = Depends(get_auth_service),
):
    """GitHub redirects here. Sets cookies then posts to the opener window."""
    try:
        _, access_token, refresh_token = await service.github_callback(code)
    except Exception as exc:
        return HTMLResponse(_error_html(str(exc)), status_code=200)

    response = HTMLResponse(_success_html())
    _set_auth_cookies(response, access_token, refresh_token)
    return response


# ------------------------------------------------------------------ #
# Google OAuth (popup flow)                                          #
# ------------------------------------------------------------------ #

@router.get("/google")
async def google_oauth_start():
    """Redirect to Google — this URL is what the popup window opens."""
    # FIXED: The redirect URI must point to the backend route that catches the callback
    redirect_uri = f"{settings.BACKEND_URL}/api/v1/auth/google/callback"
    
    params = urllib.parse.urlencode({
        "client_id": settings.GOOGLE_CLIENT_ID,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
        "access_type": "offline",
    })
    return RedirectResponse(f"https://accounts.google.com/o/oauth2/v2/auth?{params}")


@router.get("/google/callback")
async def google_oauth_callback(
    code: str,
    service: AuthService = Depends(get_auth_service),
):
    try:
        _, access_token, refresh_token = await service.google_callback(code)
    except Exception as exc:
        return HTMLResponse(_error_html(str(exc)), status_code=200)

    response = HTMLResponse(_success_html())
    _set_auth_cookies(response, access_token, refresh_token)
    return response


# ------------------------------------------------------------------ #
# Token refresh                                                      #
# ------------------------------------------------------------------ #

@router.post("/refresh")
async def refresh_token(
    request: Request,
    response: Response,
    service: AuthService = Depends(get_auth_service),
):
    """
    The refresh_token cookie is scoped to this path so it only travels here.
    Returns new cookies — the client retries its original request automatically.
    """
    refresh_token = request.cookies.get("refresh_token")
    if not refresh_token:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="No refresh token")

    new_access, new_refresh = await service.refresh(refresh_token)
    _set_auth_cookies(response, new_access, new_refresh)
    return {"detail": "Token refreshed"}


# ------------------------------------------------------------------ #
# Logout                                                             #
# ------------------------------------------------------------------ #

@router.post("/logout")
async def logout(
    request: Request,
    response: Response,
    service: AuthService = Depends(get_auth_service),
):
    access_token = request.cookies.get("access_token")
    refresh_token = request.cookies.get("refresh_token")
    await service.logout(access_token, refresh_token)
    _clear_auth_cookies(response)
    return {"detail": "Logged out"}


# ------------------------------------------------------------------ #
# Current user                                                       #
# ------------------------------------------------------------------ #

@router.get("/me", response_model=UserRead)
async def get_me(current_user: User = Depends(get_current_user)):
    """Called by the frontend on boot to rehydrate session state."""
    return UserRead.model_validate(current_user)