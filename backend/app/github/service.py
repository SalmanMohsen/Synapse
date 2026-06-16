import base64
import time
import hmac
import hashlib
import uuid
from datetime import datetime, timezone

import httpx
import redis.asyncio as aioredis
from fastapi import HTTPException
from jose import jwt

from app.project.models import ProjectRole
from app.ticket.models import TicketStatus, TicketSource, TicketPriority
from app.inbox.schemas import InboxItemRead
from app.inbox.service import InboxService
from app.message.service import MessageService
from app.websocket.manager import publish_to_user, publish_to_channel
from app.config import get_settings
from app.ticket.schemas import TicketRead

from .models import WebhookEventStatus, GitIntegration
from .schemas import GitIntegrationRead, GitInstallUrlResponse
from .uow import AbstractGitIntegrationUnitOfWork

settings = get_settings()


class GitIntegrationService:
    def __init__(
        self,
        uow: AbstractGitIntegrationUnitOfWork,
        redis: aioredis.Redis,
    ) -> None:
        self.uow = uow
        self.redis = redis

    def _generate_github_app_jwt(self) -> str:
        if not settings.github_app_private_key_base64:
            raise HTTPException(
                status_code=500,
                detail="GitHub App credentials are not configured on the server."
            )
        try:
            private_key_pem = base64.b64decode(settings.github_app_private_key_base64).decode("utf-8")
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"Failed to decode the base64-encoded GitHub App private key: {e}"
            )

        now = int(time.time())
        payload = {
            "iat": now - 60,
            "exp": now + (10 * 60),
            "iss": settings.github_app_id,
        }
        return jwt.encode(payload, private_key_pem, algorithm="RS256")

    async def _get_installation_access_token(self, installation_id: str) -> str:
        app_jwt = self._generate_github_app_jwt()
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"https://api.github.com/app/installations/{installation_id}/access_tokens",
                headers={
                    "Authorization": f"Bearer {app_jwt}",
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "Synapse-App",
                },
                timeout=10,
            )
            if resp.status_code != 201:
                raise HTTPException(
                    status_code=resp.status_code,
                    detail=f"Could not generate GitHub App installation token: {resp.text}"
                )
            return resp.json()["token"]

    async def get_install_url(self, project_id: str, requester_id: str) -> GitInstallUrlResponse:
        async with self.uow:
            project = await self.uow.projects.get_by_id(project_id)
            if not project:
                raise HTTPException(status_code=404, detail="Project not found.")

            await self._require_team_lead_or_owner(project, requester_id)

            state_token = str(uuid.uuid4())
            await self.redis.setex(f"github_install_state:{state_token}", 600, project_id)

            app_slug = settings.github_app_slug
            url = f"https://github.com/apps/{app_slug}/installations/new?state={state_token}"
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

        # 3. Fetch all repositories authorized under this installation from GitHub
        installation_token = await self._get_installation_access_token(installation_id)
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                "https://api.github.com/installation/repositories",
                headers={
                    "Authorization": f"Bearer {installation_token}",
                    "Accept": "application/vnd.github+json",
                    "User-Agent": "Synapse-App",
                },
                timeout=10,
            )
            if resp.status_code != 200:
                raise HTTPException(
                    status_code=resp.status_code,
                    detail=f"Could not retrieve repositories: {resp.text}"
                )

            repos_json = resp.json()
            repositories = repos_json.get("repositories", [])
            if not repositories:
                raise HTTPException(
                    status_code=400,
                    detail="No repositories are configured under this App installation."
                )

        # 4. Smart Repository Selection:
        # Find the best candidate among the authorized repositories.
        # We skip repositories that are already linked to other projects.
        selected_repo = None
        async with self.uow:
            for r in repositories:
                name = r["full_name"]
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

            repo_full_name = selected_repo["full_name"]
            default_branch = selected_repo.get("default_branch", "main")

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
        delivery_id: str,
        event_type: str,
        action: str,
        payload: dict,
        body_bytes: bytes,
        signature: str | None,
    ) -> None:
        if not signature or not signature.startswith("sha256="):
            raise HTTPException(status_code=401, detail="Invalid signature header.")

        received_hash = signature[7:]
        expected_hash = hmac.new(
            settings.github_webhook_secret.encode("utf-8"),
            body_bytes,
            hashlib.sha256
        ).hexdigest()

        if not hmac.compare_digest(received_hash, expected_hash):
            raise HTTPException(status_code=401, detail="Webhook signature mismatch.")

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

    async def process_webhook_event(self, delivery_id: str) -> None:
        async with self.uow:
            event = await self.uow.webhook_events.get_by_delivery_id(delivery_id)
            if not event:
                return
            await self.uow.webhook_events.update(event, status=WebhookEventStatus.processing)
            await self.uow.commit()

        try:
            if event.event_type == "issues" and event.action == "opened":
                await self._handle_issue_opened(event.payload)
            elif event.event_type == "issues" and event.action == "reopened":
                await self._handle_issue_reopened(event.payload)

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

    async def _handle_issue_opened(self, payload: dict) -> None:
        repo_data = payload.get("repository", {})
        repo_full_name = repo_data.get("full_name")
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

            issue_data = payload.get("issue", {})
            title = issue_data.get("title", "")
            description = issue_data.get("body", "")
            issue_number = issue_data.get("number")
            github_user_id = str(issue_data.get("user", {}).get("id"))
            github_author_login = issue_data.get("user", {}).get("login")

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

    async def _handle_issue_reopened(self, payload: dict) -> None:
        repo_data = payload.get("repository", {})
        repo_full_name = repo_data.get("full_name")
        if not repo_full_name:
            raise ValueError("No repository full name located in webhook payload.")

        async with self.uow:
            # Query the precise project based on the repository name
            integration = await self.uow.git_integrations.get_by_repo_full_name(repo_full_name)
            if not integration:
                raise ValueError(f"Integration record not found for repository: {repo_full_name}")

            project_id = integration.project_id
            issue_data = payload.get("issue", {})
            issue_number = issue_data.get("number")
            title = issue_data.get("title", "")
            github_author_login = issue_data.get("user", {}).get("login")

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