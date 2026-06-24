from __future__ import annotations

import base64
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio


class MockHandlers:
    def __init__(self) -> None:
        self.audio_deltas: list[str] = []
        self.user_transcripts: list[str] = []
        self.agent_transcripts: list[str] = []
        self.errors: list[Exception] = []
        self.session_ready = False

    async def on_audio_delta(self, audio_base64: str, _stream_sid: str) -> None:
        self.audio_deltas.append(audio_base64)

    async def on_user_transcript(self, transcript: str) -> None:
        self.user_transcripts.append(transcript)

    async def on_agent_transcript(self, transcript: str) -> None:
        self.agent_transcripts.append(transcript)

    async def on_error(self, error: Exception) -> None:
        self.errors.append(error)

    async def on_session_ready(self) -> None:
        self.session_ready = True


@pytest_asyncio.fixture
async def mock_handlers() -> MockHandlers:
    return MockHandlers()


@pytest.fixture
def mock_settings():
    from src.config import Settings

    return Settings(
        groq_api_key="test-key",
        groq_llm_model="llama-3.1-70b-versatile",
        groq_stt_model="whisper-large-v3-turbo",
        system_message="Test system",
        temperature=0.8,
    )


class TestPipelineOrchestrator:
    @pytest.mark.asyncio
    async def test_connect_disconnect(self, mock_settings, mock_handlers):
        from src.services.pipeline_service import PipelineOrchestrator

        pipeline = PipelineOrchestrator(settings=mock_settings, handlers=mock_handlers)
        assert not pipeline.is_connected

        await pipeline.connect()
        assert pipeline.is_connected
        assert mock_handlers.session_ready

        await pipeline.disconnect()
        assert not pipeline.is_connected

    @pytest.mark.asyncio
    async def test_send_text(self, mock_settings, mock_handlers):
        from src.services.pipeline_service import PipelineOrchestrator

        pipeline = PipelineOrchestrator(settings=mock_settings, handlers=mock_handlers)
        await pipeline.connect()

        with patch.object(pipeline._llm, "generate") as mock_generate:
            async def mock_gen(*args, **kwargs):
                yield "Hello "
                yield "world!"

            mock_generate.side_effect = mock_gen

            with patch.object(pipeline._tts, "synthesize", return_value=b"fake-audio-data") as mock_tts:
                await pipeline.send_text("Test message")

                assert len(mock_handlers.user_transcripts) == 1
                assert mock_handlers.user_transcripts[0] == "Test message"

                assert len(mock_handlers.agent_transcripts) == 1
                assert mock_handlers.agent_transcripts[0] == "Hello world!"

                assert len(mock_handlers.audio_deltas) == 1
                audio_b64 = mock_handlers.audio_deltas[0]
                audio_data = base64.b64decode(audio_b64)
                assert audio_data == b"fake-audio-data"

        await pipeline.disconnect()

    @pytest.mark.asyncio
    async def test_send_audio_flush(self, mock_settings, mock_handlers):
        from src.services.pipeline_service import PipelineOrchestrator

        pipeline = PipelineOrchestrator(settings=mock_settings, handlers=mock_handlers)
        await pipeline.connect()

        pcm16_data = b"\x00\x01" * 12000
        await pipeline.send_audio(pcm16_data)

        with patch.object(pipeline._stt, "transcribe", return_value="Audio transcript") as mock_stt:
            with patch.object(pipeline._llm, "generate") as mock_generate:
                async def mock_gen(*args, **kwargs):
                    yield "Response to audio"

                mock_generate.side_effect = mock_gen

                with patch.object(pipeline._tts, "synthesize", return_value=b"audio-response") as mock_tts:
                    await pipeline._flush()

                    mock_stt.assert_called_once()
                    assert len(mock_handlers.user_transcripts) == 1
                    assert mock_handlers.user_transcripts[0] == "Audio transcript"
                    assert len(mock_handlers.agent_transcripts) == 1
                    assert mock_handlers.agent_transcripts[0] == "Response to audio"

        await pipeline.disconnect()

    @pytest.mark.asyncio
    async def test_send_audio_below_min_duration(self, mock_settings, mock_handlers):
        from src.services.pipeline_service import PipelineOrchestrator

        pipeline = PipelineOrchestrator(settings=mock_settings, handlers=mock_handlers)
        await pipeline.connect()

        short_audio = b"\x00\x01" * 100
        await pipeline.send_audio(short_audio)

        with patch.object(pipeline._stt, "transcribe") as mock_stt:
            await pipeline._delayed_flush()
            mock_stt.assert_not_called()

        await pipeline.disconnect()

    @pytest.mark.asyncio
    async def test_error_handling(self, mock_settings, mock_handlers):
        from src.services.pipeline_service import PipelineOrchestrator

        pipeline = PipelineOrchestrator(settings=mock_settings, handlers=mock_handlers)
        await pipeline.connect()

        # Add audio to buffer first
        pipeline._audio_buffer.extend(b"\x00\x01" * 12000)

        with patch.object(pipeline._stt, "transcribe", side_effect=RuntimeError("STT failed")):
            await pipeline._flush()

        assert len(mock_handlers.errors) == 1
        assert isinstance(mock_handlers.errors[0], RuntimeError)
        assert "Pipeline processing failed" in str(mock_handlers.errors[0])

        await pipeline.disconnect()


