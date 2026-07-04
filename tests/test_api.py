from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient

from src.main import app as fastapi_app


@pytest.fixture
def client() -> TestClient:
    return TestClient(fastapi_app)


@pytest.fixture
async def async_client() -> AsyncClient:
    transport = ASGITransport(app=fastapi_app)
    return AsyncClient(transport=transport, base_url="http://test")


class TestHealthEndpoints:
    def test_root(self, client: TestClient) -> None:
        response = client.get("/")
        assert response.status_code == 200
        assert response.json() == {"message": "Twilio Media Stream Server is running!"}

    def test_health(self, client: TestClient) -> None:
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json() == {"status": "healthy"}

    @pytest.mark.asyncio
    async def test_ready_with_mocks(self, async_client: AsyncClient) -> None:
        with patch("src.api.routes.get_session_manager") as mock_get_manager:
            mock_manager = AsyncMock()
            mock_manager.health_check = AsyncMock()
            mock_get_manager.return_value = mock_manager

            with patch("src.api.routes.GroqSTTService") as mock_stt_class:
                mock_stt = AsyncMock()
                mock_stt._client.audio.transcriptions.create = AsyncMock(return_value="test")
                mock_stt_class.return_value = mock_stt

                with patch("src.api.routes.GroqLLMService") as mock_llm_class:
                    mock_llm = AsyncMock()
                    mock_response = AsyncMock()
                    mock_response.choices = [AsyncMock(message=AsyncMock(content="pong"))]
                    mock_llm._client.chat.completions.create = AsyncMock(return_value=mock_response)
                    mock_llm_class.return_value = mock_llm

                    with patch("src.api.routes.EdgeTTSService") as mock_tts_class:
                        mock_tts = AsyncMock()
                        mock_tts.synthesize = AsyncMock(return_value=b"audio")
                        mock_tts_class.return_value = mock_tts

                        response = await async_client.get("/ready")
                        assert response.status_code == 200
                        data = response.json()
                        assert data["status"] == "ready"

    @pytest.mark.asyncio
    async def test_ready_session_manager_failure(self, async_client: AsyncClient) -> None:
        with patch("src.api.routes.get_session_manager") as mock_get_manager:
            mock_manager = AsyncMock()
            mock_manager.health_check = AsyncMock(side_effect=Exception("Redis down"))
            mock_get_manager.return_value = mock_manager

            with patch("src.api.routes.GroqSTTService"):
                response = await async_client.get("/ready")
                assert response.status_code == 200
                data = response.json()
                assert data["status"] == "not ready"
                assert data["reason"] == "session_manager_unhealthy"


class TestIncomingCall:
    def test_incoming_call_get(self, client: TestClient) -> None:
        response = client.get("/incoming-call")
        assert response.status_code == 200
        assert "text/xml" in response.headers["content-type"]
        assert "Twilio Media Stream Server" not in response.text
        assert "<Response>" in response.text
        assert "<Connect>" in response.text
        assert "<Stream" in response.text

    def test_incoming_call_post(self, client: TestClient) -> None:
        response = client.post("/incoming-call")
        assert response.status_code == 200
        assert "text/xml" in response.headers["content-type"]
        assert "<Response>" in response.text

    def test_incoming_call_host_header(self, client: TestClient) -> None:
        response = client.get("/incoming-call", headers={"host": "example.com"})
        assert response.status_code == 200
        assert "wss://example.com" in response.text
