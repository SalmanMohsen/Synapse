from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .models import Channel, ChannelMember, ChannelMemberRole


class ChannelRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, channel_id: str) -> Channel | None:
        result = await self.db.execute(
            select(Channel).where(Channel.id == channel_id)
        )
        return result.scalar_one_or_none()

    async def list_by_project(self, project_id: str) -> list[Channel]:
        result = await self.db.execute(
            select(Channel).where(Channel.project_id == project_id)
        )
        return list(result.scalars().all())

    async def get_leads_channel(self, project_id: str) -> Channel | None:
        result = await self.db.execute(
            select(Channel).where(
                Channel.project_id == project_id,
                Channel.is_leads_channel.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def create(self, **kwargs) -> Channel:
        channel = Channel(**kwargs)
        self.db.add(channel)
        await self.db.flush()
        await self.db.refresh(channel)
        return channel

    async def update(self, channel: Channel, **kwargs) -> Channel:
        for key, value in kwargs.items():
            setattr(channel, key, value)
        await self.db.flush()
        await self.db.refresh(channel)
        return channel

    async def delete(self, channel: Channel) -> None:
        await self.db.delete(channel)
        await self.db.flush()


class ChannelMemberRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_channel_and_user(
        self, channel_id: str, user_id: str
    ) -> ChannelMember | None:
        result = await self.db.execute(
            select(ChannelMember).where(
                ChannelMember.channel_id == channel_id,
                ChannelMember.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_by_channel(self, channel_id: str) -> list[ChannelMember]:
        result = await self.db.execute(
            select(ChannelMember).where(ChannelMember.channel_id == channel_id)
        )
        return list(result.scalars().all())

    async def is_channel_lead(self, channel_id: str, user_id: str) -> bool:
        member = await self.get_by_channel_and_user(channel_id, user_id)
        return member is not None and member.role == ChannelMemberRole.channel_lead

    async def create(self, **kwargs) -> ChannelMember:
        member = ChannelMember(**kwargs)
        self.db.add(member)
        await self.db.flush()
        await self.db.refresh(member)
        return member

    async def update(self, member: ChannelMember, **kwargs) -> ChannelMember:
        for key, value in kwargs.items():
            setattr(member, key, value)
        await self.db.flush()
        await self.db.refresh(member)
        return member

    async def delete(self, member: ChannelMember) -> None:
        await self.db.delete(member)
        await self.db.flush()