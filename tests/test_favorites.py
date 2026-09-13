# tests/test_favorites.py
"""お気に入り銘柄 API（Issue #50）のテスト。

リポジトリのルートディレクトリから実行する:

    pip install -r requirements-dev.txt
    python -m pytest tests/ -v
"""
import datetime
from unittest import mock

import pytest
from rest_framework.test import APIClient

from stockapp.app.models import FavoriteStock, StockMeta
from stockapp.app.yahoo import fetch_and_save, upsert_stock_meta
from test_api import _patch_yfinance


@pytest.fixture
def api_client():
    """DRF のテストクライアントを返す。"""
    return APIClient()


def _make_favorite(symbol, name="", created_at=None):
    """FavoriteStock を作成し、created_at を明示的に設定して返す。

    auto_now_add フィールドは save() 側で現在時刻に上書きされるため、
    ソート順テストでは queryset.update() で明示的に時刻を書き換える。
    """
    favorite = FavoriteStock.objects.create(symbol=symbol, name=name)
    if created_at is not None:
        FavoriteStock.objects.filter(pk=favorite.pk).update(created_at=created_at)
    favorite.refresh_from_db()
    return favorite


# ---------------------------------------------------------------------------
# GET /api/favorites/ （一覧）
# ---------------------------------------------------------------------------

def test_favorites_list_empty(api_client, db):
    """お気に入りが無い場合は空リストを返すこと。"""
    response = api_client.get("/api/favorites/")
    assert response.status_code == 200
    assert response.json() == []


def test_favorites_list_ordered_by_created_at(api_client, db):
    """一覧が登録日付 (created_at) 順に並び、symbol・name を含むこと。"""
    _make_favorite("MSFT", "Microsoft Corporation", datetime.datetime(2026, 9, 1, 9, 0))
    _make_favorite("AAPL", "Apple Inc.", datetime.datetime(2026, 9, 1, 12, 0))
    _make_favorite("GOOG", "Alphabet Inc.", datetime.datetime(2026, 9, 1, 15, 0))

    response = api_client.get("/api/favorites/")
    assert response.status_code == 200
    data = response.json()
    assert [item["symbol"] for item in data] == ["MSFT", "AAPL", "GOOG"]
    assert data[1] == {"symbol": "AAPL", "name": "Apple Inc."}


# ---------------------------------------------------------------------------
# POST /api/favorites/ （追加）
# ---------------------------------------------------------------------------

def test_favorite_add_success(api_client, db):
    """有効なシンボルは 201 で追加され、StockMeta から銘柄名を引き継ぐこと。"""
    StockMeta.objects.create(symbol="AAPL", name="Apple Inc.")

    response = api_client.post("/api/favorites/", {"symbol": "aapl"}, format="json")
    assert response.status_code == 201
    assert response.json() == {"symbol": "AAPL", "name": "Apple Inc."}
    favorite = FavoriteStock.objects.get(symbol="AAPL")
    assert favorite.name == "Apple Inc."


def test_favorite_add_without_stock_meta_has_empty_name(api_client, db):
    """StockMeta 未キャッシュの場合は空名称で保存し、201 を返すこと。"""
    response = api_client.post("/api/favorites/", {"symbol": "NVDA"}, format="json")
    assert response.status_code == 201
    assert response.json() == {"symbol": "NVDA", "name": ""}


def test_favorite_add_invalid_symbol(api_client, db):
    """無効なシンボルは 400 を返し、行が作成されないこと。"""
    for payload in ({}, {"symbol": None}, {"symbol": ""},
                    {"symbol": "BAD SYMBOL"}, {"symbol": "AAPL!"},
                    {"symbol": "A" * 11}, {"symbol": "aapl;drop"}):
        response = api_client.post("/api/favorites/", payload, format="json")
        assert response.status_code == 400, payload
    assert FavoriteStock.objects.count() == 0



def test_favorite_add_duplicate_returns_409(api_client, db):
    """重複登録は 409 を返すこと。"""
    assert api_client.post("/api/favorites/", {"symbol": "AAPL"}, format="json").status_code == 201
    response = api_client.post("/api/favorites/", {"symbol": "aapl"}, format="json")
    assert response.status_code == 409
    assert FavoriteStock.objects.count() == 1


def test_favorite_add_over_limit_returns_400(api_client, db):
    """上限 (10 件) 超過時は 400 を返し、行が作成されないこと。"""
    for i in range(10):
        _make_favorite(f"SYM{i}")

    response = api_client.post("/api/favorites/", {"symbol": "NEW"}, format="json")
    assert response.status_code == 400
    assert FavoriteStock.objects.count() == 10


# ---------------------------------------------------------------------------
# DELETE /api/favorites/<symbol>/ （削除）
# ---------------------------------------------------------------------------

def test_favorite_delete_success(api_client, db):
    """存在するシンボルは 204 で削除されること。"""
    _make_favorite("AAPL")
    response = api_client.delete("/api/favorites/AAPL/")
    assert response.status_code == 204
    assert FavoriteStock.objects.count() == 0


def test_favorite_delete_not_found(api_client, db):
    """未登録のシンボル削除は 404 を返すこと。"""
    response = api_client.delete("/api/favorites/NOSUCH/")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# StockMeta からの銘柄名自動同期 (Issue #50)
# ---------------------------------------------------------------------------

def test_upsert_stock_meta_syncs_favorite_name(db):
    """upsert_stock_meta は同名シンボルの FavoriteStock.name を同期すること。"""
    _make_favorite("AAPL", name="")
    upsert_stock_meta("AAPL", "Apple Inc.")
    assert FavoriteStock.objects.get(symbol="AAPL").name == "Apple Inc."


def test_upsert_stock_meta_syncs_empty_name(db):
    """StockMeta 側が空文字（負のキャッシュ）でも FavoriteStock 側に同期すること。"""
    _make_favorite("AAPL", name="Apple Inc.")
    upsert_stock_meta("AAPL", "")
    assert FavoriteStock.objects.get(symbol="AAPL").name == ""


def test_stock_meta_endpoint_syncs_favorite_name(api_client, db):
    """GET /api/stocks/<symbol>/meta/ 経由でもお気に入り銘柄名が同期されること。"""
    _make_favorite("AAPL", name="")
    with mock.patch("stockapp.app.views.fetch_stock_name", return_value="Apple Inc."):
        response = api_client.get("/api/stocks/AAPL/meta/")
    assert response.status_code == 200
    assert FavoriteStock.objects.get(symbol="AAPL").name == "Apple Inc."


def test_fetch_and_save_syncs_favorite_name(db):
    """fetch_and_save（Yahoo 取得フロー）でもお気に入り銘柄名が同期されること。"""
    _make_favorite("AAPL", name="")
    with _patch_yfinance({"shortName": "Apple Inc."}):
        fetch_and_save("AAPL", period="5d")
    assert FavoriteStock.objects.get(symbol="AAPL").name == "Apple Inc."
    assert StockMeta.objects.get(symbol="AAPL").name == "Apple Inc."