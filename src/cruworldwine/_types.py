from __future__ import annotations

from typing import Any, Callable, Dict, Generic, Iterator, List, Optional, TypeVar

T = TypeVar('T')


class Page(Generic[T]):
    """One page of a list. Iterate it for its items, or auto_paging_iter() for every item of every page."""

    def __init__(self, items: List[T], data: Dict[str, Any], meta: Dict[str, Any], fetch: Callable[[int], 'Page[T]']) -> None:
        self.items = items
        self.data = data
        self.meta = meta
        pagination = meta.get('pagination') or {}
        self.limit: Optional[int] = pagination.get('limit')
        self.offset: int = pagination.get('offset') or 0
        self.total: Optional[int] = pagination.get('total')
        self.has_more: bool = bool(pagination.get('has_more', len(items) == self.limit and len(items) > 0))
        self._fetch = fetch

    def __iter__(self) -> Iterator[T]:
        return iter(self.items)

    def __len__(self) -> int:
        return len(self.items)

    def next_page(self) -> Optional['Page[T]']:
        if not self.has_more or not self.items:
            return None
        return self._fetch(self.offset + len(self.items))

    def auto_paging_iter(self) -> Iterator[T]:
        page: Optional[Page[T]] = self
        while page is not None:
            yield from page.items
            page = page.next_page()

    def __repr__(self) -> str:
        return f'Page(items={len(self.items)}, offset={self.offset}, total={self.total}, has_more={self.has_more})'


class Write(Generic[T]):
    """What a write did.

    A partner credential's write runs at once: staged is False and result holds what it did. A
    connected app's write is staged: staged is True, nothing has happened yet, and confirmation
    holds the code to confirm once the customer agrees (client.confirmations.confirm(code)).
    replayed is True when this is the stored answer to an earlier request with the same reference.
    """

    def __init__(self, result: Optional[T], confirmation: Any, replayed: bool, request_id: Optional[str]) -> None:
        self.result = result
        self.confirmation = confirmation
        self.staged = confirmation is not None
        self.replayed = replayed
        self.request_id = request_id

    def __repr__(self) -> str:
        if self.staged:
            return f'Write(staged=True, confirmation={self.confirmation!r})'
        return f'Write(result={self.result!r}, replayed={self.replayed})'


class Response:
    """The envelope of a raw call made with client.request()."""

    def __init__(self, status_code: int, headers: Dict[str, str], body: Any) -> None:
        self.status_code = status_code
        self.headers = headers
        self.body = body
        self.data = body.get('data') if isinstance(body, dict) else None
        self.meta = body.get('meta', {}) if isinstance(body, dict) else {}
