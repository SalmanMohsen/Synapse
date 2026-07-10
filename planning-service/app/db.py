import os
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    JSON,
    MetaData,
    String,
    Table,
    Text,
)
from sqlalchemy.dialects.postgresql import ENUM as PGEnum
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

# Explicit schema coupling mapping strictly to what planning-service reads/writes
metadata = MetaData()

agent_run_status_enum = PGEnum(
    "pending",
    "running",
    "awaiting_review",
    "approved",
    "rejected",
    "failed",
    name="agentrunstatus",
    create_type=False,
)

agent_run_step_status_enum = PGEnum(
    "running",
    "completed",
    "failed",
    name="agentrunstepstatus",
    create_type=False,
)

# --- READ-ONLY TABLES ---

tickets = Table(
    "tickets",
    metadata,
    Column("id", String, primary_key=True),
    Column("channel_id", String, nullable=False),
    Column("title", String(500), nullable=False),
    Column("description", Text, nullable=True),
    Column("status", String(50), nullable=False),
    Column("source", String(50), nullable=False),
    Column("priority", String(50), nullable=False),
    Column("creator_id", String, nullable=True),
)

messages = Table(
    "messages",
    metadata,
    Column("id", String, primary_key=True),
    Column("ticket_id", String, nullable=False),
    Column("author_id", String, nullable=True),
    Column("content", Text, nullable=False),
    Column("type", String(50), nullable=False),
    Column("metadata_json", JSON, nullable=True),
    Column("deleted_at", DateTime(timezone=True), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

skill_files = Table(
    "skill_files",
    metadata,
    Column("id", String, primary_key=True),
    Column("workspace_id", String, nullable=False),
    Column("name", String(100), nullable=False),
    Column("dimension", String(50), nullable=False),  # specialty / technology
    Column("discipline", String(50), nullable=True),
    Column("file_content", Text, nullable=False),
)

skill_assignments = Table(
    "skill_assignments",
    metadata,
    Column("id", String, primary_key=True),
    Column("channel_id", String, nullable=False),
    Column("specialty_file_id", String, nullable=True),
    Column("technology_file_id", String, nullable=True),
)


# --- READ / WRITE TABLES ---

agent_runs = Table(
    "agent_runs",
    metadata,
    Column("id", String, primary_key=True),
    Column("ticket_id", String, nullable=False),
    Column("status", agent_run_status_enum, nullable=False),
    Column("plan_json", JSON, nullable=True),
    Column("attempt_count", Integer, nullable=False, default=0),
    Column("edited_by_user_id", String, nullable=True),
    Column("edited_at", DateTime(timezone=True), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)

agent_run_steps = Table(
    "agent_run_steps",
    metadata,
    Column("id", String, primary_key=True),
    Column("agent_run_id", String, nullable=False),
    Column("step_number", Integer, nullable=False),
    Column("description", String(200), nullable=False),
    Column("status", agent_run_step_status_enum, nullable=False),
    Column("model_prompt", Text, nullable=True),
    Column("model_response", Text, nullable=True),
    Column("error", Text, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
)

git_integrations = Table(
    "git_integrations",
    metadata,
    Column("id", String, primary_key=True),
    Column("project_id", String, nullable=False),
    Column("github_app_installation_id", String(100), nullable=False),
    Column("repo_full_name", String(200), nullable=False),
    Column("default_branch", String(100), nullable=False),
    Column("last_ingested_sha", String(100), nullable=True),  # Added per Step 2/Data Model changes
)


# --- DATABASE CONNECTION ENGINE ---

DATABASE_URL = os.getenv("PLANNING_DATABASE_URL", "postgresql+asyncpg://postgres:postgres@localhost:5432/synapse")

engine = create_async_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)

@asynccontextmanager
async def get_connection() -> AsyncGenerator[AsyncConnection, None]:
    """Provide a direct execution boundary for transaction commits."""
    async with engine.begin() as conn:
        yield conn