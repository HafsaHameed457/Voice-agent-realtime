from __future__ import annotations

import asyncio
import base64
import contextlib
from typing import TYPE_CHECKING, Protocol

from src.services.groq_llm import GroqLLMService
from src.services.groq_stt import GroqSTTService
from src.services.tts_service import EdgeTTSService
from src.utils.logging import get_logger

if TYPE_CHECKING:
    from src.config import Settings

logger = get_logger(__name__)


class PipelineEventHandlers(Protocol):
    async def on_audio_delta(self, audio_base64: str, stream_sid: str) -> None: ...

    async def on_user_transcript(self, transcript: str) -> None: ...

    async def on_agent_transcript(self, transcript: str) -> None: ...

    async def on_error(self, error: Exception) -> None: ...

    async def on_session_ready(self) -> None: ...


class PipelineOrchestrator:
    def __init__(
        self,
        settings: Settings,
        handlers: PipelineEventHandlers,
    ) -> None:
        self._stt = GroqSTTService(settings)
        self._llm = GroqLLMService(settings)
        self._tts = EdgeTTSService()
        self._handlers = handlers
        self._history: list[dict[str, str]] = []
        self._audio_buffer = bytearray()
        self._sample_rate = 24000
        self._is_processing = False
        self._flush_task: asyncio.Task[None] | None = None
        self._silence_timeout = 1.0
        self._min_audio_duration = 0.5
        self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        self._connected = True
        await self._handlers.on_session_ready()
        logger.info("Pipeline connected")

    async def disconnect(self) -> None:
        self._connected = False
        if self._flush_task and not self._flush_task.done():
            self._flush_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._flush_task
        if self._audio_buffer:
            await self._flush()
        logger.info("Pipeline disconnected")

    async def send_audio(self, pcm16_chunk: bytes) -> None:
        if not self._connected:
            return
        self._audio_buffer.extend(pcm16_chunk)
        if self._flush_task and not self._flush_task.done():
            self._flush_task.cancel()
        self._flush_task = asyncio.create_task(self._delayed_flush())

    async def _delayed_flush(self) -> None:
        try:
            duration_s = (len(self._audio_buffer) / 2) / self._sample_rate
            if duration_s < self._min_audio_duration:
                return
            await asyncio.sleep(self._silence_timeout)
            if not self._audio_buffer or self._is_processing:
                return
            await self._flush()
        except asyncio.CancelledError:
            pass

    async def send_text(self, text: str) -> None:
        if not self._connected:
            return
        text = text.strip()
        if not text:
            return
        self._history.append({"role": "user", "content": text})
        await self._handlers.on_user_transcript(text)
        await self._generate_response()

    async def _flush(self) -> None:
        if not self._audio_buffer or self._is_processing:
            return
        self._is_processing = True
        audio_data = bytes(self._audio_buffer)
        self._audio_buffer.clear()
        try:
            transcript = await self._stt.transcribe(audio_data, self._sample_rate)
            logger.info("TRANSCRIPT: %s", transcript if transcript else "(empty)")
            if not transcript:
                return

            self._history.append({"role": "user", "content": transcript})
            await self._handlers.on_user_transcript(transcript)
            await self._generate_response()
        except Exception:
            logger.exception("Pipeline flush failed")
            await self._handlers.on_error(RuntimeError("Pipeline processing failed"))
        finally:
            self._is_processing = False

    async def _generate_response(self) -> None:
        try:
            full_response = ""
            async for chunk in self._llm.generate(self._history):
                full_response += chunk
            if not full_response:
                return

            self._history.append({"role": "assistant", "content": full_response})
            await self._handlers.on_agent_transcript(full_response)

            audio_pcm16 = await self._tts.synthesize(full_response)
            if audio_pcm16:
                audio_b64 = base64.b64encode(audio_pcm16).decode("ascii")
                await self._handlers.on_audio_delta(audio_b64, "")
        except Exception:
            logger.exception("Pipeline response generation failed")
            await self._handlers.on_error(RuntimeError("Response generation failed"))
