import uuid
import logging
from datetime import datetime, timezone

import redis.asyncio as aioredis
from fastapi import HTTPException

from app.project.models import ProjectRole
from app.ticket.models import TicketStatus, TicketSource, TicketPriority
from app.inbox.schemas import InboxItemRead
from app.inbox.service import InboxService
from app.message.service import MessageService
from app.websocket.manager import publish_to_user, publish_to_channel
from app.ticket.schemas import TicketRead
from app.git_providers import GitProvider, NormalizedGitEvent, get_git_provider

from .models import WebhookEventStatus, GitIntegration
from .schemas import GitIntegrationRead, GitInstallUrlResponse
from .uow import AbstractGitIntegrationUnitOfWork
from app.jobs import get_arq_pool, JOB_INGEST_REPOSITORY

logger = logging.getLogger(__name__)


class GitIntegrationService:
    def __init__(
        self,
        uow: AbstractGitIntegrationUnitOfWork,
        redis: aioredis.Redis,
        git_provider: GitProvider | None = None,
    ) -> None:
        self.uow = uow
        self.redis = redis
        # git_integrations doesn't have a `provider` column yet -- every row
        # is implicitly GitHub today, hence the hardcoded default. Once that
        # (Alembic) migration lands, this becomes
        # get_git_provider(integration.provider) resolved per-integration
        # instead of once per service instance.
        self.git_provider = git_provider or get_git_provider("github")

    async def get_install_url(self, project_id: str, requester_id: str) -> GitInstallUrlResponse:
        async with self.uow:
            project = await self.uow.projects.get_by_id(project_id)
            if not project:
                raise HTTPException(status_code=404, detail="Project not found.")

            await self._require_team_lead_or_owner(project, requester_id)

            state_token = str(uuid.uuid4())
            await self.redis.setex(f"github_install_state:{state_token}", 600, project_id)

            url = self.git_provider.build_install_url(state_token)
            return GitInstallUrlResponse(install_url=url)

    # In backend/app/github/service.py

    async def handle_callback(
        self, 
        installation_id: str, 
        state: str | None = None,
        cookie_project_id: str | None = None,
    ) -> None:
        project_id = None

        # 1. Resolve project_id via state parameter (Redis)
        if state:
            project_id = await self.redis.get(f"github_install_state:{state}")
            if project_id:
                await self.redis.delete(f"github_install_state:{state}")

        # 2. Resolve via cookie fallback
        if not project_id and cookie_project_id:
            project_id = cookie_project_id

        # 3. Fetch all repositories authorized under this installation
        repositories = await self.git_provider.list_installation_repos(installation_id)

        # 4. Smart Repository Selection:
        # Find the best candidate among the authorized repositories.
        # We skip repositories that are already linked to other projects.
        selected_repo = None
        async with self.uow:
            for r in repositories:
                name = r.repo_full_name
                existing_link = await self.uow.git_integrations.get_by_repo_full_name(name)
                
                if not existing_link:
                    # Candidate is completely unlinked — this is the best choice for a new link!
                    selected_repo = r
                    break
                elif project_id and existing_link.project_id == project_id:
                    # Candidate is already linked to the current project we are configuring.
                    # We keep it as a fallback if no new unlinked repo is found.
                    if not selected_repo:
                        selected_repo = r

            if not selected_repo:
                # Fallback to the first available repository if all are already allocated
                selected_repo = repositories[0]

            repo_full_name = selected_repo.repo_full_name
            default_branch = selected_repo.default_branch

            # 5. Resolve project_id via repo fallback if it is still unknown
            if not project_id:
                existing_by_repo = await self.uow.git_integrations.get_by_repo_full_name(repo_full_name)
                if existing_by_repo:
                    project_id = existing_by_repo.project_id

            if not project_id:
                raise HTTPException(
                    status_code=400, 
                    detail="Could not match GitHub App installation to any project. Setup session may have expired."
                )

            # 6. Save or update the project-level integration
            existing = await self.uow.git_integrations.get_by_project_id(project_id)
            if existing:
                await self.uow.git_integrations.update(
                    existing,
                    github_app_installation_id=str(installation_id),
                    repo_full_name=repo_full_name,
                    default_branch=default_branch,
                )
            else:
                await self.uow.git_integrations.create(
                    project_id=project_id,
                    github_app_installation_id=str(installation_id),
                    repo_full_name=repo_full_name,
                    default_branch=default_branch,
                )
            await self.uow.commit()

    async def get_integration(self, project_id: str, requester_id: str) -> GitIntegrationRead:
        async with self.uow:
            project = await self.uow.projects.get_by_id(project_id)
            if not project:
                raise HTTPException(status_code=404, detail="Project not found.")

            await self._require_project_visibility(project, requester_id)

            integration = await self.uow.git_integrations.get_by_project_id(project_id)
            if not integration:
                raise HTTPException(status_code=404, detail="GitHub integration is not linked.")

            return GitIntegrationRead.model_validate(integration)

    async def delete_integration(self, project_id: str, requester_id: str) -> None:
        async with self.uow:
            project = await self.uow.projects.get_by_id(project_id)
            if not project:
                raise HTTPException(status_code=404, detail="Project not found.")

            await self._require_team_lead_or_owner(project, requester_id)

            integration = await self.uow.git_integrations.get_by_project_id(project_id)
            if not integration:
                raise HTTPException(status_code=404, detail="GitHub integration is not linked.")

            await self.uow.git_integrations.delete(integration)
            await self.uow.commit()

    # ------------------------------------------------------------------ #
    # Webhook Management                                                   #
    # ------------------------------------------------------------------ #

    async def handle_webhook(
        self,
        headers: dict,
        body_bytes: bytes,
        payload: dict,
    ) -> None:
        if not self.git_provider.verify_webhook_signature(headers, body_bytes):
            raise HTTPException(status_code=401, detail="Invalid or mismatched webhook signature.")

        delivery_id, event_type, action = self.git_provider.extract_delivery_metadata(headers, payload)

        async with self.uow:
            existing_event = await self.uow.webhook_events.get_by_delivery_id(delivery_id)
            if existing_event:
                return  # Idempotency duplicate exit

            await self.uow.webhook_events.create(
                delivery_id=delivery_id,
                event_type=event_type,
                action=action,
                payload=payload,
                status=WebhookEventStatus.pending,
            )
            await self.uow.commit()

        return delivery_id

    async def process_webhook_event(self, delivery_id: str) -> None:
        async with self.uow:
            event = await self.uow.webhook_events.get_by_delivery_id(delivery_id)
            if not event:
                return
            await self.uow.webhook_events.update(event, status=WebhookEventStatus.processing)
            await self.uow.commit()

        try:
            normalized = self.git_provider.parse_webhook_event(event.event_type, event.action, event.payload)
            if normalized is not None:
                if normalized.kind == "issue_opened":
                    await self._handle_issue_opened(normalized)
                elif normalized.kind == "issue_reopened":
                    await self._handle_issue_reopened(normalized)
                elif normalized.kind == "push":
                    await self._handle_push(normalized)
                elif normalized.kind == "change_request_closed":
                    await self._handle_pull_request_closed(normalized)

            async with self.uow:
                event = await self.uow.webhook_events.get_by_delivery_id(delivery_id)
                if event:
                    await self.uow.webhook_events.update(
                        event,
                        status=WebhookEventStatus.processed,
                        processed_at=datetime.now(timezone.utc),
                    )
                await self.uow.commit()
        except Exception as e:
            async with self.uow:
                event = await self.uow.webhook_events.get_by_delivery_id(delivery_id)
                if event:
                    await self.uow.webhook_events.update(
                        event,
                        status=WebhookEventStatus.failed,
                        error_message=str(e),
                        processed_at=datetime.now(timezone.utc),
                    )
                await self.uow.commit()

    async def _handle_issue_opened(self, event: NormalizedGitEvent) -> None:
        repo_full_name = event.repo_full_name
        if not repo_full_name:
            raise ValueError("No repository full name located in webhook payload.")

        async with self.uow:
            # Query the precise project based on the repository name
            integration = await self.uow.git_integrations.get_by_repo_full_name(repo_full_name)
            if not integration:
                raise ValueError(f"Integration record not found for repository: {repo_full_name}")

            project_id = integration.project_id
            leads_channel = await self.uow.channels.get_leads_channel(project_id)
            if not leads_channel:
                raise ValueError(f"Leads channel not found for project: {project_id}")

            title = event.title
            description = event.description
            issue_number = event.issue_number
            github_user_id = event.author_external_id
            github_author_login = event.author_login

            creator_id = None
            if github_user_id:
                user = await self.uow.users.get_by_github_id(github_user_id)
                if user:
                    creator_id = user.id

            ticket = await self.uow.tickets.create(
                channel_id=leads_channel.id,
                title=title,
                description=description,
                status=TicketStatus.backlog,
                source=TicketSource.github,
                priority=TicketPriority.medium,
                creator_id=creator_id,
                github_issue_number=issue_number,
                github_author_login=github_author_login,
            )

            await MessageService.create_system_message(
                self.uow.messages,
                ticket_id=ticket.id,
                content=f"Ticket created from GitHub Issue #{issue_number}",
                metadata={
                    "event": "ticket_created_from_github",
                    "github_issue_number": issue_number,
                    "github_author_login": github_author_login,
                },
            )

            leads_members = await self.uow.channel_members.list_by_channel(leads_channel.id)
            new_notifications = []
            for member in leads_members:
                item = await InboxService.create_notification(
                    self.uow.inbox_items,
                    user_id=member.user_id,
                    title=f"New ticket from GitHub: {title[:80]}",
                    body=f"Issue #{issue_number} opened by {github_author_login}",
                    project_id=project_id,
                    channel_id=leads_channel.id,
                    entity_type="ticket",
                    entity_id=ticket.id,
                )
                new_notifications.append((member.user_id, item))

            await self.uow.commit()

            if self.redis:
                for user_id, item in new_notifications:
                    await publish_to_user(
                        self.redis,
                        user_id,
                        {
                            "event": "notification.new",
                            "inbox_item": InboxItemRead.model_validate(item).model_dump(mode="json"),
                        },
                    )
            await publish_to_channel(
                    self.redis,
                    leads_channel.id,
                    {
                        "event": "ticket.new",
                        "ticket_id": ticket.id,
                        "channel_id": leads_channel.id,
                        "ticket": TicketRead.model_validate(ticket).model_dump(
                            mode="json"
                        ),
                    },
                )

    async def _handle_issue_reopened(self, event: NormalizedGitEvent) -> None:
        repo_full_name = event.repo_full_name
        if not repo_full_name:
            raise ValueError("No repository full name located in webhook payload.")

        async with self.uow:
            # Query the precise project based on the repository name
            integration = await self.uow.git_integrations.get_by_repo_full_name(repo_full_name)
            if not integration:
                raise ValueError(f"Integration record not found for repository: {repo_full_name}")

            project_id = integration.project_id
            issue_number = event.issue_number
            title = event.title
            github_author_login = event.author_login

            ticket = await self.uow.tickets.get_by_project_and_issue_number(project_id, issue_number)
            if not ticket:
                raise ValueError(f"Reopened untracked ticket #{issue_number} inside project: {project_id}")

            leads_channel = await self.uow.channels.get_leads_channel(project_id)
            if not leads_channel:
                raise ValueError(f"Leads channel not found for project: {project_id}")

            await self.uow.thread_states.delete_by_ticket_id(ticket.id)

            await self.uow.tickets.update(
                ticket,
                channel_id=leads_channel.id,
                status=TicketStatus.backlog,
            )

            await MessageService.create_system_message(
                self.uow.messages,
                ticket_id=ticket.id,
                content=f"Ticket reopened from GitHub Issue #{issue_number}",
                metadata={
                    "event": "ticket_reopened_from_github",
                    "github_issue_number": issue_number,
                },
            )

            leads_members = await self.uow.channel_members.list_by_channel(leads_channel.id)
            new_notifications = []
            for member in leads_members:
                item = await InboxService.create_notification(
                    self.uow.inbox_items,
                    user_id=member.user_id,
                    title=f"Ticket reopened from GitHub: {title[:80]}",
                    body=f"Issue #{issue_number} was reopened on GitHub",
                    project_id=project_id,
                    channel_id=leads_channel.id,
                    entity_type="ticket",
                    entity_id=ticket.id,
                )
                new_notifications.append((member.user_id, item))

            await self.uow.commit()

            if self.redis:
                for user_id, item in new_notifications:
                    await publish_to_user(
                        self.redis,
                        user_id,
                        {
                            "event": "notification.new",
                            "inbox_item": InboxItemRead.model_validate(item).model_dump(mode="json"),
                        },
                    )
            await publish_to_channel(
                    self.redis,
                    leads_channel.id,
                    {
                        "event": "ticket.status_change",
                        "ticket_id": ticket.id,
                        "channel_id": leads_channel.id,
                        "old_status": TicketStatus.closed,
                        "new_status": TicketStatus.backlog,
                    },
                )

    async def _handle_push(self, event: NormalizedGitEvent) -> None:
        repo_full_name = event.repo_full_name
        if not repo_full_name:
            raise ValueError("No repository full name located in webhook payload.")

        async with self.uow:
            integration = await self.uow.git_integrations.get_by_repo_full_name(repo_full_name)
            if not integration:
                # Perfectly normal event if the repository exists in the org but is unlinked
                logger.info("Ignoring push event: repository %s is not linked to any project.", repo_full_name)
                return
            
            project_id = integration.project_id
            default_branch = integration.default_branch

        ref = event.ref or ""  # e.g., "refs/heads/main"
        expected_ref = f"refs/heads/{default_branch}"

        # Filter out feature/topic branch updates
        if ref != expected_ref:
            logger.info(
                "Ignoring push event for project %s: pushed ref %s does not match default branch %s",
                project_id,
                ref,
                expected_ref
            )
            return

        # Enqueue the background ingestion task
        pool = await get_arq_pool()
        await pool.enqueue_job(JOB_INGEST_REPOSITORY, project_id=project_id)
        logger.info("Enqueued ingestion job for project %s on branch %s", project_id, default_branch)

    # ------------------------------------------------------------------ #
    # Access Rules Helpers                                                 #
    # ------------------------------------------------------------------ #

    async def _require_team_lead_or_owner(self, project, requester_id: str) -> None:
        ws_member = await self.uow.workspace_members.get_by_workspace_and_user(
            project.workspace_id, requester_id
        )
        if ws_member and ws_member.is_owner:
            return

        pm = await self.uow.project_members.get_by_project_and_user(
            project.id, requester_id
        )
        if pm and pm.role == ProjectRole.team_lead:
            return

        raise HTTPException(
            status_code=403,
            detail="Only Team Leads or workspace owners can manage this integration."
        )

    async def _require_project_visibility(self, project, requester_id: str) -> None:
        ws_member = await self.uow.workspace_members.get_by_workspace_and_user(
            project.workspace_id, requester_id
        )
        if ws_member and ws_member.is_owner:
            return

        pm = await self.uow.project_members.get_by_project_and_user(
            project.id, requester_id
        )
        if pm is None:
            raise HTTPException(
                status_code=403,
                detail="You must be a member of this project to inspect integration details."
            )
    
    async def _handle_pull_request_closed(self, event: NormalizedGitEvent) -> None:
        repo_full_name = event.repo_full_name
        if not repo_full_name:
            raise ValueError("No repository full name located in webhook payload.")
    
        pr_number = event.change_request_number
        merged = event.merged
    
        async with self.uow:
            integration = await self.uow.git_integrations.get_by_repo_full_name(repo_full_name)
            if not integration:
                raise ValueError(f"Integration record not found for repository: {repo_full_name}")
    
            project_id = integration.project_id
            ticket = await self.uow.tickets.get_by_project_and_pr_number(project_id, pr_number)
            if not ticket:
                raise ValueError(f"No ticket found for merged PR #{pr_number} in project: {project_id}")
    
            channel = await self.uow.channels.get_by_id(ticket.channel_id)
    
            old_status = ticket.status
            new_status = TicketStatus.closed if merged else TicketStatus.in_review
            ticket = await self.uow.tickets.update(ticket, status=new_status)
    
            content = (
                f"PR #{pr_number} merged. Ticket closed."
                if merged
                else f"PR #{pr_number} closed without merging."
            )
            await MessageService.create_system_message(
                self.uow.messages,
                ticket_id=ticket.id,
                content=content,
                metadata={"event": "pull_request_closed", "github_pr_number": pr_number, "merged": merged},
            )
    
            await self.uow.commit()
    
            if self.redis:
                await publish_to_channel(
                    self.redis,
                    channel.id,
                    {
                        "event": "ticket.status_change",
                        "ticket_id": ticket.id,
                        "channel_id": channel.id,
                        "old_status": old_status,
                        "new_status": new_status,
                    },
                )