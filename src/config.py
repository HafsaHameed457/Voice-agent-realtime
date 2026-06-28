from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    groq_api_key: str = Field(..., validation_alias="GROQ_API_KEY")
    groq_llm_model: str = Field(
        default="llama-3.3-70b-versatile",
        validation_alias="GROQ_LLM_MODEL",
    )
    groq_stt_model: str = Field(
        default="whisper-large-v3-turbo",
        validation_alias="GROQ_STT_MODEL",
    )

    port: int = Field(default=5050, validation_alias="PORT")
    host: str = Field(default="0.0.0.0", validation_alias="HOST")

    system_message: str = Field(
        default=(
            "You are a cheerful and bubbly customer support agent who deals "
            "with customers efficiently and says haha now and then please."
        ),
        validation_alias="SYSTEM_MESSAGE",
    )
    temperature: float = Field(default=0.8, validation_alias="TEMPERATURE")

    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    log_format: str = Field(default="json", validation_alias="LOG_FORMAT")

    webhook_url: str | None = Field(default=None, validation_alias="WEBHOOK_URL")

    redis_url: str | None = Field(default=None, validation_alias="REDIS_URL")
    redis_key_prefix: str = Field(default="voice_agent", validation_alias="REDIS_KEY_PREFIX")


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
