from __future__ import annotations

import json
import time
from typing import TYPE_CHECKING

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.config import get_settings
from src.models.session import SessionState
from src.services.openai_realtime import OpenAIEventHandlers, OpenAIRealtimeClient
from src.services.session_manager import get_session_manager
from src.services.twilio import parse_twilio_event
from src.utils.logging import get_logger

if TYPE_CHECKING:
    from src.services.base_session_manager import BaseSessionManager

logger = get_logger(__name__)

router = APIRouter()


class MediaStreamHandler(OpenAIEventHandlers):
    def __init__(
        self,
        websocket: WebSocket,
        session_manager: BaseSessionManager,
        session_id: str,
    ) -> None:
        self._websocket = websocket
        self._session_manager = session_manager
        self._session_id = session_id
        self._stream_sid: str | None = None

    def set_stream_sid(self, stream_sid: str) -> None:
        self._stream_sid = stream_sid

    async def on_audio_delta(self, audio_base64: str, stream_sid: str) -> None:
        target_stream = stream_sid or self._stream_sid
        if not target_stream:
            return
        try:
            await self._websocket.send_json(
                {
                    "event": "media",
                    "streamSid": target_stream,
                    "media": {"payload": audio_base64},
                }
            )
        except Exception:
            logger.exception("Failed to send audio to client")

    async def on_user_transcript(self, transcript: str) -> None:
        await self._session_manager.add_user_transcript(self._session_id, transcript)

    async def on_agent_transcript(self, transcript: str) -> None:
        await self._session_manager.add_agent_transcript(self._session_id, transcript)

    async def on_error(self, error: Exception) -> None:
        logger.error("OpenAI error in session %s: %s", self._session_id, error)

    async def on_session_ready(self) -> None:
        logger.info("OpenAI session ready for %s", self._session_id)


@router.websocket("/media-stream")
async def media_stream(websocket: WebSocket) -> None:
    await websocket.accept()

    session_id = (
        websocket.headers.get("x-twilio-call-sid")
        or websocket.query_params.get("session_id")
        or f"browser_{int(time.time() * 1000)}"
    )
    logger.info("Client connected: session_id=%s", session_id)

    session_manager = get_session_manager()
    session = await session_manager.create_session(session_id)

    handler = MediaStreamHandler(websocket, session_manager, session_id)
    openai_client = OpenAIRealtimeClient(
        settings=get_settings(),
        handlers=handler,
    )

    try:
        await openai_client.connect()
        session.set_state(SessionState.ACTIVE)
        logger.info("Session active: %s", session_id)

        while True:
            msg = await websocket.receive_text()
            data = json.loads(msg)
            event = parse_twilio_event(data)

            if event.event_type == "start" and event.stream_sid:
                handler.set_stream_sid(event.stream_sid)
                session.stream_sid = event.stream_sid
                await session_manager.update_session(session)
                logger.info(
                    "Stream started: session_id=%s stream_sid=%s",
                    session_id,
                    event.stream_sid,
                )

            elif event.event_type == "media" and event.audio_payload:
                await openai_client.send_audio(event.audio_payload)

            elif event.event_type == "mark":
                logger.debug("Mark received: session_id=%s", session_id)

    except WebSocketDisconnect:
        logger.info("Client disconnected: session_id=%s", session_id)
    except Exception:
        logger.exception("WebSocket error in session %s", session_id)
    finally:
        session.set_state(SessionState.DISCONNECTED)
        transcript_text = session.get_transcript_text()
        logger.info("Session %s transcript:\n%s", session_id, transcript_text)
        await openai_client.disconnect()
        await session_manager.delete_session(session_id)
