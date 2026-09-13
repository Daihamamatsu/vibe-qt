# tests/test_favorites.py
"""お気に入り銘柄 API（複数リスト化、Issue #50）のテスト。

リポジトリのルートディレクトリから実行する:

    pip install -r requirements-dev.txt
    python -m pytest tests/ -v
"""
import datetime
from unittest import mock

import pytest
from rest_framework.test import APIClient

from stockapp.app.models import FavoriteStock, StockList, StockMeta
from stockapp.app.yahoo import fetch_and_save, upsert_stock_meta
from test_api import _patch_yfinance


@pytest.fixture
def api_client():
    """DRF のテストクライアントを返す。"""
    return APIClient()


def _make_favorite(symbol, name="", created_at=None, list_name="リスト1"):
    """FavoriteStock を作成し、created_at を明示的に設定して返す。

    auto_now_add フィールドは save() 側で現在時刻に上書きされるため、
    ソート順テストでは queryset.update() で明示的に時刻を書き換える。
    """
    stock_list = StockList.objects.get(name=list_name)
    favorite = FavoriteStock.objects.create(list=stock_list, symbol=symbol, name=name)
    if created_at is not None:
        FavoriteStock.objects.filter(pk=favorite.pk).update(created_at=created_at)
    favorite.refresh_from_db()
    return favorite


# ---------------------------------------------------------------------------
# 移行 0005_stocklist: 初期 10 リストのシード
# ---------------------------------------------------------------------------

def test_default_lists_seeded(db):
    """移行後に リスト1〜リスト10 が存在すること。"""
    names = list(StockList.objects.order_by("id").values_list("name", flat=True))
    assert names == [f"リスト{i}" for i in range(1, 11)]


# ---------------------------------------------------------------------------
# GET /api/favorite-lists/ （リスト一覧）
# ---------------------------------------------------------------------------

