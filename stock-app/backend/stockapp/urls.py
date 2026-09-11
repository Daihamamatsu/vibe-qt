from django.urls import path
from stockapp.app.views import moving_average, stock_fetch, stock_list_all, stock_list_by_symbol

# ルート定義（順序が重要）:
# - api/stocks/fetch/ は api/stocks/<str:symbol>/ より前に置くこと
#   （置くと "fetch" がシンボルとして先取りされる）
# - シンボル指定ルート `/api/stocks/<str:symbol>/` が '/api/stocks/AAPL/' 等の
#   全シンボル文字列をマッチするため、汎用的な router（{pk} パターン）を
#   使わない。以前は router の {pk} がシンボル文字列を先取りして 500 を
#   出していた（Issue #19）。
urlpatterns = [
    path('api/stocks/fetch/', stock_fetch),
    path('api/stocks/<str:symbol>/', stock_list_by_symbol),
    path('api/moving_average/<str:symbol>/', moving_average),
    path('api/stocks/', stock_list_all),
]
