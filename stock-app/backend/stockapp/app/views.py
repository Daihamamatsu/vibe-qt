from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from .models import FavoriteStock, StockMeta, StockRecord
from .serializers import StockRecordSerializer
from .yahoo import (
    SYMBOL_RE,
    VALID_PERIODS,
    StockFetchError,
    fetch_and_save,
    fetch_stock_name,
    upsert_stock_meta,
)

# お気に入り銘柄の保存上限（Issue #50）
FAVORITE_LIMIT = 10


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
        # 初回取得時は Yahoo Finance から取得（best effort）して DB 保存する。
        # upsert_stock_meta はお気に入り銘柄の name も同期する (Issue #50)
        upsert_stock_meta(symbol, fetch_stock_name(symbol))
        meta = StockMeta.objects.get(symbol=symbol)
    return Response({'symbol': symbol, 'name': meta.name})


@api_view(['GET', 'POST'])
def favorites(request):
    """/api/favorites/ — お気に入り銘柄の一覧・追加 (Issue #50)。

    GET: 登録済みのお気に入りを登録日付 (created_at) 順に返す。
    POST: リクエストボディ {"symbol": "AAPL"} で追加する。
        201 = 追加成功、400 = シンボル不正・上限超過、409 = 重複登録。
    """
    if request.method == 'POST':
        data = request.data if isinstance(request.data, dict) else {}
        symbol = str(data.get('symbol') or '').strip().upper()
        if not SYMBOL_RE.match(symbol):
            return Response(
                {'detail': f'invalid symbol: {symbol}'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if FavoriteStock.objects.filter(symbol=symbol).exists():
            return Response(
                {'detail': f'favorite exists: {symbol}'},
                status=status.HTTP_409_CONFLICT,
            )
        if FavoriteStock.objects.count() >= FAVORITE_LIMIT:
            return Response(
                {'detail': f'max favorites: {FAVORITE_LIMIT}'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        # 銘柄名は StockMeta と同期 (Issue #50)。未キャッシュなら空文字で保存し、
        # 後日の株価取得 (fetch_and_save) で StockMeta 更新時に自動反映される
        meta = StockMeta.objects.filter(symbol=symbol).first()
        name = meta.name if meta is not None else ''
        FavoriteStock.objects.create(symbol=symbol, name=name)
        return Response({'symbol': symbol, 'name': name}, status=status.HTTP_201_CREATED)

    records = FavoriteStock.objects.all().order_by('created_at', 'symbol')
    return Response([{'symbol': f.symbol, 'name': f.name} for f in records])


@api_view(['DELETE'])
def favorite_delete(request, symbol):
    """/api/favorites/<symbol>/ — お気に入り銘柄の削除 (Issue #50)。"""
    deleted, _ = FavoriteStock.objects.filter(symbol=symbol).delete()
    if not deleted:
        return Response(status=status.HTTP_404_NOT_FOUND)
    return Response(status=status.HTTP_204_NO_CONTENT)


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
