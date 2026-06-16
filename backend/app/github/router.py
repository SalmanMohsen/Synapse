# backend/app/github/router.py
import json
from fastapi import APIRouter, Depends, Request, Response, BackgroundTasks, status, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse

from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.auth.router import _success_html, _error_html
from app.config import get_settings

from .dependencies import get_git_integration_service
from .schemas import GitIntegrationRead, GitInstallUrlResponse
from .service import GitIntegrationService

router = APIRouter(tags=["github"])
settings = get_settings()


@router.get("/api/v1/projects/{project_id}/github/install", response_model=GitInstallUrlResponse)
async def initiate_github_app_install(
    project_id: str,
    response: Response,
    current_user: User = Depends(get_current_user),
    service: GitIntegrationService = Depends(get_git_integration_service),
) -> GitInstallUrlResponse:
    result = await service.get_install_url(project_id, current_user.id)
    
    # Store the pending project ID in a secure HTTP-only cookie
    response.set_cookie(
        "pending_github_project_id",
        project_id,
        max_age=600,
        path="/",
        httponly=True,
        samesite="lax",
        secure=settings.cookie_secure,
    )
    return result


@router.get("/api/v1/github/app/callback")
async def github_app_callback(
    request: Request,
    response: Response,
    installation_id: str,
    state: str | None = None,
    service: GitIntegrationService = Depends(get_git_integration_service),
):
    cookie_project_id = request.cookies.get("pending_github_project_id")
    
    try:
        await service.handle_callback(installation_id, state, cookie_project_id)
        response.delete_cookie("pending_github_project_id", path="/")
        return HTMLResponse(_success_html("github_install_success"))
    except Exception as exc:
        response.delete_cookie("pending_github_project_id", path="/")
        # Keep the popup responsive: convert the Python exception to closing HTML that logs the error
        return HTMLResponse(_error_html(str(exc), "github_install_error"), status_code=200)


@router.get("/api/v1/projects/{project_id}/github", response_model=GitIntegrationRead)
async def get_github_integration(
    project_id: str,
    current_user: User = Depends(get_current_user),
    service: GitIntegrationService = Depends(get_git_integration_service),
) -> GitIntegrationRead:
    return await service.get_integration(project_id, current_user.id)


@router.delete("/api/v1/projects/{project_id}/github", status_code=status.HTTP_204_NO_CONTENT)
async def delete_github_integration(
    project_id: str,
    current_user: User = Depends(get_current_user),
    service: GitIntegrationService = Depends(get_git_integration_service),
):
    await service.delete_integration(project_id, current_user.id)


@router.post("/api/v1/webhooks/github")
async def handle_github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    service: GitIntegrationService = Depends(get_git_integration_service),
):
    body_bytes = await request.body()
    try:
        payload = json.loads(body_bytes.decode("utf-8"))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON payload structure.")

    delivery_id = request.headers.get("X-GitHub-Delivery", "")
    event_type = request.headers.get("X-GitHub-Event", "")
    action = payload.get("action", "")
    signature = request.headers.get("X-Hub-Signature-256")

    await service.handle_webhook(
        delivery_id=delivery_id,
        event_type=event_type,
        action=action,
        payload=payload,
        body_bytes=body_bytes,
        signature=signature,
    )

    background_tasks.add_task(service.process_webhook_event, delivery_id)

    return {"status": "ok"}