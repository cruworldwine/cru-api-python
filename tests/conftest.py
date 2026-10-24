"""Fixtures every test can use: run each test with Cru and with AsyncCru, and resolve what they return."""

from __future__ import annotations

import asyncio
import inspect
from collections.abc import Iterator
from typing import Any, Callable

import pytest


@pytest.fixture(params=['sync', 'async'])
def kind(request: pytest.FixtureRequest) -> str:
    """Run the test with Cru and again with AsyncCru."""
    return str(request.param)


@pytest.fixture
def run() -> Iterator[Callable[[Any], Any]]:
    """Resolve what a client method returned: a coroutine runs on this test's event loop."""
    loop = asyncio.new_event_loop()

    def resolve(value: Any) -> Any:
        return loop.run_until_complete(value) if inspect.isawaitable(value) else value

    yield resolve
    loop.close()
