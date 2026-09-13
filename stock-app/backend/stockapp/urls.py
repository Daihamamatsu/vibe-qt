from django.urls import path
from stockapp.app.views import (
    favorite_delete,
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
    # お気に入り銘柄 API (Issue #50): /api/favorites/ は /api/stocks/ と無関係な
    # 独立プレフィックスなので <str:symbol> ルートと衝突しない
    path('api/favorites/', favorites),
    path('api/favorites/<str:symbol>/', favorite_delete),
    path('api/stocks/', stock_list_all),
]
