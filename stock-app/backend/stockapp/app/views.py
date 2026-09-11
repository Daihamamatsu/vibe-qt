from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from .models import StockRecord
from .serializers import StockRecordSerializer


@api_view(['GET'])
def stock_list_all(request):
    """GET /api/stocks/ — 全銘柄の株価一覧（日付降順）。"""
    records = StockRecord.objects.all().order_by('-date')
    serializer = StockRecordSerializer(records, many=True)
    return Response(serializer.data)


@api_view(['GET'])
def stock_list_by_symbol(request, symbol):
    """GET /api/stocks/<symbol>/ — 指定シンボルの株価一覧（日付降順）。"""
    records = StockRecord.objects.filter(symbol=symbol).order_by('-date')
    serializer = StockRecordSerializer(records, many=True)
    return Response(serializer.data)


@api_view(['GET'])
def moving_average(request, symbol):
    """GET /api/moving_average/<symbol>/ — 直近 days 日（既定 5）の終値移動平均。"""
    # days クエリパラメータをバリデーション: 非整数・1 未満は 400（500 を避ける）
    try:
        days = int(request.query_params.get('days', 5))
    except (TypeError, ValueError):
        return Response(status=status.HTTP_400_BAD_REQUEST)
    if days < 1:
        return Response(status=status.HTTP_400_BAD_REQUEST)
    records = StockRecord.objects.filter(symbol=symbol).order_by('-date')[:days]
    if not records:
        return Response(status=status.HTTP_404_NOT_FOUND)
    avg = sum(r.close for r in records) / len(records)
    return Response({'symbol': symbol, 'moving_average': float(avg)})
