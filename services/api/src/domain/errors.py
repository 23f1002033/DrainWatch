class DomainError(Exception):
    status_code = 400
    code = "BAD_REQUEST"

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class NotFound(DomainError):
    status_code = 404
    code = "NOT_FOUND"


class Forbidden(DomainError):
    status_code = 403
    code = "FORBIDDEN"


class Unauthorized(DomainError):
    status_code = 401
    code = "UNAUTHORIZED"


class IllegalTransition(DomainError):
    status_code = 409
    code = "ILLEGAL_TRANSITION"


class VersionConflict(DomainError):
    status_code = 409
    code = "VERSION_CONFLICT"


class IdempotencyKeyReused(DomainError):
    status_code = 409
    code = "IDEMPOTENCY_KEY_REUSED"


class Invalid(DomainError):
    status_code = 422
    code = "VALIDATION_ERROR"


class BadRequest(DomainError):
    status_code = 400
    code = "BAD_REQUEST"
