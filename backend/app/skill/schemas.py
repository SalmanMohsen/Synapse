from datetime import datetime
from pydantic import BaseModel, field_validator
from app.channel.models import ChannelDiscipline
from app.skill.models import SkillDimension

class SkillFileCreate(BaseModel):
    name: str
    dimension: SkillDimension
    discipline: ChannelDiscipline | None = None
    file_content: str

    @field_validator("name")
    @classmethod
    def name_not_empty(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 2 or len(v) > 100:
            raise ValueError("Skill file name must be between 2 and 100 characters.")
        return v

    @field_validator("file_content")
    @classmethod
    def content_not_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("File content cannot be empty.")
        return v

class SkillFileRead(BaseModel):
    id: str
    workspace_id: str
    name: str
    dimension: SkillDimension
    discipline: ChannelDiscipline | None
    file_content: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

class SkillAssignmentAssignTech(BaseModel):
    technology_file_id: str | None

class SkillAssignmentRead(BaseModel):
    id: str
    channel_id: str
    specialty_file_id: str | None
    technology_file_id: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}