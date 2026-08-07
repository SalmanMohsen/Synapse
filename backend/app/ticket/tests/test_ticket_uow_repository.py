import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.ticket.uow import SqlAlchemyTicketUnitOfWork
from app.ticket.repository import TicketRepository


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


class TestTicketUoWRepository:
    @pytest.mark.asyncio
    async def test_uow_attributes(self):
        session = AsyncMock()
        uow = SqlAlchemyTicketUnitOfWork(session)
        assert isinstance(uow.tickets, TicketRepository)
        
        await uow.commit()
        session.commit.assert_awaited_once()
        
        await uow.rollback()
        session.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_ticket_repository(self):
        ticket_mock = MagicMock()
        session = _mock_session(scalar_one_or_none_val=ticket_mock)
        repo = TicketRepository(session)

        # get_by_id
        res = await repo.get_by_id("ticket-1")
        assert res is ticket_mock

        # list_by_channel
        tickets_list = [MagicMock()]
        session_list = _mock_session(query_return=tickets_list)
        repo_list = TicketRepository(session_list)
        res_list = await repo_list.list_by_channel("channel-1")
        assert res_list == tickets_list

        # get_by_project_and_issue_number
        session_issue = _mock_session(scalar_one_or_none_val=ticket_mock)
        repo_issue = TicketRepository(session_issue)
        res_issue = await repo_issue.get_by_project_and_issue_number("proj-1", 42)
        assert res_issue is ticket_mock

        # get_by_project_and_pr_number
        session_pr = _mock_session(scalar_one_or_none_val=ticket_mock)
        repo_pr = TicketRepository(session_pr)
        res_pr = await repo_pr.get_by_project_and_pr_number("proj-1", 101)
        assert res_pr is ticket_mock

        # create and update
        session_ops = AsyncMock()
        repo_ops = TicketRepository(session_ops)
        with patch("app.ticket.repository.Ticket") as mock_cls:
            fake_ticket = MagicMock()
            mock_cls.return_value = fake_ticket
            res_create = await repo_ops.create(title="Ticket")
            assert res_create is fake_ticket
            session_ops.add.assert_called_once_with(fake_ticket)
            session_ops.flush.assert_awaited_once()
            session_ops.refresh.assert_awaited_once_with(fake_ticket)

        # Clear mock history before the next update operation
        session_ops.reset_mock()

        await repo_ops.update(fake_ticket, status="closed")
        session_ops.flush.assert_awaited_once()