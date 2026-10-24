from __future__ import annotations

DEFAULT_TIMEOUT = 30.0
"""Seconds to wait for the API, unless a client, a with_options() copy or a call sets its own."""

DEFAULT_MAX_RETRIES = 2
"""Retries after the first attempt, for reads and partner writes."""

INITIAL_RETRY_DELAY = 0.5
MAX_BACKOFF = 8.0
MAX_RETRY_DELAY = 30.0
"""No wait between attempts is longer than this, whatever Retry-After asks for."""

RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
