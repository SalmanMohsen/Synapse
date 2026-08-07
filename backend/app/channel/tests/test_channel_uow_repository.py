import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.channel.uow import SqlAlchemyChannelUnitOfWork
from app.channel.repository import ChannelRepository, ChannelMemberRepository


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


class TestChannelUoWRepository:
    @pytest.mark.asyncio
    async def test_uow_attributes(self):
        session = AsyncMock()
        uow = SqlAlchemyChannelUnitOfWork(session)
        assert isinstance(uow.channels, ChannelRepository)
        assert isinstance(uow.channel_members, ChannelMemberRepository)
        
        await uow.commit()
        session.commit.assert_awaited_once()
        
        await uow.rollback()
        session.rollback.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_channel_repository_get_by_id(self):
        channel_mock = MagicMock()
        session = _mock_session(scalar_one_or_none_val=channel_mock)
        repo = ChannelRepository(session)

        result = await repo.get_by_id("channel-123")
        assert result is channel_mock
        session.execute.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_channel_repository_list_by_project(self):
        channels_mock = [MagicMock(), MagicMock()]
        session = _mock_session(query_return=channels_mock)
        repo = ChannelRepository(session)

        result = await repo.list_by_project("project-123")
        assert len(result) == 2
        assert result == channels_mock

    @pytest.mark.asyncio
    async def test_channel_repository_get_leads_channel(self):
        channel_mock = MagicMock()
        session = _mock_session(scalar_one_or_none_val=channel_mock)
        repo = ChannelRepository(session)

        result = await repo.get_leads_channel("project-123")
        assert result is channel_mock

    @pytest.mark.asyncio
    async def test_channel_repository_create_and_delete(self):
        session = AsyncMock()
        repo = ChannelRepository(session)

        with patch("app.channel.repository.Channel") as mock_cls:
            fake_channel = MagicMock()
            mock_cls.return_value = fake_channel
            result = await repo.create(name="QA")
            assert result is fake_channel
            session.add.assert_called_once_with(fake_channel)
            session.flush.assert_awaited_once()
            session.refresh.assert_awaited_once_with(fake_channel)

        await repo.delete(fake_channel)
        session.delete.assert_called_once_with(fake_channel)

    @pytest.mark.asyncio
    async def test_channel_member_repository(self):
        member_mock = MagicMock()
        session = _mock_session(scalar_one_or_none_val=member_mock)
        repo = ChannelMemberRepository(session)

        # get_by_channel_and_user
        res = await repo.get_by_channel_and_user("chan-1", "user-1")
        assert res is member_mock

        # list_by_channel
        members_mock = [MagicMock()]
        session_list = _mock_session(query_return=members_mock)
        repo_list = ChannelMemberRepository(session_list)
        res_list = await repo_list.list_by_channel("chan-1")
        assert res_list == members_mock

        # is_channel_lead
        session_lead = _mock_session(scalar_one_or_none_val=None)
        repo_lead = ChannelMemberRepository(session_lead)
        assert await repo_lead.is_channel_lead("chan-1", "user-1") is False

        # list_by_channel_with_users
        fake_rows = [(MagicMock(), MagicMock())]
        session_rows = _mock_session(all_vals=fake_rows)
        repo_rows = ChannelMemberRepository(session_rows)
        res_rows = await repo_rows.list_by_channel_with_users("chan-1")
        assert res_rows == fake_rows