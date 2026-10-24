"""Logging through logging.getLogger('cruworldwine'), CRU_LOG, and keeping secrets out of logs and reprs."""

import logging
import re

import httpx
import pytest

import cruworldwine
from conftest import envelope, error, make
from cruworldwine import _logs

KEY = 'cru_live_KEY_4f1d9c'
SECRET = 'SECRET_8e2b7a'
ACCESS_ONE = 'AT_ONE_5c3e'
REFRESH_ONE = 'RT_ONE_9a7f'
ACCESS_TWO = 'AT_TWO_2d6b'
REFRESH_TWO = 'RT_TWO_7e1c'
OAUTH_SECRET = 'OAUTH_SECRET_0b4d'
SECRETS = (KEY, SECRET, ACCESS_ONE, REFRESH_ONE, ACCESS_TWO, REFRESH_TWO, OAUTH_SECRET)
BODY_MARKER = 'BODY_MARKER_3f8a'


def partner(mock, kind, **kwargs):
    return make(kind, mock, client_key=KEY, client_secret=SECRET, **kwargs)


def oauth(mock, kind, **kwargs):
    return make(
        kind,
        mock,
        access_token=ACCESS_ONE,
        refresh_token=REFRESH_ONE,
        oauth_client_id='client-1',
        oauth_client_secret=OAUTH_SECRET,
        **kwargs,
    )


def cru_messages(caplog):
    return [(r.levelname, r.getMessage()) for r in caplog.records if r.name == 'cruworldwine']


def test_attempts_retries_and_refreshes_are_logged(mock, kind, run, caplog):
    caplog.set_level(logging.DEBUG, logger='cruworldwine')
    mock.add(401, error('AUTH_INVALID_CREDENTIALS'), headers={'X-Request-Id': 'req_a'})
    mock.add(200, {'access_token': ACCESS_TWO, 'refresh_token': REFRESH_TWO})
    mock.add(503, error('SERVICE_UNAVAILABLE'), headers={'X-Request-Id': 'req_b', 'Retry-After': '1'})
    mock.fail(httpx.ConnectError('reset'))
    mock.add(200, envelope({'pong': True, 'client': {}}), headers={'X-Request-Id': 'req_c'})
    run(oauth(mock, kind, max_retries=3).ping())
    got = cru_messages(caplog)
    expected = [
        ('DEBUG', r'GET /ping -> 401 in \d+\.\d{3}s \(attempt 1, request_id req_a\)'),
        ('INFO', r'Refreshing the OAuth access token'),
        ('DEBUG', r'POST /api/oauth/token -> 200 in \d+\.\d{3}s'),
        ('INFO', r'Refreshed the OAuth access token'),
        ('DEBUG', r'GET /ping -> 503 in \d+\.\d{3}s \(attempt 2, request_id req_b\)'),
        ('INFO', r'Retrying GET /ping in 1\.00s \(retry 1 of 3\) after HTTP 503'),
        ('DEBUG', r'GET /ping failed in \d+\.\d{3}s \(attempt 3\): ConnectError'),
        ('INFO', r'Retrying GET /ping in \d\.\d{2}s \(retry 2 of 3\) after ConnectError'),
        ('DEBUG', r'GET /ping -> 200 in \d+\.\d{3}s \(attempt 4, request_id req_c\)'),
    ]
    assert len(got) == len(expected), got
    for (level, message), (want_level, pattern) in zip(got, expected):
        assert level == want_level
        assert re.fullmatch(pattern, message), message


