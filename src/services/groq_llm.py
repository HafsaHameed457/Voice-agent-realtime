from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

from groq import AsyncGroq

from src.utils.logging import get_logger

if TYPE_CHECKING:
    from src.config import Settings

logger = get_logger(__name__)


class GroqLLMService:
    def __init__(self, settings: Settings) -> None:
        self._client = AsyncGroq(api_key=settings.groq_api_key)
        self._model = settings.groq_llm_model
        self._temperature = settings.temperature
        self._system_message = settings.system_message

    async def generate(
        self,
        messages: list[dict[str, str]],
    ) -> AsyncGenerator[str, None]:
        full_messages = [{"role": "system", "content": self._system_message}, *messages]
        try:
            stream = await self._client.chat.completions.create(
                model=self._model,
                messages=full_messages,  # type: ignore[arg-type]
                temperature=self._temperature,
                stream=True,
            )
            async for chunk in stream:  # type: ignore[union-attr]
                content = chunk.choices[0].delta.content or ""
                if content:
                    yield content
        except Exception:
            logger.exception("Groq LLM request failed")
