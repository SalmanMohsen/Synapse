from datetime import datetime, timezone

from fastapi import HTTPException

from app.auth.models import User
from app.channel.models import ChannelMemberRole
from app.project.models import ProjectRole
from app.ticket.models import TicketStatus

from .models import Message, MessageType
from .repository import MessageRepository
from .schemas import AuthorRead, MessageCreate, MessageListResponse, MessageRead, MessageUpdate
from .uow import AbstractMessageUnitOfWork

# Ticket statuses that lock the thread in a discipline channel.
# Everything else (active and beyond) is writable.
_LOCKED_STATUSES = {TicketStatus.backlog, TicketStatus.routed}


class MessageService:
    def __init__(self, uow: AbstractMessageUnitOfWork) -> None:
        self.uow = uow

    # ------------------------------------------------------------------ #
    # Public REST methods                                                  #
    # ------------------------------------------------------------------ #

    async def create_message(
        self, ticket_id: str, requester_id: str, data: MessageCreate
    ) -> MessageRead:
        async with self.uow:
            ticket = await self._require_ticket(ticket_id)
            channel = await self._require_channel(ticket.channel_id)
            project = await self._require_project(channel.project_id)

            # Visibility first, then viewer gate — order matters: we want
            # 403 "not a member" before 403 "viewers can't post".
            await self._require_ticket_visibility(channel, project, requester_id)
            await self._require_not_viewer(project, requester_id)

            # Discipline channel: thread is locked until Channel Lead activates
            # the ticket.  Leads channel tickets have no activation gate.
            if not channel.is_leads_channel and ticket.status in _LOCKED_STATUSES:
                raise HTTPException(
                    status_code=400,
                    detail="This ticket's thread is locked until a Channel Lead activates it.",
                )

            message = await self.uow.messages.create(
                ticket_id=ticket_id,
                author_id=requester_id,
                content=data.content,
                type=MessageType.human,
            )

            # Auto-transition: first human message in a discipline channel
            # moves the ticket from active → in_discussion.
            # Leads channel tickets stay at backlog regardless of messages.
            if not channel.is_leads_channel and ticket.status == TicketStatus.active:
                await self.uow.tickets.update(ticket, status=TicketStatus.in_discussion)
                # WebSocket ticket.status_change published in Step 7

            author = await self.uow.users.get_by_id(requester_id)
            await self.uow.commit()
            # WebSocket message.new published in Step 7
            return self._to_read(message, author)

    async def list_messages(
        self,
        ticket_id: str,
        requester_id: str,
        before_id: str | None = None,
    ) -> MessageListResponse:
        async with self.uow:
            ticket = await self._require_ticket(ticket_id)
            channel = await self._require_channel(ticket.channel_id)
            project = await self._require_project(channel.project_id)
            await self._require_ticket_visibility(channel, project, requester_id)

            rows, has_more = (
                await self.uow.messages.list_by_ticket_paginated_with_authors(
                    ticket_id, before_id=before_id
                )
            )
            items = [self._to_read(msg, author) for msg, author in rows]
            # next_cursor is the oldest message's ID in this page — the client
            # passes it as before_id to scroll further back in history.
            next_cursor = items[0].id if has_more and items else None
            return MessageListResponse(items=items, has_more=has_more, next_cursor=next_cursor)

    async def edit_message(
        self,
        ticket_id: str,
        message_id: str,
        requester_id: str,
        data: MessageUpdate,
    ) -> MessageRead:
        async with self.uow:
            ticket = await self._require_ticket(ticket_id)
            channel = await self._require_channel(ticket.channel_id)
            project = await self._require_project(channel.project_id)
            await self._require_ticket_visibility(channel, project, requester_id)

            msg, author = await self._require_message_in_ticket(message_id, ticket_id)

            if msg.author_id != requester_id:
                raise HTTPException(
                    status_code=403,
                    detail="Only the message author can edit this message.",
                )
            if msg.deleted_at is not None:
                raise HTTPException(
                    status_code=400,
                    detail="Deleted messages cannot be edited.",
                )
            if msg.type != MessageType.human:
                raise HTTPException(
                    status_code=400,
                    detail="Only human messages can be edited.",
                )

            msg = await self.uow.messages.update(
                msg,
                content=data.content,
                edited_at=datetime.now(timezone.utc),
            )
            await self.uow.commit()
            # WebSocket message.updated published in Step 7
            return self._to_read(msg, author)

    async def delete_message(
        self,
        ticket_id: str,
        message_id: str,
        requester_id: str,
    ) -> MessageRead:
        async with self.uow:
            ticket = await self._require_ticket(ticket_id)
            channel = await self._require_channel(ticket.channel_id)
            project = await self._require_project(channel.project_id)
            await self._require_ticket_visibility(channel, project, requester_id)

            msg, author = await self._require_message_in_ticket(message_id, ticket_id)

            if msg.deleted_at is not None:
                raise HTTPException(
                    status_code=400,
                    detail="Message is already deleted.",
                )
            if msg.type == MessageType.system:
                raise HTTPException(
                    status_code=400,
                    detail="System messages cannot be deleted.",
                )

            # Auth: author can always delete their own message.
            # In a discipline channel, a channel lead can also delete.
            # In the leads channel, only the author can delete (no single
            # designated lead owns the channel).
            is_author = msg.author_id == requester_id
            if not is_author:
                if channel.is_leads_channel:
                    raise HTTPException(
                        status_code=403,
                        detail=(
                            "Only the message author can delete messages "
                            "in the leads channel."
                        ),
                    )
                is_lead = await self.uow.channel_members.is_channel_lead(
                    channel.id, requester_id
                )
                if not is_lead:
                    raise HTTPException(
                        status_code=403,
                        detail=(
                            "Only the message author or a Channel Lead "
                            "can delete messages."
                        ),
                    )

            msg = await self.uow.messages.update(
                msg, deleted_at=datetime.now(timezone.utc)
            )
            await self.uow.commit()
            # WebSocket message.updated published in Step 7
            return self._to_read(msg, author)

    # ------------------------------------------------------------------ #
    # Internal system-message helper                                       #
    # ------------------------------------------------------------------ #

    @staticmethod
    async def create_system_message(
        message_repo: MessageRepository,
        *,
        ticket_id: str,
        content: str,
        metadata: dict,
    ) -> Message:
        """Insert a system message within a calling service's UoW transaction.

        Never triggers the active → in_discussion auto-transition and never
        publishes a WebSocket event — those are exclusively caller concerns.

        Usage (inside ticket service, within its own async with self.uow block):
            await MessageService.create_system_message(
                self.uow.messages,
                ticket_id=ticket.id,
                content="Ticket activated by Alice",
                metadata={"event": "ticket_activated", "actor_id": "..."},
            )
        """
        return await message_repo.create(
            ticket_id=ticket_id,
            content=content,
            type=MessageType.system,
            author_id=None,
            metadata_json=metadata,
        )

    # ------------------------------------------------------------------ #
    # Private helpers                                                      #
    # ------------------------------------------------------------------ #

    async def _require_ticket(self, ticket_id: str):
        ticket = await self.uow.tickets.get_by_id(ticket_id)
        if ticket is None:
            raise HTTPException(status_code=404, detail="Ticket not found.")
        return ticket

    async def _require_channel(self, channel_id: str):
        channel = await self.uow.channels.get_by_id(channel_id)
        if channel is None:
            raise HTTPException(status_code=404, detail="Channel not found.")
        return channel

    async def _require_project(self, project_id: str):
        project = await self.uow.projects.get_by_id(project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found.")
        return project

    async def _require_message_in_ticket(
        self, message_id: str, ticket_id: str
    ) -> tuple[Message, User | None]:
        """Fetch the message with its author and verify it belongs to ticket_id."""
        row = await self.uow.messages.get_by_id_with_author(message_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Message not found.")
        msg, author = row
        if msg.ticket_id != ticket_id:
            # Don't leak the message's real ticket — treat as 404.
            raise HTTPException(status_code=404, detail="Message not found.")
        return msg, author

    async def _require_ticket_visibility(
        self, channel, project, requester_id: str
    ) -> None:
        """Mirrors TicketService._require_ticket_visibility.

        Leads channel → leads channel access required.
        Discipline channel → workspace owner / team_lead / advisor / viewer
        pass automatically; regular members need an explicit ChannelMember record.
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

        cm = await self.uow.channel_members.get_by_channel_and_user(
            channel.id, requester_id
        )
        if cm is None:
            raise HTTPException(
                status_code=403,
                detail="You are not a member of this channel.",
            )

    async def _require_leads_channel_access(self, project, user_id: str) -> None:
        """Workspace owners, team leads, advisors, viewers, and channel leads
        of any discipline channel may access the leads channel."""
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

    async def _require_not_viewer(self, project, user_id: str) -> None:
        """Viewers may read tickets and messages but cannot post."""
        # Workspace owners never hold a project-member viewer record —
        # they pass the visibility check before reaching this helper.
        pm = await self.uow.project_members.get_by_project_and_user(project.id, user_id)
        if pm and pm.role == ProjectRole.viewer:
            raise HTTPException(
                status_code=403,
                detail="Viewers cannot post messages.",
            )

    def _to_read(self, message: Message, author: User | None) -> MessageRead:
        """Build a MessageRead from an ORM message + its optional author.

        Content is masked to None for soft-deleted messages so the client
        can render a placeholder without a separate request.
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