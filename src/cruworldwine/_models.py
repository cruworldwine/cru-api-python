from __future__ import annotations

import copy
from collections.abc import Mapping
from typing import Any, ClassVar, Optional

_registry: dict[str, type[Model]] = {}


class Model:
    """An object the API answered with.

    Its attributes are the fields this version of the SDK knows; a field that is missing is None,
    and one of a type the SDK did not expect is kept as the API sent it. Every field the API sent,
    including ones added after this SDK was released, is kept in .raw and can be read as
    model["name"].

    A model a method returns directly, or as an item of the list it returns, carries the id of the
    request that answered it as _request_id: quote it to Cru support. The leading underscore keeps
    it apart from the API's own fields.
    """

    _fields: ClassVar[tuple[str, ...]] = ()
    _nested: ClassVar[Mapping[str, tuple[str, bool]]] = {}
    _request_id: Optional[str] = None

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        _registry[cls.__name__] = cls

    def __init__(self, raw: Mapping[str, Any]) -> None:
        self.raw: dict[str, Any] = dict(raw)
        for name in self._fields:
            value = self.raw.get(name)
            nested = self._nested.get(name)
            if nested is not None:
                model, many = _registry[nested[0]], nested[1]
                if not many:
                    value = model.parse(value)
                elif isinstance(value, list):
                    value = [model.parse(v) for v in value]
            setattr(self, name, value)

    @classmethod
    def parse(cls, value: Any) -> Any:
        """A model of this class for a JSON object; any other value is returned as it is."""
        return cls(value) if isinstance(value, Mapping) else value

    def __getitem__(self, key: str) -> Any:
        return self.raw[key]

    def get(self, key: str, default: Any = None) -> Any:
        """The field named key as the API sent it, or default when it is missing."""
        return self.raw.get(key, default)

    def __contains__(self, key: object) -> bool:
        return key in self.raw

    def to_dict(self) -> dict[str, Any]:
        """A deep copy of every field the API sent, known or not."""
        return copy.deepcopy(self.raw)

    def __eq__(self, other: object) -> bool:
        return isinstance(other, Model) and type(other) is type(self) and other.raw == self.raw

    def __repr__(self) -> str:
        shown = ', '.join(f'{k}={getattr(self, k)!r}' for k in self._fields[:4])
        return f'{type(self).__name__}({shown}{", ..." if len(self._fields) > 4 else ""})'


def with_request_id(value: Any, request_id: Optional[str]) -> Any:
    """Mark a model as answered by this request; any other value is returned as it is."""
    if isinstance(value, Model):
        value._request_id = request_id
    return value
