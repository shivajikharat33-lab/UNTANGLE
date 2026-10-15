"""Demo access code and the transparency list. Neither response contains a secret."""

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse

from app.access_tokens import codes_match
from app.errors import AppError
from app.services.transparency import transparency_report

router = APIRouter()


@router.post("/api/access")
async def unlock(request: Request) -> JSONResponse:
    """Check the shared demo code and return a process-local token."""
    settings = request.app.state.settings
    if not settings.demo_access_code:
        raise AppError(400, "ACCESS_NOT_REQUIRED", "This server does not require an access code.")
    try:
        body = await request.json()
    except Exception:
        body = None
    provided = body.get("code") if isinstance(body, dict) else ""
    if not isinstance(provided, str):
        provided = ""
    if not codes_match(provided, settings.demo_access_code):
        raise AppError(401, "ACCESS_DENIED", "The access code was not accepted.")
    token = request.app.state.access_tokens.issue(settings.access_token_ttl_seconds)
    cookie = (
        f"untangle_access={token}; HttpOnly; Path=/; SameSite=Lax; "
        f"Max-Age={settings.access_token_ttl_seconds}"
    )
    if request.url.scheme == "https":
        cookie += "; Secure"
    return JSONResponse(content={"ok": True, "token": token}, headers={"Set-Cookie": cookie})


@router.get("/api/transparency")
def transparency(request: Request) -> dict:
    """Libraries and switches actually configured on this process."""
    return transparency_report(request.app.state.settings)
