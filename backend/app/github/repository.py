# backend/app/github/repository.py (new file)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from .models import GitIntegration, WebhookEvent


class GitIntegrationRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, git_integration_id: str) -> GitIntegration | None:
        result = await self.db.execute(
            select(GitIntegration).where(GitIntegration.id == git_integration_id)
        )
        return result.scalar_one_or_none()

    async def get_by_project_id(self, project_id: str) -> GitIntegration | None:
        result = await self.db.execute(
            select(GitIntegration).where(GitIntegration.project_id == project_id)
        )
        return result.scalar_one_or_none()

    async def get_by_installation_id(self, installation_id: str) -> GitIntegration | None:
        result = await self.db.execute(
            select(GitIntegration).where(GitIntegration.github_app_installation_id == installation_id)
        )
        return result.scalar_one_or_none()

    async def create(self, **kwargs) -> GitIntegration:
        integration = GitIntegration(**kwargs)
        self.db.add(integration)
        await self.db.flush()
        await self.db.refresh(integration)
        return integration

    async def update(self, integration: GitIntegration, **kwargs) -> GitIntegration:
        for key, value in kwargs.items():
            setattr(integration, key, value)
        await self.db.flush()
        await self.db.refresh(integration)
        return integration

    async def delete(self, integration: GitIntegration) -> None:
        await self.db.delete(integration)
        await self.db.flush()


class WebhookEventRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, event_id: str) -> WebhookEvent | None:
        result = await self.db.execute(
            select(WebhookEvent).where(WebhookEvent.id == event_id)
        )
        return result.scalar_one_or_none()

    async def get_by_delivery_id(self, delivery_id: str) -> WebhookEvent | None:
        result = await self.db.execute(
            select(WebhookEvent).where(WebhookEvent.delivery_id == delivery_id)
        )
        return result.scalar_one_or_none()

    async def create(self, **kwargs) -> WebhookEvent:
        event = WebhookEvent(**kwargs)
        self.db.add(event)
        await self.db.flush()
        await self.db.refresh(event)
        return event

    async def update(self, event: WebhookEvent, **kwargs) -> WebhookEvent:
        for key, value in kwargs.items():
            setattr(event, key, value)
        await self.db.flush()
        await self.db.refresh(event)
        return event