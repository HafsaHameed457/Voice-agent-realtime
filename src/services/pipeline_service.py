from __future__ import annotations

import asyncio
import base64
import contextlib
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Awaitable, Protocol, TypeVar

from src.services.groq_llm import GroqLLMService
from src.services.groq_stt import GroqSTTService
from src.services.tts_service import EdgeTTSService
from src.utils.logging import get_logger

if TYPE_CHECKING:
    from src.config import Settings

T = TypeVar("T")

logger = get_logger(__name__)


class PipelineEventHandlers(Protocol):
    async def on_audio_delta(self, audio_base64: str, stream_sid: str) -> None: ...

    async def on_user_transcript(self, transcript: str) -> None: ...

    async def on_agent_transcript(self, transcript: str) -> None: ...

    async def on_error(self, error: Exception) -> None: ...

    async def on_session_ready(self) -> None: ...


@dataclass
class CircuitBreakerState:
    failures: int = 0
    last_failure: float = 0.0
    state: str = "closed"  # closed, open, half-open
    failure_threshold: int = 5
    recovery_timeout: float = 30.0
    half_open_max_calls: int = 3
    half_open_calls: int = 0


class CircuitBreaker:
    def __init__(self, name: str, failure_threshold: int = 5, recovery_timeout: float = 30.0) -> None:
        self.name = name
        self._state = CircuitBreakerState(failure_threshold=failure_threshold, recovery_timeout=recovery_timeout)

    def _should_attempt(self) -> bool:
        if self._state.state == "closed":
            return True
        if self._state.state == "open":
            if time.time() - self._state.last_failure > self._state.recovery_timeout:
                self._state.state = "half-open"
                self._state.half_open_calls = 0
                logger.info("Circuit breaker %s: half-open", self.name)
                return True
            return False
        if self._state.state == "half-open":
            return self._state.half_open_calls < self._state.half_open_max_calls
        return False

    def record_success(self) -> None:
        if self._state.state == "half-open":
            self._state.state = "closed"
            self._state.failures = 0
            logger.info("Circuit breaker %s: closed", self.name)
        elif self._state.state == "closed":
            self._state.failures = 0

    def record_failure(self) -> None:
        self._state.failures += 1
        self._state.last_failure = time.time()
        if self._state.state == "half-open":
            self._state.state = "open"
            logger.warning("Circuit breaker %s: opened after half-open failure", self.name)
        elif self._state.failures >= self._state.failure_threshold:
            self._state.state = "open"
            logger.warning("Circuit breaker %s: opened after %d failures", self.name, self._state.failures)

    async def call(self, coro: Awaitable[T]) -> T:
        if not self._should_attempt():
            raise RuntimeError(f"Circuit breaker {self.name} is open")
        if self._state.state == "half-open":
            self._state.half_open_calls += 1
        try:
            result = await coro
            self.record_success()
            return result
        except Exception:
            self.record_failure()
            raise


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
        self._silence_timeout = settings.silence_timeout
        self._min_audio_duration = settings.min_audio_duration
        self._vad_threshold = settings.vad_threshold
        self._connected = False

        self._stt_cb = CircuitBreaker("stt", failure_threshold=5, recovery_timeout=30.0)
        self._llm_cb = CircuitBreaker("llm", failure_threshold=5, recovery_timeout=30.0)
        self._tts_cb = CircuitBreaker("tts", failure_threshold=5, recovery_timeout=30.0)

        self._stt_timeout = settings.stt_timeout
        self._llm_timeout = settings.llm_timeout
        self._tts_timeout = settings.tts_timeout

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
            transcript = await asyncio.wait_for(
                self._stt_cb.call(self._stt.transcribe(audio_data, self._sample_rate)),
                timeout=self._stt_timeout,
            )
            logger.info("TRANSCRIPT: %s", transcript if transcript else "(empty)")
            if not transcript:
                return

            self._history.append({"role": "user", "content": transcript})
            await self._handlers.on_user_transcript(transcript)
            await self._generate_response()
        except asyncio.TimeoutError:
            logger.error("STT timeout after %ss", self._stt_timeout)
            await self._handlers.on_error(RuntimeError(f"Speech recognition timed out ({self._stt_timeout}s)"))
        except Exception:
            logger.exception("Pipeline flush failed")
            await self._handlers.on_error(RuntimeError("Pipeline processing failed"))
        finally:
            self._is_processing = False

    async def _generate_response(self) -> None:
        try:
            full_response = ""

            async def _collect_llm_chunks() -> None:
                nonlocal full_response
                async for chunk in self._llm.generate(self._history):
                    full_response += chunk

            await asyncio.wait_for(
                self._llm_cb.call(_collect_llm_chunks()),
                timeout=self._llm_timeout,
            )

            if not full_response:
                return

            self._history.append({"role": "assistant", "content": full_response})
            await self._handlers.on_agent_transcript(full_response)

            audio_pcm16 = await asyncio.wait_for(
                self._tts_cb.call(self._tts.synthesize(full_response)),
                timeout=self._tts_timeout,
            )
            if audio_pcm16:
                audio_b64 = base64.b64encode(audio_pcm16).decode("ascii")
                await self._handlers.on_audio_delta(audio_b64, "")
        except asyncio.TimeoutError:
            logger.error("LLM/TTS timeout")
            await self._handlers.on_error(RuntimeError("Response generation timed out"))
        except Exception:
            logger.exception("Pipeline response generation failed")
            await self._handlers.on_error(RuntimeError("Response generation failed"))
