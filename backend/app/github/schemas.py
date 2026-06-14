# backend/app/github/schemas.py (new file)
from datetime import datetime
from pydantic import BaseModel


class GitIntegrationRead(BaseModel):
    id: str
    project_id: str
    github_app_installation_id: str
    repo_full_name: str
    default_branch: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class GitInstallUrlResponse(BaseModel):
    install_url: str