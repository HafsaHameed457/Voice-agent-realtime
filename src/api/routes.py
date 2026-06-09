from __future__ import annotations

from fastapi import APIRouter, Request, Response

from src.services.twilio import generate_incoming_call_twiml
from src.utils.logging import get_logger

logger = get_logger(__name__)

router = APIRouter()


@router.get("/")
async def health_check() -> dict[str, str]:
    return {"message": "Twilio Media Stream Server is running!"}


@router.api_route("/incoming-call", methods=["GET", "POST"])
async def incoming_call(request: Request) -> Response:
    host = request.headers.get("host", "localhost")
    logger.info("Incoming call from host=%s", host)
    twiml = generate_incoming_call_twiml(host)
    return Response(content=twiml, media_type="text/xml")
