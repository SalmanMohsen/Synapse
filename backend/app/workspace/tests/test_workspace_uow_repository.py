import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.workspace.uow import SqlAlchemyWorkspaceUnitOfWork
from app.workspace.repository import WorkspaceRepository, WorkspaceMemberRepository


def _make_async_result(values, scalar_one_or_none_val=None, scalar_val=0, all_vals=None):
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar_one_or_none_val
    result.scalars.return_value.all.return_value = values
    result.scalar.return_value = scalar_val
    result.all.return_value = all_vals or []
    return result


def _mock_session(query_return=None, scalar_one_or_none_val=None, scalar_val=0, all_vals=None):
    session = AsyncMock()
    session.execute.return_value = _make_async_result(
        query_return or [], scalar_one_or_none_val, scalar_val, all_vals
    )
    return session


class TestWorkspaceUoWRepository:
    @pytest.mark.asyncio
    async def test_uow_attributes(self):
        session = AsyncMock()
        uow = SqlAlchemyWorkspaceUnitOfWork(session)
        assert isinstance(uow.workspaces, WorkspaceRepository)
        assert isinstance(uow.members, WorkspaceMemberRepository)
        
        await uow.commit()
        session.commit.assert_awaited_once()
        
        await uow.rollback()
        session.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_workspace_repository(self):
        ws_mock = MagicMock()
        session = _mock_session(scalar_one_or_none_val=ws_mock)
        repo = WorkspaceRepository(session)

        # get_by_id
        res = await repo.get_by_id("ws-1")
        assert res is ws_mock

        # list_by_user
        ws_list = [MagicMock()]
        session_list = _mock_session(query_return=ws_list)
        repo_list = WorkspaceRepository(session_list)
        res_list = await repo_list.list_by_user("user-1")
        assert res_list == ws_list

        # create and delete
        session_ops = AsyncMock()
        repo_ops = WorkspaceRepository(session_ops)
        with patch("app.workspace.repository.Workspace") as mock_cls:
            fake_ws = MagicMock()
            mock_cls.return_value = fake_ws
            res_create = await repo_ops.create(name="WS")
            assert res_create is fake_ws
            session_ops.add.assert_called_once_with(fake_ws)
            session_ops.flush.assert_awaited_once()
            session_ops.refresh.assert_awaited_once_with(fake_ws)

        await repo_ops.delete(fake_ws)
        session_ops.delete.assert_called_once_with(fake_ws)

    @pytest.mark.asyncio
    async def test_workspace_member_repository(self):
        member_mock = MagicMock()
        session = _mock_session(scalar_one_or_none_val=member_mock)
        repo = WorkspaceMemberRepository(session)

        # get_by_workspace_and_user
        res = await repo.get_by_workspace_and_user("ws-1", "user-1")
        assert res is member_mock

        # list_by_workspace
        member_list = [MagicMock()]
        session_list = _mock_session(query_return=member_list)
        repo_list = WorkspaceMemberRepository(session_list)
        res_list = await repo_list.list_by_workspace("ws-1")
        assert res_list == member_list

        # list_owners_except
        owners_list = [MagicMock()]
        session_owners = _mock_session(query_return=owners_list)
        repo_owners = WorkspaceMemberRepository(session_owners)
        res_owners = await repo_owners.list_owners_except("ws-1", "user-1")
        assert res_owners == owners_list

        # count_owners
        session_count = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one.return_value = 2
        session_count.execute.return_value = result_mock
        repo_count = WorkspaceMemberRepository(session_count)
        res_count = await repo_count.count_owners("ws-1")
        assert res_count == 2