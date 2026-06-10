from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import RedirectResponse

router = APIRouter()

REACT_DIST = str(Path(__file__).resolve().parent.parent.parent / "frontend" / "dist")
DIST_PATH = Path(REACT_DIST)


def is_react_built() -> bool:
    return DIST_PATH.is_dir() and (DIST_PATH / "index.html").is_file()


@router.get("/test")
async def test_root() -> RedirectResponse:
    return RedirectResponse(url="/test/")


if not is_react_built():

    @router.get("/test/")
    async def test_fallback() -> dict[str, str]:
        return {
            "status": "not_built",
            "message": "Run `cd frontend && npm run build` first",
        }