class TestGroqSTTService:
    @pytest.mark.asyncio
    async def test_transcribe(self, mock_settings):
        from src.services.groq_stt import GroqSTTService

        service = GroqSTTService(mock_settings)
        with patch.object(service._client.audio.transcriptions, "create", new_callable=AsyncMock) as mock_create:
            mock_create.return_value = "Transcribed text"
            result = await service.transcribe(b"fake-audio", 24000)
            assert result == "Transcribed text"

    @pytest.mark.asyncio
    async def test_transcribe_error(self, mock_settings):
        from src.services.groq_stt import GroqSTTService

        service = GroqSTTService(mock_settings)
        with patch.object(service._client.audio.transcriptions, "create", new_callable=AsyncMock) as mock_create:
            mock_create.side_effect = Exception("API error")
            result = await service.transcribe(b"fake-audio", 24000)
            assert result == ""


class TestGroqLLMService:
    @pytest.mark.asyncio
    async def test_generate(self, mock_settings):
        from src.services.groq_llm import GroqLLMService

        service = GroqLLMService(mock_settings)

        class MockChunk:
            def __init__(self, content: str):
                self.choices = [MagicMock(delta=MagicMock(content=content))]

        async def mock_stream(*args, **kwargs):
            for chunk in [MockChunk("Hello"), MockChunk(" "), MockChunk("world")]:
                yield chunk

        with patch.object(service._client.chat.completions, "create", return_value=mock_stream()):
            result = []
            async for chunk in service.generate([{"role": "user", "content": "test"}]):
                result.append(chunk)
            assert "".join(result) == "Hello world"

    @pytest.mark.asyncio
    async def test_generate_error(self, mock_settings):
        from src.services.groq_llm import GroqLLMService

        service = GroqLLMService(mock_settings)
        with patch.object(service._client.chat.completions, "create", side_effect=Exception("API error")):
            result = []
            async for chunk in service.generate([{"role": "user", "content": "test"}]):
                result.append(chunk)
            assert result == []


class TestEdgeTTSService:
    @pytest.mark.asyncio
    async def test_synthesize(self):
        from src.services.tts_service import EdgeTTSService

        service = EdgeTTSService()
        with patch("edge_tts.Communicate") as mock_communicate:
            mock_stream = AsyncMock()
            mock_stream.__aiter__.return_value = [
                {"type": "audio", "data": b"mp3-data"},
                {"type": "word", "data": "test"},
            ]
            mock_communicate.return_value.stream.return_value = mock_stream

            with patch("pydub.AudioSegment.from_mp3") as mock_from_mp3:
                mock_audio = MagicMock()
                mock_audio.set_frame_rate.return_value.set_channels.return_value.set_sample_width.return_value.raw_data = b"pcm16-data"
                mock_from_mp3.return_value = mock_audio

                result = await service.synthesize("Test text")
                assert result == b"pcm16-data"
