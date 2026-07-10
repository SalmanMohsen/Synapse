from fastapi import HTTPException
from app.skill.uow import AbstractSkillUnitOfWork
from app.skill.schemas import SkillFileCreate, SkillAssignmentAssignTech, SkillFileRead, SkillAssignmentRead
from app.skill.models import SkillDimension
from app.project.models import ProjectRole

class SkillService:
    def __init__(self, uow: AbstractSkillUnitOfWork) -> None:
        self.uow = uow

    async def create_skill_file(self, workspace_id: str, requester_id: str, data: SkillFileCreate) -> SkillFileRead:
        async with self.uow:
            # Check owner access privileges
            wm = await self.uow.workspace_members.get_by_workspace_and_user(workspace_id, requester_id)
            if not wm or not wm.is_owner:
                raise HTTPException(status_code=403, detail="Only workspace owners can manage skill configuration files.")

            if data.dimension == SkillDimension.specialty and not data.discipline:
                raise HTTPException(status_code=400, detail="Discipline mapping field is required for specialty metrics files.")
            if data.dimension == SkillDimension.technology:
                data.discipline = None

            file_record = await self.uow.skills.create_file(
                workspace_id=workspace_id,
                name=data.name,
                dimension=data.dimension,
                discipline=data.discipline,
                file_content=data.file_content
            )
            await self.uow.commit()
            return SkillFileRead.model_validate(file_record)

    async def assign_technology_file(self, channel_id: str, requester_id: str, data: SkillAssignmentAssignTech) -> SkillAssignmentRead:
        async with self.uow:
            channel = await self.uow.channels.get_by_id(channel_id)
            if not channel:
                raise HTTPException(status_code=404, detail="Channel targeted does not exist.")

            project = await self.uow.projects.get_by_id(channel.project_id)
            pm = await self.uow.project_members.get_by_project_and_user(project.id, requester_id)
            wm = await self.uow.workspace_members.get_by_workspace_and_user(project.workspace_id, requester_id)
            
            is_authorized = (wm and wm.is_owner) or (pm and pm.role == ProjectRole.team_lead)
            if not is_authorized:
                raise HTTPException(status_code=403, detail="Only Team Leads or Workspace Owners can assign tech context files.")

            if data.technology_file_id:
                tech_file = await self.uow.skills.get_file_by_id(data.technology_file_id)
                if not tech_file or tech_file.dimension != SkillDimension.technology or tech_file.workspace_id != project.workspace_id:
                    raise HTTPException(status_code=400, detail="Provided ID does not reference a valid tech matrix profile file within this workspace.")

            assignment = await self.uow.skills.get_assignment_by_channel(channel_id)
            if not assignment:
                assignment = await self.uow.skills.create_assignment(
                    channel_id=channel_id,
                    specialty_file_id=None,
                    technology_file_id=data.technology_file_id
                )
            else:
                assignment = await self.uow.skills.update_assignment(assignment, technology_file_id=data.technology_file_id)

            await self.uow.commit()
            return SkillAssignmentRead.model_validate(assignment)