from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Literal


class SessionState(StrEnum):
    CONNECTING = "connecting"
    ACTIVE = "active"
    DISCONNECTED = "disconnected"


@dataclass
class TranscriptEntry:
    role: Literal["user", "agent"]
    content: str
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class Session:
    session_id: str
    stream_sid: str | None = None
    transcript: list[TranscriptEntry] = field(default_factory=list)
    state: SessionState = SessionState.CONNECTING
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    def add_user_message(self, content: str) -> None:
        self.transcript.append(TranscriptEntry(role="user", content=content))
        self.updated_at = datetime.now(UTC)

    def add_agent_message(self, content: str) -> None:
        self.transcript.append(TranscriptEntry(role="agent", content=content))
        self.updated_at = datetime.now(UTC)

    def get_transcript_text(self) -> str:
        return "\n".join(f"{entry.role}: {entry.content}" for entry in self.transcript)

    def set_state(self, state: SessionState) -> None:
        self.state = state
        self.updated_at = datetime.now(UTC)
