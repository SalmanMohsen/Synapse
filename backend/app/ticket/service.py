from fastapi import HTTPException

from app.channel.models import ChannelMemberRole
from app.project.models import ProjectRole

from .models import TicketSource, TicketStatus
from .schemas import TicketCreate, TicketRead, TicketUpdate
from .uow import AbstractTicketUnitOfWork


class TicketService:
    def __init__(self, uow: AbstractTicketUnitOfWork) -> None:
        self.uow = uow

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
            await self.uow.commit()
            return TicketRead.model_validate(ticket)

    async def get_ticket(self, ticket_id: str, requester_id: str) -> TicketRead:
        async with self.uow:
            ticket = await self._require_ticket(ticket_id)
            channel = await self._require_channel(ticket.channel_id)
            project = await self._require_project(channel.project_id)
            await self._require_ticket_visibility(channel, project, requester_id)
            return TicketRead.model_validate(ticket)

    async def list_tickets(
        self, channel_id: str, requester_id: str
    ) -> list[TicketRead]:
        async with self.uow:
            channel = await self._require_channel(channel_id)
            project = await self._require_project(channel.project_id)
            # Visibility is channel-level — same rules apply to every ticket in it.
            await self._require_ticket_visibility(channel, project, requester_id)
            tickets = await self.uow.tickets.list_by_channel(channel_id)
            return [TicketRead.model_validate(t) for t in tickets]

    async def update_ticket(
        self, ticket_id: str, requester_id: str, data: TicketUpdate
    ) -> TicketRead:
        """Update mutable metadata: title, description, priority.

        Lifecycle transitions (activate, route, close, split) are separate
        service methods added in Step 6.
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