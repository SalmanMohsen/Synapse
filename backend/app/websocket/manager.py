import json
from datetime import datetime

import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.channel.models import ChannelMember
from app.channel.repository import ChannelRepository
from app.project.models import ProjectMember, ProjectRole


def _json_default(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serialisable")


async def publish_to_channel(
    redis: aioredis.Redis, channel_id: str, event: dict
) -> None:
    await redis.publish(
        f"channel:{channel_id}:events",
        json.dumps(event, default=_json_default),
    )


async def publish_to_user(
    redis: aioredis.Redis, user_id: str, event: dict
) -> None:
    await redis.publish(
        f"user:{user_id}:events",
        json.dumps(event, default=_json_default),
    )


async def compute_subscriptions(session: AsyncSession, user_id: str) -> list[str]:
    """Return all Redis Pub/Sub keys that *user_id* should be subscribed to.

    Rules:
    1. Always include ``user:{user_id}:events``.
    2. Include ``channel:{channel_id}:events`` for every ChannelMember record.
    3. For project members with roles team_lead / advisor / viewer, include
       all channel streams in those projects.
    4. For Workspace Owners, automatically subscribe to all channels under
       all projects within their owned workspaces.
    """
    keys: set[str] = {f"user:{user_id}:events"}

    channel_repo = ChannelRepository(session)

    # Rule 2 — explicit channel memberships.
    channel_result = await session.execute(
        select(ChannelMember).where(ChannelMember.user_id == user_id)
    )
    for membership in channel_result.scalars().all():
        keys.add(f"channel:{membership.channel_id}:events")

    # Rule 3 — broad project-role grants.
    _BROAD_ROLES = {ProjectRole.team_lead, ProjectRole.advisor, ProjectRole.viewer}

    pm_result = await session.execute(
        select(ProjectMember).where(ProjectMember.user_id == user_id)
    )
    for pm in pm_result.scalars().all():
        if pm.role in _BROAD_ROLES:
            channels = await channel_repo.list_by_project(pm.project_id)
            for ch in channels:
                keys.add(f"channel:{ch.id}:events")

    # Rule 4 — Workspace Owners broad visibility grants.
    from app.workspace.models import WorkspaceMember
    from app.project.models import Project
    
    wm_result = await session.execute(
        select(WorkspaceMember).where(
            WorkspaceMember.user_id == user_id,
            WorkspaceMember.is_owner.is_(True)
        )
    )
    for wm in wm_result.scalars().all():
        # Get all projects in this workspace
        proj_result = await session.execute(
            select(Project).where(Project.workspace_id == wm.workspace_id)
        )
        for proj in proj_result.scalars().all():
            channels = await channel_repo.list_by_project(proj.id)
            for ch in channels:
                keys.add(f"channel:{ch.id}:events")

    return list(keys)