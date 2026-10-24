from __future__ import annotations

from collections.abc import Awaitable
from typing import Any, Callable, Optional, Union

import httpx

from ._base_client import AppInfo, Timeout
from ._constants import DEFAULT_MAX_RETRIES
from .resources import AsyncResources, Resources


class Cru(Resources):
    """A client for the Cru Trading API.

    Authenticate with a partner credential (client_key and client_secret), whose writes run at once,
    or as a connected app with an OAuth access token, whose writes are staged for the customer to
    confirm. Give refresh_token and oauth_client_id as well and an expired access token is
    refreshed once, automatically; on_token_refresh is then called with the new tokens, which must
    be stored, since a refresh token works once. Refreshes are serialised, so threads sharing a
    client never spend the same refresh token twice.

    The environment supplies what is not given: CRU_CLIENT_KEY, CRU_CLIENT_SECRET, CRU_ACCESS_TOKEN,
    CRU_MARKET and CRU_BASE_URL.

    Args:
        client_key: A partner credential's key, cru_live_... or cru_test_...
        client_secret: A partner credential's secret.
        access_token: A connected app's OAuth access token.
        refresh_token: The refresh token that came with access_token.
        oauth_client_id: Your app's OAuth client id, needed to refresh.
        oauth_client_secret: Your app's OAuth client secret, for a confidential client.
        on_token_refresh: Called with the token response after each refresh. Store its tokens.
        market: The market to call: uk (the default), us, hk, sg, eu, ae or cn.
        base_url: The API's base URL, in place of the market's.
        timeout: Seconds, or an httpx.Timeout. Default 30 seconds, or http_client's own timeout
            when it was given one.
        max_retries: Retries after the first attempt, for reads and partner writes. Default 2.
        http_client: An httpx.Client to send requests with, for proxies, certificates or limits.
            The SDK never follows redirects, whatever the client is set to do.
        app_info: (name, version, url) of your application, added to the User-Agent header so Cru
            can tell integrations apart. version and url may be None.
    """

    def __init__(
        self,
        *,
        client_key: Optional[str] = None,
        client_secret: Optional[str] = None,
        access_token: Optional[str] = None,
        refresh_token: Optional[str] = None,
        oauth_client_id: Optional[str] = None,
        oauth_client_secret: Optional[str] = None,
        on_token_refresh: Optional[Callable[[dict[str, Any]], None]] = None,
        market: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: Optional[Timeout] = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        http_client: Optional[httpx.Client] = None,
        app_info: Optional[AppInfo] = None,
    ) -> None:
        super().__init__(
            client_key=client_key,
            client_secret=client_secret,
            access_token=access_token,
            refresh_token=refresh_token,
            oauth_client_id=oauth_client_id,
            oauth_client_secret=oauth_client_secret,
            on_token_refresh=on_token_refresh,
            market=market,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
            http_client=http_client,
            app_info=app_info,
        )
        self._attach()


class AsyncCru(AsyncResources):
    """An asyncio client for the Cru Trading API.

    The same as Cru, with every method a coroutine: await it. Lists return an AsyncPage, which
    async for walks page by page. Use it as an async context manager, or call aclose() when done.
    One refresh runs at a time, so concurrent tasks never spend the same refresh token twice.

    Args:
        client_key: A partner credential's key, cru_live_... or cru_test_...
        client_secret: A partner credential's secret.
        access_token: A connected app's OAuth access token.
        refresh_token: The refresh token that came with access_token.
        oauth_client_id: Your app's OAuth client id, needed to refresh.
        oauth_client_secret: Your app's OAuth client secret, for a confidential client.
        on_token_refresh: Called with the token response after each refresh; it may be a
            coroutine function. Store its tokens.
        market: The market to call: uk (the default), us, hk, sg, eu, ae or cn.
        base_url: The API's base URL, in place of the market's.
        timeout: Seconds, or an httpx.Timeout. Default 30 seconds, or http_client's own timeout
            when it was given one.
        max_retries: Retries after the first attempt, for reads and partner writes. Default 2.
        http_client: An httpx.AsyncClient to send requests with, for proxies, certificates or
            limits. The SDK never follows redirects, whatever the client is set to do.
        app_info: (name, version, url) of your application, added to the User-Agent header so Cru
            can tell integrations apart. version and url may be None.
    """

    def __init__(
        self,
        *,
        client_key: Optional[str] = None,
        client_secret: Optional[str] = None,
        access_token: Optional[str] = None,
        refresh_token: Optional[str] = None,
        oauth_client_id: Optional[str] = None,
        oauth_client_secret: Optional[str] = None,
        on_token_refresh: Optional[Callable[[dict[str, Any]], Union[Awaitable[None], None]]] = None,
        market: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: Optional[Timeout] = None,
        max_retries: int = DEFAULT_MAX_RETRIES,
        http_client: Optional[httpx.AsyncClient] = None,
        app_info: Optional[AppInfo] = None,
    ) -> None:
        super().__init__(
            client_key=client_key,
            client_secret=client_secret,
            access_token=access_token,
            refresh_token=refresh_token,
            oauth_client_id=oauth_client_id,
            oauth_client_secret=oauth_client_secret,
            on_token_refresh=on_token_refresh,
            market=market,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
            http_client=http_client,
            app_info=app_info,
        )
        self._attach()
