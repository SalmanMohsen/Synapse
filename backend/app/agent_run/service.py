from datetime import datetime, timezone
import os
import httpx
import redis.asyncio as aioredis
from fastapi import HTTPException
import logging
from app.agent_run.models import AgentRunStatus
from app.project.models import ProjectRole
from app.ticket.models import TicketStatus
from app.ticket.uow import AbstractTicketUnitOfWork
from app.websocket.manager import publish_to_channel
from app.jobs import get_arq_pool, JOB_EXECUTE_PLAN


QDRANT_URL = os.environ.get("QDRANT_URL", "http://qdrant:6333")
QDRANT_COLLECTION = os.environ.get("QDRANT_COLLECTION", "codebase_chunks")
logger = logging.getLogger(__name__)
class AgentRunService:
    def __init__(
        self,
        uow: AbstractTicketUnitOfWork,
        redis: aioredis.Redis | None = None,
    ) -> None:
        self.uow = uow
        self.redis = redis

    # ------------------------------------------------------------------ #
    # Helper: Direct HTTP Qdrant File Grounding Validation for Edits      #
    # ------------------------------------------------------------------ #

    async def _file_exists_in_chunks(self, project_id: str, file_path: str) -> bool:
        """Mirrors planning-service/app/ingestion/qdrant_store.file_exists_in_chunks —
        keep the two in sync if the payload schema or collection name changes."""
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.post(
                    f"{QDRANT_URL}/collections/{QDRANT_COLLECTION}/points/scroll",
                    json={
                        "filter": {
                            "must": [
                                {"key": "project_id", "match": {"value": project_id}},
                                {"key": "file_path", "match": {"value": file_path}},
                            ]
                        },
                        "limit": 1,
                        "with_payload": False,
                        "with_vector": False,
                    },
                    timeout=5.0,
                )
            except httpx.HTTPError as e:
                # Qdrant unreachable/timeout is a hard technical failure — don't let it
                # masquerade as "file doesn't exist" and silently reject a valid edit.
                raise HTTPException(
                    status_code=503,
                    detail=f"Codebase index is temporarily unavailable, try again shortly: {e}",
                )

            if resp.status_code != 200:
                raise HTTPException(
                    status_code=503,
                    detail="Codebase index returned an unexpected error, try again shortly.",
                )

            data = resp.json()
            points = data.get("result", {}).get("points", [])
            return len(points) > 0

    async def _validate_plan_grounding_on_edit(self, project_id: str, plan_json: dict) -> None:
        """Enforces that edited plans strictly obey grounding validation boundaries prior to commit."""
        steps = plan_json.get("steps", [])
        for step in steps:
            action_type = step.get("action_type")
            file_path = (step.get("target_file_path") or "").strip()
            step_number = step.get("step_number")

            if action_type == "no_op":
                continue

            if not file_path:
                raise HTTPException(
                    status_code=400,
                    detail=f"Step {step_number} has action '{action_type}' but target_file_path is empty."
                )

            exists = await self._file_exists_in_chunks(project_id, file_path)

            if action_type in ("modify", "delete"):
                if not exists:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            f"Grounding validation failed at edited Step {step_number}: "
                            f"Attempted to '{action_type}' file '{file_path}', "
                            f"but it does not exist in the codebase index."
                        )
                    )
            elif action_type == "create":
                if exists:
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            f"Grounding validation failed at edited Step {step_number}: "
                            f"Attempted to '{action_type}' file '{file_path}', "
                            f"but it already exists in the codebase index."
                        )
                    )

    # ------------------------------------------------------------------ #
    # Step 14 REST Endpoint Actions                                      #
    # ------------------------------------------------------------------ #

    async def approve_plan(self, run_id: str, requester_id: str) -> None:
        """Approve the generated development plan, transitioning to 'agent_working' (hand-off)."""
        async with self.uow:
            run = await self.uow.agent_runs.get_by_id(run_id)
            if not run or run.status != AgentRunStatus.awaiting_review:
                raise HTTPException(status_code=404, detail="No active plan awaiting review found.")

            ticket = await self.uow.tickets.get_by_id(run.ticket_id)
            channel = await self.uow.channels.get_by_id(ticket.channel_id)
            project = await self.uow.projects.get_by_id(channel.project_id)

            await self._require_team_lead_or_owner(project, requester_id)

            # Mark AgentRun as approved & transition Ticket to agent_working (Code Agent scoping boundary)
            await self.uow.agent_runs.update(run, status=AgentRunStatus.approved)
            await self.uow.tickets.update(ticket, status=TicketStatus.agent_working)

            # Insert system audit message
            actor_name = await self._get_actor_name(requester_id)
            await self.uow.messages.create(
                ticket_id=ticket.id,
                author_id=None,
                content=f"Development Plan approved by Team Lead {actor_name}. Scoping hand-off initiated.",
                type="system",
                metadata_json={"event": "plan_approved", "actor_id": requester_id}
            )

            await self.uow.commit()

            # Enqueue the execute_plan_job on arq to hand-off control to code-service
            try:
                from app.jobs import get_arq_pool, JOB_EXECUTE_PLAN
                pool = await get_arq_pool()
                await pool.enqueue_job(
                    JOB_EXECUTE_PLAN, 
                    agent_run_id=run_id, 
                    _queue_name="code_queue"  # Targets the isolated code queue
                )
                logger.info("Successfully enqueued execution plan job on code_queue for agent_run_id=%s", run_id)
            except Exception as arq_err:
                logger.error("Failed to enqueue execute_plan_job on Redis queue: %s", arq_err)

            if self.redis:
                await publish_to_channel(
                    self.redis,
                    channel.id,
                    {
                        "event": "ticket.status_change",
                        "ticket_id": ticket.id,
                        "channel_id": channel.id,
                        "old_status": TicketStatus.plan_review,
                        "new_status": TicketStatus.agent_working,
                    }
                )

    async def reject_plan(self, run_id: str, requester_id: str) -> None:
        """Reject the development plan, reverting the ticket to 'consensus_reached' (re-triggerable)."""
        async with self.uow:
            run = await self.uow.agent_runs.get_by_id(run_id)
            if not run or run.status != AgentRunStatus.awaiting_review:
                raise HTTPException(status_code=404, detail="No active plan awaiting review found.")

            ticket = await self.uow.tickets.get_by_id(run.ticket_id)
            channel = await self.uow.channels.get_by_id(ticket.channel_id)
            project = await self.uow.projects.get_by_id(channel.project_id)

            await self._require_team_lead_or_owner(project, requester_id)

            # Mark AgentRun as rejected & revert Ticket to consensus_reached so it can be cleanly re-run
            await self.uow.agent_runs.update(run, status=AgentRunStatus.rejected)
            await self.uow.tickets.update(ticket, status=TicketStatus.consensus_reached)

            actor_name = await self._get_actor_name(requester_id)
            await self.uow.messages.create(
                ticket_id=ticket.id,
                author_id=None,
                content=f"Development Plan was rejected by Team Lead {actor_name}. Ticket returned to consensus state.",
                type="system",
                metadata_json={"event": "plan_rejected", "actor_id": requester_id}
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
                        "old_status": TicketStatus.plan_review,
                        "new_status": TicketStatus.consensus_reached,
                    }
                )

    async def edit_plan(self, run_id: str, plan_json: dict, requester_id: str) -> dict:
        """Submit inline modifications to the plan, requiring real-time grounding checks before commit."""
        async with self.uow:
            run = await self.uow.agent_runs.get_by_id(run_id)
            if not run or run.status != AgentRunStatus.awaiting_review:
                raise HTTPException(status_code=404, detail="No active plan awaiting review found.")

            ticket = await self.uow.tickets.get_by_id(run.ticket_id)
            channel = await self.uow.channels.get_by_id(ticket.channel_id)
            project = await self.uow.projects.get_by_id(channel.project_id)

            await self._require_team_lead_or_owner(project, requester_id)

            # Perform physical grounding validation before allowing any updates to SQL
            await self._validate_plan_grounding_on_edit(project.id, plan_json)

            # Mutate AgentRun record in-place
            updated_run = await self.uow.agent_runs.update(
                run,
                plan_json=plan_json,
                edited_by_user_id=requester_id,
                edited_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc)
            )

            actor_name = await self._get_actor_name(requester_id)
            await self.uow.messages.create(
                ticket_id=ticket.id,
                author_id=None,
                content=f"Development Plan edited inline by Team Lead {actor_name}.",
                type="system",
                metadata_json={"event": "plan_edited", "actor_id": requester_id}
            )

            await self.uow.commit()
            return updated_run.plan_json

    # ------------------------------------------------------------------ #
    # Permissions & Auxiliary Queries                                    #
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
            detail="Only Team Leads or Workspace Owners can approve, reject, or edit development plans."
        )

    async def _get_actor_name(self, user_id: str) -> str:
        user = await self.uow.users.get_by_id(user_id)
        return user.display_name if user else "Unknown"
    
    async def get_run(self, run_id: str, requester_id: str):
        """Fetch a single AgentRun for display (any project member can view)."""
        async with self.uow:
            run = await self.uow.agent_runs.get_by_id(run_id)
            if not run:
                raise HTTPException(status_code=404, detail="Agent run not found.")

            ticket = await self.uow.tickets.get_by_id(run.ticket_id)
            channel = await self.uow.channels.get_by_id(ticket.channel_id)
            project = await self.uow.projects.get_by_id(channel.project_id)

            await self._require_project_access(project, requester_id)
            return run

    async def _require_project_access(self, project, requester_id: str) -> None:
        ws_member = await self.uow.workspace_members.get_by_workspace_and_user(
            project.workspace_id, requester_id
        )
        if ws_member and ws_member.is_owner:
            return

        pm = await self.uow.project_members.get_by_project_and_user(
            project.id, requester_id
        )
        if pm:
            return

        raise HTTPException(status_code=403, detail="You do not have access to this project.")