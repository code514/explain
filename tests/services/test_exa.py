from datetime import UTC, date, datetime
from types import SimpleNamespace
from typing import Any

import pytest

from app.config import Settings
from app.schemas import NewsTier
from app.services import exa as exa_service


class FakeExa:
    """Stands in for AsyncExa. `calls` records the arguments of each search() call."""

    calls: list[dict[str, Any]] = []
    results: list[SimpleNamespace] = []

    async def search(self, query: str, **kwargs: Any) -> SimpleNamespace:
        FakeExa.calls.append({"query": query, **kwargs})
        return SimpleNamespace(results=FakeExa.results)


@pytest.fixture(autouse=True)
def fake_exa(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(exa_service, "_client", lambda: FakeExa())
    FakeExa.calls = []
    FakeExa.results = []


def _result(**fields: Any) -> SimpleNamespace:
    defaults = {
        "url": "https://example.com/a",
        "title": "A",
        "published_date": None,
        "highlights": None,
    }
    return SimpleNamespace(**{**defaults, **fields})


async def test_search_news_sends_recommended_request_with_window() -> None:
    await exa_service.search_news("nvidia news", date(2026, 3, 2), date(2026, 3, 5))

    assert FakeExa.calls == [
        {
            "query": "nvidia news",
            "type": "auto",
            "category": "news",
            "start_published_date": "2026-03-02T00:00:00.000Z",
            "end_published_date": "2026-03-05T23:59:59.999Z",
            "contents": {"highlights": True},
        }
    ]


async def test_search_news_maps_results_to_articles() -> None:
    FakeExa.results = [
        _result(published_date="2026-03-04T14:30:00.000Z", highlights=["Beat estimates."]),
        _result(url="https://example.com/b", title=None),
    ]

    articles = await exa_service.search_news("q", date(2026, 3, 2), date(2026, 3, 5))

    assert [a.url for a in articles] == ["https://example.com/a", "https://example.com/b"]
    assert articles[0].published_at == datetime(2026, 3, 4, 14, 30, tzinfo=UTC)
    assert articles[0].highlights == ["Beat estimates."]
    assert articles[1].title is None
    assert articles[1].published_at is None
    assert articles[1].highlights == []


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, None),
        ("not a date", None),
        ("2026-03-04", datetime(2026, 3, 4, tzinfo=UTC)),
        ("2026-03-04T14:30:00+02:00", datetime(2026, 3, 4, 12, 30, tzinfo=UTC)),
    ],
)
def test_parse_published_date(value: str | None, expected: datetime | None) -> None:
    parsed = exa_service._parse_published_date(value)
    assert parsed == expected


def test_build_query_per_tier() -> None:
    company = exa_service.build_query(NewsTier.COMPANY, "NVIDIA Corporation", "NVDA", "Semis")
    industry = exa_service.build_query(NewsTier.INDUSTRY, "NVIDIA Corporation", "NVDA", "Semis")
    macro = exa_service.build_query(NewsTier.MACRO, "NVIDIA Corporation", "NVDA", "Semis")

    assert "NVIDIA Corporation (NVDA)" in company
    assert "Semis" in industry
    assert macro == exa_service.MACRO_QUERY


def test_industry_query_falls_back_to_company_name() -> None:
    query = exa_service.build_query(NewsTier.INDUSTRY, "SPDR S&P 500", "SPY", None)
    assert "SPDR S&P 500" in query


def test_missing_api_key_raises(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.undo()
    exa_service._client.cache_clear()
    monkeypatch.setattr(exa_service, "get_settings", lambda: Settings(exa_api_key=""))
    with pytest.raises(exa_service.MissingApiKeyError):
        exa_service._client()
    exa_service._client.cache_clear()
