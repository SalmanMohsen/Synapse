import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncGenerator

from app.config import DATABASE_URL
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Integer,
    JSON,
    MetaData,
    String,
    Table,
    Text,
    select,
    update,
    insert,
)
from sqlalchemy.dialects.postgresql import ENUM as PGEnum
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

# Explicit schema coupling mapping strictly to what planning-service reads/writes
metadata = MetaData()

# Postgres-native enum types, matching the type names backend's Alembic migration
# already created. create_type=False stops Core from trying to CREATE TYPE.
agent_run_status_enum = PGEnum(
    "pending",
    "running",
    "awaiting_review",
    "approved",
    "rejected",
    "rejected_out_of_scope",
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

message_type_enum = PGEnum(
    "human",
    "system",
    "agent_plan_card",
    name="messagetype",
    create_type=False,
)

ticket_status_enum = PGEnum(
    "backlog",
    "routed",
    "active",
    "in_discussion",
    "consensus_reached",
    "plan_review",
    "agent_working",
    "in_review",
    "merged",
    "closed",
    "split",
    name="ticketstatus",
    create_type=False,
)

agent_run_step_phase_enum = PGEnum(
    "planning",
    "execution",
    name="agentrunstepphase",
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
    Column("status", ticket_status_enum, nullable=False),
    Column("source", String(50), nullable=False),
    Column("priority", String(50), nullable=False),
    Column("creator_id", String, nullable=True),
)

channels = Table(
    "channels",
    metadata,
    Column("id", String, primary_key=True),
    Column("project_id", String, nullable=False),
    Column("name", String(100), nullable=False),
    Column("discipline", String(50), nullable=True),
    Column("is_leads_channel", Boolean, nullable=False, default=False),
)

messages = Table(
    "messages",
    metadata,
    Column("id", String, primary_key=True),
    Column("ticket_id", String, nullable=False),
    Column("author_id", String, nullable=True),
    Column("content", Text, nullable=False),
    Column("type", message_type_enum, nullable=False),
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
    Column("phase", agent_run_step_phase_enum, nullable=False),
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
    Column("last_ingested_sha", String(100), nullable=True),
)


# --- DATABASE CONNECTION ENGINE ---

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


def get_engine():
    """Returns the shared engine."""
    return engine


async def close_engine() -> None:
    """Disposes the engine's connection pool."""
    await engine.dispose()


# --- DATABASE AGENT RUN STEP TRACKING HELPERS ---

async def create_agent_run_step(
    agent_run_id: str,
    step_number: int,
    description: str,
    phase: str = "planning",
) -> str:
    """Create a step in 'running' status. Commits immediately — independent
    of whatever the caller does afterward, so it survives a later failure."""
    step_id = str(uuid.uuid4())
    async with get_connection() as conn:
        await conn.execute(
            agent_run_steps.insert().values(
                id=step_id,
                agent_run_id=agent_run_id,
                step_number=step_number,
                description=description,
                status="running",
                phase=phase,
                created_at=datetime.now(timezone.utc),
            )
        )
    return step_id


async def complete_agent_run_step(
    step_id: str,
    model_prompt: str | None = None,
    model_response: str | None = None,
) -> None:
    async with get_connection() as conn:
        await conn.execute(
            agent_run_steps.update()
            .where(agent_run_steps.c.id == step_id)
            .values(
                status="completed",
                model_prompt=model_prompt,
                model_response=model_response,
            )
        )


async def fail_agent_run_step(
    step_id: str,
    error: str,
    model_prompt: str | None = None,
    model_response: str | None = None,
) -> None:
    async with get_connection() as conn:
        await conn.execute(
            agent_run_steps.update()
            .where(agent_run_steps.c.id == step_id)
            .values(
                status="failed",
                error=error,
                model_prompt=model_prompt,
                model_response=model_response,
            )
        )