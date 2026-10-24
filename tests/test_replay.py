"""Every response the API really gave, through the method that asks for it.

CRU_CAPTURES names a run of the server's docs/api/tools/spec_capture.php. The captures hold real
account data, so they are read from there and never copied here.
"""
import glob
import inspect
import json
import os
import re

import httpx
import pytest

import cruworldwine
from cruworldwine import Model, Page, Write
from cruworldwine._resources import _OPS

RUN = os.environ.get('CRU_CAPTURES')
FILES = sorted(glob.glob(os.path.join(RUN, 'captures', '*.json'))) if RUN else []
ROUTES = sorted(
    ((op, re.compile('^' + re.sub(r'\\\{[a-z0-9_]+\\\}', '([^/]+)', re.escape(op['path'])) + '$')) for op in _OPS.values()),
    key=lambda r: r[0]['path'].count('{'),
)


def route(method, path):
    for op, rx in ROUTES:
        m = rx.match(path)
        if op['method'] == method and m:
            names = re.findall(r'\{([a-z0-9_]+)\}', op['path'])
            return op, dict(zip(names, m.groups()))
    return None, None


def check(value, raw):
    """Every typed field equals what the API sent, all the way down."""
    if isinstance(value, Model):
        assert value.raw == raw
        for name in value._fields:
            check(getattr(value, name), raw.get(name))
    elif isinstance(value, list):
        assert len(value) == len(raw)
        for v, r in zip(value, raw):
            check(v, r)
    else:
        assert value == raw


@pytest.mark.skipif(not RUN, reason='set CRU_CAPTURES to a spec_capture.php run')
@pytest.mark.parametrize('path', FILES, ids=[os.path.basename(f)[:-5] for f in FILES])
def test_replay(path):
    cap = json.load(open(path))
    req = cap['request']
    op, params = route(req['method'], req['path'])
    if op is None:
        pytest.skip('no operation: ' + req['method'])
    body = cap['body']

    def respond(request):
        if body is None:
            return httpx.Response(cap['status'])
        return httpx.Response(cap['status'], json=body)

    http = httpx.Client(transport=httpx.MockTransport(respond))
    if req.get('grant') == 'oauth':
        client = cruworldwine.Cru(access_token='cru_at_x', http_client=http, max_retries=0)
    else:
        client = cruworldwine.Cru(client_key='k', client_secret='s', http_client=http, max_retries=0)
    resource, name = op['sdk']
    target = client if resource == 'client' else getattr(client, resource)
    method = getattr(target, name)
    known = inspect.signature(method).parameters
    query, sent = req.get('query') or {}, req.get('body') or {}
    kwargs = {k: v for k, v in {**query, **sent}.items() if k in known}
    extra_query = {k: v for k, v in query.items() if k not in known}
    if extra_query:
        kwargs['extra_query'] = extra_query
    call = lambda: method(*params.values(), **kwargs)  # noqa: E731

    if cap['status'] >= 400:
        with pytest.raises(cruworldwine.APIStatusError) as caught:
            call()
        assert caught.value.code == body['errors'][0]['code']
        return
    result = call()
    data = body['data'] if body else None
    if isinstance(result, Page):
        check(result.items, data[op['items_key']])
        assert result.total == body['meta']['pagination'].get('total')
    elif isinstance(result, Write):
        if result.staged:
            check(result.confirmation, data['confirmation'])
        else:
            check(result.result, data)
    elif isinstance(result, list):
        check(result, data[op['items_key']])
    elif result is not None:
        check(result, data[op['items_key']] if op['items_key'] else data)
