import urllib.parse
from fastapi import APIRouter, Depends, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse

from app.auth.dependencies import get_auth_service, get_current_user
from app.auth.models import User
from app.auth.schemas import LoginRequest, RegisterRequest, UserRead
from app.auth.service import AuthService
from app.config import get_settings

settings = get_settings()
router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


# ------------------------------------------------------------------ #
# Cookie helpers                                                       #
# ------------------------------------------------------------------ #

def _set_auth_cookies(response: Response, access_token: str, refresh_token: str) -> None:
    base = dict(httponly=True, samesite="lax", secure=settings.cookie_secure)
    response.set_cookie(
        "access_token", access_token,
        max_age=settings.access_token_expire_minutes * 60,
        path="/",
        **base,
    )
    response.set_cookie(
        "refresh_token", refresh_token,
        max_age=settings.refresh_token_expire_days * 86400,
        path="/api/v1/auth/refresh",
        **base,
    )

def _clear_auth_cookies(response: Response) -> None:
    response.delete_cookie("access_token", path="/")
    response.delete_cookie("refresh_token", path="/api/v1/auth/refresh")


# ------------------------------------------------------------------ #
# Popup OAuth HTML helpers                                             #
# ------------------------------------------------------------------ #

def _success_html(event_type: str = "oauth_success") -> str:
    origin = settings.frontend_url
    return f"""<!DOCTYPE html><html><body><script>
if(window.opener){{window.opener.postMessage({{type:'{event_type}'}},'{origin}');}}
window.close();
</script></body></html>"""

def _error_html(reason: str, event_type: str = "oauth_error") -> str:
    origin = settings.frontend_url
    safe = reason.replace("'", "\\'")
    return f"""<!DOCTYPE html><html><body><script>
if(window.opener){{window.opener.postMessage({{type:'{event_type}',reason:'{safe}'}},'{origin}');}}
window.close();
</script></body></html>"""


# ------------------------------------------------------------------ #
# Email / password                                                     #
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
# GitHub OAuth — sign in / register                                    #
# ------------------------------------------------------------------ #

@router.get("/github")
async def github_oauth_start():
    params = urllib.parse.urlencode({
        "client_id": settings.github_client_id,
        "scope": "user:email",
        "allow_signup": "true",
    })
    return RedirectResponse(f"https://github.com/login/oauth/authorize?{params}")


@router.get("/github/callback")
async def github_oauth_callback(
    code: str,
    state: str | None = None,
    service: AuthService = Depends(get_auth_service),
):
    if state and state.startswith("link:"):
        user_id = state.split(":", 1)[1]
        try:
            await service.link_github(user_id, code)
        except Exception as exc:
            return HTMLResponse(_error_html(str(exc), "link_error"), status_code=200)
        return HTMLResponse(_success_html("link_success"))
    
    try:
        _, access_token, refresh_token = await service.github_callback(code)
    except Exception as exc:
        return HTMLResponse(_error_html(str(exc)), status_code=200)

    response = HTMLResponse(_success_html())
    _set_auth_cookies(response, access_token, refresh_token)
    return response


# ------------------------------------------------------------------ #
# GitHub linking — authenticated users only                            #
# ------------------------------------------------------------------ #

@router.get("/link/github")
async def link_github_start(current_user: User = Depends(get_current_user)):
    """Opens GitHub OAuth for account linking (not sign-in)."""
    params = urllib.parse.urlencode({
        "client_id": settings.github_client_id,
        "scope": "user:email",
        "state": f"link:{current_user.id}",
    })
    return RedirectResponse(f"https://github.com/login/oauth/authorize?{params}")


@router.get("/link/github/callback")
async def link_github_callback(
    code: str,
    request: Request,
    service: AuthService = Depends(get_auth_service),
    current_user: User = Depends(get_current_user),
):
    try:
        await service.link_github(current_user.id, code)
    except Exception as exc:
        return HTMLResponse(_error_html(str(exc), "link_error"), status_code=200)

    return HTMLResponse(_success_html("link_success"))


@router.delete("/link/github", response_model=UserRead)
async def unlink_github(
    service: AuthService = Depends(get_auth_service),
    current_user: User = Depends(get_current_user),
):
    return await service.unlink_github(current_user.id)


# ------------------------------------------------------------------ #
# Google OAuth — sign in / register                                    #
# ------------------------------------------------------------------ #

@router.get("/google")
async def google_oauth_start():
    redirect_uri = f"{settings.backend_url}/api/v1/auth/google/callback"
    params = urllib.parse.urlencode({
        "client_id": settings.google_client_id,
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
# Google linking — authenticated users only                            #
# ------------------------------------------------------------------ #

@router.get("/link/google")
async def link_google_start():
    """Opens Google OAuth for account linking (not sign-in)."""
    redirect_uri = f"{settings.backend_url}/api/v1/auth/link/google/callback"
    params = urllib.parse.urlencode({
        "client_id": settings.google_client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid email profile",
    })
    return RedirectResponse(f"https://accounts.google.com/o/oauth2/v2/auth?{params}")


@router.get("/link/google/callback")
async def link_google_callback(
    code: str,
    service: AuthService = Depends(get_auth_service),
    current_user: User = Depends(get_current_user),
):
    try:
        await service.link_google(current_user.id, code)
    except Exception as exc:
        return HTMLResponse(_error_html(str(exc), "link_error"), status_code=200)

    return HTMLResponse(_success_html("link_success"))


@router.delete("/link/google", response_model=UserRead)
async def unlink_google(
    service: AuthService = Depends(get_auth_service),
    current_user: User = Depends(get_current_user),
):
    return await service.unlink_google(current_user.id)


# ------------------------------------------------------------------ #
# Token refresh                                                        #
# ------------------------------------------------------------------ #

@router.post("/refresh")
async def refresh_token(
    request: Request,
    response: Response,
    service: AuthService = Depends(get_auth_service),
):
    token = request.cookies.get("refresh_token")
    if not token:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="No refresh token")

    new_access, new_refresh = await service.refresh(token)
    _set_auth_cookies(response, new_access, new_refresh)
    return {"detail": "Token refreshed"}


# ------------------------------------------------------------------ #
# Logout                                                               #
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
# Current user                                                         #
# ------------------------------------------------------------------ #

@router.get("/me", response_model=UserRead)
async def get_me(current_user: User = Depends(get_current_user)):
    return UserRead.model_validate(current_user)