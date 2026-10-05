import pytest
from fastapi.testclient import TestClient

from app.controllers import tickers
from app.schemas import MovesResponse


def test_moves_route(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    async def fake_get_moves(ticker: str, start, end) -> MovesResponse:
        return MovesResponse(ticker=ticker.upper(), start=start, end=end, moves=[])

    monkeypatch.setattr(tickers, "get_moves", fake_get_moves)

    response = client.get(
        "/tickers/nvda/moves", params={"start": "2025-03-01", "end": "2025-03-05"}
    )

    assert response.status_code == 200
    assert response.json() == {
        "ticker": "NVDA",
        "start": "2025-03-01",
        "end": "2025-03-05",
        "moves": [],
    }


def test_moves_route_unknown_ticker_is_404(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    async def not_found(ticker: str, start, end) -> MovesResponse:
        raise tickers.TickerNotFoundError(ticker)

    monkeypatch.setattr(tickers, "get_moves", not_found)

    assert client.get("/tickers/BOGUS/moves").status_code == 404


def test_moves_route_rejects_inverted_range(client: TestClient) -> None:
    response = client.get(
        "/tickers/NVDA/moves", params={"start": "2025-03-05", "end": "2025-03-01"}
    )
    assert response.status_code == 422
