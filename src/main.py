from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import router as http_router
from src.api.websocket import router as ws_router
from src.config import get_settings
from src.utils.logging import get_logger, setup_logging

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

settings = get_settings()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, Any]:
    setup_logging()
    logger.info("Starting Voice Agent Realtime server")
    logger.info("Voice=%s | Temperature=%s", settings.voice, settings.temperature)
    yield
    logger.info("Shutting down Voice Agent Realtime server")


app = FastAPI(
    title="Voice Agent Realtime",
    description="Real-time voice agent using OpenAI Realtime API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(http_router)
app.include_router(ws_router)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "src.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
        log_level=settings.log_level.lower(),
    )
