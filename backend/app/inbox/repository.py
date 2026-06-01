from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import InboxItem, InboxItemStatus, InboxItemType


class InboxItemRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, item_id: str) -> InboxItem | None:
        result = await self.db.execute(
            select(InboxItem).where(InboxItem.id == item_id)
        )
        return result.scalar_one_or_none()

    async def list_by_user(self, user_id: str) -> list[InboxItem]:
        """Return all inbox items for a user, newest first."""
        result = await self.db.execute(
            select(InboxItem)
            .where(InboxItem.user_id == user_id)
            .order_by(InboxItem.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_pending_invites_for_target(
        self, target_user_id: str, workspace_id: str | None = None,
        project_id: str | None = None, channel_id: str | None = None,
    ) -> list[InboxItem]:
        """
        Find pending invite items for a user scoped to a specific entity.
        Used to detect duplicate in-flight invites.
        """
        stmt = select(InboxItem).where(
            InboxItem.user_id == target_user_id,
            InboxItem.status == InboxItemStatus.pending,
            InboxItem.type.in_([
                InboxItemType.workspace_invite,
                InboxItemType.project_invite,
                InboxItemType.channel_invite,
            ]),
        )
        if workspace_id is not None:
            stmt = stmt.where(InboxItem.workspace_id == workspace_id)
        if project_id is not None:
            stmt = stmt.where(InboxItem.project_id == project_id)
        if channel_id is not None:
            stmt = stmt.where(InboxItem.channel_id == channel_id)
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def create(self, **kwargs) -> InboxItem:
        item = InboxItem(**kwargs)
        self.db.add(item)
        await self.db.flush()
        await self.db.refresh(item)
        return item

    async def update(self, item: InboxItem, **kwargs) -> InboxItem:
        for key, value in kwargs.items():
            setattr(item, key, value)
        await self.db.flush()
        await self.db.refresh(item)
        return item

    async def expire_stale(self, item: InboxItem) -> InboxItem:
        """Mark a pending invite as expired (called lazily on read)."""
        item.status = InboxItemStatus.expired
        await self.db.flush()
        await self.db.refresh(item)
        return item