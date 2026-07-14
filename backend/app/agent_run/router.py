from fastapi import APIRouter, Depends, status

from app.auth.dependencies import get_current_user
from app.auth.models import User

from .dependencies import get_agent_run_service
from .schemas import AgentRunRead, AgentRunEditRequest
from .service import AgentRunService

router = APIRouter(prefix="/api/v1/agent-runs", tags=["agent-runs"])


@router.get("/{run_id}", response_model=AgentRunRead)
async def get_agent_run(
    run_id: str,
    current_user: User = Depends(get_current_user),
    service: AgentRunService = Depends(get_agent_run_service),
):
    return await service.get_run(run_id, current_user.id)


@router.post("/{run_id}/approve", status_code=status.HTTP_204_NO_CONTENT)
async def approve_agent_run_plan(
    run_id: str,
    current_user: User = Depends(get_current_user),
    service: AgentRunService = Depends(get_agent_run_service),
):
    await service.approve_plan(run_id, current_user.id)


@router.post("/{run_id}/reject", status_code=status.HTTP_204_NO_CONTENT)
async def reject_agent_run_plan(
    run_id: str,
    current_user: User = Depends(get_current_user),
    service: AgentRunService = Depends(get_agent_run_service),
):
    await service.reject_plan(run_id, current_user.id)


@router.patch("/{run_id}", response_model=dict)
async def edit_agent_run_plan(
    run_id: str,
    data: AgentRunEditRequest,
    current_user: User = Depends(get_current_user),
    service: AgentRunService = Depends(get_agent_run_service),
):
    return await service.edit_plan(run_id, data.plan_json, current_user.id)