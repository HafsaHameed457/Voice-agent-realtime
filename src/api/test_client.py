from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import FileResponse

router = APIRouter()


@router.get("/test")
async def test_client() -> FileResponse:
    return FileResponse("static/test-client.html")
