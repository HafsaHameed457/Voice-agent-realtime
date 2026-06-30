from __future__ import annotations

import asyncio
import contextlib
import json
from dataclasses import asdict
from datetime import UTC, datetime
from typing import TYPE_CHECKING

import redis.asyncio as redis

from src.config import get_settings
from src.models.session import Session, SessionState, TranscriptEntry
from src.services.base_session_manager import BaseSessionManager
from src.utils.logging import get_logger

if TYPE_CHECKING:
    from src.config import Settings

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
    def __init__(
        self,
        redis_url: str,
        key_prefix: str = "voice_agent",
        ttl_seconds: int = 86400,
        cleanup_interval: int = 300,
    ) -> None:
        self._redis = redis.from_url(redis_url, decode_responses=True)
        self._prefix = key_prefix
        self._ttl = ttl_seconds
        self._cleanup_interval = cleanup_interval
        self._cleanup_task: asyncio.Task[None] | None = None
        self._pubsub: redis.client.PubSub | None = None
        logger.info(
            "RedisSessionManager initialized: prefix=%s ttl=%ds cleanup_interval=%ds",
            key_prefix,
            ttl_seconds,
            cleanup_interval,
        )

    def _session_key(self, session_id: str) -> str:
        return f"{self._prefix}:sessions:{session_id}"

    def _index_key(self) -> str:
        return f"{self._prefix}:sessions:index"

    def _pubsub_channel(self) -> str:
        return f"{self._prefix}:sessions:events"

    async def start(self) -> None:
        """Start background cleanup task and pub/sub listener."""
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        self._pubsub = self._redis.pubsub()
        await self._pubsub.subscribe(self._pubsub_channel())
        asyncio.create_task(self._pubsub_listener())
        logger.info("RedisSessionManager started")

    async def stop(self) -> None:
        """Stop background tasks."""
        if self._cleanup_task:
            self._cleanup_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._cleanup_task
        if self._pubsub:
            await self._pubsub.unsubscribe(self._pubsub_channel())
            await self._pubsub.aclose()  # type: ignore[no-untyped-call]
        await self._redis.aclose()
        logger.info("RedisSessionManager stopped")

    async def _cleanup_loop(self) -> None:
        """Periodically clean up expired sessions."""
        while True:
            try:
                await asyncio.sleep(self._cleanup_interval)
                await self._cleanup_expired()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Session cleanup error")

    async def _cleanup_expired(self) -> None:
        """Remove sessions that have expired (TTL passed)."""
        session_ids = await self._redis.smembers(self._index_key())
        for sid in session_ids:
            key = self._session_key(str(sid))
            ttl = await self._redis.ttl(key)
            if ttl == -2:  # key doesn't exist
                await self._redis.srem(self._index_key(), str(sid))
                logger.debug("Cleaned up expired session: %s", sid)

    async def _pubsub_listener(self) -> None:
        """Listen for session events from other workers."""
        if not self._pubsub:
            return
        async for message in self._pubsub.listen():
            if message["type"] == "message":
                logger.debug("Received pubsub event: %s", message["data"])

    async def _publish_event(self, event_type: str, session_id: str, data: dict[str, str] | None = None) -> None:
        """Publish session event to other workers."""
        import time
        payload = json.dumps({"type": event_type, "session_id": session_id, "data": data or {}, "ts": time.time()})
        await self._redis.publish(self._pubsub_channel(), payload)

    async def create_session(self, session_id: str) -> Session:
        session = Session(session_id=session_id)
        await self._save_session(session)
        await self._redis.sadd(self._index_key(), session_id)
        await self._redis.expire(self._session_key(session_id), self._ttl)
        await self._redis.expire(self._index_key(), self._ttl)
        await self._publish_event("created", session_id)
        logger.info("Created session: %s", session_id)
        return session

    async def get_session(self, session_id: str) -> Session | None:
        data = await self._redis.get(self._session_key(session_id))
        if data is None:
            return None
        # Refresh TTL on access
        await self._redis.expire(self._session_key(session_id), self._ttl)
        return _json_to_session(str(data))

    async def get_or_create_session(self, session_id: str) -> Session:
        session = await self.get_session(session_id)
        if session is None:
            session = await self.create_session(session_id)
        return session

    async def update_session(self, session: Session) -> None:
        session.updated_at = datetime.now(UTC)
        await self._save_session(session)
        await self._redis.expire(self._session_key(session.session_id), self._ttl)

    async def delete_session(self, session_id: str) -> None:
        session = await self.get_session(session_id)
        if session:
            session.set_state(SessionState.DISCONNECTED)
            await self._save_session(session)
        await self._redis.srem(self._index_key(), session_id)
        await self._redis.delete(self._session_key(session_id))
        await self._publish_event("deleted", session_id)
        logger.info("Deleted session: %s", session_id)

    async def add_user_transcript(self, session_id: str, text: str) -> None:
        session = await self.get_session(session_id)
        if session:
            session.add_user_message(text)
            await self._save_session(session)
            await self._redis.expire(self._session_key(session_id), self._ttl)
            await self._publish_event("user_transcript", session_id, {"text": text})
            logger.info("User(%s): %s", session_id, text)

    async def add_agent_transcript(self, session_id: str, text: str) -> None:
        session = await self.get_session(session_id)
        if session:
            session.add_agent_message(text)
            await self._save_session(session)
            await self._redis.expire(self._session_key(session_id), self._ttl)
            await self._publish_event("agent_transcript", session_id, {"text": text})
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
