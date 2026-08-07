import pytest
from unittest.mock import AsyncMock, MagicMock
from app.websocket.manager import compute_subscriptions
from app.channel.models import ChannelMember
from app.project.models import ProjectMember, ProjectRole, Project
from app.workspace.models import WorkspaceMember
from app.channel.models import Channel


def _make_async_result(values):
    """Mocks the execution result of the SQLAlchemy AsyncSession."""
    result = MagicMock()
    result.scalars.return_value.all.return_value = values
    return result


@pytest.mark.asyncio
async def test_compute_subscriptions_complex_cascade():
    """Validates multi-tiered role cascading rules for WebSocket streams."""
    session = AsyncMock()

    # Rule 1/2: User is direct member of Channel 'ch-direct'
    cm = MagicMock(spec=ChannelMember)
    cm.channel_id = "ch-direct"
    
    # Rule 3: User is Team Lead of Project 'p-lead', which has channel 'ch-team-lead'
    pm = MagicMock(spec=ProjectMember)
    pm.project_id = "p-lead"
    pm.role = ProjectRole.team_lead
    
    ch_project_lead = MagicMock(spec=Channel)
    ch_project_lead.id = "ch-team-lead"

    # Rule 4: User is Owner of Workspace 'ws-owner', which contains Project 'p-workspace', having channel 'ch-owner-cascade'
    wm = MagicMock(spec=WorkspaceMember)
    wm.workspace_id = "ws-owner"
    wm.is_owner = True

    p_workspace = MagicMock(spec=Project)
    p_workspace.id = "p-workspace"

    ch_workspace_cascade = MagicMock(spec=Channel)
    ch_workspace_cascade.id = "ch-owner-cascade"

    # Set up mock DB result sequencing for compute_subscriptions execution steps
    session.execute.side_effect = [
        _make_async_result([cm]),                     # ChannelMember lookup
        _make_async_result([pm]),                     # ProjectMember lookup
        _make_async_result([ch_project_lead]),         # Project channels list for p-lead
        _make_async_result([wm]),                     # WorkspaceMember lookup
        _make_async_result([p_workspace]),            # Projects list for ws-owner
        _make_async_result([ch_workspace_cascade]),   # Project channels list for p-workspace
    ]

    user_id = "user-123"
    subscriptions = await compute_subscriptions(session, user_id)

    expected_keys = {
        f"user:{user_id}:events",
        "channel:ch-direct:events",
        "channel:ch-team-lead:events",
        "channel:ch-owner-cascade:events",
    }
    
    assert set(subscriptions) == expected_keys