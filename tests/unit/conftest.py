"""Fixtures for the unit tests: a clean environment, and a mock transport whose retries never sleep."""

from __future__ import annotations

import os

import pytest
from hypothesis import settings

import cruworldwine
from tests.helpers import Recorder, sleeps

# Hypothesis: a quick run by default, a thorough one in CI (HYPOTHESIS_PROFILE=ci).
settings.register_profile('dev', max_examples=25, deadline=None)
settings.register_profile('ci', max_examples=150, deadline=None, print_blob=True)
settings.load_profile(os.environ.get('HYPOTHESIS_PROFILE', 'dev'))

ENV = ('CRU_CLIENT_KEY', 'CRU_CLIENT_SECRET', 'CRU_ACCESS_TOKEN', 'CRU_MARKET', 'CRU_BASE_URL', 'CRU_LOG')


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ENV:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def mock(monkeypatch: pytest.MonkeyPatch) -> Recorder:
    """A Recorder, with both clients' waits between retries recorded instead of slept."""

    def sync_sleep(self: object, seconds: float) -> None:
        sleeps.append(seconds)

    async def async_sleep(self: object, seconds: float) -> None:
        sleeps.append(seconds)

    monkeypatch.setattr(cruworldwine.Cru, '_sleep', sync_sleep)
    monkeypatch.setattr(cruworldwine.AsyncCru, '_sleep', async_sleep)
    sleeps.clear()
    return Recorder()
