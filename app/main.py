from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from datetime import date
from typing import Annotated

from fastapi import FastAPI, HTTPException, Query

from app.controllers import tickers
from app.migrations import run_migrations
from app.schemas import TickerResponse


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
    run_migrations()
    yield


app = FastAPI(title="Explain", lifespan=lifespan)


@app.get("/tickers/{ticker}", response_model=TickerResponse)
async def get_ticker(
    ticker: str,
    start: Annotated[
        date | None, Query(description="First day, inclusive. Default: a year before `end`")
    ] = None,
    end: Annotated[date | None, Query(description="Last day, inclusive. Default: today")] = None,
) -> TickerResponse:
    try:
        return await tickers.get_ticker(ticker, start, end)
    except tickers.InvalidDateRangeError as error:
        raise HTTPException(status_code=422, detail=str(error)) from None
    except tickers.TickerNotFoundError:
        raise HTTPException(status_code=404, detail=f"No price data for {ticker.upper()}") from None
