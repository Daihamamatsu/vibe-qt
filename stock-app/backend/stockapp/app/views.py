from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response
from .models import FavoriteStock, StockList, StockMeta, StockRecord
from .serializers import StockRecordSerializer
from .yahoo import (
    SYMBOL_RE,
    VALID_PERIODS,
    StockFetchError,
    fetch_and_save,
    fetch_stock_name,
    upsert_stock_meta,
)


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
def favorite_lists(request):
    """/api/favorite-lists/ — 銘柄リスト一覧・作成 (Issue #50)。

    GET: 全リストを返す（各リストの所属銘柄数を含む）。
    POST: {"name": "xxx"} で新しいリストを作成する。
        201 = 作成成功、400 = 名前不正（空 / 50 字超過）、409 = 同名リストが存在。
    """
    if request.method == 'POST':
        data = request.data if isinstance(request.data, dict) else {}
        name = str(data.get('name') or '').strip()
        if not name or len(name) > 50:
            return Response(
                {'detail': 'invalid list name'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if StockList.objects.filter(name=name).exists():
            return Response(
                {'detail': f'list exists: {name}'},
                status=status.HTTP_409_CONFLICT,
            )
        stock_list = StockList.objects.create(name=name)
        return Response(
            {'id': stock_list.id, 'name': stock_list.name},
            status=status.HTTP_201_CREATED,
        )

    lists = StockList.objects.all().order_by('created_at', 'id')
    return Response([
        {'id': s.id, 'name': s.name, 'count': s.favorites.count()}
        for s in lists
    ])


@api_view(['PATCH', 'PUT', 'DELETE'])
def favorite_list_detail(request, list_id):
    """/api/favorite-lists/<id>/ — 銘柄リストの名前変更・削除 (Issue #50)。

    PATCH/PUT: {"name": "yyy"} で名前を変更する。
        200 = 成功、400 = 名前不正、404 = リスト不存在、409 = 同名リストが存在。
    DELETE: リストを削除する（リスト内の銘柄所属も一緒に削除）。
        204 = 成功、404 = リスト不存在。
    """
    stock_list = StockList.objects.filter(id=list_id).first()
    if stock_list is None:
        return Response(
            {'detail': 'list not found'},
            status=status.HTTP_404_NOT_FOUND,
        )

    if request.method == 'DELETE':
        stock_list.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

    data = request.data if isinstance(request.data, dict) else {}
    name = str(data.get('name') or '').strip()
    if not name or len(name) > 50:
        return Response(
            {'detail': 'invalid list name'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if StockList.objects.filter(name=name).exclude(id=stock_list.id).exists():
        return Response(
            {'detail': f'list exists: {name}'},
            status=status.HTTP_409_CONFLICT,
        )
    stock_list.name = name
    stock_list.save()
    return Response({'id': stock_list.id, 'name': stock_list.name})


@api_view(['GET', 'POST'])
def favorites(request):
    """/api/favorites/ — お気に入り銘柄の一覧（リスト別）・追加 (Issue #50)。

    GET: 全リストと各リストに所属する銘柄を返す（空リストも含まれる）。
    POST: {"symbol": "AAPL", "list_id": 1} でリストに銘柄を追加する。
        銘柄は複数リストに所属できる。
        201 = 追加成功、400 = シンボル不正 / list_id 不足、
        404 = リスト不存在、409 = 同一リスト内で重複。
    """
    if request.method == 'POST':
        data = request.data if isinstance(request.data, dict) else {}
        symbol = str(data.get('symbol') or '').strip().upper()
        if not SYMBOL_RE.match(symbol):
            return Response(
                {'detail': f'invalid symbol: {symbol}'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        list_id = data.get('list_id')
        if isinstance(list_id, bool) or not isinstance(list_id, int) or list_id <= 0:
            return Response(
                {'detail': 'list_id is required'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        stock_list = StockList.objects.filter(id=list_id).first()
        if stock_list is None:
            return Response(
                {'detail': 'list not found'},
                status=status.HTTP_404_NOT_FOUND,
            )
        if FavoriteStock.objects.filter(list=stock_list, symbol=symbol).exists():
            return Response(
                {'detail': f'favorite exists: {symbol}'},
                status=status.HTTP_409_CONFLICT,
            )
        # 銘柄名は StockMeta と同期 (Issue #50)。未キャッシュなら空文字で保存し、
        # 後日の株価取得 (fetch_and_save) で StockMeta 更新時に自動反映される
        meta = StockMeta.objects.filter(symbol=symbol).first()
        name = meta.name if meta is not None else ''
        FavoriteStock.objects.create(list=stock_list, symbol=symbol, name=name)
        return Response(
            {'symbol': symbol, 'name': name, 'list_id': list_id},
            status=status.HTTP_201_CREATED,
        )

    # リストごとに所属銘柄をグルーピングする（空リストも保持）
    grouped = {
        s.id: {'id': s.id, 'name': s.name, 'stocks': []}
        for s in StockList.objects.order_by('created_at', 'id')
    }
    favorites_qs = FavoriteStock.objects.order_by('created_at', 'symbol')
    for f in favorites_qs:
        item = grouped.get(f.list_id)
        if item is not None:
            item['stocks'].append({'symbol': f.symbol, 'name': f.name})
    return Response(list(grouped.values()))


@api_view(['DELETE'])
def favorite_delete(request, list_id, symbol):
    """/api/favorites/<list_id>/<symbol>/ — リストからの銘柄削除 (Issue #50)。

    他リストでの所属は影響を受けない。
    """
    deleted, _ = FavoriteStock.objects.filter(list_id=list_id, symbol=symbol).delete()
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
