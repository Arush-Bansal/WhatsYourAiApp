import logging
import time
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

logger = logging.getLogger("app.http")

_SENSITIVE_HEADERS = frozenset(
    {
        "authorization",
        "cookie",
        "x-hub-signature-256",
        "x-api-key",
        "proxy-authorization",
    }
)


def _client_host(request: Request) -> str:
    if request.client:
        return request.client.host
    return "-"


def _path_with_query(request: Request) -> str:
    path = request.url.path
    if request.url.query:
        return f"{path}?{request.url.query}"
    return path


def _safe_headers_for_debug(request: Request) -> str:
    parts: list[str] = []
    for name, value in request.headers.items():
        if name.lower() in _SENSITIVE_HEADERS:
            parts.append(f"{name}=[redacted]")
        else:
            parts.append(f"{name}={value}")
    return "; ".join(parts)


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Log every HTTP request at DEBUG (full line) and INFO (one compact line)."""

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        path_q = _path_with_query(request)
        client = _client_host(request)
        if logger.isEnabledFor(logging.DEBUG):
            logger.debug(
                "request headers (%s %s client=%s): %s",
                request.method,
                path_q,
                client,
                _safe_headers_for_debug(request),
            )
        start = time.perf_counter()
        response = await call_next(request)
        duration_ms = (time.perf_counter() - start) * 1000
        logger.info(
            "%s %s -> %s %.2fms client=%s",
            request.method,
            path_q,
            response.status_code,
            duration_ms,
            client,
        )
        return response