def test_secrets_and_bodies_are_never_logged(mock, kind, run, caplog):
    caplog.set_level(logging.DEBUG)  # every logger, httpx's own included
    marker = {'note': BODY_MARKER}
    mock.add(503, error('SERVICE_UNAVAILABLE'))
    mock.fail(httpx.ConnectError('reset'))
    mock.add(422, error('TRADE_REFUSED', details=marker))
    with pytest.raises(cruworldwine.UnprocessableEntityError):
        run(partner(mock, kind).bids.place(lwin18='1', quantity=1, price=1, client_ref=BODY_MARKER))
    mock.add(401, error('AUTH_INVALID_CREDENTIALS'))
    mock.add(200, {'access_token': ACCESS_TWO, 'refresh_token': REFRESH_TWO, 'note': BODY_MARKER})
    mock.add(200, envelope({'pong': True, 'client': marker}))
    run(oauth(mock, kind).ping())
    mock.add(401, error('AUTH_INVALID_CREDENTIALS'))
    mock.add(400, {'error': 'invalid_grant'})
    with pytest.raises(cruworldwine.AuthenticationError):
        run(oauth(mock, kind).ping())

    assert caplog.records, 'nothing was logged'
    logged = caplog.text + '\n'.join(r.getMessage() for r in caplog.records)
    for secret in (*SECRETS, BODY_MARKER):
        assert secret not in logged


def test_cru_log_writes_to_stderr(mock, kind, run, monkeypatch, capsys):
    monkeypatch.setenv('CRU_LOG', 'debug')
    level, handlers = _logs.logger.level, list(_logs.logger.handlers)
    try:
        _logs.setup_logging()
        _logs.setup_logging()  # once is enough: no second handler
        added = [h for h in _logs.logger.handlers if h not in handlers]
        assert len(added) == 1
        assert _logs.logger.level == logging.DEBUG
        mock.add(200, envelope({'pong': True, 'client': {}}), headers={'X-Request-Id': 'req_stderr'})
        run(partner(mock, kind).ping())
        err = capsys.readouterr().err
        assert 'DEBUG cruworldwine] GET /ping -> 200' in err
        assert 'request_id req_stderr' in err
        for secret in SECRETS:
            assert secret not in err
    finally:
        _logs.logger.handlers[:] = handlers
        _logs.logger.setLevel(level)


@pytest.mark.parametrize(('value', 'level'), [('info', logging.INFO), (' DEBUG ', logging.DEBUG)])
def test_cru_log_levels(monkeypatch, value, level):
    monkeypatch.setenv('CRU_LOG', value)
    saved_level, saved = _logs.logger.level, list(_logs.logger.handlers)
    try:
        _logs.setup_logging()
        assert _logs.logger.level == level
    finally:
        _logs.logger.handlers[:] = saved
        _logs.logger.setLevel(saved_level)


@pytest.mark.parametrize('value', ['', 'verbose', 'warning'])
def test_cru_log_other_values_add_nothing(monkeypatch, value):
    monkeypatch.setenv('CRU_LOG', value)
    saved = list(_logs.logger.handlers)
    _logs.setup_logging()
    assert _logs.logger.handlers == saved


def test_library_logger_is_silent_by_default():
    assert any(isinstance(h, logging.NullHandler) for h in _logs.logger.handlers)


def test_reprs_and_errors_hold_no_secrets(mock, kind, run):
    clients = [partner(mock, kind), oauth(mock, kind)]
    clients += [c.with_options(timeout=1) for c in clients]
    shown = [repr(c) for c in clients] + [str(c) for c in clients] + [repr(c._auth) for c in clients]

    mock.add(401, error('AUTH_INVALID_CREDENTIALS'))
    mock.add(401, error('AUTH_INVALID_CREDENTIALS'))
    mock.add(400, {'error': 'invalid_grant', 'error_description': 'The refresh token was used already.'})
    mock.fail(httpx.ConnectError('connection refused'))
    errors = []
    for call in (
        lambda: partner(mock, kind).ping(),
        lambda: oauth(mock, kind).ping(),
        lambda: partner(mock, kind, max_retries=0).ping(),
    ):
        with pytest.raises(cruworldwine.CruError) as caught:
            run(call())
        errors.append(caught.value)
    assert [type(e) for e in errors] == [
        cruworldwine.AuthenticationError,
        cruworldwine.AuthenticationError,
        cruworldwine.APIConnectionError,
    ]
    shown += [str(e) for e in errors] + [repr(e) for e in errors]
    shown += [repr(e.__cause__) for e in errors if e.__cause__ is not None]
    text = '\n'.join(shown)
    for secret in SECRETS:
        assert secret not in text
    assert "auth='partner credential'" in shown[0]
    assert "auth='connected app'" in shown[1]
