"""Raised when a request is understood and refused."""


class AppError(Exception):
    """A failure with a stable error code and a plain-English message."""

    def __init__(
        self,
        status_code: int,
        error_code: str,
        message: str,
        details: dict | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code
        self.message = message
        self.details = details
