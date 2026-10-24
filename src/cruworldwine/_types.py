from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Iterator, Mapping
from typing import Any, Callable, Generic, Optional, TypeVar

T = TypeVar('T')


class _BasePage(Generic[T]):
    def __init__(
        self,
        items: list[T],
        data: Mapping[str, Any],
        meta: Mapping[str, Any],
        request_id: Optional[str] = None,
    ) -> None:
        self.items = items
        self.data = dict(data)
        self.meta = dict(meta)
        self.request_id = request_id
        pagination = self.meta.get('pagination')
        pagination = pagination if isinstance(pagination, dict) else {}
        self.limit: Optional[int] = _int(pagination.get('limit'))
        self.offset: int = _int(pagination.get('offset')) or 0
        self.total: Optional[int] = _int(pagination.get('total'))
        has_more = pagination.get('has_more')
        self.has_more: bool = has_more if isinstance(has_more, bool) else (len(items) == self.limit and len(items) > 0)

    @property
    def _request_id(self) -> Optional[str]:
        """The same as request_id, so every answer's request id reads the same way."""
        return self.request_id

    def __iter__(self) -> Iterator[T]:
        return iter(self.items)

    def __len__(self) -> int:
        return len(self.items)

    def _next_offset(self) -> Optional[int]:
        return self.offset + len(self.items) if self.has_more and self.items else None

    def __repr__(self) -> str:
        return (
            f'{type(self).__name__}(items={len(self.items)}, offset={self.offset}, total={self.total}, '
            f'has_more={self.has_more}, request_id={self.request_id!r})'
        )


class Page(_BasePage[T]):
    """One page of a list.

    Iterate it for this page's items, call next_page() for the next one, or auto_paging_iter() for
    every item of every page. request_id is the id of the request that answered this page.
    """

    def __init__(
        self,
        items: list[T],
        data: Mapping[str, Any],
        meta: Mapping[str, Any],
        fetch: Callable[[int], Page[T]],
        request_id: Optional[str] = None,
    ) -> None:
        super().__init__(items, data, meta, request_id)
        self._fetch = fetch

    def next_page(self) -> Optional[Page[T]]:
        """The next page, or None when this is the last one."""
        offset = self._next_offset()
        return None if offset is None else self._fetch(offset)

    def auto_paging_iter(self) -> Iterator[T]:
        """Every item of this page and of each page after it, fetching them as they are needed."""
        page: Optional[Page[T]] = self
        while page is not None:
            yield from page.items
            page = page.next_page()


class AsyncPage(_BasePage[T]):
    """One page of a list, from AsyncCru.

    Iterate it with for for this page's items, await next_page() for the next one, or use
    async for (or auto_paging_iter()) for every item of every page.
    """

    def __init__(
        self,
        items: list[T],
        data: Mapping[str, Any],
        meta: Mapping[str, Any],
        fetch: Callable[[int], Awaitable[AsyncPage[T]]],
        request_id: Optional[str] = None,
    ) -> None:
        super().__init__(items, data, meta, request_id)
        self._fetch = fetch

    async def next_page(self) -> Optional[AsyncPage[T]]:
        """The next page, or None when this is the last one."""
        offset = self._next_offset()
        return None if offset is None else await self._fetch(offset)

    async def auto_paging_iter(self) -> AsyncIterator[T]:
        """Every item of this page and of each page after it, fetching them as they are needed."""
        page: Optional[AsyncPage[T]] = self
        while page is not None:
            for item in page.items:
                yield item
            page = await page.next_page()

    def __aiter__(self) -> AsyncIterator[T]:
        return self.auto_paging_iter()


class Write(Generic[T]):
    """What a write did.

    A partner credential's write runs at once: staged is False and result holds what it did. A
    connected app's write is staged: staged is True, nothing has happened yet, and confirmation
    holds the code to confirm once the customer agrees (client.confirmations.confirm(code)).
    replayed is True when this is the stored answer to an earlier request with the same reference.
    request_id is the id of the request that answered.
    """

    def __init__(self, result: Optional[T], confirmation: Any, replayed: bool, request_id: Optional[str]) -> None:
        self.result = result
        self.confirmation = confirmation
        self.staged = confirmation is not None
        self.replayed = replayed
        self.request_id = request_id

    @property
    def _request_id(self) -> Optional[str]:
        """The same as request_id, so every answer's request id reads the same way."""
        return self.request_id

    def __repr__(self) -> str:
        if self.staged:
            return f'Write(staged=True, confirmation={self.confirmation!r}, request_id={self.request_id!r})'
        return f'Write(result={self.result!r}, replayed={self.replayed}, request_id={self.request_id!r})'


class Response:
    """The envelope of a raw call made with client.request()."""

    def __init__(self, status_code: int, headers: Mapping[str, str], body: Any) -> None:
        self.status_code = status_code
        self.headers = dict(headers)
        self.body = body
        self.data = body.get('data') if isinstance(body, dict) else None
        meta = body.get('meta') if isinstance(body, dict) else None
        self.meta: dict[str, Any] = meta if isinstance(meta, dict) else {}
        meta_id = self.meta.get('request_id')
        self.request_id: Optional[str] = meta_id if isinstance(meta_id, str) and meta_id else None
        self.request_id = self.request_id or self.headers.get('x-request-id')

    def __repr__(self) -> str:
        return f'Response(status_code={self.status_code}, request_id={self.request_id!r})'


def _int(value: Any) -> Optional[int]:
    return value if isinstance(value, int) and not isinstance(value, bool) else None
