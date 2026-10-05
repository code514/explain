import pytest
from fastapi.testclient import TestClient

from app.controllers import tickers
from app.schemas import TickerResponse


def test_ticker_route(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get_ticker(ticker: str, start, end) -> TickerResponse:
        return TickerResponse(moves=[], major_moves=[])

    monkeypatch.setattr(tickers, "get_ticker", fake_get_ticker)

    response = client.get("/tickers/nvda", params={"start": "2025-03-01", "end": "2025-03-05"})

    assert response.status_code == 200
    assert response.json() == {"moves": [], "majorMoves": []}


def test_ticker_route_unknown_ticker_is_404(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def not_found(ticker: str, start, end) -> TickerResponse:
        raise tickers.TickerNotFoundError(ticker)

    monkeypatch.setattr(tickers, "get_ticker", not_found)

    assert client.get("/tickers/BOGUS").status_code == 404


def test_ticker_route_rejects_inverted_range(client: TestClient) -> None:
    response = client.get("/tickers/NVDA", params={"start": "2025-03-05", "end": "2025-03-01"})
    assert response.status_code == 422
