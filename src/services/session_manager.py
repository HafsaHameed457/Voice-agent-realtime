from __future__ import annotations

from datetime import UTC, datetime

from src.models.session import Session, SessionState
from src.services.base_session_manager import BaseSessionManager
from src.utils.logging import get_logger

logger = get_logger(__name__)


class SessionManager(BaseSessionManager):
    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        logger.info("SessionManager initialized")

    async def create_session(self, session_id: str) -> Session:
        session = Session(session_id=session_id)
        self._sessions[session_id] = session
        logger.info("Created session: %s", session_id)
        return session

    async def get_session(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)

    async def get_or_create_session(self, session_id: str) -> Session:
        session = self._sessions.get(session_id)
        if session is None:
            session = await self.create_session(session_id)
        return session

    async def update_session(self, session: Session) -> None:
        session.updated_at = datetime.now(UTC)
        self._sessions[session.session_id] = session

    async def delete_session(self, session_id: str) -> None:
        session = self._sessions.pop(session_id, None)
        if session:
            session.set_state(SessionState.DISCONNECTED)
            logger.info("Deleted session: %s", session_id)

    async def add_user_transcript(self, session_id: str, text: str) -> None:
        session = self._sessions.get(session_id)
        if session:
            session.add_user_message(text)
            logger.info("User(%s): %s", session_id, text)

    async def add_agent_transcript(self, session_id: str, text: str) -> None:
        session = self._sessions.get(session_id)
        if session:
            session.add_agent_message(text)
            logger.info("Agent(%s): %s", session_id, text)

    async def get_transcript_text(self, session_id: str) -> str:
        session = self._sessions.get(session_id)
        if session is None:
            return ""
        return session.get_transcript_text()

    async def list_sessions(self) -> list[str]:
        return list(self._sessions.keys())

    async def get_active_count(self) -> int:
        return len(self._sessions)

    async def health_check(self) -> None:
        pass


def get_session_manager() -> BaseSessionManager:
    from src.config import get_settings  # noqa: PLC0415

    settings = get_settings()
    if settings.redis_url:
        from src.services.redis_session_manager import RedisSessionManager  # noqa: PLC0415

        return RedisSessionManager(
            redis_url=settings.redis_url,
            key_prefix=settings.redis_key_prefix,
            ttl_seconds=86400,  # 24 hours
            cleanup_interval=300,  # 5 minutes
        )
    return SessionManager()
