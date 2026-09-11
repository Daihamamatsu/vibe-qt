# tests/test_api.py
"""株価 API（Django/DRF）のテスト。

リポジトリのルートディレクトリから実行する:

    pip install -r requirements-dev.txt
    python -m pytest tests/ -v
"""
import datetime

import pytest
from rest_framework.test import APIClient

from stockapp.app.models import StockRecord


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


