from __future__ import annotations

import io

import edge_tts
from pydub import AudioSegment  # type: ignore[import-untyped]

from src.utils.logging import get_logger

logger = get_logger(__name__)

_DEFAULT_VOICE = "en-US-JennyNeural"
_TARGET_SAMPLE_RATE = 24000


class EdgeTTSService:
    def __init__(self) -> None:
        self._voice = _DEFAULT_VOICE

    async def synthesize(self, text: str) -> bytes:
        communicate = edge_tts.Communicate(text, self._voice)
        mp3_buf = io.BytesIO()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                mp3_buf.write(chunk["data"])
        mp3_buf.seek(0)

        audio = AudioSegment.from_mp3(mp3_buf)
        audio = audio.set_frame_rate(_TARGET_SAMPLE_RATE).set_channels(1).set_sample_width(2)
        return bytes(audio.raw_data)
