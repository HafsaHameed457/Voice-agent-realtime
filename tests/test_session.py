from __future__ import annotations

import pytest
import pytest_asyncio

from src.models.session import Session, SessionState, TranscriptEntry


@pytest.fixture
def session() -> Session:
    return Session(session_id="test-session-123")


class TestSession:
    def test_create_session(self, session: Session) -> None:
        assert session.session_id == "test-session-123"
        assert session.state == SessionState.CONNECTING
        assert session.transcript == []

    def test_set_state(self, session: Session) -> None:
        session.set_state(SessionState.ACTIVE)
        assert session.state == SessionState.ACTIVE

        session.set_state(SessionState.DISCONNECTED)
        assert session.state == SessionState.DISCONNECTED

    def test_add_user_message(self, session: Session) -> None:
        session.add_user_message("Hello")
        assert len(session.transcript) == 1
        entry = session.transcript[0]
        assert isinstance(entry, TranscriptEntry)
        assert entry.role == "user"
        assert entry.content == "Hello"

    def test_add_agent_message(self, session: Session) -> None:
        session.add_agent_message("Hi there!")
        assert len(session.transcript) == 1
        entry = session.transcript[0]
        assert entry.role == "agent"
        assert entry.content == "Hi there!"

    def test_get_transcript_text(self, session: Session) -> None:
        session.add_user_message("Hello")
        session.add_agent_message("Hi there!")
        session.add_user_message("How are you?")

        text = session.get_transcript_text()
        assert "user: Hello" in text
        assert "agent: Hi there!" in text
        assert "user: How are you?" in text


@pytest_asyncio.fixture
async def session_manager():
    from src.services.session_manager import SessionManager

    manager = SessionManager()
    yield manager
    for session_id in await manager.list_sessions():
        await manager.delete_session(session_id)


class TestSessionManager:
    @pytest.mark.asyncio
    async def test_create_and_get_session(self, session_manager):
        session = await session_manager.create_session("test-1")
        assert session.session_id == "test-1"
        assert session.state == SessionState.CONNECTING

        retrieved = await session_manager.get_session("test-1")
        assert retrieved is not None
        assert retrieved.session_id == "test-1"

    @pytest.mark.asyncio
    async def test_get_nonexistent_session(self, session_manager):
        session = await session_manager.get_session("nonexistent")
        assert session is None

    @pytest.mark.asyncio
    async def test_get_or_create_session(self, session_manager):
        session1 = await session_manager.get_or_create_session("test-2")
        session2 = await session_manager.get_or_create_session("test-2")
        assert session1 is session2

    @pytest.mark.asyncio
    async def test_update_session(self, session_manager):
        session = await session_manager.create_session("test-3")
        original_updated = session.updated_at
        session.set_state(SessionState.ACTIVE)
        await session_manager.update_session(session)
        assert session.updated_at >= original_updated

    @pytest.mark.asyncio
    async def test_delete_session(self, session_manager):
        await session_manager.create_session("test-4")
        await session_manager.delete_session("test-4")
        session = await session_manager.get_session("test-4")
        assert session is None

    @pytest.mark.asyncio
    async def test_add_user_transcript(self, session_manager):
        await session_manager.create_session("test-5")
        await session_manager.add_user_transcript("test-5", "Hello")
        text = await session_manager.get_transcript_text("test-5")
        assert "user: Hello" in text

    @pytest.mark.asyncio
    async def test_add_agent_transcript(self, session_manager):
        await session_manager.create_session("test-6")
        await session_manager.add_agent_transcript("test-6", "Hi there!")
        text = await session_manager.get_transcript_text("test-6")
        assert "agent: Hi there!" in text

    @pytest.mark.asyncio
    async def test_list_sessions(self, session_manager):
        await session_manager.create_session("test-7a")
        await session_manager.create_session("test-7b")
        sessions = await session_manager.list_sessions()
        assert "test-7a" in sessions
        assert "test-7b" in sessions

    @pytest.mark.asyncio
    async def test_get_active_count(self, session_manager):
        assert await session_manager.get_active_count() == 0
        await session_manager.create_session("test-8a")
        await session_manager.create_session("test-8b")
        assert await session_manager.get_active_count() == 2

    @pytest.mark.asyncio
    async def test_health_check(self, session_manager):
        await session_manager.health_check()
