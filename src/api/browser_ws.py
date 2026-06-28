from __future__ import annotations

import base64
import time
from typing import TYPE_CHECKING

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.config import get_settings
from src.models.session import Session, SessionState
from src.services.pipeline_service import PipelineOrchestrator
from src.services.session_manager import get_session_manager
from src.utils.audio import pcm16_to_mulaw
from src.utils.logging import get_logger

if TYPE_CHECKING:
    from src.services.base_session_manager import BaseSessionManager

logger = get_logger(__name__)
router = APIRouter()


class BrowserStreamHandler:
    def __init__(
        self,
        websocket: WebSocket,
        session_manager: BaseSessionManager,
        session: Session,
        session_id: str,
    ) -> None:
        self._websocket = websocket
        self._session_manager = session_manager
        self._session = session
        self._session_id = session_id

    async def on_audio_delta(self, audio_base64: str, _stream_sid: str) -> None:
        try:
            pcm16 = base64.b64decode(audio_base64)
            mulaw = pcm16_to_mulaw(pcm16)
            payload = base64.b64encode(mulaw).decode("ascii")
            await self._websocket.send_json(
                {
                    "type": "audio.delta",
                    "audio": payload,
                }
            )
        except Exception:
            logger.exception("Failed to send audio delta to browser")

    async def on_user_transcript(self, transcript: str) -> None:
        await self._session_manager.add_user_transcript(self._session_id, transcript)
        try:
            await self._websocket.send_json(
                {
                    "type": "transcript",
                    "role": "user",
                    "text": transcript,
                }
            )
        except Exception:
            logger.exception("Failed to send user transcript")

    async def on_agent_transcript(self, transcript: str) -> None:
        await self._session_manager.add_agent_transcript(self._session_id, transcript)
        try:
            await self._websocket.send_json(
                {
                    "type": "transcript",
                    "role": "assistant",
                    "text": transcript,
                }
            )
        except Exception:
            logger.exception("Failed to send agent transcript")

    async def on_error(self, error: Exception) -> None:
        logger.error("Browser session error: %s", error)
        try:
            await self._websocket.send_json(
                {
                    "type": "error",
                    "message": str(error),
                }
            )
        except Exception:
            logger.exception("Failed to send error to browser")

    async def on_session_ready(self) -> None:
        logger.info("Browser session ready: %s", self._session_id)
        try:
            await self._websocket.send_json(
                {
                    "type": "session.ready",
                    "session_id": self._session_id,
                }
            )
        except Exception:
            logger.exception("Failed to send session ready")


@router.websocket("/browser-stream")
async def browser_stream(websocket: WebSocket) -> None:
    await websocket.accept()

    session_id = websocket.query_params.get("session_id") or f"browser_{int(time.time() * 1000)}"
    logger.info("Browser client connected: session_id=%s", session_id)

    session_manager = get_session_manager()
    session = await session_manager.create_session(session_id)

    handler = BrowserStreamHandler(websocket, session_manager, session, session_id)
    pipeline = PipelineOrchestrator(
        settings=get_settings(),
        handlers=handler,
    )

    try:
        await pipeline.connect()
        session.set_state(SessionState.ACTIVE)

        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type", "")

            if msg_type == "text":
                text = data.get("text", "").strip()
                if text:
                    await session_manager.add_user_transcript(session_id, text)
                    await pipeline.send_text(text)

            elif msg_type == "audio":
                audio_b64 = data.get("audio", "")
                if audio_b64:
                    pcm16 = base64.b64decode(audio_b64)
                    await pipeline.send_audio(pcm16)

            elif msg_type == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        logger.info("Browser client disconnected: %s", session_id)
    except Exception:
        logger.exception("Browser stream error: %s", session_id)
    finally:
        session.set_state(SessionState.DISCONNECTED)
        await session_manager.update_session(session)
        await pipeline.disconnect()
        logger.info("Browser session cleaned up: %s", session_id)
