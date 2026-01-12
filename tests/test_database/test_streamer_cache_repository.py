"""Tests for the StreamerCacheRepository helper methods."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.exc import ProgrammingError

from src.database.repositories import StreamerCacheRepository


@pytest.mark.asyncio
async def test_search_by_similarity_falls_back_when_pg_trgm_missing(monkeypatch):
    """Ensure we degrade gracefully if the pg_trgm extension isn't installed."""

    session = SimpleNamespace()
    session.execute = AsyncMock(
        side_effect=ProgrammingError("SELECT", {}, Exception("pg_trgm missing"))
    )

    async def fake_candidates(session_arg, username_arg, limit_arg):
        assert session_arg is session
        assert username_arg == "tester"
        assert limit_arg == 50
        return ["fallback"]

    monkeypatch.setattr(
        StreamerCacheRepository,
        "get_candidates_for_username",
        staticmethod(fake_candidates),
    )

    result = await StreamerCacheRepository.search_by_similarity(session, "tester")

    assert result == ["fallback"]
    session.execute.assert_awaited()
