"""Stable errors shared by services without depending on transport frameworks."""


class DomainError(Exception):
    code = "DOMAIN_ERROR"
    status = 400
    retryable = False

    def __init__(self, detail: str, *, fields: dict[str, str] | None = None) -> None:
        super().__init__(detail)
        self.detail = detail
        self.fields = fields or {}


class ValidationError(DomainError):
    code = "VALIDATION_ERROR"
    status = 422


class NotFoundError(DomainError):
    code = "NOT_FOUND"
    status = 404


class ConflictError(DomainError):
    code = "CONFLICT"
    status = 409


class ForbiddenError(DomainError):
    code = "FORBIDDEN"
    status = 403


class AuthenticationError(DomainError):
    code = "AUTHENTICATION_REQUIRED"
    status = 401
