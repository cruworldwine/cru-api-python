"""verify_webhook, against signatures made by the API's own signer (Cru_Api_Model_Webhook_Signer).

The secrets are invented samples, not keys of any webhook.
"""

import pytest

import cruworldwine
from cruworldwine import WebhookVerificationError, models, verify_webhook

BODY = (
    '{"id":"evt_6f1c0d2e9a7b4c3d5e8f9a0b","type":"webhook.test","api_version":"1",'
    '"created_at":"2026-10-19T10:11:01Z","data":{"webhook_id":"whs_3f9a1c7e5b2d4086a1e9c4b7",'
    '"message":"A test event from Cru. Answer with any 2xx status to show your endpoint works."}}'
)
OLD = 'whsec_c2FtcGxlLXNlY3JldC1ub3QtYS1yZWFsLWtleQ=='
NEW = 'whsec_c2Vjb25kLXNhbXBsZS1zZWNyZXQtbm90LXJlYWw='
SIGNED_AT = 1792404661
HEADERS = {
    'webhook-id': 'evt_6f1c0d2e9a7b4c3d5e8f9a0b',
    'webhook-timestamp': str(SIGNED_AT),
    'webhook-signature': 'v1,fpcbXyd+iRNLUrvep/lKQ+/nbKRqmRkE/jbH+gndpZc=',
}
# The day after a rotation: the new secret's signature, then the old one's.
ROTATING = {
    **HEADERS,
    'webhook-signature': (
        'v1,I8G3oULkwTjh5XwYduia9NQKJWTNYCaQjyZJMJ+fotc= v1,fpcbXyd+iRNLUrvep/lKQ+/nbKRqmRkE/jbH+gndpZc='
    ),
}


def test_a_genuine_delivery_returns_its_event():
    event = verify_webhook(BODY.encode(), HEADERS, OLD, now=SIGNED_AT)
    assert isinstance(event, models.WebhookEvent)
    assert event.id == 'evt_6f1c0d2e9a7b4c3d5e8f9a0b'
    assert event.type == 'webhook.test'
    data = models.WebhookTestData.parse(event.data)
    assert data.webhook_id == 'whs_3f9a1c7e5b2d4086a1e9c4b7'


def test_the_body_may_be_text_and_the_headers_any_case():
    headers = {k.title(): v for k, v in HEADERS.items()}
    assert verify_webhook(BODY, headers, OLD, now=SIGNED_AT).id == 'evt_6f1c0d2e9a7b4c3d5e8f9a0b'


def test_during_a_rotation_either_secret_verifies():
    assert verify_webhook(BODY, ROTATING, NEW, now=SIGNED_AT).type == 'webhook.test'
    assert verify_webhook(BODY, ROTATING, OLD, now=SIGNED_AT).type == 'webhook.test'


def test_the_new_secret_alone_does_not_verify_an_old_signature():
    with pytest.raises(WebhookVerificationError, match='No signature matches'):
        verify_webhook(BODY, HEADERS, NEW, now=SIGNED_AT)


def test_a_changed_body_is_refused():
    with pytest.raises(WebhookVerificationError, match='No signature matches'):
        verify_webhook(BODY.replace('webhook.test', 'sale.created'), HEADERS, OLD, now=SIGNED_AT)


@pytest.mark.parametrize('offset', [301, -301])
def test_a_timestamp_outside_five_minutes_is_refused(offset):
    with pytest.raises(WebhookVerificationError, match='too far from now'):
        verify_webhook(BODY, HEADERS, OLD, now=SIGNED_AT + offset)


@pytest.mark.parametrize('offset', [300, -300])
def test_a_timestamp_inside_five_minutes_is_accepted(offset):
    assert verify_webhook(BODY, HEADERS, OLD, now=SIGNED_AT + offset).id


def test_the_tolerance_can_be_changed():
    assert verify_webhook(BODY, HEADERS, OLD, now=SIGNED_AT + 3600, tolerance=7200).id


@pytest.mark.parametrize('missing', ['webhook-id', 'webhook-signature'])
def test_a_missing_header_is_refused(missing):
    headers = {k: v for k, v in HEADERS.items() if k != missing}
    with pytest.raises(WebhookVerificationError, match='required'):
        verify_webhook(BODY, headers, OLD, now=SIGNED_AT)


@pytest.mark.parametrize('timestamp', ['', 'soon', '-1792404661', '1792404661.5'])
def test_a_timestamp_that_is_not_a_unix_time_is_refused(timestamp):
    with pytest.raises(WebhookVerificationError, match='not a Unix time'):
        verify_webhook(BODY, {**HEADERS, 'webhook-timestamp': timestamp}, OLD, now=SIGNED_AT)


@pytest.mark.parametrize('signature', ['v2,fpcbXyd+iRNLUrvep/lKQ+/nbKRqmRkE/jbH+gndpZc=', 'fpcbXyd', 'v1,'])
def test_a_signature_of_another_version_or_shape_is_refused(signature):
    with pytest.raises(WebhookVerificationError):
        verify_webhook(BODY, {**HEADERS, 'webhook-signature': signature}, OLD, now=SIGNED_AT)


def test_a_secret_that_is_not_base64_is_refused():
    with pytest.raises(WebhookVerificationError, match='base64'):
        verify_webhook(BODY, HEADERS, 'whsec_not base64!', now=SIGNED_AT)


def test_a_signed_body_that_is_not_a_json_object_is_refused():
    import base64
    import hashlib
    import hmac

    for body, problem in [(b'not json', 'not JSON'), (b'[1]', 'not a JSON object')]:
        key = base64.b64decode(OLD[len('whsec_') :])
        mac = hmac.new(key, f'{HEADERS["webhook-id"]}.{SIGNED_AT}.'.encode() + body, hashlib.sha256).digest()
        headers = {**HEADERS, 'webhook-signature': 'v1,' + base64.b64encode(mac).decode()}
        with pytest.raises(WebhookVerificationError, match=problem):
            verify_webhook(body, headers, OLD, now=SIGNED_AT)


def test_it_checks_against_the_current_time_by_default():
    with pytest.raises(WebhookVerificationError, match='too far from now'):
        verify_webhook(BODY, HEADERS, OLD)


def test_the_error_is_a_cru_error():
    assert issubclass(WebhookVerificationError, cruworldwine.CruError)