def test_favorite_lists_returns_seeded(api_client, db):
    """初期 10 リストが id・name・count を付けて返ること。"""
    response = api_client.get("/api/favorite-lists/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 10
    assert all(item["count"] == 0 for item in data)
    assert {item["name"] for item in data} == {f"リスト{i}" for i in range(1, 11)}
    assert all(set(item.keys()) == {"id", "name", "count"} for item in data)


def test_favorite_lists_counts_reflect_memberships(api_client, db):
    """count が各リストの所属銘柄数を反映すること。"""
    _make_favorite("AAPL", list_name="リスト2")
    response = api_client.get("/api/favorite-lists/")
    counts = {item["name"]: item["count"] for item in response.json()}
    assert counts["リスト2"] == 1
    assert counts["リスト1"] == 0


# ---------------------------------------------------------------------------
# POST /api/favorite-lists/ （リスト作成）
# ---------------------------------------------------------------------------

def test_create_list_success(api_client, db):
    """新しい名前のリストは 201 で作成されること。"""
    response = api_client.post("/api/favorite-lists/", {"name": "私のリスト"}, format="json")
    assert response.status_code == 201
    body = response.json()
    assert body["name"] == "私のリスト"
    assert "id" in body
    assert StockList.objects.filter(name="私のリスト").count() == 1


def test_create_list_invalid_name(api_client, db):
    """空文字・50 字超過の名前は 400 を返し、リストが作成されないこと。"""
    for payload in ({}, {"name": None}, {"name": "  "}, {"name": "A" * 51}):
        response = api_client.post("/api/favorite-lists/", payload, format="json")
        assert response.status_code == 400, payload
    assert StockList.objects.count() == 10


def test_create_list_strips_whitespace(api_client, db):
    """前後空白は除去されて保存されること。"""
    response = api_client.post("/api/favorite-lists/", {"name": "  テスト  "}, format="json")
    assert response.status_code == 201
    assert StockList.objects.filter(name="テスト").exists()


def test_create_list_duplicate_returns_409(api_client, db):
    """同名リストが既に存在するなら 409 を返すこと。"""
    response = api_client.post("/api/favorite-lists/", {"name": "リスト1"}, format="json")
    assert response.status_code == 409
    assert StockList.objects.filter(name="リスト1").count() == 1


# ---------------------------------------------------------------------------
# PATCH/PUT /api/favorite-lists/<id>/ （名前変更）
# ---------------------------------------------------------------------------

def test_rename_list_success(api_client, db):
    """PATCH で名前を変更できること。"""
    stock_list = StockList.objects.get(name="リスト3")
    response = api_client.patch(
        f"/api/favorite-lists/{stock_list.id}/", {"name": "改名リスト"}, format="json"
    )
    assert response.status_code == 200
    assert response.json()["name"] == "改名リスト"
    stock_list.refresh_from_db()
    assert stock_list.name == "改名リスト"


def test_rename_list_put_also_works(api_client, db):
    """PUT でも名前を変更できること。"""
    stock_list = StockList.objects.get(name="リスト3")
    response = api_client.put(
        f"/api/favorite-lists/{stock_list.id}/", {"name": "PUTリスト"}, format="json"
    )
    assert response.status_code == 200
    stock_list.refresh_from_db()
    assert stock_list.name == "PUTリスト"


def test_rename_list_invalid_name(api_client, db):
    """空文字・50 字超過の名前は 400 を返すこと。"""
    stock_list = StockList.objects.get(name="リスト3")
    for payload in ({}, {"name": "  "}, {"name": "A" * 51}):
        response = api_client.patch(
            f"/api/favorite-lists/{stock_list.id}/", payload, format="json"
        )
        assert response.status_code == 400, payload
    stock_list.refresh_from_db()
    assert stock_list.name == "リスト3"


def test_rename_list_not_found(api_client, db):
    """存在しないリスト ID は 404 を返すこと。"""
    response = api_client.patch("/api/favorite-lists/999/", {"name": "X"}, format="json")
    assert response.status_code == 404


def test_rename_list_duplicate_returns_409(api_client, db):
    """既存の他リストと同じ名前に変更すると 409 を返すこと。"""
    stock_list = StockList.objects.get(name="リスト3")
    response = api_client.patch(
        f"/api/favorite-lists/{stock_list.id}/", {"name": "リスト4"}, format="json"
    )
    assert response.status_code == 409
    stock_list.refresh_from_db()
    assert stock_list.name == "リスト3"


# ---------------------------------------------------------------------------
# DELETE /api/favorite-lists/<id>/ （リスト削除）
# ---------------------------------------------------------------------------

def test_delete_list_success(api_client, db):
    """リスト削除は 204 を返し、リスト内の所属行も削除されること。"""
    stock_list = StockList.objects.get(name="リスト5")
    _make_favorite("AAPL", list_name="リスト5")
    _make_favorite("MSFT", list_name="リスト5")

    response = api_client.delete(f"/api/favorite-lists/{stock_list.id}/")
    assert response.status_code == 204
    assert StockList.objects.filter(id=stock_list.id).count() == 0
    # リスト内の所属行は CASCADE で消える（他リストへの所属は保持される）
    _make_favorite("AAPL", list_name="リスト6")
    assert FavoriteStock.objects.filter(list=stock_list).count() == 0
    assert FavoriteStock.objects.filter(symbol="AAPL").count() == 1


def test_delete_list_not_found(api_client, db):
    """存在しないリスト ID は 404 を返すこと。"""
    response = api_client.delete("/api/favorite-lists/999/")
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# GET /api/favorites/ （リスト別の銘柄グループ）
# ---------------------------------------------------------------------------

def test_favorites_grouped_includes_empty_lists(api_client, db):
    """全リスト（空リスト含む）と、その所属銘柄を返すこと。"""
    _make_favorite("AAPL", name="Apple Inc.", list_name="リスト1")
    _make_favorite("MSFT", name="Microsoft Corporation", list_name="リスト1")

    response = api_client.get("/api/favorites/")
    assert response.status_code == 200
    data = response.json()
    assert len(data) == 10  # 空リストも含めた全リスト
    list1 = next(item for item in data if item["name"] == "リスト1")
    assert list1["stocks"] == [
        {"symbol": "AAPL", "name": "Apple Inc."},
        {"symbol": "MSFT", "name": "Microsoft Corporation"},
    ]
    list2 = next(item for item in data if item["name"] == "リスト2")
    assert list2["stocks"] == []


def test_favorites_stocks_ordered_by_created_at(api_client, db):
    """リスト内の銘柄は登録日付 (created_at) 順に並ぶこと。"""
    _make_favorite("MSFT", created_at=datetime.datetime(2026, 9, 1, 9, 0), list_name="リスト3")
    _make_favorite("AAPL", created_at=datetime.datetime(2026, 9, 1, 12, 0), list_name="リスト3")
    _make_favorite("GOOG", created_at=datetime.datetime(2026, 9, 1, 15, 0), list_name="リスト3")

    response = api_client.get("/api/favorites/")
    list3 = next(item for item in response.json() if item["name"] == "リスト3")
    assert [s["symbol"] for s in list3["stocks"]] == ["MSFT", "AAPL", "GOOG"]
    assert list3["stocks"][1] == {"symbol": "AAPL", "name": ""}


# ---------------------------------------------------------------------------
# POST /api/favorites/ （リストへの銘柄追加）
# ---------------------------------------------------------------------------

def test_favorite_add_success(api_client, db):
    """有効なシンボルは 201 で追加され、StockMeta から銘柄名を引き継ぐこと。"""
    StockMeta.objects.create(symbol="AAPL", name="Apple Inc.")
    list1 = StockList.objects.get(name="リスト1")

    response = api_client.post(
        "/api/favorites/", {"symbol": "aapl", "list_id": list1.id}, format="json"
    )
    assert response.status_code == 201
    assert response.json() == {"symbol": "AAPL", "name": "Apple Inc.", "list_id": list1.id}
    favorite = FavoriteStock.objects.get(symbol="AAPL")
    assert favorite.list_id == list1.id
    assert favorite.name == "Apple Inc."


def test_favorite_add_without_stock_meta_has_empty_name(api_client, db):
    """StockMeta 未キャッシュの場合は空名称で保存し、201 を返すこと。"""
    list1 = StockList.objects.get(name="リスト1")
    response = api_client.post(
        "/api/favorites/", {"symbol": "NVDA", "list_id": list1.id}, format="json"
    )
    assert response.status_code == 201
    assert response.json() == {"symbol": "NVDA", "name": "", "list_id": list1.id}


def test_favorite_add_invalid_symbol(api_client, db):
    """無効なシンボルは 400 を返し、行が作成されないこと。"""
    list1 = StockList.objects.get(name="リスト1")
    for symbol in (None, "", "BAD SYMBOL", "AAPL!", "A" * 11, "aapl;drop"):
        response = api_client.post(
            "/api/favorites/", {"symbol": symbol, "list_id": list1.id}, format="json"
        )
        assert response.status_code == 400, symbol
    assert FavoriteStock.objects.count() == 0


def test_favorite_add_missing_list_id(api_client, db):
    """list_id が無い・不正な場合は 400 を返し、行が作成されないこと。"""
    for list_id in (None, True, -1, "1"):
        response = api_client.post(
            "/api/favorites/", {"symbol": "AAPL", "list_id": list_id}, format="json"
        )
        assert response.status_code == 400, list_id
    response = api_client.post("/api/favorites/", {"symbol": "AAPL"}, format="json")
    assert response.status_code == 400
    assert FavoriteStock.objects.count() == 0


def test_favorite_add_unknown_list_returns_404(api_client, db):
    """存在しない list_id は 404 を返し、行が作成されないこと。"""
    response = api_client.post(
        "/api/favorites/", {"symbol": "AAPL", "list_id": 999}, format="json"
    )
    assert response.status_code == 404
    assert FavoriteStock.objects.count() == 0


def test_favorite_add_same_list_duplicate_returns_409(api_client, db):
    """同一リスト内での重複登録は 409 を返すこと。"""
    list1 = StockList.objects.get(name="リスト1")
    assert api_client.post(
        "/api/favorites/", {"symbol": "AAPL", "list_id": list1.id}, format="json"
    ).status_code == 201
    response = api_client.post(
        "/api/favorites/", {"symbol": "aapl", "list_id": list1.id}, format="json"
    )
    assert response.status_code == 409
    assert FavoriteStock.objects.filter(symbol="AAPL").count() == 1


def test_favorite_add_same_symbol_to_another_list_ok(api_client, db):
    """同じシンボルでも別のリストへの追加は 201 を返すこと（複数リスト所属）。"""
    list1 = StockList.objects.get(name="リスト1")
    list2 = StockList.objects.get(name="リスト2")
    assert api_client.post(
        "/api/favorites/", {"symbol": "AAPL", "list_id": list1.id}, format="json"
    ).status_code == 201
    response = api_client.post(
        "/api/favorites/", {"symbol": "AAPL", "list_id": list2.id}, format="json"
    )
    assert response.status_code == 201
    assert FavoriteStock.objects.filter(symbol="AAPL").count() == 2


# ---------------------------------------------------------------------------
# DELETE /api/favorites/<list_id>/<symbol>/ （リストからの銘柄削除）
# ---------------------------------------------------------------------------

def test_favorite_delete_success(api_client, db):
    """指定リストから銘柄を削除すると 204 を返すこと。"""
    _make_favorite("AAPL", list_name="リスト1")
    list1 = StockList.objects.get(name="リスト1")

    response = api_client.delete(f"/api/favorites/{list1.id}/AAPL/")
    assert response.status_code == 204
    assert FavoriteStock.objects.filter(symbol="AAPL").count() == 0


def test_favorite_delete_not_in_list_returns_404(api_client, db):
    """対象リストに未登録の銘柄削除は 404 を返し、他リストの所属に影響しないこと。"""
    _make_favorite("AAPL", list_name="リスト1")
    list2 = StockList.objects.get(name="リスト2")

    response = api_client.delete(f"/api/favorites/{list2.id}/AAPL/")
    assert response.status_code == 404
    assert FavoriteStock.objects.filter(symbol="AAPL").count() == 1


def test_favorite_delete_keeps_other_lists(api_client, db):
    """複数リスト所属の銘柄を 1 つのリストから削除しても他リストの所属は保持されること。"""
    _make_favorite("AAPL", list_name="リスト1")
    _make_favorite("AAPL", list_name="リスト2")
    list1 = StockList.objects.get(name="リスト1")

    response = api_client.delete(f"/api/favorites/{list1.id}/AAPL/")
    assert response.status_code == 204
    remaining = FavoriteStock.objects.filter(symbol="AAPL")
    assert remaining.count() == 1
    assert remaining.first().list_id == StockList.objects.get(name="リスト2").id


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