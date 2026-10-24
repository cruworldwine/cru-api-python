from __future__ import annotations

from typing import Any, Dict, List, Optional


class CruError(Exception):
    """Every error this SDK raises."""


class APIConnectionError(CruError):
    """The API could not be reached, or the connection failed before it answered."""


class APITimeoutError(APIConnectionError):
    """The API did not answer in time."""


class APIStatusError(CruError):
    """The API answered with an error.

    Branch on status_code and code; message is for people and may change. errors holds every
    entry the API sent, and request_id is what Cru support needs to find the request.
    """

    def __init__(self, status_code: int, body: Optional[Dict[str, Any]], headers: Dict[str, str]) -> None:
        self.status_code = status_code
        self.body = body or {}
        self.errors: List[Dict[str, Any]] = list(self.body.get('errors') or [])
        first = self.errors[0] if self.errors else {}
        self.code: Optional[str] = first.get('code')
        self.field: Optional[str] = first.get('field')
        self.details: Dict[str, Any] = first.get('details') or {}
        self.message: str = first.get('message') or self.body.get('message') or f'HTTP {status_code}'
        self.request_id: Optional[str] = (self.body.get('meta') or {}).get('request_id') or headers.get('x-request-id')
        super().__init__(f'{status_code} {self.code or ""}: {self.message}'.replace('  ', ' '))


class BadRequestError(APIStatusError):
    """400: VALIDATION_UNKNOWN_PARAMETER or VALIDATION_MALFORMED_BODY."""


class AuthenticationError(APIStatusError):
    """401: the credentials are missing or wrong, or the access token has expired."""


class PermissionDeniedError(APIStatusError):
    """403: a scope, store, address or account check refused the call."""


class NotFoundError(APIStatusError):
    """404."""


class MethodNotAllowedError(APIStatusError):
    """405."""


class ConflictError(APIStatusError):
    """409."""


class PriceChangedError(ConflictError):
    """409 PRICE_CHANGED: the price moved since the preview. Preview it again."""


class RequestInProgressError(ConflictError):
    """409 REQUEST_IN_PROGRESS: an earlier request with this reference is still running."""


class GoneError(APIStatusError):
    """410: the confirmation code has expired or was cancelled."""


class UnprocessableEntityError(APIStatusError):
    """422: a value was refused (VALIDATION_*), or Cru could not carry it out (TRADE_REFUSED)."""


class RateLimitError(APIStatusError):
    """429."""


class InternalServerError(APIStatusError):
    """5xx."""


_BY_STATUS = {
    400: BadRequestError, 401: AuthenticationError, 403: PermissionDeniedError, 404: NotFoundError,
    405: MethodNotAllowedError, 409: ConflictError, 410: GoneError, 422: UnprocessableEntityError,
    429: RateLimitError,
}
_BY_CODE = {'PRICE_CHANGED': PriceChangedError, 'REQUEST_IN_PROGRESS': RequestInProgressError}


def error_for(status_code: int, body: Optional[Dict[str, Any]], headers: Dict[str, str]) -> APIStatusError:
    errors = (body or {}).get('errors') or [{}]
    cls = (_BY_CODE.get(errors[0].get('code', '')) if status_code == 409 else None) or _BY_STATUS.get(status_code)
    if cls is None:
        cls = InternalServerError if status_code >= 500 else APIStatusError
    return cls(status_code, body, headers)
