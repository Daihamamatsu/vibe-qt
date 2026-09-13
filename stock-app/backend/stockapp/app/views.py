from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from .models import StockMeta, StockRecord
from .serializers import StockRecordSerializer
from .yahoo import SYMBOL_RE, VALID_PERIODS, StockFetchError, fetch_and_save, fetch_stock_name


@api_view(['POST'])
def stock_fetch(request):
    """POST /api/stocks/fetch/ — Yahoo Finance から日足株価を取得して DB に保存。

    リクエストボディ: {"symbol": "AAPL", "period": "1mo"}
    period: 5d / 1mo / 3mo / 6mo / 1y / 2y / 5y
    """
    data = request.data if isinstance(request.data, dict) else {}
    symbol = str(data.get('symbol') or '').strip().upper()
    period = str(data.get('period') or '1mo')
    if not SYMBOL_RE.match(symbol):
        return Response(
            {'detail': f'invalid symbol: {symbol}'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if period not in VALID_PERIODS:
        return Response(
            {'detail': f'invalid period: {period}'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    try:
        result = fetch_and_save(symbol, period)
    except LookupError as exc:
        return Response({'detail': str(exc)}, status=status.HTTP_404_NOT_FOUND)
    except StockFetchError as exc:
        return Response({'detail': str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
    return Response(result)


@api_view(['GET'])
def stock_meta(request, symbol):
    """GET /api/stocks/<symbol>/meta/ — 銘柄名（メタ情報）(Issue #49)。

    DB に StockMeta 行があれば（name が空の場合 = 負のキャッシュも含む）それを返す。
    行がない場合は Yahoo Finance から取得（best effort）して DB 保存の上で返す。
    """
    if not SYMBOL_RE.match(symbol):
        return Response(
            {'detail': f'invalid symbol: {symbol}'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    meta = StockMeta.objects.filter(symbol=symbol).first()
    if meta is None:
        meta, _ = StockMeta.objects.update_or_create(
            symbol=symbol,
            defaults={'name': fetch_stock_name(symbol)},
        )
    return Response({'symbol': symbol, 'name': meta.name})


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
