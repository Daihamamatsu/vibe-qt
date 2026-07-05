from django.urls import path, include
from rest_framework.routers import DefaultRouter
from stockapp.app.views import StockViewSet, moving_average, stock_list_by_symbol

router = DefaultRouter()
router.register(r'stocks', StockViewSet, basename='stock')

urlpatterns = [
    path('api/', include(router.urls)),
    path('api/moving_average/<str:symbol>/', moving_average),
    path('api/stocks/<str:symbol>/', stock_list_by_symbol),
]
