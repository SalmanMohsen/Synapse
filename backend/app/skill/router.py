from fastapi import APIRouter, Depends, status
from app.auth.dependencies import get_current_user
from app.auth.models import User
from app.skill.dependencies import get_skill_service
from app.skill.service import SkillService
from app.skill.schemas import SkillFileCreate, SkillFileRead, SkillAssignmentAssignTech, SkillAssignmentRead

router = APIRouter(prefix="/api/v1", tags=["skills"])

@router.post("/workspaces/{workspace_id}/skills", response_model=SkillFileRead, status_code=status.HTTP_201_CREATED)
async def create_skill_file(
    workspace_id: str,
    data: SkillFileCreate,
    current_user: User = Depends(get_current_user),
    service: SkillService = Depends(get_skill_service)
):
    return await service.create_skill_file(workspace_id, current_user.id, data)

@router.post("/channels/{channel_id}/skills/technology", response_model=SkillAssignmentRead)
async def assign_technology_file(
    channel_id: str,
    data: SkillAssignmentAssignTech,
    current_user: User = Depends(get_current_user),
    service: SkillService = Depends(get_skill_service)
):
    return await service.assign_technology_file(channel_id, current_user.id, data)