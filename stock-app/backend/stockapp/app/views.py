from rest_framework import viewsets, status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from .models import StockRecord

class StockViewSet(viewsets.ReadOnlyModelViewSet):
    queryset = StockRecord.objects.all()
    serializer_class = StockRecordSerializer

@api_view(['GET'])
def moving_average(request, symbol):
    days = int(request.query_params.get('days', 5))
    records = StockRecord.objects.filter(symbol=symbol).order_by('-date')[:days]
    if not records:
        return Response(status=status.HTTP_404_NOT_FOUND)
    avg = sum(r.close for r in records) / len(records)
    return Response({'symbol': symbol, 'moving_average': float(avg)})