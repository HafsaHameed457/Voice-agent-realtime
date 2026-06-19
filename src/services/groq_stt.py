from __future__ import annotations

import io
import wave
from typing import TYPE_CHECKING

from groq import AsyncGroq

from src.utils.logging import get_logger

if TYPE_CHECKING:
    from src.config import Settings

logger = get_logger(__name__)


class GroqSTTService:
    def __init__(self, settings: Settings) -> None:
        self._client = AsyncGroq(api_key=settings.groq_api_key)
        self._model = settings.groq_stt_model

    async def transcribe(self, pcm16_bytes: bytes, sample_rate: int = 24000) -> str:
        wav_bytes = _pcm16_to_wav(pcm16_bytes, sample_rate)
        try:
            transcription = await self._client.audio.transcriptions.create(
                file=("audio.wav", wav_bytes),
                model=self._model,
                response_format="text",
            )
            text = str(transcription).strip()
        except Exception:
            logger.exception("Groq STT request failed")
            return ""
        else:
            if text:
                logger.debug("STT: %s", text[:80])
            return text


def _pcm16_to_wav(pcm16_bytes: bytes, sample_rate: int = 24000) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm16_bytes)
    return buf.getvalue()
