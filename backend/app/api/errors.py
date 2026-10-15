"""Turn every failure into the shared ErrorResponse body."""

import logging
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from app.errors import AppError
from app.schemas.errors import ErrorResponse

logger = logging.getLogger("untangle.api")


def get_request_id(request: Request) -> str:
    """Use the middleware id, or make one if this request never reached it."""
    request_id = getattr(request.state, "request_id", None)
    if isinstance(request_id, str) and request_id.strip():
        return request_id
    return str(uuid4())


def error_response(
    request: Request,
    *,
    status_code: int,
    error_code: str,
    message: str,
    details: dict | None = None,
) -> JSONResponse:
    """Build the only error body the API returns."""
    request_id = get_request_id(request)
    payload = ErrorResponse(
        error_code=error_code,
        message=message,
        details=details,
        request_id=request_id,
    )
    return JSONResponse(
        status_code=status_code,
        content=payload.model_dump(mode="json"),
        headers={"X-Request-ID": request_id},
    )


def register_exception_handlers(application: FastAPI) -> None:
    """Replace FastAPI's default error JSON with the shared schema."""

    # Starlette raises its own HTTPException for a missing route. FastAPI's
    # HTTPException is a subclass, so registering the base class covers both.
    @application.exception_handler(AppError)
    async def handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        details = {"path": request.url.path}
        if exc.details:
            details.update(exc.details)
        return error_response(
            request,
            status_code=exc.status_code,
            error_code=exc.error_code,
            message=exc.message,
            details=details,
        )

    @application.exception_handler(HTTPException)
    async def handle_http_exception(request: Request, exc: HTTPException) -> JSONResponse:
        details = {"path": request.url.path}
        if (
            isinstance(exc.detail, dict)
            and isinstance(exc.detail.get("error_code"), str)
            and isinstance(exc.detail.get("message"), str)
        ):
            error_code = exc.detail["error_code"]
            message = exc.detail["message"]
            extra = exc.detail.get("details")
            if isinstance(extra, dict):
                details.update(extra)
        elif exc.status_code == 404:
            error_code = "NOT_FOUND"
            message = (
                "No route matches this request."
                if exc.detail in (None, "Not Found")
                else str(exc.detail)
            )
        elif exc.status_code == 405:
            error_code = "METHOD_NOT_ALLOWED"
            message = "That method is not allowed on this route."
        else:
            error_code = "HTTP_ERROR"
            message = str(exc.detail) if exc.detail else "The request failed."
            if exc.detail not in (None, ""):
                details["detail"] = jsonable_encoder(exc.detail)
        return error_response(
            request,
            status_code=exc.status_code,
            error_code=error_code,
            message=message,
            details=details,
        )

    @application.exception_handler(RequestValidationError)
    async def handle_validation_error(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        return error_response(
            request,
            status_code=422,
            error_code="VALIDATION_ERROR",
            message="The request failed validation.",
            details={"errors": jsonable_encoder(exc.errors())},
        )

    @application.exception_handler(Exception)
    async def handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("unhandled error", exc_info=exc)
        return error_response(
            request,
            status_code=500,
            error_code="INTERNAL_ERROR",
            message="The server hit an unexpected error.",
            details=None,
        )
