import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.inbox.uow import SqlAlchemyInboxUnitOfWork
from app.inbox.repository import InboxItemRepository


def _make_async_result(values, scalar_one_or_none_val=None, all_vals=None):
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar_one_or_none_val
    result.scalars.return_value.all.return_value = values
    result.all.return_value = all_vals or []
    return result


def _mock_session(query_return=None, scalar_one_or_none_val=None, all_vals=None):
    session = AsyncMock()
    session.execute.return_value = _make_async_result(
        query_return or [], scalar_one_or_none_val, all_vals
    )
    return session


class TestInboxUoWRepository:
    @pytest.mark.asyncio
    async def test_uow_attributes(self):
        session = AsyncMock()
        uow = SqlAlchemyInboxUnitOfWork(session)
        assert isinstance(uow.inbox_items, InboxItemRepository)
        
        await uow.commit()
        session.commit.assert_awaited_once()
        
        await uow.rollback()
        session.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_inbox_item_repository(self):
        item_mock = MagicMock()
        session = _mock_session(scalar_one_or_none_val=item_mock)
        repo = InboxItemRepository(session)

        # get_by_id
        res = await repo.get_by_id("item-1")
        assert res is item_mock

        # list_by_user
        items_list = [MagicMock()]
        session_list = _mock_session(query_return=items_list)
        repo_list = InboxItemRepository(session_list)
        res_list = await repo_list.list_by_user("user-1")
        assert res_list == items_list

        # list_pending_invites_for_target
        pending_list = [MagicMock()]
        session_pending = _mock_session(query_return=pending_list)
        repo_pending = InboxItemRepository(session_pending)
        res_pending = await repo_pending.list_pending_invites_for_target("user-1", workspace_id="ws-1")
        assert res_pending == pending_list

        # create and update
        session_ops = AsyncMock()
        repo_ops = InboxItemRepository(session_ops)
        with patch("app.inbox.repository.InboxItem") as mock_cls:
            fake_item = MagicMock()
            mock_cls.return_value = fake_item
            res_create = await repo_ops.create(title="Invite")
            assert res_create is fake_item
            session_ops.add.assert_called_once_with(fake_item)
            session_ops.flush.assert_awaited_once()
            session_ops.refresh.assert_awaited_once_with(fake_item)

        # Clear mock history before the next update operation
        session_ops.reset_mock()

        await repo_ops.update(fake_item, status="accepted")
        session_ops.flush.assert_awaited_once()

        # expire_stale
        await repo_ops.expire_stale(fake_item)
        assert fake_item.status == "expired"