from __future__ import annotations

import base64
import io
import struct
import wave

from pydub import AudioSegment

MULAW_BIAS = 0x84
MULAW_CLIP = 32635


def _linear_to_mulaw(sample: int) -> int:
    if sample < 0:
        sample = -sample
        sign = 0x80
    else:
        sign = 0x00
    sample = min(sample, MULAW_CLIP)
    sample += MULAW_BIAS
    exponent = 7
    for exp in range(7, 0, -1):
        if sample >= (1 << (exp + 3)):
            exponent = exp
            break
    mantissa = (sample >> (exponent + 3)) & 0x0F
    return sign | (exponent << 4) | mantissa


def _mulaw_to_linear(mulaw: int) -> int:
    sign = -1 if (mulaw & 0x80) else 1
    exponent = (mulaw >> 4) & 0x07
    mantissa = mulaw & 0x0F
    sample = ((mantissa << 3) + 0x84) << exponent
    return sign * (sample - MULAW_BIAS)


def mulaw_to_pcm16(mulaw_bytes: bytes) -> bytes:
    """Convert mulaw bytes to PCM16 little-endian."""
    out = bytearray(len(mulaw_bytes) * 2)
    for i, b in enumerate(mulaw_bytes):
        linear = _mulaw_to_linear(b)
        struct.pack_into("<h", out, i * 2, linear)
    return bytes(out)


def pcm16_to_mulaw(pcm16_bytes: bytes) -> bytes:
    """Convert PCM16 little-endian bytes to mulaw."""
    if len(pcm16_bytes) % 2 != 0:
        raise ValueError("PCM16 length must be even")
    out = bytearray(len(pcm16_bytes) // 2)
    for i in range(0, len(pcm16_bytes), 2):
        sample = struct.unpack_from("<h", pcm16_bytes, i)[0]
        out[i // 2] = _linear_to_mulaw(sample)
    return bytes(out)


def webm_to_pcm16(webm_bytes: bytes, target_sample_rate: int = 24000) -> bytes:
    """Convert WebM/Opus bytes to PCM16 @ target_sample_rate."""
    audio = AudioSegment.from_file(io.BytesIO(webm_bytes), format="webm")
    audio = audio.set_frame_rate(target_sample_rate).set_channels(1).set_sample_width(2)
    return audio.raw_data


def pcm16_to_wav(pcm16_bytes: bytes, sample_rate: int = 24000) -> bytes:
    """Wrap PCM16 bytes in a WAV container for browser playback."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sample_rate)
        wf.writeframes(pcm16_bytes)
    return buf.getvalue()


def mulaw_to_wav(mulaw_bytes: bytes, sample_rate: int = 24000) -> bytes:
    """Convert mulaw bytes directly to WAV for playback."""
    pcm16 = mulaw_to_pcm16(mulaw_bytes)
    return pcm16_to_wav(pcm16, sample_rate)


def encode_base64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def decode_base64(data: str) -> bytes:
    return base64.b64decode(data)
