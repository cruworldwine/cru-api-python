from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Optional


class CruError(Exception):
    """Every error this SDK raises."""


class APIConnectionError(CruError):
    """The API could not be reached, or the connection failed before it answered."""


class APITimeoutError(APIConnectionError):
    """The API did not answer in time."""


class APIStatusError(CruError):
    """The API answered with an error.

    Branch on status_code and code; message is for people and may change. errors holds every
    entry the API sent, headers the response's headers, and request_id is what Cru support needs to
    find the request.
    """

    def __init__(
        self,
        status_code: int,
        body: Optional[Mapping[str, Any]],
        headers: Optional[Mapping[str, str]] = None,
    ) -> None:
        self.status_code = status_code
        self.body: dict[str, Any] = dict(body) if isinstance(body, Mapping) else {}
        self.headers: dict[str, str] = {k.lower(): v for k, v in (headers or {}).items()}
        entries = self.body.get('errors')
        entries = entries if isinstance(entries, list) else []
        self.errors: list[dict[str, Any]] = [e for e in entries if isinstance(e, dict)]
        first = self.errors[0] if self.errors else {}
        self.code: Optional[str] = _str(first.get('code'))
        self.field: Optional[str] = _str(first.get('field'))
        details = first.get('details')
        self.details: dict[str, Any] = details if isinstance(details, dict) else {}
        self.message: str = _str(first.get('message')) or _str(self.body.get('message')) or f'HTTP {status_code}'
        meta = self.body.get('meta')
        meta_id = _str(meta.get('request_id')) if isinstance(meta, dict) else None
        self.request_id: Optional[str] = meta_id or self.headers.get('x-request-id')
        super().__init__(' '.join(filter(None, (str(status_code), self.code))) + f': {self.message}')

    def __repr__(self) -> str:
        return (
            f'{type(self).__name__}(status_code={self.status_code}, code={self.code!r}, '
            f'message={self.message!r}, request_id={self.request_id!r})'
        )


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


_BY_STATUS: dict[int, type[APIStatusError]] = {
    400: BadRequestError,
    401: AuthenticationError,
    403: PermissionDeniedError,
    404: NotFoundError,
    405: MethodNotAllowedError,
    409: ConflictError,
    410: GoneError,
    422: UnprocessableEntityError,
    429: RateLimitError,
}
_BY_CODE: dict[str, type[APIStatusError]] = {
    'PRICE_CHANGED': PriceChangedError,
    'REQUEST_IN_PROGRESS': RequestInProgressError,
}


def error_for(status_code: int, body: Optional[Mapping[str, Any]], headers: Mapping[str, str]) -> APIStatusError:
    """The error class for this status and the API's error code."""
    cls = (_BY_CODE.get(error_code(body) or '') if status_code == 409 else None) or _BY_STATUS.get(status_code)
    if cls is None:
        cls = InternalServerError if status_code >= 500 else APIStatusError
    return cls(status_code, body, headers)


def error_code(body: Any) -> Optional[str]:
    """The code of the first error entry in an envelope, if it has one."""
    entries = body.get('errors') if isinstance(body, Mapping) else None
    first = entries[0] if isinstance(entries, list) and entries else None
    return _str(first.get('code')) if isinstance(first, dict) else None


def _str(value: Any) -> Optional[str]:
    return value if isinstance(value, str) and value else None
