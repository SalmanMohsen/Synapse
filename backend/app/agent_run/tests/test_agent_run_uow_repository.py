import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.agent_run.uow import AgentRunUnitOfWork
from app.agent_run.repository import AgentRunRepository, AgentRunStepRepository
from app.agent_run.models import AgentRunStatus, AgentRunStepStatus


def _make_async_result(values, scalar_one_or_none_val=None):
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar_one_or_none_val
    result.scalars.return_value.all.return_value = values
    return result


def _mock_session(query_return=None, scalar_one_or_none_val=None):
    session = AsyncMock()
    session.execute.return_value = _make_async_result(
        query_return or [], scalar_one_or_none_val
    )
    return session


class TestAgentRunUoWRepository:
    @pytest.mark.asyncio
    async def test_uow_attributes(self):
        session = AsyncMock()
        async with AgentRunUnitOfWork(session) as uow:
            assert isinstance(uow.agent_runs, AgentRunRepository)
            assert isinstance(uow.agent_run_steps, AgentRunStepRepository)
            await uow.commit()
            session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_agent_run_repository(self):
        session = AsyncMock()
        repo = AgentRunRepository(session)

        # create
        with patch("app.agent_run.repository.AgentRun") as mock_cls:
            fake_run = MagicMock()
            mock_cls.return_value = fake_run
            result = await repo.create(ticket_id="ticket-1", status=AgentRunStatus.pending)
            assert result is fake_run
            session.add.assert_called_once_with(fake_run)
            session.flush.assert_awaited_once()

        # get_by_id
        session.get.return_value = fake_run
        res_get = await repo.get_by_id("run-1")
        assert res_get is fake_run

        # get_active_by_ticket
        session_active = _mock_session(scalar_one_or_none_val=fake_run)
        repo_active = AgentRunRepository(session_active)
        res_active = await repo_active.get_active_by_ticket("ticket-1")
        assert res_active is fake_run

        # list_by_ticket
        runs_list = [fake_run]
        session_list = _mock_session(query_return=runs_list)
        repo_list = AgentRunRepository(session_list)
        res_list = await repo_list.list_by_ticket("ticket-1")
        assert res_list == runs_list

    @pytest.mark.asyncio
    async def test_agent_run_step_repository(self):
        session = AsyncMock()
        repo = AgentRunStepRepository(session)

        # create
        with patch("app.agent_run.repository.AgentRunStep") as mock_cls:
            fake_step = MagicMock()
            mock_cls.return_value = fake_step
            result = await repo.create(
                agent_run_id="run-1",
                step_number=1,
                description="test step",
                status=AgentRunStepStatus.running,
            )
            assert result is fake_step
            session.add.assert_called_once_with(fake_step)

        # list_by_run
        steps_list = [fake_step]
        session_list = _mock_session(query_return=steps_list)
        repo_list = AgentRunStepRepository(session_list)
        res_list = await repo_list.list_by_run("run-1")
        assert res_list == steps_list