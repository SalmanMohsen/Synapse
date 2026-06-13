from datetime import datetime

from pydantic import BaseModel


class ThreadStateRead(BaseModel):
    id: str
    ticket_id: str
    rolling_summary: str | None
    structured_state_json: dict | None
    last_processed_message_id: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}