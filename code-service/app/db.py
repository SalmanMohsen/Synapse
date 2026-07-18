"""Thin SQLAlchemy Core schema-coupling for code-service.

Deliberately NOT a shared installable package with backend/planning-service:
backend retains sole ownership of Alembic migrations. This module maps ONLY the
tables code-service actually reads or writes, using Core (not the ORM) so there
is no runtime dependency on backend's declarative models.

Postgres-native enum types use create_type=False — the enum types already exist
(created by backend's Alembic migration); Core must not attempt CREATE TYPE.
"""

import os
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import AsyncGenerator

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
)
from sqlalchemy.dialects.postgresql import ENUM as PGEnum
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

from app.config import DATABASE_URL

metadata = MetaData()


# ------------------------------------------------------------------ #
# Postgres-native enum types (names must match backend's migrations)  #
# ------------------------------------------------------------------ #

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

# check_tier: which validation tier actually ran for a step (Step 9). New enum
# type added by code-agent migration.
check_tier_enum = PGEnum(
    "repo_test_suite",
    "generic_validator",
    "sanity_only",
    name="checktier",
    create_type=False,
)

agent_run_step_phase_enum = PGEnum(
    "planning",
    "execution",
    name="agentrunstepphase",
    create_type=False,
)

message_type_enum = PGEnum(
    "human",
    "system",
    "approval_card",
    "plan_card",
    "blocker_card",
    name="messagetype",
    create_type=False,
)

# Ticket status: includes the new `blocked` value added by the code-agent
# migration (reachable only from agent_working).
ticket_status_enum = PGEnum(
    "backlog",
    "routed",
    "active",
    "in_discussion",
    "consensus_reached",
    "plan_review",
    "agent_working",
    "in_review",
    "blocked",
    "split",
    "closed",
    name="ticketstatus",
    create_type=False,
)


# ------------------------------------------------------------------ #
# READ-ONLY tables                                                     #
# ------------------------------------------------------------------ #

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
    Column("github_issue_number", Integer, nullable=True),
    Column("github_pr_number", Integer, nullable=True),
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


# ------------------------------------------------------------------ #
# READ / WRITE tables                                                  #
# ------------------------------------------------------------------ #

agent_runs = Table(
    "agent_runs",
    metadata,
    Column("id", String, primary_key=True),
    Column("ticket_id", String, nullable=False),
    Column("status", agent_run_status_enum, nullable=False),
    Column("plan_json", JSON, nullable=True),
    Column("attempt_count", Integer, nullable=False, default=0),
    # Reserved for Code Agent step-based resume — this service owns it.
    Column("checkpoint_state_json", JSON, nullable=True),
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
    # --- Code-agent additions (Step 6) ---
    # Which validation tier actually ran (must be visible to a human reviewer).
    Column("check_tier", check_tier_enum, nullable=True),
    # Flagged when a step touches migrations/alembic paths (observability).
    Column("requires_human_review", Boolean, nullable=False, default=False),
    # arq attempt number this step record was produced under.
    Column("job_try", Integer, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("phase", agent_run_step_phase_enum, nullable=False, server_default="execution"),
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
    Column("edited_at", DateTime(timezone=True), nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=True),
)

# Codebase Manifest — incrementally updated per-file after each step commit.
codebase_manifest = Table(
    "codebase_manifest",
    metadata,
    Column("id", String, primary_key=True),
    Column("project_id", String, nullable=False),
    Column("file_path", String(500), nullable=False),
    # tree-sitter structural data (exports/symbols).
    Column("exports_json", JSON, nullable=True),
    # lightweight LLM summarization of file purpose.
    Column("purpose_summary", Text, nullable=True),
    # Stamp of the last ticket that touched this file.
    Column("last_ticket_id", String, nullable=True),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)


# ------------------------------------------------------------------ #
# Engine + connection helpers                                         #
# ------------------------------------------------------------------ #

engine = create_async_engine(
    DATABASE_URL,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=20,
)


@asynccontextmanager
async def get_connection() -> AsyncGenerator[AsyncConnection, None]:
    """Direct execution boundary; commits on clean exit of the block."""
    async with engine.begin() as conn:
        yield conn


def get_engine():
    return engine


async def close_engine() -> None:
    await engine.dispose()
