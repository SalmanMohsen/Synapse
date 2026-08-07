import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.project.uow import SqlAlchemyProjectUnitOfWork
from app.project.repository import ProjectRepository, ProjectMemberRepository


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


class TestProjectUoWRepository:
    @pytest.mark.asyncio
    async def test_uow_attributes(self):
        session = AsyncMock()
        uow = SqlAlchemyProjectUnitOfWork(session)
        assert isinstance(uow.projects, ProjectRepository)
        assert isinstance(uow.project_members, ProjectMemberRepository)
        
        await uow.commit()
        session.commit.assert_awaited_once()
        
        await uow.rollback()
        session.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_project_repository(self):
        proj_mock = MagicMock()
        session = _mock_session(scalar_one_or_none_val=proj_mock)
        repo = ProjectRepository(session)

        # get_by_id
        res = await repo.get_by_id("p-1")
        assert res is proj_mock

        # list_by_workspace
        proj_list = [MagicMock()]
        session_list = _mock_session(query_return=proj_list)
        repo_list = ProjectRepository(session_list)
        res_list = await repo_list.list_by_workspace("ws-1")
        assert res_list == proj_list

        # create and delete
        session_ops = AsyncMock()
        repo_ops = ProjectRepository(session_ops)
        with patch("app.project.repository.Project") as mock_cls:
            fake_proj = MagicMock()
            mock_cls.return_value = fake_proj
            res_create = await repo_ops.create(name="P")
            assert res_create is fake_proj
            session_ops.add.assert_called_once_with(fake_proj)
            session_ops.flush.assert_awaited_once()
            session_ops.refresh.assert_awaited_once_with(fake_proj)

        await repo_ops.delete(fake_proj)
        session_ops.delete.assert_called_once_with(fake_proj)

    @pytest.mark.asyncio
    async def test_project_member_repository(self):
        member_mock = MagicMock()
        session = _mock_session(scalar_one_or_none_val=member_mock)
        repo = ProjectMemberRepository(session)

        # get_by_project_and_user
        res = await repo.get_by_project_and_user("p-1", "user-1")
        assert res is member_mock

        # list_by_project
        member_list = [MagicMock()]
        session_list = _mock_session(query_return=member_list)
        repo_list = ProjectMemberRepository(session_list)
        res_list = await repo_list.list_by_project("p-1")
        assert res_list == member_list

        # count_by_role
        session_count = AsyncMock()
        result_mock = MagicMock()
        result_mock.scalar_one.return_value = 1
        session_count.execute.return_value = result_mock
        repo_count = ProjectMemberRepository(session_count)
        res_count = await repo_count.count_by_role("p-1", "team_lead")
        assert res_count == 1

        # list_by_project_with_users
        fake_rows = [(MagicMock(), MagicMock())]
        session_rows = _mock_session(all_vals=fake_rows)
        repo_rows = ProjectMemberRepository(session_rows)
        res_rows = await repo_rows.list_by_project_with_users("p-1")
        assert res_rows == fake_rows