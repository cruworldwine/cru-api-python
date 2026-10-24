from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Generic, Optional, TypeVar

R = TypeVar('R')
M = TypeVar('M')


@dataclass(frozen=True)
class Operation:
    """One endpoint, as the generated resources describe it to the client.

    kind says what the answer is: get (one model), list (a list of models), page (a page of
    them), write (a Write), confirm (a Write typed by the action confirmed), empty (no body) or
    binary (bytes). model names the model class, items_key the key of data that holds it, and
    results, for confirm, the model of each action.
    """

    id: str
    method: str
    path: str
    kind: str
    model: Optional[str] = None
    items_key: Optional[str] = None
    sdk: tuple[str, str] = ('', '')
    results: Mapping[str, str] = field(default_factory=dict)


class Op(Operation, Generic[R]):
    """An operation whose method returns R, whichever client calls it."""


class PageOp(Operation, Generic[M]):
    """A paged list of M: Cru returns a Page[M], AsyncCru an AsyncPage[M]."""
