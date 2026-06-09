from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    openai_api_key: str = Field(..., validation_alias="OPENAI_API_KEY")

    port: int = Field(default=5050, validation_alias="PORT")
    host: str = Field(default="0.0.0.0", validation_alias="HOST")

    voice: str = Field(default="alloy", validation_alias="VOICE")
    system_message: str = Field(
        default="You are a cheerful and bubbly customer support agent who deals with customers efficiently and says haha now and then please.",
        validation_alias="SYSTEM_MESSAGE",
    )
    temperature: float = Field(default=0.8, validation_alias="TEMPERATURE")
    turn_detection_type: str = Field(default="server_vad", validation_alias="TURN_DETECTION_TYPE")
    input_audio_format: str = Field(default="g711_ulaw", validation_alias="INPUT_AUDIO_FORMAT")
    output_audio_format: str = Field(default="g711_ulaw", validation_alias="OUTPUT_AUDIO_FORMAT")
    input_audio_transcription_model: str = Field(default="whisper-1", validation_alias="INPUT_AUDIO_TRANSCRIPTION_MODEL")

    log_level: str = Field(default="INFO", validation_alias="LOG_LEVEL")
    log_format: str = Field(default="json", validation_alias="LOG_FORMAT")

    webhook_url: str | None = Field(default=None, validation_alias="WEBHOOK_URL")

    @property
    def openai_ws_url(self) -> str:
        return "wss://api.openai.com/v1/realtime?model=gpt-realtime"


@lru_cache
def get_settings() -> Settings:
    return Settings()