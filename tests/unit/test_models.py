"""Models take whatever JSON the API sends, never raise, and keep it all in .raw."""

import copy
import json

import pytest
from hypothesis import given
from hypothesis import strategies as st

from cruworldwine import Model, models
from cruworldwine._models import _registry

MODELS = [getattr(models, name) for name in models.__all__]

scalars = st.none() | st.booleans() | st.integers() | st.floats(allow_nan=False) | st.text(max_size=12)
json_values = st.recursive(
    scalars,
    lambda inner: st.lists(inner, max_size=4) | st.dictionaries(st.text(max_size=10), inner, max_size=4),
    max_leaves=25,
)


def shaped(cls, depth=2):
    """Objects with this model's own field names, nested models included, holding anything at all."""
    fields = {}
    for name in cls._fields:
        nested = cls._nested.get(name)
        value = json_values
        if nested is not None and depth > 0:
            inner = shaped(_registry[nested[0]], depth - 1)
            value = value | (st.lists(inner, max_size=3) if nested[1] else inner)
        fields[name] = value
    extra = st.dictionaries(st.text(max_size=10).filter(lambda k: k not in cls._fields), json_values, max_size=3)
    return st.tuples(st.fixed_dictionaries({}, optional=fields), extra).map(lambda parts: {**parts[1], **parts[0]})


SHAPED = {cls: shaped(cls) for cls in MODELS}


def check(cls, value):
    original = copy.deepcopy(value)
    parsed = cls.parse(value)
    if not isinstance(value, dict):
        assert parsed is value
        return
    assert type(parsed) is cls
    assert parsed.raw == original
    assert parsed.to_dict() == original
    assert json.loads(json.dumps(parsed.to_dict())) == original
    assert parsed == cls.parse(copy.deepcopy(original))
    assert isinstance(repr(parsed), str)
    for name in cls._fields:
        got = getattr(parsed, name)
        sent = original.get(name)
        nested = cls._nested.get(name)
        if nested is None:
            assert got == sent
        elif isinstance(sent, dict) and not nested[1]:
            assert isinstance(got, _registry[nested[0]])
            assert got.raw == sent
        elif isinstance(sent, list) and nested[1]:
            assert len(got) == len(sent)
            assert all(g.raw == s for g, s in zip(got, sent) if isinstance(s, dict))
        else:
            assert got == sent
    for key in original:
        assert key in parsed
        assert parsed[key] == original[key]
        assert parsed.get(key) == original[key]
    assert parsed.get('\x00missing', 'default') == 'default'
    assert value == original, 'parsing changed its input'


@pytest.mark.parametrize('cls', MODELS, ids=lambda cls: cls.__name__)
@given(data=st.data())
def test_any_json_parses_and_round_trips(cls, data):
    check(cls, data.draw(json_values, label='any JSON'))
    check(cls, data.draw(SHAPED[cls], label='shaped like the model'))


def test_every_generated_model_is_registered():
    assert {cls.__name__ for cls in MODELS} <= set(_registry)
    assert all(issubclass(cls, Model) for cls in MODELS)


def test_equality_is_by_class_and_content():
    a = models.OwnBid({'code': 'CB-1'})
    assert a == models.OwnBid({'code': 'CB-1'})
    assert a != models.OwnBid({'code': 'CB-2'})
    assert a != models.MarketBid({'code': 'CB-1'})
    assert a != {'code': 'CB-1'}
    assert a._request_id is None
