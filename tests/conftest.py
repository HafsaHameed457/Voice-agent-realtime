from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncGenerator
from typing import TYPE_CHECKING

import pytest
import pytest_asyncio

if TYPE_CHECKING:
    from src.services.base_session_manager import BaseSessionManager

pytest_plugins = ("pytest_asyncio",)


def pytest_configure(config: pytest.Config) -> None:
    os.environ.setdefault("GROQ_API_KEY", "test-key")
    os.environ.setdefault("GROQ_LLM_MODEL", "llama-3.1-70b-versatile")
    os.environ.setdefault("GROQ_STT_MODEL", "whisper-large-v3-turbo")
    os.environ.setdefault("SYSTEM_MESSAGE", "Test system message")
    os.environ.setdefault("TEMPERATURE", "0.8")
    os.environ.setdefault("LOG_LEVEL", "DEBUG")
    os.environ.setdefault("LOG_FORMAT", "json")


@pytest.fixture(scope="session")
def event_loop() -> asyncio.AbstractEventLoop:
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest_asyncio.fixture
async def session_manager() -> AsyncGenerator[BaseSessionManager, None]:
    from src.services.session_manager import SessionManager

    manager = SessionManager()
    yield manager
    for session_id in await manager.list_sessions():
        await manager.delete_session(session_id)
