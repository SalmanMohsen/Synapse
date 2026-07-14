from datetime import datetime

from pydantic import BaseModel

from app.agent_run.models import AgentRunStatus, AgentRunStepStatus


class AgentRunStepRead(BaseModel):
    id: str
    agent_run_id: str
    step_number: int
    description: str
    status: AgentRunStepStatus
    model_prompt: str | None
    model_response: str | None
    error: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class AgentRunRead(BaseModel):
    id: str
    ticket_id: str
    status: AgentRunStatus
    plan_json: dict | None
    attempt_count: int
    edited_by_user_id: str | None
    edited_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}

class AgentRunEditRequest(BaseModel):
    plan_json: dict