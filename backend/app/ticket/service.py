import redis.asyncio as aioredis
from fastapi import HTTPException

from app.channel.models import ChannelMemberRole
from app.inbox.schemas import InboxItemRead
from app.inbox.service import InboxService
from app.message.models import Message, MessageType
from app.message.schemas import AuthorRead, MessageListResponse, MessageRead
from app.message.service import MessageService
from app.project.models import ProjectRole
from app.thread_state.schemas import ThreadStateRead
from app.websocket.manager import publish_to_channel, publish_to_user

from .models import TicketSource, TicketStatus
from .schemas import (
    TicketCreate,
    TicketDetailResponse,
    TicketRead,
    TicketRouteRequest,
    TicketSplitRequest,
    TicketUpdate,
)
from .uow import AbstractTicketUnitOfWork


def _build_message_read(message: Message, author) -> MessageRead:
    """Convert an ORM Message + optional User into a MessageRead schema.

    Mirrors MessageService._to_read.  Content is masked to None for
    soft-deleted messages so the client can render a placeholder.
    """
    return MessageRead(
        id=message.id,
        ticket_id=message.ticket_id,
        author_id=message.author_id,
        author=AuthorRead.model_validate(author) if author else None,
        content=None if message.deleted_at is not None else message.content,
        type=message.type,
        metadata_json=message.metadata_json,
        deleted_at=message.deleted_at,
        edited_at=message.edited_at,
        created_at=message.created_at,
        updated_at=message.updated_at,
    )


