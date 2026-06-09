from __future__ import annotations

import asyncio
import base64
import contextlib
import json
from typing import TYPE_CHECKING, Any, Protocol

import websockets

from src.utils.logging import get_logger

if TYPE_CHECKING:
    from src.config import Settings

logger = get_logger(__name__)

LOG_EVENT_TYPES = [
    "response.content.done",
    "rate_limits.updated",
    "response.done",
    "input_audio_buffer.committed",
    "input_audio_buffer.speech_stopped",
    "input_audio_buffer.speech_started",
    "session.created",
    "response.text.done",
    "conversation.item.input_audio_transcription.completed",
    "session.updated",
    "error",
]


class OpenAIEventHandlers(Protocol):
    async def on_audio_delta(self, audio_base64: str, stream_sid: str) -> None: ...

    async def on_user_transcript(self, transcript: str) -> None: ...

    async def on_agent_transcript(self, transcript: str) -> None: ...

    async def on_error(self, error: Exception) -> None: ...

    async def on_session_ready(self) -> None: ...


class OpenAIRealtimeClient:
    def __init__(self, settings: Settings, handlers: OpenAIEventHandlers) -> None:
        self._settings = settings
        self._handlers = handlers
        self._ws: websockets.ClientConnection | None = None
        self._connected = False
        self._receive_task: asyncio.Task[None] | None = None

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        headers: dict[str, str] = {
            "Authorization": f"Bearer {self._settings.openai_api_key}",
            "OpenAI-Beta": "realtime=v1",
        }

        logger.info("Connecting to OpenAI Realtime API")
        self._ws = await websockets.connect(
            self._settings.openai_ws_url,
            additional_headers=headers,
        )
        self._connected = True
        logger.info("Connected to OpenAI Realtime API")

        await self._send_session_update()
        self._receive_task = asyncio.create_task(self._receive_loop())

    async def disconnect(self) -> None:
        self._connected = False
        if self._receive_task and not self._receive_task.done():
            self._receive_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._receive_task
        if self._ws:
            await self._ws.close()
            self._ws = None
        logger.info("Disconnected from OpenAI Realtime API")

    async def send_audio(self, audio_base64: str) -> None:
        if not self._ws or not self._connected:
            return
        try:
            payload = json.dumps(
                {
                    "type": "input_audio_buffer.append",
                    "audio": audio_base64,
                }
            )
            await self._ws.send(payload)
        except websockets.ConnectionClosed:
            logger.warning("Cannot send audio: OpenAI connection closed")
            self._connected = False

    async def _send_session_update(self) -> None:
        if not self._ws:
            return
        try:
            session_update = {
                "type": "session.update",
                "session": {
                    "turn_detection": {
                        "type": self._settings.turn_detection_type,
                    },
                    "input_audio_format": self._settings.input_audio_format,
                    "output_audio_format": self._settings.output_audio_format,
                    "voice": self._settings.voice,
                    "instructions": self._settings.system_message,
                    "modalities": ["text", "audio"],
                    "temperature": self._settings.temperature,
                    "input_audio_transcription": {
                        "model": self._settings.input_audio_transcription_model,
                    },
                },
            }
            await self._ws.send(json.dumps(session_update))
            logger.info(
                "Session update sent: voice=%s temperature=%s",
                self._settings.voice,
                self._settings.temperature,
            )
        except websockets.ConnectionClosedOK:
            logger.info("OpenAI connection closed normally during session update")
        except websockets.ConnectionClosedError:
            logger.exception("OpenAI connection closed unexpectedly during session update")
        except Exception:
            logger.exception("Failed to send session update")

    async def _receive_loop(self) -> None:
        if not self._ws:
            return
        try:
            async for message in self._ws:
                response = json.loads(message)
                event_type = response.get("type", "")
                await self._handle_event(event_type, response)
        except websockets.ConnectionClosedOK:
            logger.info("OpenAI receive loop: connection closed normally")
        except websockets.ConnectionClosedError:
            logger.exception("OpenAI receive loop: connection closed")
            self._connected = False
        except asyncio.CancelledError:
            logger.debug("OpenAI receive loop cancelled")
        except Exception:
            logger.exception("OpenAI receive loop error")
            self._connected = False

    async def _handle_event(self, event_type: str, response: dict[str, Any]) -> None:
        if event_type in LOG_EVENT_TYPES:
            logger.debug("Event: %s", event_type)

        if event_type == "session.updated":
            await self._handlers.on_session_ready()
        elif event_type == "conversation.item.input_audio_transcription.completed":
            await self._handle_user_transcript(response)
        elif event_type == "response.done":
            await self._handle_agent_transcript(response)
        elif event_type == "response.audio.delta":
            await self._handle_audio_delta(response)
        elif event_type == "error":
            await self._handle_error(response)

    async def _handle_user_transcript(self, response: dict[str, Any]) -> None:
        transcript = response.get("transcript", "").strip()
        if transcript:
            await self._handlers.on_user_transcript(transcript)

    async def _handle_agent_transcript(self, response: dict[str, Any]) -> None:
        agent_msg = self._extract_agent_message(response)
        if agent_msg:
            await self._handlers.on_agent_transcript(agent_msg)

    async def _handle_audio_delta(self, response: dict[str, Any]) -> None:
        delta = response.get("delta", "")
        if delta:
            decoded = base64.b64decode(delta)
            re_encoded = base64.b64encode(decoded).decode("utf-8")
            await self._handlers.on_audio_delta(re_encoded, "")

    async def _handle_error(self, response: dict[str, Any]) -> None:
        error_data = response.get("error", {})
        logger.error("OpenAI error event: %s", error_data)
        await self._handlers.on_error(RuntimeError(f"OpenAI error: {error_data}"))

    @staticmethod
    def _extract_agent_message(response: dict[str, Any]) -> str:
        output = response.get("response", {}).get("output", [])
        if output and isinstance(output, list):
            for item in output:
                if isinstance(item, dict):
                    for content in item.get("content", []):
                        if isinstance(content, dict) and "transcript" in content:
                            return str(content["transcript"])
        return ""
