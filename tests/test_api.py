# tests/test_api.py
"""株価 API（Django/DRF）のテスト。

リポジトリのルートディレクトリから実行する:

    pip install -r requirements-dev.txt
    python -m pytest tests/ -v
"""
import datetime
from unittest import mock

import pytest
from rest_framework.test import APIClient

from stockapp.app.models import StockRecord
from stockapp.app.yahoo import StockFetchError


@pytest.fixture
def api_client():
    """DRF のテストクライアントを返す。"""
    return APIClient()


@pytest.fixture
def stock_records(db):
    """テストデータを投入する: AAPL（5 営業日分）と GOOG（1 日分）。

    db フィクスチャはテストごとにトランザクションでロールバックされる。
    """
    base = datetime.date(2026, 9, 11)
    closes = [150.0, 152.0, 151.0, 155.0, 154.0]
    objects = [
        StockRecord(
            symbol="AAPL",
            date=base - datetime.timedelta(days=5 - i),
            close=str(c),
        )
        for i, c in enumerate(closes)
    ]
    objects.append(StockRecord(symbol="GOOG", date=base, close="100.0"))
    StockRecord.objects.bulk_create(objects)
    return objects


# ---------------------------------------------------------------------------
# GET /api/stocks/ （全銘柄リスト）
# ---------------------------------------------------------------------------

def test_stock_list(api_client, stock_records):
    """/api/stocks/ が 200 を返し、全レコードのリストを返すこと。"""
    response = api_client.get("/api/stocks/")
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) == 6
    first = data[0]
    for key in ("id", "symbol", "date", "close"):
        assert key in first


# ---------------------------------------------------------------------------
# GET /api/stocks/<symbol>/ （シンボル指定の株価一覧）
# ---------------------------------------------------------------------------

def test_stock_list_by_symbol(api_client, stock_records):
    """/api/stocks/AAPL/ が AAPL のみを日付降順で返すこと。"""
    response = api_client.get("/api/stocks/AAPL/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 5
    assert all(record["symbol"] == "AAPL" for record in data)
    dates = [record["date"] for record in data]
    assert dates == sorted(dates, reverse=True)


def test_stock_list_unknown_symbol_returns_empty(api_client, stock_records):
    """データのないシンボルは空リストを返すこと。"""
    response = api_client.get("/api/stocks/NOSUCH/")
    assert response.status_code == 200
    assert response.json() == []


def test_stock_list_by_symbol_without_slash(api_client, stock_records):
    """trailing slash なし呼び出し（フロントエンドの実リクエスト形態）が
    リダイレクト解決されてデータを取得できること。"""
    response = api_client.get("/api/stocks/AAPL", follow=True)
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 5


# ---------------------------------------------------------------------------
# GET /api/moving_average/<symbol>/ （移動平均）
# ---------------------------------------------------------------------------

def test_moving_average(api_client, stock_records):
    """最新 3 日の平均が正しく計算されること: (151+155+154)/3 = 153.33..."""
    response = api_client.get("/api/moving_average/AAPL/?days=3")
    assert response.status_code == 200
    data = response.json()
    assert data["symbol"] == "AAPL"
    assert data["moving_average"] == pytest.approx(153.33333333333334)


def test_moving_average_default_days(api_client, stock_records):
    """days 未指定時は 5 日が既定値になること: (150+152+151+155+154)/5 = 152.4。"""
    response = api_client.get("/api/moving_average/AAPL/")
    assert response.status_code == 200
    assert response.json()["moving_average"] == pytest.approx(152.4)


def test_moving_average_unknown_symbol_404(api_client, stock_records):
    """データのないシンボルは 404 を返すこと。"""
    response = api_client.get("/api/moving_average/NOSUCH/")
    assert response.status_code == 404


@pytest.mark.parametrize(
    "query",
    ["?days=abc", "?days=-1", "?days=0", "?days="],
    ids=["not-int", "negative", "zero", "empty"],
)
def test_moving_average_invalid_days_400(api_client, stock_records, query):
    """days が不正（非整数・1 未満）なときは 500 ではなく 400 を返すこと。"""
    response = api_client.get(f"/api/moving_average/AAPL/{query}")
    assert response.status_code == 400


# ---------------------------------------------------------------------------
# POST /api/stocks/fetch/ （Yahoo Finance 株価取得・保存 / Issue #23）
# ---------------------------------------------------------------------------

def test_stock_list_includes_ohlcv(api_client, stock_records):
    """株価リストが open/high/low/volume キーも含むこと。"""
    response = api_client.get("/api/stocks/")
    assert response.status_code == 200
    first = response.json()[0]
    for key in ("open", "high", "low", "volume"):
        assert key in first


@pytest.mark.parametrize(
    "payload",
    [
        {"symbol": "AAPL", "period": "99x"},
        {"symbol": "BAD SYMBOL", "period": "1mo"},
        {"period": "1mo"},
        {},
    ],
    ids=["bad-period", "bad-symbol", "no-symbol", "empty"],
)
def test_stock_fetch_validation(api_client, payload):
    """symbol/period が不正なときは 400 を返すこと（Yahoo は呼ばない）。"""
    with mock.patch(
        "stockapp.app.views.fetch_and_save",
        side_effect=AssertionError("不正な入力で呼ばれるべきではない"),
    ):
        response = api_client.post("/api/stocks/fetch/", payload, format="json")
    assert response.status_code == 400


def test_stock_fetch_success(api_client, db):
    """取得に成功すれば DB に保存され、保存結果を返すこと。"""

    def fake_fetch_and_save(symbol, period="1mo"):
        StockRecord.objects.create(
            symbol=symbol,
            date=datetime.date(2026, 9, 11),
            open="150.5000", high="155.0000", low="150.0000",
            close="154.0000", volume=1000,
        )
        return {
            "symbol": symbol, "period": period, "fetched": 1,
            "created": 1, "updated": 0,
            "start_date": "2026-09-11", "end_date": "2026-09-11",
        }

    with mock.patch(
        "stockapp.app.views.fetch_and_save",
        side_effect=fake_fetch_and_save,
    ):
        response = api_client.post(
            "/api/stocks/fetch/", {"symbol": "aapl", "period": "5d"}, format="json"
        )

    assert response.status_code == 200
    data = response.json()
    assert data["fetched"] == 1
    assert data["created"] == 1
    # シンボルは大文字に正規化されて保存される
    assert data["symbol"] == "AAPL"
    assert StockRecord.objects.filter(symbol="AAPL").count() == 1


def test_stock_fetch_no_data_404(api_client):
    """Yahoo からデータが返らない（未知のシンボル等）ときは 404 を返すこと。"""
    with mock.patch(
        "stockapp.app.views.fetch_and_save",
        side_effect=LookupError("該当社種 NOSUCH の株価データがありませんでした"),
    ):
        response = api_client.post(
            "/api/stocks/fetch/", {"symbol": "NOSUCH", "period": "1mo"}, format="json"
        )
    assert response.status_code == 404


def test_stock_fetch_yahoo_error_502(api_client):
    """Yahoo Finance への通信に失敗したときは 500 ではなく 502 を返すこと。"""
    with mock.patch(
        "stockapp.app.views.fetch_and_save",
        side_effect=StockFetchError("Yahoo Finance の取得に失敗しました"),
    ):
        response = api_client.post(
            "/api/stocks/fetch/", {"symbol": "AAPL", "period": "1mo"}, format="json"
        )
    assert response.status_code == 502


