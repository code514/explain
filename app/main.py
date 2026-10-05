from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.migrations import run_migrations
from app.schemas import HelloWorldResponse


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncGenerator[None]:
    run_migrations()
    yield


app = FastAPI(title="Explain", lifespan=lifespan)


@app.get("/hello-world", response_model=HelloWorldResponse)
async def hello_world() -> HelloWorldResponse:
    return HelloWorldResponse(message="Hello, world!")
