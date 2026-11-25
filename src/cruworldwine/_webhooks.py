"""Checking that a webhook delivery came from Cru, as Standard Webhooks v1 signs it."""

from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import json
import time
from collections.abc import Mapping
from typing import Optional, Union

from ._errors import CruError
from .models import WebhookEvent

__all__ = ['WEBHOOK_TOLERANCE', 'WebhookVerificationError', 'verify_webhook']

#: How far a delivery's webhook-timestamp may be from now, either way, in seconds.
WEBHOOK_TOLERANCE = 300

_SECRET_PREFIX = 'whsec_'  # noqa: S105 - the prefix every signing secret starts with, not a secret


class WebhookVerificationError(CruError):
    """The delivery is not one Cru signed with this secret, or it is too old: answer it 401 and drop it."""


def verify_webhook(
    body: Union[bytes, str],
    headers: Mapping[str, str],
    secret: str,
    *,
    tolerance: int = WEBHOOK_TOLERANCE,
    now: Optional[float] = None,
) -> WebhookEvent:
    """Check a webhook delivery's signature and return its event.

    Cru signs every delivery as Standard Webhooks v1 does: webhook-signature holds v1, and the base64
    HMAC-SHA256 of "{webhook-id}.{webhook-timestamp}.{body}", keyed with the base64-decoded part of
    the signing secret after whsec_. For 24 hours after the secret is rotated there are two
    signatures, separated by a space, and either is accepted.

    Deduplicate on the event's id, and answer 2xx at once: do the work afterwards. data depends on
    type: models.SaleCreatedData.parse(event.data) for sale.created, models.PurchaseCreatedData for
    purchase.created, models.WebhookTestData for webhook.test.

    Args:
        body: The request body exactly as it arrived, before any JSON parsing.
        headers: The request's headers, in any case: Flask's request.headers, Django's
            request.headers, or a plain dict.
        secret: The webhook's signing_secret, whsec_ and a base64 key.
        tolerance: How old, or how far ahead, webhook-timestamp may be, in seconds.
        now: The Unix time to check the timestamp against, for tests. None is the current time.

    Raises:
        WebhookVerificationError: A header is missing, the timestamp is outside the tolerance, no
            signature matches, or the body is not a JSON object.
    """
    raw = body.encode() if isinstance(body, str) else bytes(body)
    lower = {k.lower(): v for k, v in headers.items()}
    msg_id = lower.get('webhook-id', '')
    timestamp = lower.get('webhook-timestamp', '')
    signature = lower.get('webhook-signature', '')
    if not msg_id or not signature:
        raise WebhookVerificationError('The webhook-id and webhook-signature headers are required')
    if not timestamp.isdigit():
        raise WebhookVerificationError('The webhook-timestamp header is not a Unix time')
    current = time.time() if now is None else now
    if abs(current - int(timestamp)) > tolerance:
        raise WebhookVerificationError('The webhook-timestamp is too far from now: an old or replayed delivery')

    signed = f'{msg_id}.{timestamp}.'.encode() + raw
    expected = base64.b64encode(hmac.new(_key(secret), signed, hashlib.sha256).digest()).decode()
    for candidate in signature.split(' '):
        version, _, value = candidate.partition(',')
        if version == 'v1' and hmac.compare_digest(expected, value):
            break
    else:
        raise WebhookVerificationError('No signature matches: not signed by Cru with this secret')

    try:
        payload = json.loads(raw)
    except ValueError as e:
        raise WebhookVerificationError('The body is not JSON') from e
    if not isinstance(payload, dict):
        raise WebhookVerificationError('The body is not a JSON object')
    return WebhookEvent(payload)


def _key(secret: str) -> bytes:
    encoded = secret[len(_SECRET_PREFIX) :] if secret.startswith(_SECRET_PREFIX) else secret
    try:
        return base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as e:
        raise WebhookVerificationError('The secret is not whsec_ and a base64 key') from e
