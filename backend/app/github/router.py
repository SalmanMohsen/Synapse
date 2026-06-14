# backend/app/github/router.py (new file)
import json
from fastapi import APIRouter, Depends, Request, BackgroundTasks, status, HTTPException
from fastapi.responses import RedirectResponse

from app.auth.dependencies import get_current_user
from app.auth.models import User

from .dependencies import get_git_integration_service
from .schemas import GitIntegrationRead, GitInstallUrlResponse
from .service import GitIntegrationService

router = APIRouter(tags=["github"])


@router.get("/api/v1/projects/{project_id}/github/install", response_model=GitInstallUrlResponse)
async def initiate_github_app_install(
    project_id: str,
    current_user: User = Depends(get_current_user),
    service: GitIntegrationService = Depends(get_git_integration_service),
) -> GitInstallUrlResponse:
    return await service.get_install_url(project_id, current_user.id)


@router.get("/api/v1/github/app/callback")
async def github_app_callback(
    installation_id: str,
    state: str,
    service: GitIntegrationService = Depends(get_git_integration_service),
):
    redirect_url = await service.handle_callback(installation_id, state)
    return RedirectResponse(url=redirect_url)


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