from django.urls import path, include
from rest_framework.routers import DefaultRouter
from stockapp.app.views import StockViewSet, moving_average

router = DefaultRouter()
router.register(r'stocks', StockViewSet, basename='stock')

urlpatterns = [
    path('api/', include(router.urls)),
    path('api/ma/<str:symbol>/', moving_average),
]