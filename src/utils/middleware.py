from __future__ import annotations

import time
from typing import Any

from starlette.requests import Request
from starlette.responses import Response

from src.utils.logging import get_logger

logger = get_logger("api.middleware")


async def log_requests(request: Request, call_next: Any) -> Response:
    start = time.perf_counter()
    client_ip = request.client.host if request.client else "unknown"
    method = request.method
    path = request.url.path
    query = str(request.url.query) if request.url.query else ""

    response = await call_next(request)

    elapsed = (time.perf_counter() - start) * 1000
    status = response.status_code
    size = response.headers.get("content-length", "?")

    logger.info(
        "%s %s%s -> %s [%.0fms] [%sB] from %s",
        method,
        path,
        f"?{query}" if query else "",
        status,
        elapsed,
        size,
        client_ip,
    )

    return response
