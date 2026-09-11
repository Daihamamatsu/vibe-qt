from django.urls import path, include
from rest_framework.routers import DefaultRouter
from stockapp.app.views import StockViewSet, moving_average, stock_list_by_symbol

router = DefaultRouter()
router.register(r'stocks', StockViewSet, basename='stock')

urlpatterns = [
    # シンボル指定エンドポイントは router より前に配置する
    # （router の {pk} パターンが 'AAPL' 等の文字列を先取りするため）
    path('api/stocks/<str:symbol>/', stock_list_by_symbol),
    path('api/moving_average/<str:symbol>/', moving_average),
    path('api/', include(router.urls)),
]
