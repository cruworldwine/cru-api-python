"""The generated resources: Cru and AsyncCru have the same methods, and each sends its own operation."""

import inspect
import re

import httpx
import pytest

import cruworldwine
from cruworldwine import AsyncPage, Page, Write, resources
from cruworldwine.resources import _OPS
from tests.helpers import envelope, partner

OPTIONS = ('extra_headers', 'extra_query', 'timeout', 'max_retries')
DUMMY = {str: 'x', int: 1, float: 1.5, bool: True}


def methods(client_cls):
    """(resource, name) -> the unbound method, for the client's own methods and every resource's."""
    out = {('client', name): getattr(client_cls, name) for name in ('ping',)}
    hints = client_cls.__mro__[1].__annotations__
    for resource, annotation in hints.items():
        cls = getattr(resources, annotation)
        for name, fn in vars(cls).items():
            if not name.startswith('_') and callable(fn):
                out[(resource, name)] = fn
    return out


def test_every_operation_has_a_method_on_both_clients():
    sync, async_ = methods(cruworldwine.Cru), methods(cruworldwine.AsyncCru)
    assert set(sync) == set(async_) == {op.sdk for op in _OPS.values()}


@pytest.mark.parametrize('op', list(_OPS.values()), ids=lambda op: op.id)
def test_sync_and_async_signatures_match(op):
    sync = methods(cruworldwine.Cru)[op.sdk]
    async_ = methods(cruworldwine.AsyncCru)[op.sdk]
    assert not inspect.iscoroutinefunction(sync)
    assert inspect.iscoroutinefunction(async_)
    sync_sig, async_sig = inspect.signature(sync), inspect.signature(async_)
    assert list(sync_sig.parameters.values()) == list(async_sig.parameters.values())
    assert sync.__doc__.split('\n')[0] == async_.__doc__.split('\n')[0]
    names = list(sync_sig.parameters)
    for option in OPTIONS + (('extra_body',) if op.method != 'GET' else ()):
        assert option in names
        assert sync_sig.parameters[option].kind is inspect.Parameter.KEYWORD_ONLY
        assert sync_sig.parameters[option].default is None
        assert f'{option}:' in sync.__doc__


def answer(op):
    if op.kind == 'empty':
        return httpx.Response(204)
    if op.kind == 'binary':
        return httpx.Response(200, content=b'bytes')
    if op.kind in ('page', 'list'):
        pagination = {'limit': 10, 'offset': 0, 'total': 0, 'has_more': False}
        return httpx.Response(200, json=envelope({op.items_key: []}, pagination=pagination))
    if op.kind == 'get' and op.items_key:
        return httpx.Response(200, json=envelope({op.items_key: {}}))
    return httpx.Response(200, json=envelope({'action': 'x', 'status': 'completed'}))


def arguments(bound):
    args, kwargs = [], {}
    for p in inspect.signature(bound).parameters.values():
        if p.kind is inspect.Parameter.POSITIONAL_OR_KEYWORD:
            args.append('A/1')
        elif p.default is inspect.Parameter.empty:
            kwargs[p.name] = DUMMY[{'str': str, 'int': int, 'float': float, 'bool': bool}[p.annotation]]
    return args, kwargs


@pytest.mark.parametrize('op', list(_OPS.values()), ids=lambda op: op.id)
def test_every_method_sends_its_operation(op, kind, run):
    seen = []

    def handler(request):
        seen.append(request)
        return answer(op)

    client = partner(handler, kind)
    resource, name = op.sdk
    target = client if resource == 'client' else getattr(client, resource)
    method = getattr(target, name)
    args, kwargs = arguments(method)
    result = run(method(*args, extra_headers={'X-Test': op.id}, timeout=5, max_retries=0, **kwargs))

    (request,) = seen
    assert request.method == op.method
    path = re.sub(r'\{[a-z0-9_]+\}', 'A%2F1', op.path)
    assert request.url.raw_path.decode().split('?')[0] == '/api/v1' + path
    assert request.headers['x-test'] == op.id
    if op.method != 'GET':
        assert request.headers['content-type'] == 'application/json'
    expected = {
        'page': AsyncPage if kind == 'async' else Page,
        'list': list,
        'write': Write,
        'confirm': Write,
        'empty': type(None),
        'binary': bytes,
        'get': cruworldwine.Model,
    }[op.kind]
    assert isinstance(result, expected)
