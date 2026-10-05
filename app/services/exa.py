"""All Exa interaction. Nothing else in the app imports `exa_py`.

Stateless: no caching and no DB. Callers check the cache first, call `search_news` on a miss, and
store the response themselves. The request follows the build-with-exa skill: query, `type: auto`
and bare `highlights`. `category="news"` and the published-date window are deliberate, since the
plan asks for news only inside a bounded window around the move.
"""

import logging
from datetime import UTC, date, datetime
from functools import lru_cache

from exa_py import AsyncExa

from app.config import get_settings
from app.schemas import Article, NewsTier

logger = logging.getLogger(__name__)

MACRO_QUERY = "stock market today: Fed interest rate decision, inflation, tariffs"


class MissingApiKeyError(Exception):
    """`EXA_API_KEY` is not set."""


def build_query(tier: NewsTier, company_name: str, ticker: str, industry: str | None) -> str:
    """Natural-language query for one tier. Phrasing carries the intent, not extra parameters."""
    match tier:
        case NewsTier.COMPANY:
            return f"{company_name} ({ticker}) stock news: earnings, guidance, lawsuit, analyst"
        case NewsTier.INDUSTRY:
            return f"{industry or company_name} industry stocks news and competitors"
        case NewsTier.MACRO:
            return MACRO_QUERY


async def search_news(query: str, start: date, end: date) -> list[Article]:
    """News matching `query`, published from the start of `start` to the end of `end` (UTC).

    Returns Exa's default 10 results with highlights, in Exa's relevance order. Results missing
    a title, date or highlights are kept as they are.
    """
    response = await _client().search(
        query,
        type="auto",
        category="news",
        start_published_date=f"{start.isoformat()}T00:00:00.000Z",
        end_published_date=f"{end.isoformat()}T23:59:59.999Z",
        contents={"highlights": True},
    )
    return [
        Article(
            url=result.url,
            title=result.title,
            published_at=_parse_published_date(result.published_date),
            highlights=result.highlights or [],
        )
        for result in response.results
    ]


@lru_cache
def _client() -> AsyncExa:
    api_key = get_settings().exa_api_key
    if not api_key:
        raise MissingApiKeyError("Set EXA_API_KEY in .env")
    return AsyncExa(api_key=api_key)


def _parse_published_date(value: str | None) -> datetime | None:
    """Exa returns ISO 8601, usually with a trailing Z. Naive values are taken as UTC."""
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        logger.warning("Unparseable Exa published date: %r", value)
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
