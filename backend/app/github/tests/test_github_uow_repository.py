import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.github.uow import SqlAlchemyGitIntegrationUnitOfWork
from app.github.repository import GitIntegrationRepository, WebhookEventRepository


def _make_async_result(values, scalar_one_or_none_val=None, scalars_first_val=None):
    result = MagicMock()
    result.scalar_one_or_none.return_value = scalar_one_or_none_val
    result.scalars.return_value.first.return_value = scalars_first_val
    result.scalars.return_value.all.return_value = values
    return result


def _mock_session(query_return=None, scalar_one_or_none_val=None, scalars_first_val=None):
    session = AsyncMock()
    session.execute.return_value = _make_async_result(
        query_return or [], scalar_one_or_none_val, scalars_first_val
    )
    return session


class TestGithubUoWRepository:
    @pytest.mark.asyncio
    async def test_uow_attributes(self):
        session = AsyncMock()
        uow = SqlAlchemyGitIntegrationUnitOfWork(session)
        assert isinstance(uow.git_integrations, GitIntegrationRepository)
        assert isinstance(uow.webhook_events, WebhookEventRepository)
        
        await uow.commit()
        session.commit.assert_awaited_once()
        
        await uow.rollback()
        session.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_git_integration_repository(self):
        int_mock = MagicMock()
        session = _mock_session(scalar_one_or_none_val=int_mock, scalars_first_val=int_mock)
        repo = GitIntegrationRepository(session)

        # get_by_id
        res = await repo.get_by_id("int-1")
        assert res is int_mock

        # get_by_project_id
        res_proj = await repo.get_by_project_id("project-1")
        assert res_proj is int_mock

        # get_by_installation_id
        res_inst = await repo.get_by_installation_id("inst-1")
        assert res_inst is int_mock

        # get_by_repo_full_name
        res_repo = await repo.get_by_repo_full_name("org/repo")
        assert res_repo is int_mock

        # create and delete
        session_ops = AsyncMock()
        repo_ops = GitIntegrationRepository(session_ops)
        with patch("app.github.repository.GitIntegration") as mock_cls:
            fake_int = MagicMock()
            mock_cls.return_value = fake_int
            res_create = await repo_ops.create(repo_full_name="org/repo")
            assert res_create is fake_int
            session_ops.add.assert_called_once_with(fake_int)
            session_ops.flush.assert_awaited_once()

        await repo_ops.delete(fake_int)
        session_ops.delete.assert_called_once_with(fake_int)

    @pytest.mark.asyncio
    async def test_webhook_event_repository(self):
        event_mock = MagicMock()
        session = _mock_session(scalar_one_or_none_val=event_mock)
        repo = WebhookEventRepository(session)

        # get_by_id
        res = await repo.get_by_id("event-1")
        assert res is event_mock

        # get_by_delivery_id
        res_delivery = await repo.get_by_delivery_id("delivery-1")
        assert res_delivery is event_mock

        # create and update
        session_ops = AsyncMock()
        repo_ops = WebhookEventRepository(session_ops)
        with patch("app.github.repository.WebhookEvent") as mock_cls:
            fake_event = MagicMock()
            mock_cls.return_value = fake_event
            res_create = await repo_ops.create(delivery_id="delivery-1")
            assert res_create is fake_event
            session_ops.add.assert_called_once_with(fake_event)
            session_ops.flush.assert_awaited_once()

        # Clear mock history before the next update operation
        session_ops.reset_mock()

        await repo_ops.update(fake_event, status="processed")
        session_ops.flush.assert_awaited_once()