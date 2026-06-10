from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Message


class MessageRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, **kwargs) -> Message:
        message = Message(**kwargs)
        self.db.add(message)
        await self.db.flush()
        await self.db.refresh(message)
        return message

    async def get_by_id(self, message_id: str) -> Message | None:
        result = await self.db.execute(
            select(Message).where(Message.id == message_id)
        )
        return result.scalar_one_or_none()

    async def list_by_ticket_paginated(
        self,
        ticket_id: str,
        before_id: str | None = None,
        limit: int = 50,
    ) -> tuple[list[Message], bool]:
        """Return up to `limit` messages for the ticket in chronological order.

        When `before_id` is given, only messages older than that message are
        returned — this is the "load more history" scroll-up path.

        Returns (messages, has_more).  The caller derives next_cursor from
        messages[0].id when has_more is True.

        Soft-deleted messages are included — content masking is the
        service/schema layer's responsibility, not the repository's.
        """
        query = select(Message).where(Message.ticket_id == ticket_id)

        if before_id is not None:
            # Resolve the anchor timestamp.  If before_id is unknown we skip
            # the filter — callers treat the result as a fresh initial load.
            anchor_result = await self.db.execute(
                select(Message.created_at).where(Message.id == before_id)
            )
            anchor_created_at = anchor_result.scalar_one_or_none()
            if anchor_created_at is not None:
                query = query.where(Message.created_at < anchor_created_at)

        # Fetch limit+1 descending to detect has_more without a second COUNT query.
        query = query.order_by(Message.created_at.desc()).limit(limit + 1)
        result = await self.db.execute(query)
        rows = list(result.scalars().all())

        has_more = len(rows) > limit
        if has_more:
            rows = rows[:limit]

        # Restore chronological order: oldest first, newest last.
        rows.reverse()
        return rows, has_more

    async def update(self, message: Message, **kwargs) -> Message:
        """Generic field updater used for both edits and soft-deletes.

        Edit:        update(message, content=new_text, edited_at=now())
        Soft-delete: update(message, deleted_at=now())
        """
        for key, value in kwargs.items():
            setattr(message, key, value)
        await self.db.flush()
        await self.db.refresh(message)
        return message