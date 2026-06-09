from __future__ import annotations

from datetime import UTC, datetime

from src.models.session import Session, SessionState
from src.utils.logging import get_logger

logger = get_logger(__name__)


class SessionManager:
    def __init__(self) -> None:
        self._sessions: dict[str, Session] = {}
        logger.info("SessionManager initialized")

    def create_session(self, session_id: str) -> Session:
        session = Session(session_id=session_id)
        self._sessions[session_id] = session
        logger.info("Created session: %s", session_id)
        return session

    def get_session(self, session_id: str) -> Session | None:
        return self._sessions.get(session_id)

    def get_or_create_session(self, session_id: str) -> Session:
        session = self._sessions.get(session_id)
        if session is None:
            session = self.create_session(session_id)
        return session

    def update_session(self, session: Session) -> None:
        session.updated_at = datetime.now(UTC)
        self._sessions[session.session_id] = session

    def delete_session(self, session_id: str) -> None:
        session = self._sessions.pop(session_id, None)
        if session:
            session.set_state(SessionState.DISCONNECTED)
            logger.info("Deleted session: %s", session_id)

    def add_user_transcript(self, session_id: str, text: str) -> None:
        session = self._sessions.get(session_id)
        if session:
            session.add_user_message(text)
            logger.info("User(%s): %s", session_id, text)

    def add_agent_transcript(self, session_id: str, text: str) -> None:
        session = self._sessions.get(session_id)
        if session:
            session.add_agent_message(text)
            logger.info("Agent(%s): %s", session_id, text)

    def get_transcript_text(self, session_id: str) -> str:
        session = self._sessions.get(session_id)
        if session is None:
            return ""
        return session.get_transcript_text()

    def list_sessions(self) -> list[str]:
        return list(self._sessions.keys())

    @property
    def active_count(self) -> int:
        return len(self._sessions)
