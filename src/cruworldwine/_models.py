from __future__ import annotations

import copy
from typing import Any, ClassVar, Dict, Mapping, Tuple, Type

_registry: Dict[str, Type['Model']] = {}


class Model:
    """An object the API answered with.

    Its attributes are the fields this version of the SDK knows; a field that is missing is None.
    Every field the API sent, including ones added after this SDK was released, is kept in .raw
    and can be read as model["name"].
    """

    _fields: ClassVar[Tuple[str, ...]] = ()
    _nested: ClassVar[Dict[str, Tuple[str, bool]]] = {}

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        _registry[cls.__name__] = cls

    def __init__(self, raw: Mapping[str, Any]) -> None:
        self.raw: Dict[str, Any] = dict(raw)
        for name in self._fields:
            value = raw.get(name)
            nested = self._nested.get(name)
            if nested is not None and value is not None:
                model, many = _registry[nested[0]], nested[1]
                value = [model.parse(v) for v in value] if many else model.parse(value)
            setattr(self, name, value)

    @classmethod
    def parse(cls, value: Any) -> Any:
        return cls(value) if isinstance(value, Mapping) else value

    def __getitem__(self, key: str) -> Any:
        return self.raw[key]

    def get(self, key: str, default: Any = None) -> Any:
        return self.raw.get(key, default)

    def __contains__(self, key: str) -> bool:
        return key in self.raw

    def to_dict(self) -> Dict[str, Any]:
        return copy.deepcopy(self.raw)

    def __eq__(self, other: object) -> bool:
        return type(other) is type(self) and other.raw == self.raw  # type: ignore[attr-defined]

    def __repr__(self) -> str:
        shown = ', '.join(f'{k}={getattr(self, k)!r}' for k in self._fields[:4])
        return f'{type(self).__name__}({shown}{", ..." if len(self._fields) > 4 else ""})'
