from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import date
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query

from app.controllers import tickers
from app.migrations import run_migrations
from app.schemas import MovesResponse


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
    run_migrations()
    yield


app = FastAPI(title="Explain", lifespan=lifespan)


@app.get("/tickers/{ticker}/moves", response_model=MovesResponse)
async def get_ticker_moves(
    ticker: str,
    start: Annotated[
        date | None, Query(description="First day, inclusive. Default: a year before `end`")
    ] = None,
    end: Annotated[date | None, Query(description="Last day, inclusive. Default: today")] = None,
) -> MovesResponse:
    try:
        return await tickers.get_moves(ticker, start, end)
    except tickers.InvalidDateRangeError as error:
        raise HTTPException(status_code=422, detail=str(error)) from None
    except tickers.TickerNotFoundError:
        raise HTTPException(status_code=404, detail=f"No price data for {ticker.upper()}") from None
