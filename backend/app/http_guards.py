"""Rate limit and demo-gate checks that run before the route."""

from __future__ import annotations

import json

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.rate_limit import bucket_for
from app.request_context import request_id_var

_OPEN_PATHS = {"/health", "/ready", "/api/health", "/api/ready", "/api/config"}
_CSP = "default-src 'none'; frame-ancestors 'none'; base-uri 'none'"


def _header_map(scope: Scope) -> dict[str, str]:
    found: dict[str, str] = {}
    for key, value in scope.get("headers") or []:
        found[key.decode("latin-1").lower()] = value.decode("latin-1")
    return found


def _request_id(scope: Scope) -> str:
    state = scope.get("state") or {}
    if isinstance(state, dict):
        request_id = state.get("request_id")
        if isinstance(request_id, str) and request_id.strip():
            return request_id
    return ""


def _client_host(scope: Scope) -> str:
    client = scope.get("client")
    if isinstance(client, tuple) and client:
        return str(client[0])
    return "local"


def _token(headers: dict[str, str]) -> str:
    authorization = headers.get("authorization", "")
    if authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    for part in headers.get("cookie", "").split(";"):
        name, separator, value = part.strip().partition("=")
        if separator and name == "untangle_access":
            return value.strip()
    return ""


def _limits(settings: object, bucket: str) -> tuple[int, int]:
    window = int(getattr(settings, "upload_rate_window_seconds"))
    if bucket == "access":
        return int(getattr(settings, "access_rate_limit")), window
    if bucket == "heavy":
        return int(getattr(settings, "heavy_rate_limit")), window
    return int(getattr(settings, "upload_rate_limit")), window


def _locked(settings: object, method: str, path: str) -> bool:
    if not str(getattr(settings, "demo_access_code", "") or ""):
        return False
    if path in _OPEN_PATHS:
        return False
    if method == "POST" and path == "/api/access":
        return False
    return True


async def _json(send: Send, status: int, code: str, message: str, path: str, request_id: str) -> None:
    body = json.dumps(
        {
            "error_code": code,
            "message": message,
            "details": {"path": path},
            "request_id": request_id or "unknown",
        }
    ).encode("utf-8")
    await send(
        {
            "type": "http.response.start",
            "status": status,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(body)).encode("ascii")),
                (b"x-request-id", (request_id or "unknown").encode("utf-8")),
            ],
        }
    )
    await send({"type": "http.response.body", "body": body})


class GuardMiddleware:
    """Count heavy requests, then require a demo token when a code is configured."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope.get("method") == "OPTIONS":
            await self.app(scope, receive, send)
            return
        application = scope["app"]
        settings = application.state.settings
        path = str(scope.get("path") or "")
        method = str(scope.get("method") or "GET")
        request_id = request_id_var.get("") or _request_id(scope)
        bucket = bucket_for(method, path)
        if bucket is not None:
            limit, window = _limits(settings, bucket)
            allowed = application.state.rate_limiter.allow(f"{bucket}:{_client_host(scope)}", limit, window)
            if not allowed:
                await _json(
                    send,
                    429,
                    "RATE_LIMITED",
                    "Too many requests from this process. Wait a minute and try again.",
                    path,
                    request_id,
                )
                return
        if _locked(settings, method, path):
            token = _token(_header_map(scope))
            if not application.state.access_tokens.valid(token):
                await _json(
                    send,
                    401,
                    "ACCESS_REQUIRED",
                    "Enter the demo access code to use this server.",
                    path,
                    request_id,
                )
                return
        await self.app(scope, receive, send)


class SecurityHeadersMiddleware:
    """Add headers that keep API responses from being sniffed or framed."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                if "x-content-type-options" not in headers:
                    headers.append("X-Content-Type-Options", "nosniff")
                if "referrer-policy" not in headers:
                    headers.append("Referrer-Policy", "no-referrer")
                if "x-frame-options" not in headers:
                    headers.append("X-Frame-Options", "DENY")
                if "content-security-policy" not in headers:
                    headers.append("Content-Security-Policy", _CSP)
                if "permissions-policy" not in headers:
                    headers.append("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
            await send(message)

        await self.app(scope, receive, send_with_headers)
