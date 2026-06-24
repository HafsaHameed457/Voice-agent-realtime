from __future__ import annotations

from fastapi import APIRouter, Request, Response

from src.config import get_settings
from src.services.groq_llm import GroqLLMService
from src.services.groq_stt import GroqSTTService
from src.services.session_manager import get_session_manager
from src.services.tts_service import EdgeTTSService
from src.services.twilio import generate_incoming_call_twiml
from src.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()


@router.get("/")
async def health_check() -> dict[str, str]:
    return {"message": "Twilio Media Stream Server is running!"}


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "healthy"}


@router.get("/ready")
async def ready() -> dict[str, str]:
    settings = get_settings()
    session_manager = get_session_manager()

    try:
        await session_manager.health_check()
    except Exception:
        logger.exception("Session manager health check failed")
        return {"status": "not ready", "reason": "session_manager_unhealthy"}

    try:
        stt = GroqSTTService(settings)
        await stt._client.audio.transcriptions.create(
            file=("test.wav", b"RIFF\x00\x00\x00\x00WAVE"),
            model=settings.groq_stt_model,
            response_format="text",
        )
    except Exception:
        logger.exception("Groq STT health check failed")
        return {"status": "not ready", "reason": "groq_stt_unhealthy"}

    try:
        llm = GroqLLMService(settings)
        stream = await llm._client.chat.completions.create(
            model=settings.groq_llm_model,
            messages=[{"role": "user", "content": "ping"}],
            max_tokens=1,
            stream=False,
        )
        _ = stream.choices[0].message.content
    except Exception:
        logger.exception("Groq LLM health check failed")
        return {"status": "not ready", "reason": "groq_llm_unhealthy"}

    try:
        tts = EdgeTTSService()
        await tts.synthesize("test")
    except Exception:
        logger.exception("TTS health check failed")
        return {"status": "not ready", "reason": "tts_unhealthy"}

    return {"status": "ready"}


@router.api_route("/incoming-call", methods=["GET", "POST"])
async def incoming_call(request: Request) -> Response:
    host = request.headers.get("host", "localhost")
    logger.info("Incoming call from host=%s", host)
    twiml = generate_incoming_call_twiml(host)
    return Response(content=twiml, media_type="text/xml")
