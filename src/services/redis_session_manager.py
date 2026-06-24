from __future__ import annotations

import json
from dataclasses import asdict
from datetime import UTC, datetime

import redis.asyncio as redis

from src.models.session import Session, SessionState, TranscriptEntry
from src.services.base_session_manager import BaseSessionManager
from src.utils.logging import get_logger

logger = get_logger(__name__)


def _session_to_json(session: Session) -> str:
    data = asdict(session)
    data["created_at"] = session.created_at.isoformat()
    data["updated_at"] = session.updated_at.isoformat()
    data["transcript"] = [
        {"role": e.role, "content": e.content, "timestamp": e.timestamp.isoformat()}
        for e in session.transcript
    ]
    return json.dumps(data)


def _json_to_session(data: str) -> Session:
    d = json.loads(data)
    transcript = [
        TranscriptEntry(
            role=e["role"],
            content=e["content"],
            timestamp=datetime.fromisoformat(e["timestamp"]),
        )
        for e in d.get("transcript", [])
    ]
    return Session(
        session_id=d["session_id"],
        stream_sid=d.get("stream_sid"),
        transcript=transcript,
        state=SessionState(d["state"]),
        created_at=datetime.fromisoformat(d["created_at"]),
        updated_at=datetime.fromisoformat(d["updated_at"]),
    )


class RedisSessionManager(BaseSessionManager):
    def __init__(self, redis_url: str, key_prefix: str = "voice_agent") -> None:
        self._redis = redis.from_url(redis_url, decode_responses=True)
        self._prefix = key_prefix
        logger.info("RedisSessionManager initialized with prefix=%s", key_prefix)

    def _session_key(self, session_id: str) -> str:
        return f"{self._prefix}:sessions:{session_id}"

    def _index_key(self) -> str:
        return f"{self._prefix}:sessions:index"

    async def create_session(self, session_id: str) -> Session:
        session = Session(session_id=session_id)
        await self._save_session(session)
        await self._redis.sadd(self._index_key(), session_id)
        logger.info("Created session: %s", session_id)
        return session

    async def get_session(self, session_id: str) -> Session | None:
        data = await self._redis.get(self._session_key(session_id))
        if data is None:
            return None
        return _json_to_session(str(data))

    async def get_or_create_session(self, session_id: str) -> Session:
        session = await self.get_session(session_id)
        if session is None:
            session = await self.create_session(session_id)
        return session

    async def update_session(self, session: Session) -> None:
        session.updated_at = datetime.now(UTC)
        await self._save_session(session)

    async def delete_session(self, session_id: str) -> None:
        session = await self.get_session(session_id)
        if session:
            session.set_state(SessionState.DISCONNECTED)
            await self._save_session(session)
        await self._redis.srem(self._index_key(), session_id)
        await self._redis.delete(self._session_key(session_id))
        logger.info("Deleted session: %s", session_id)

    async def add_user_transcript(self, session_id: str, text: str) -> None:
        session = await self.get_session(session_id)
        if session:
            session.add_user_message(text)
            await self._save_session(session)
            logger.info("User(%s): %s", session_id, text)

    async def add_agent_transcript(self, session_id: str, text: str) -> None:
        session = await self.get_session(session_id)
        if session:
            session.add_agent_message(text)
            await self._save_session(session)
            logger.info("Agent(%s): %s", session_id, text)

    async def get_transcript_text(self, session_id: str) -> str:
        session = await self.get_session(session_id)
        if session is None:
            return ""
        return session.get_transcript_text()

    async def list_sessions(self) -> list[str]:
        members = await self._redis.smembers(self._index_key())
        return [str(m) for m in members]

    async def get_active_count(self) -> int:
        return await self._redis.scard(self._index_key())

    async def health_check(self) -> None:
        await self._redis.ping()

    async def _save_session(self, session: Session) -> None:
        await self._redis.set(self._session_key(session.session_id), _session_to_json(session))

    async def close(self) -> None:
        await self._redis.aclose()
        logger.info("RedisSessionManager closed")
