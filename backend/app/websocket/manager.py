"""
WebSocket infrastructure helpers.

publish_to_channel   — publish an event dict to all clients subscribed to a
                       discipline or leads channel's Redis Pub/Sub stream.
publish_to_user      — publish an event dict to a user's personal Redis stream.
compute_subscriptions — derive the full set of Redis Pub/Sub keys a user should
                        receive on connect, based on their memberships (§8.3).
"""
import json
from datetime import datetime

import redis.asyncio as aioredis
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.channel.models import ChannelMember
from app.channel.repository import ChannelRepository
from app.project.models import ProjectMember, ProjectRole


def _json_default(obj):
    """Serialise types that json.dumps cannot handle natively."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serialisable")


async def publish_to_channel(
    redis: aioredis.Redis, channel_id: str, event: dict
) -> None:
    """Publish *event* to the per-channel Redis Pub/Sub stream.

    Consumers are all WebSocket connections whose user is subscribed to
    ``channel:{channel_id}:events`` (discipline or leads channel).
    """
    await redis.publish(
        f"channel:{channel_id}:events",
        json.dumps(event, default=_json_default),
    )


async def publish_to_user(
    redis: aioredis.Redis, user_id: str, event: dict
) -> None:
    """Publish *event* to the per-user Redis Pub/Sub stream.

    Used for targeted delivery: inbox notifications, agent cards, etc.
    """
    await redis.publish(
        f"user:{user_id}:events",
        json.dumps(event, default=_json_default),
    )


async def compute_subscriptions(session: AsyncSession, user_id: str) -> list[str]:
    """Return all Redis Pub/Sub keys that *user_id* should be subscribed to.

    Rules (§8.3):
    1. Always include ``user:{user_id}:events``.
    2. Include ``channel:{channel_id}:events`` for every ChannelMember record.
    3. For project members with roles team_lead / advisor / viewer, include
       all channel streams in those projects (broad visibility grant).

    Workspace owners are covered by (2) when they also hold ChannelMember
    records, or by (3) when they hold a project-level role.
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

    return list(keys)