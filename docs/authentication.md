# Authentication

There are two ways to connect to the Cru Trading API, and the SDK supports both with the same
clients, `Cru` and `AsyncCru`. Each answers on one market's host,
`https://{market}.cruworldwine.com/api/v1`, where market is `uk` (the default), `us`, `hk`, `sg`,
`eu`, `ae` or `cn`. A credential works on its own market only.

| | Partner credential | Connected app (OAuth 2.0) |
|---|---|---|
| Who it acts for | Your own organisation | A Cru customer who authorised your app |
| What you pass | `client_key` and `client_secret` | `access_token`, and to refresh it `refresh_token` and `oauth_client_id` |
| Writes | Run at once | Staged until the customer confirms them |
| Retries of writes | Yes, with the same `reference` | Never |

## With a partner credential

Cru issues a partner credential: a key (`cru_live_...`) and a secret, which is shown once. Keep
both out of source control: read them from the environment or a secret manager.

```python
from cruworldwine import Cru

cru = Cru(client_key='cru_live_...', client_secret='...', market='uk')
```

The SDK sends them as the `CLIENT-KEY` and `CLIENT-SECRET` headers. A partner credential's writes
run at once; see [Writes and confirmations](writes-and-confirmations.md).

## As a connected app (OAuth 2.0)

An app that acts for a Cru customer gets their tokens with the OAuth 2.0 authorization code flow
with PKCE (S256), at `/api/oauth/authorize` and `/api/oauth/token` on the market's host. The SDK
does not run that flow; it starts from the tokens it produced.

```python
cru = Cru(
    access_token=tokens['access_token'],
    refresh_token=tokens['refresh_token'],
    oauth_client_id='your-client-id',
    oauth_client_secret=None,  # only for a confidential client
    on_token_refresh=save_tokens,
)
```

The SDK sends the access token as `Authorization: Bearer ...`. A connected app's writes are
staged: nothing happens until the customer confirms them.

### Refreshing the access token

Give `refresh_token` and `oauth_client_id`, and when the API answers 401 the SDK refreshes the
access token once, at `/api/oauth/token`, and retries the request with the new one. A refresh token
works once, so the new tokens must be stored: `on_token_refresh` is called with the token response
after each refresh. With `AsyncCru` it may be a coroutine function.

```python
def save_tokens(tokens: dict[str, object]) -> None:
    store.put('cru-tokens', tokens)  # your storage
```

Refreshes are serialised: when many threads (with `Cru`) or tasks (with `AsyncCru`) share a
client and its token expires, one of them refreshes it while the others wait, and they then carry
on with the new token rather than spend the refresh token again. Copies made with
`with_options()` share the tokens too. `cru.access_token` and `cru.refresh_token` always read the
current ones.

If the refresh fails, for example because the refresh token was already used, the call raises
`AuthenticationError` with the token endpoint's description. A second 401 after a refresh raises
too: the SDK never refreshes twice for one request.

## From the environment

Anything not given is read from the environment, so `Cru()` alone works when these are set:

| Variable | Used for |
|---|---|
| `CRU_CLIENT_KEY`, `CRU_CLIENT_SECRET` | A partner credential |
| `CRU_ACCESS_TOKEN` | A connected app's access token |
| `CRU_MARKET` | The market, when neither `market` nor `base_url` is given |
| `CRU_BASE_URL` | The API's base URL, in place of the market's |

The credential variables are read only when no credential is passed at all: passing an
`access_token` never picks up a key and secret from the environment.

## Check the connection

`ping()` confirms the credential works and shows what it carries:

```python
client = cru.ping().client
print(client.organisation, client.market, client.currency, client.scopes, client.expires_at)
```

## Keeping credentials safe

- The SDK never follows redirects, so a credential is never sent to another host.
- It never logs a client key or secret, an access or refresh token, or a request or response body,
  and none of them appears in `repr()` of a client or in an error's message.
- `base_url` must be `http` or `https`, and `market` a market code, so a mistyped value cannot
  send requests somewhere unexpected.
