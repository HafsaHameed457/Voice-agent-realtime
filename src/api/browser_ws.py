from __future__ import annotations

import time

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from src.config import get_settings
from src.models.session import Session, SessionState
from src.services.openai_realtime import OpenAIRealtimeClient
from src.services.session_manager import SessionManager
from src.utils.logging import get_logger

logger = get_logger(__name__)
router = APIRouter()


class BrowserStreamHandler:
    def __init__(
        self,
        websocket: WebSocket,
        session_manager: SessionManager,
        session: Session,
        session_id: str,
    ) -> None:
        self._websocket = websocket
        self._session_manager = session_manager
        self._session = session
        self._session_id = session_id

    async def on_audio_delta(self, audio_base64: str, _stream_sid: str) -> None:
        try:
            await self._websocket.send_json(
                {
                    "type": "audio.delta",
                    "audio": audio_base64,
                }
            )
        except Exception:
            logger.exception("Failed to send audio delta to browser")

    async def on_user_transcript(self, transcript: str) -> None:
        self._session_manager.add_user_transcript(self._session_id, transcript)
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
        self._session_manager.add_agent_transcript(self._session_id, transcript)
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

    session_manager = SessionManager()
    session = session_manager.create_session(session_id)

    handler = BrowserStreamHandler(websocket, session_manager, session, session_id)
    openai_client = OpenAIRealtimeClient(
        settings=get_settings(),
        handlers=handler,
    )

    try:
        await openai_client.connect()
        session.set_state(SessionState.ACTIVE)

        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type", "")

            if msg_type == "text":
                text = data.get("text", "").strip()
                if text:
                    session_manager.add_user_transcript(session_id, text)
                    await openai_client.send_text(text)

            elif msg_type == "ping":
                await websocket.send_json({"type": "pong"})

    except WebSocketDisconnect:
        logger.info("Browser client disconnected: %s", session_id)
    except Exception:
        logger.exception("Browser stream error: %s", session_id)
    finally:
        session.set_state(SessionState.DISCONNECTED)
        session_manager.update_session(session)
        await openai_client.disconnect()
        logger.info("Browser session cleaned up: %s", session_id)