class TicketService:
    def __init__(
        self,
        uow: AbstractTicketUnitOfWork,
        redis: aioredis.Redis | None = None,
    ) -> None:
        self.uow = uow
        self.redis = redis

    # ------------------------------------------------------------------ #
    # Ticket CRUD                                                          #
    # ------------------------------------------------------------------ #

    async def create_ticket(
        self, channel_id: str, requester_id: str, data: TicketCreate
    ) -> TicketRead:
        async with self.uow:
            channel = await self._require_channel(channel_id)
            project = await self._require_project(channel.project_id)

            if channel.is_leads_channel:
                await self._require_leads_channel_access(project, requester_id)
                initial_status = TicketStatus.backlog
            else:
                # Discipline channel — creator must hold an explicit channel membership.
                cm = await self.uow.channel_members.get_by_channel_and_user(
                    channel_id, requester_id
                )
                if cm is None:
                    raise HTTPException(
                        status_code=403,
                        detail="You must be a channel member to create tickets here.",
                    )
                initial_status = TicketStatus.routed

            ticket = await self.uow.tickets.create(
                channel_id=channel_id,
                title=data.title,
                description=data.description,
                status=initial_status,
                source=TicketSource.synapse,
                priority=data.priority,
                creator_id=requester_id,
            )

            actor_name = await self._get_actor_name(requester_id)

            # System message records the creation event in the thread.
            await MessageService.create_system_message(
                self.uow.messages,
                ticket_id=ticket.id,
                content=f"Ticket created by {actor_name}.",
                metadata={
                    "event": "ticket_created_in_channel",
                    "actor_id": requester_id,
                    "actor_name": actor_name,
                },
            )

            # Notify channel lead(s) so they know a ticket is waiting for
            # activation.  Leads channel creation has no notification because
            # team leads are already watching that channel.
            # Capture items to publish after commit.
            lead_notifications: list[tuple[str, object]] = []
            if not channel.is_leads_channel:
                members = await self.uow.channel_members.list_by_channel(channel_id)
                for m in members:
                    if m.role == ChannelMemberRole.channel_lead:
                        item = await InboxService.create_notification(
                            self.uow.inbox_items,
                            user_id=m.user_id,
                            title="New ticket waiting for activation",
                            body=ticket.title,
                            project_id=project.id,
                            channel_id=channel_id,
                            entity_type="ticket",
                            entity_id=ticket.id,
                        )
                        lead_notifications.append((m.user_id, item))

            await self.uow.commit()

            # Broadcast the new ticket event to the entire channel
            if self.redis:
                # Personal notification alerts
                for user_id, item in lead_notifications:
                    await publish_to_user(
                        self.redis,
                        user_id,
                        {
                            "event": "notification.new",
                            "inbox_item": InboxItemRead.model_validate(item).model_dump(
                                mode="json"
                            ),
                        },
                    )
                # Channel-wide real-time ticket sync alert
                await publish_to_channel(
                    self.redis,
                    channel_id,
                    {
                        "event": "ticket.new",
                        "ticket_id": ticket.id,
                        "channel_id": channel_id,
                        "ticket": TicketRead.model_validate(ticket).model_dump(
                            mode="json"
                        ),
                    },
                )

            return TicketRead.model_validate(ticket)

    async def get_ticket(
        self, ticket_id: str, requester_id: str
    ) -> TicketDetailResponse:
        """Composite detail endpoint: ticket + latest messages page + thread state."""
        async with self.uow:
            ticket = await self._require_ticket(ticket_id)
            channel = await self._require_channel(ticket.channel_id)
            project = await self._require_project(channel.project_id)
            await self._require_ticket_visibility(channel, project, requester_id)

            # Latest 50 messages (chronological, newest last).
            message_rows, has_more = (
                await self.uow.messages.list_by_ticket_paginated_with_authors(
                    ticket_id=ticket_id
                )
            )
            message_items = [_build_message_read(msg, author) for msg, author in message_rows]
            # next_cursor is the oldest message ID in this page.
            next_cursor = message_items[0].id if has_more and message_items else None

            thread_state = await self.uow.thread_states.get_by_ticket_id(ticket_id)

            return TicketDetailResponse(
                ticket=TicketRead.model_validate(ticket),
                messages=MessageListResponse(
                    items=message_items,
                    has_more=has_more,
                    next_cursor=next_cursor,
                ),
                thread_state=(
                    ThreadStateRead.model_validate(thread_state)
                    if thread_state else None
                ),
            )

    async def list_tickets(
        self, channel_id: str, requester_id: str
    ) -> list[TicketRead]:
        async with self.uow:
            channel = await self._require_channel(channel_id)
            project = await self._require_project(channel.project_id)
            await self._require_ticket_visibility(channel, project, requester_id)
            tickets = await self.uow.tickets.list_by_channel(channel_id)
            return [TicketRead.model_validate(t) for t in tickets]

    async def update_ticket(
        self, ticket_id: str, requester_id: str, data: TicketUpdate
    ) -> TicketRead:
        """Update mutable metadata: title, description, priority.

        Lifecycle transitions (route, activate, close, split) are separate
        service methods below.
        """
        async with self.uow:
            ticket = await self._require_ticket(ticket_id)
            channel = await self._require_channel(ticket.channel_id)
            project = await self._require_project(channel.project_id)
            await self._require_ticket_update_access(ticket, project, requester_id)

            updates = data.model_dump(exclude_none=True)
            if updates:
                ticket = await self.uow.tickets.update(ticket, **updates)

            await self.uow.commit()
            return TicketRead.model_validate(ticket)

    # ------------------------------------------------------------------ #
    # Ticket lifecycle                                                     #
    # ------------------------------------------------------------------ #

    async def route_ticket(
        self, ticket_id: str, requester_id: str, data: TicketRouteRequest
    ) -> TicketRead:
        async with self.uow:
            ticket = await self._require_ticket(ticket_id)
            current_channel = await self._require_channel(ticket.channel_id)
            project = await self._require_project(current_channel.project_id)

            await self._require_team_lead_or_owner(project, requester_id)

            _ROUTABLE_STATUSES = {
                TicketStatus.backlog,
                TicketStatus.routed,
                TicketStatus.active,
                TicketStatus.in_discussion,
            }
            if ticket.status not in _ROUTABLE_STATUSES:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Tickets in '{ticket.status}' status cannot be routed. "
                        "Only backlog, routed, active, and in_discussion tickets "
                        "are eligible."
                    ),
                )

            target_channel = await self._require_channel(data.channel_id)

            if target_channel.is_leads_channel:
                raise HTTPException(
                    status_code=400,
                    detail="Cannot route a ticket to the leads channel.",
                )
            if target_channel.project_id != project.id:
                raise HTTPException(
                    status_code=400,
                    detail="Target channel must belong to the same project.",
                )
            if target_channel.id == current_channel.id:
                raise HTTPException(
                    status_code=400,
                    detail="Ticket is already in this channel.",
                )

            actor_name = await self._get_actor_name(requester_id)
            is_reroute = ticket.status in (TicketStatus.active, TicketStatus.in_discussion)
            old_channel_id = current_channel.id  # capture before ticket update

            if is_reroute:
                # Remove the now-stale thread state — the Channel Lead of the new
                # channel will create a fresh one when they activate the ticket.
                await self.uow.thread_states.delete_by_ticket_id(ticket.id)

                await MessageService.create_system_message(
                    self.uow.messages,
                    ticket_id=ticket.id,
                    content=(
                        f"Ticket rerouted from {current_channel.name} "
                        f"to {target_channel.name}."
                    ),
                    metadata={
                        "event": "ticket_rerouted",
                        "actor_id": requester_id,
                        "actor_name": actor_name,
                        "from_channel_id": current_channel.id,
                        "from_channel_name": current_channel.name,
                        "to_channel_id": target_channel.id,
                        "to_channel_name": target_channel.name,
                    },
                )
            else:
                await MessageService.create_system_message(
                    self.uow.messages,
                    ticket_id=ticket.id,
                    content=f"Ticket routed to {target_channel.name}.",
                    metadata={
                        "event": "ticket_routed",
                        "actor_id": requester_id,
                        "actor_name": actor_name,
                        "to_channel_id": target_channel.id,
                        "to_channel_name": target_channel.name,
                    },
                )

            ticket = await self.uow.tickets.update(
                ticket,
                channel_id=target_channel.id,
                status=TicketStatus.routed,
            )

            # Notify every member of the target channel.
            target_members = await self.uow.channel_members.list_by_channel(
                target_channel.id
            )
            member_notifications: list[tuple[str, object]] = []
            for member in target_members:
                item = await InboxService.create_notification(
                    self.uow.inbox_items,
                    user_id=member.user_id,
                    title="Ticket routed to your channel",
                    body=ticket.title,
                    project_id=project.id,
                    channel_id=target_channel.id,
                    entity_type="ticket",
                    entity_id=ticket.id,
                )
                member_notifications.append((member.user_id, item))

            await self.uow.commit()

            if self.redis:
                # Notify old channel that this ticket has moved away.
                await publish_to_channel(
                    self.redis,
                    old_channel_id,
                    {
                        "event": "ticket.routed",
                        "ticket_id": ticket.id,
                        "from_channel_id": old_channel_id,
                        "to_channel_id": target_channel.id,
                    },
                )
                # Personal notifications for target channel members.
                for user_id, item in member_notifications:
                    await publish_to_user(
                        self.redis,
                        user_id,
                        {
                            "event": "notification.new",
                            "inbox_item": InboxItemRead.model_validate(item).model_dump(
                                mode="json"
                            ),
                        },
                    )

            return TicketRead.model_validate(ticket)

    async def activate_ticket(
        self, ticket_id: str, requester_id: str
    ) -> TicketRead:
        async with self.uow:
            ticket = await self._require_ticket(ticket_id)
            channel = await self._require_channel(ticket.channel_id)

            if channel.is_leads_channel:
                raise HTTPException(
                    status_code=400,
                    detail="Leads channel tickets cannot be activated.",
                )
            if ticket.status != TicketStatus.routed:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Only routed tickets can be activated. "
                        f"Current status: '{ticket.status}'."
                    ),
                )

            # Activation is exclusively a Channel Lead privilege — no fallback
            # to Team Lead.  If no lead is assigned, the ticket waits.
            is_lead = await self.uow.channel_members.is_channel_lead(
                channel.id, requester_id
            )
            if not is_lead:
                raise HTTPException(
                    status_code=403,
                    detail="Only the Channel Lead can activate tickets.",
                )

            # Create a blank ThreadState: all Observer Agent fields remain null
            # until Phase 3 wires up the Observer Agent.
            await self.uow.thread_states.create(ticket_id=ticket.id)

            ticket = await self.uow.tickets.update(ticket, status=TicketStatus.active)

            actor_name = await self._get_actor_name(requester_id)
            await MessageService.create_system_message(
                self.uow.messages,
                ticket_id=ticket.id,
                content=f"Ticket activated by {actor_name}.",
                metadata={
                    "event": "ticket_activated",
                    "actor_id": requester_id,
                    "actor_name": actor_name,
                },
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
                        "old_status": TicketStatus.routed,
                        "new_status": TicketStatus.active,
                    },
                )

            return TicketRead.model_validate(ticket)

    async def close_ticket(
        self, ticket_id: str, requester_id: str
    ) -> TicketRead:
        """Manual close — discussion-only path (no active agent run)."""
        async with self.uow:
            ticket = await self._require_ticket(ticket_id)
            channel = await self._require_channel(ticket.channel_id)
            project = await self._require_project(channel.project_id)

            _CLOSEABLE_STATUSES = {TicketStatus.active, TicketStatus.in_discussion}
            if ticket.status not in _CLOSEABLE_STATUSES:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Only active or in_discussion tickets can be manually closed."
                    ),
                )

            await self._require_channel_lead_team_lead_or_owner(
                channel, project, requester_id
            )

            old_status = ticket.status
            ticket = await self.uow.tickets.update(ticket, status=TicketStatus.closed)

            actor_name = await self._get_actor_name(requester_id)
            await MessageService.create_system_message(
                self.uow.messages,
                ticket_id=ticket.id,
                content=f"Ticket closed by {actor_name}.",
                metadata={
                    "event": "ticket_closed",
                    "actor_id": requester_id,
                    "actor_name": actor_name,
                },
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
                        "new_status": TicketStatus.closed,
                    },
                )

            return TicketRead.model_validate(ticket)

    async def split_ticket(
        self, ticket_id: str, requester_id: str, data: TicketSplitRequest
    ) -> TicketRead:
        """Mark a ticket as split and link its child tickets.

        The parent becomes terminal (status=split).  Child tickets are
        pre-existing tickets in the same project that have not been
        previously assigned to a parent.
        """
        async with self.uow:
            ticket = await self._require_ticket(ticket_id)
            channel = await self._require_channel(ticket.channel_id)
            project = await self._require_project(channel.project_id)

            await self._require_team_lead_or_owner(project, requester_id)

            _SPLITTABLE_STATUSES = {TicketStatus.backlog,TicketStatus.active, TicketStatus.in_discussion}
            if ticket.status not in _SPLITTABLE_STATUSES:
                raise HTTPException(
                    status_code=400,
                    detail="Only active or in_discussion tickets can be split.",
                )

            # Validate all child tickets before mutating anything.
            child_tickets = []
            for child_id in data.child_ticket_ids:
                if child_id == ticket.id:
                    raise HTTPException(
                        status_code=400,
                        detail="A ticket cannot be a child of itself.",
                    )
                child = await self.uow.tickets.get_by_id(child_id)
                if child is None:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Child ticket '{child_id}' not found.",
                    )
                child_channel = await self._require_channel(child.channel_id)
                if child_channel.project_id != project.id:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            f"Child ticket '{child_id}' does not belong to "
                            "the same project."
                        ),
                    )
                if child.parent_ticket_id is not None:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            f"Child ticket '{child_id}' already has a parent ticket."
                        ),
                    )
                child_tickets.append(child)

            for child in child_tickets:
                await self.uow.tickets.update(child, parent_ticket_id=ticket.id)

            old_status = ticket.status
            ticket = await self.uow.tickets.update(ticket, status=TicketStatus.split)

            actor_name = await self._get_actor_name(requester_id)
            await MessageService.create_system_message(
                self.uow.messages,
                ticket_id=ticket.id,
                content=(
                    f"Ticket split into {len(child_tickets)} child tickets "
                    f"by {actor_name}."
                ),
                metadata={
                    "event": "ticket_split",
                    "actor_id": requester_id,
                    "actor_name": actor_name,
                    "child_ticket_ids": [c.id for c in child_tickets],
                },
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
                        "new_status": TicketStatus.split,
                    },
                )

            return TicketRead.model_validate(ticket)

    # ------------------------------------------------------------------ #
    # Private helpers                                                      #
    # ------------------------------------------------------------------ #

    async def _require_project(self, project_id: str):
        project = await self.uow.projects.get_by_id(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found.")
        return project

    async def _require_channel(self, channel_id: str):
        channel = await self.uow.channels.get_by_id(channel_id)
        if channel is None:
            raise HTTPException(status_code=404, detail="Channel not found.")
        return channel

    async def _require_ticket(self, ticket_id: str):
        ticket = await self.uow.tickets.get_by_id(ticket_id)
        if ticket is None:
            raise HTTPException(status_code=404, detail="Ticket not found.")
        return ticket

    async def _get_actor_name(self, user_id: str) -> str:
        user = await self.uow.users.get_by_id(user_id)
        return user.display_name if user else "Unknown"

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
            detail="Only Team Leads or workspace owners can perform this action.",
        )

    async def _require_channel_lead_team_lead_or_owner(
        self, channel, project, requester_id: str
    ) -> None:
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

        is_lead = await self.uow.channel_members.is_channel_lead(
            channel.id, requester_id
        )
        if is_lead:
            return

        raise HTTPException(
            status_code=403,
            detail=(
                "Only Channel Leads, Team Leads, or workspace owners "
                "can perform this action."
            ),
        )

    async def _require_leads_channel_access(self, project, user_id: str) -> None:
        """Permit: workspace owners, team leads, advisors, viewers, and channel
        leads of any discipline channel in the project.

        This is the fully composed version that includes channel leads.  The
        channel service's equivalent is updated to match in Step 6.
        """
        ws_member = await self.uow.workspace_members.get_by_workspace_and_user(
            project.workspace_id, user_id
        )
        if ws_member and ws_member.is_owner:
            return

        pm = await self.uow.project_members.get_by_project_and_user(project.id, user_id)
        if pm and pm.role in (
            ProjectRole.team_lead,
            ProjectRole.advisor,
            ProjectRole.viewer,
        ):
            return

        # Channel lead of any discipline channel in this project.
        channels = await self.uow.channels.list_by_project(project.id)
        for ch in channels:
            if ch.is_leads_channel:
                continue
            cm = await self.uow.channel_members.get_by_channel_and_user(ch.id, user_id)
            if cm and cm.role == ChannelMemberRole.channel_lead:
                return

        raise HTTPException(
            status_code=403,
            detail="You are not authorized to access the leads channel.",
        )

    async def _require_ticket_visibility(
        self, channel, project, requester_id: str
    ) -> None:
        """Visibility rules mirror the WebSocket subscription model (§8.3):

        - Leads channel ticket  → leads channel access required.
        - Discipline channel ticket:
            workspace owner, team_lead, advisor, viewer → always allowed.
            member role → must hold an explicit ChannelMember record.
        """
        if channel.is_leads_channel:
            await self._require_leads_channel_access(project, requester_id)
            return

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
                detail="You do not have access to this project.",
            )

        if pm.role in (ProjectRole.team_lead, ProjectRole.advisor, ProjectRole.viewer):
            return

        # Regular member — channel assignment is required.
        cm = await self.uow.channel_members.get_by_channel_and_user(
            channel.id, requester_id
        )
        if cm is None:
            raise HTTPException(
                status_code=403,
                detail="You are not a member of this channel.",
            )

    async def _require_ticket_update_access(
        self, ticket, project, requester_id: str
    ) -> None:
        """Only the original creator, a team lead, or a workspace owner may
        update ticket metadata (title / description / priority).
        """
        if ticket.creator_id == requester_id:
            return

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
            detail=(
                "Only Team Leads, workspace owners, or the ticket creator "
                "can update a ticket."
            ),
        )