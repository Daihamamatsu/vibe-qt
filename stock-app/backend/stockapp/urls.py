from django.urls import path
from stockapp.app.views import (
    favorite_delete,
    favorite_list_detail,
    favorite_lists,
    favorites,
    moving_average,
    stock_fetch,
    stock_list_all,
    stock_list_by_symbol,
    stock_meta,
)

# ルート定義（順序が重要）:
# - api/stocks/fetch/ は api/stocks/<str:symbol>/ より前に置くこと
#   （置くと "fetch" がシンボルとして先取りされる）
# - シンボル指定ルート `/api/stocks/<str:symbol>/` が '/api/stocks/AAPL/' 等の
#   全シンボル文字列をマッチするため、汎用的な router（{pk} パターン）を
#   使わない。以前は router の {pk} がシンボル文字列を先取りして 500 を
#   出していた（Issue #19）。
urlpatterns = [
    path('api/stocks/fetch/', stock_fetch),
    # meta ルートは <str:symbol> ルートより前に置く（"AAPL" の後続セグメントを
    # シンボル先取りで 404 にしないため）
    path('api/stocks/<str:symbol>/meta/', stock_meta),
    path('api/stocks/<str:symbol>/', stock_list_by_symbol),
    path('api/moving_average/<str:symbol>/', moving_average),
    # お気に入り銘柄 API (Issue #50): /api/favorites/ と /api/favorite-lists/ は
    # /api/stocks/ と無関係な独立プレフィックスなので <str:symbol> ルートと衝突しない
    # 銘柄リスト（複数リスト化）
    path('api/favorite-lists/', favorite_lists),
    path('api/favorite-lists/<int:list_id>/', favorite_list_detail),
    # お気に入り銘柄（リスト別）: 削除は /api/favorites/<list_id>/<symbol>/
    path('api/favorites/', favorites),
    path('api/favorites/<int:list_id>/<str:symbol>/', favorite_delete),
    path('api/stocks/', stock_list_all),
]
