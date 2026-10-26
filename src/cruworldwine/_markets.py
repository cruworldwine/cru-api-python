"""Cru's markets and environments: MarketInfo, MARKETS and lookup_market(), from the generated table."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from types import MappingProxyType
from typing import Literal, Optional
from urllib.parse import urlsplit

from . import _errors
from ._market_table import ENVIRONMENTS
from ._market_table import MARKETS as _ROWS

Environment = Literal['live', 'sandbox']
"""live, Cru's real markets, or sandbox, where no real money or wine changes hands."""

# The domain each environment's hosts share, such as crusandbox.com for {market}.crusandbox.com.
_DOMAINS = frozenset(
    host[len('{market}.') :]
    for host in (urlsplit(template).hostname or '' for template in ENVIRONMENTS.values())
    if host.startswith('{market}.')
)


@dataclass(frozen=True)
class MarketInfo:
    """One of Cru's markets, with the currency every amount on its host is in and its base URLs.

    Attributes:
        code: The market code, as market= takes it, such as uk.
        name: The market's name, such as United Kingdom.
        currency: The ISO 4217 code of the currency every amount on the market's host is in, such as
            GBP.
        symbol: The symbol Cru's website shows for that currency, such as £.
        live_url: The market's base URL in the live environment.
        sandbox_url: The market's base URL in the sandbox.
    """

    code: str
    name: str
    currency: str
    symbol: str
    live_url: str
    sandbox_url: str

    def url(self, environment: str) -> str:
        """The market's base URL in an environment.

        Args:
            environment: live or sandbox, in any case.

        Raises:
            CruError: environment is neither live nor sandbox.
        """
        return self.sandbox_url if environment_name(environment) == 'sandbox' else self.live_url


MARKETS: Mapping[str, MarketInfo] = MappingProxyType({row[0]: MarketInfo(*row) for row in _ROWS})
"""Every market this version of the SDK knows, by code, in the API's order. Read-only."""


def lookup_market(code: str) -> Optional[MarketInfo]:
    """The market with this code, in any case, or None when this version of the SDK does not know it."""
    return MARKETS.get(_lower(code))


def environment_name(value: object) -> str:
    """The environment's name, live or sandbox, from a value in any case; anything else raises CruError."""
    name = _lower(value)
    if name not in ENVIRONMENTS:
        raise _errors.CruError(f'environment must be {" or ".join(ENVIRONMENTS)}, not {value!r}')
    return name


def market_of(base_url: str, market: Optional[str]) -> Optional[MarketInfo]:
    """The market a client with this base URL calls.

    On a Cru host, {code}.cruworldwine.com or {code}.crusandbox.com, it is the host's; elsewhere it
    is the market given, if any. None when that market is not in MARKETS.
    """
    label, _, domain = (urlsplit(base_url).hostname or '').partition('.')
    if domain in _DOMAINS:
        return lookup_market(label)
    return lookup_market(market) if market else None


def _lower(value: object) -> str:
    return value.strip().lower() if isinstance(value, str) else ''
