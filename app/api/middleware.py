from __future__ import annotations

import time

from fastapi import FastAPI, Request
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import Response

from app.core.logger import JarvisLogger


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(
        self,
        request: Request,
        call_next: RequestResponseEndpoint,
    ) -> Response:
        start = time.monotonic()
        response = await call_next(request)
        duration = time.monotonic() - start
        JarvisLogger.info(
            "%s %s -> %s (%.3fs)",
            request.method, request.url.path,
            response.status_code, duration,
        )
        return response


def register_middleware(app: FastAPI) -> None:
    app.add_middleware(RequestLoggingMiddleware)
