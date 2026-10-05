import datetime as dt
from enum import StrEnum

from pydantic import BaseModel, Field


class NewsTier(StrEnum):
    """How broad a news search is: about the company, its industry, or the whole market."""

    COMPANY = "company"
    INDUSTRY = "industry"
    MACRO = "macro"


class Article(BaseModel):
    """A news article found by Exa. Only highlights are kept, never the full text."""

    url: str
    title: str | None = None
    published_at: dt.datetime | None = Field(
        default=None, description="Publication time (UTC) when Exa knows it"
    )
    highlights: list[str] = Field(default_factory=list)


class TickerInfo(BaseModel):
    """Company metadata from Yahoo. Sector and industry are missing for ETFs and some funds."""

    symbol: str
    name: str | None = None
    sector: str | None = None
    industry: str | None = None


class Move(BaseModel):
    """A day on which the stock moved a lot."""

    date: dt.date
    daily_return: float = Field(description="Close-to-close return as a fraction, 0.032 = +3.2%")


class TickerResponse(BaseModel):
    moves: list[Move]
    major_moves: list[Move] = Field(
        serialization_alias="majorMoves",
        description="The 10 days with the biggest absolute daily return, biggest first",
    )
