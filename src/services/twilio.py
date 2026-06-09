from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from src.utils.logging import get_logger

logger = get_logger(__name__)

TwilioEventType = Literal["start", "media", "stop", "mark"]


@dataclass
class TwilioEvent:
    event_type: TwilioEventType
    stream_sid: str | None = None
    audio_payload: str | None = None
    sequence_number: str | None = None
    call_sid: str | None = None


def generate_incoming_call_twiml(
    host: str,
    greeting: str = "Hi, you have called Bart's Automotive Centre. How can we help?",
    websocket_path: str = "/media-stream",
) -> str:
    """Generate TwiML response for incoming call webhook."""
    logger.info("Generating TwiML for host=%s", host)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
    <Say>{greeting}</Say>
    <Connect>
        <Stream url="wss://{host}{websocket_path}" />
    </Connect>
</Response>"""


def parse_twilio_event(data: dict[str, object]) -> TwilioEvent:
    """Parse a Twilio WebSocket event into a structured TwilioEvent."""
    event_type = data.get("event", "")
    if event_type not in ("start", "media", "stop", "mark"):
        logger.debug("Ignoring unknown event type: %s", event_type)
        return TwilioEvent(event_type="stop")

    if event_type == "start":
        start_info = data.get("start", {})
        if isinstance(start_info, dict):
            stream_sid = str(start_info.get("streamSid", ""))
            call_sid = str(start_info.get("callSid", ""))
            logger.info(
                "Stream started: stream_sid=%s call_sid=%s",
                stream_sid,
                call_sid,
            )
            return TwilioEvent(
                event_type="start",
                stream_sid=stream_sid,
                call_sid=call_sid,
            )

    if event_type == "media":
        media = data.get("media", {})
        if isinstance(media, dict):
            return TwilioEvent(
                event_type="media",
                audio_payload=str(media.get("payload", "")),
                sequence_number=str(data.get("sequenceNumber", "")),
            )

    if event_type == "mark":
        mark_info = data.get("mark", {})
        if isinstance(mark_info, dict):
            name = str(mark_info.get("name", ""))
            logger.debug("Mark event: name=%s", name)
        return TwilioEvent(event_type="mark")

    logger.debug("Unhandled event: %s", event_type)
    return TwilioEvent(event_type="stop")
