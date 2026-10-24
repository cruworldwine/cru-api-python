"""The Cru Trading API: Cru's bid and offer books, your bids, offers, portfolio and trades."""

from . import models
from ._client import AsyncCru, Cru
from ._constants import DEFAULT_MAX_RETRIES, DEFAULT_TIMEOUT
from ._errors import (
    APIConnectionError,
    APIStatusError,
    APITimeoutError,
    AuthenticationError,
    BadRequestError,
    ConflictError,
    CruError,
    GoneError,
    InternalServerError,
    MethodNotAllowedError,
    NotFoundError,
    PermissionDeniedError,
    PriceChangedError,
    RateLimitError,
    RequestInProgressError,
    UnprocessableEntityError,
)
from ._logs import setup_logging as _setup_logging
from ._models import Model
from ._types import AsyncPage, Page, Response, Write
from ._version import VERSION

__version__ = VERSION
__all__ = [
    'DEFAULT_MAX_RETRIES',
    'DEFAULT_TIMEOUT',
    'VERSION',
    'APIConnectionError',
    'APIStatusError',
    'APITimeoutError',
    'AsyncCru',
    'AsyncPage',
    'AuthenticationError',
    'BadRequestError',
    'ConflictError',
    'Cru',
    'CruError',
    'GoneError',
    'InternalServerError',
    'MethodNotAllowedError',
    'Model',
    'NotFoundError',
    'Page',
    'PermissionDeniedError',
    'PriceChangedError',
    'RateLimitError',
    'RequestInProgressError',
    'Response',
    'UnprocessableEntityError',
    'Write',
    '__version__',
    'models',
]

_setup_logging()
