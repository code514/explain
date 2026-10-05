import datetime as dt

from pydantic import BaseModel, Field


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
