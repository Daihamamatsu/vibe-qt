"""Yahoo Finance（yfinance）から実株価の日足を取得して DB に保存するサービス。

注意: yfinance は重い依存（pandas 等）を含むため、未導入環境（テスト環境など）で
アプリ起動時に ImportError とならないよう、関数内で遅延 import する。
"""
import re
from decimal import Decimal, ROUND_HALF_UP

# 取得エンドポイントで指定可能な期間（yfinance の period 値）
VALID_PERIODS = {'5d', '1mo', '3mo', '6mo', '1y', '2y', '5y'}

# 記号の許容文字（英大文字・数字・ドット・ハイフン・ハット・イコール、最大 10 文字 = モデルの max_length）
SYMBOL_RE = re.compile(r'^[A-Z0-9.\-^=]{1,10}$')


class StockFetchError(Exception):
    """Yahoo Finance からデータを取得できなかった（通信エラー等）ときに送出される。"""


def _to_decimal(value) -> Decimal:
    """株価をモデルの桁数（小数 4 桁）に丸める。"""
    return Decimal(str(value)).quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)


def _to_volume(value):
    """出来高を int 化する（NaN・欠損・負値は None）。"""
    try:
        volume = int(value)
    except (TypeError, ValueError):
        return None
    return volume if volume >= 0 else None


def fetch_ohlcv(symbol: str, period: str = '1mo') -> list:
    """Yahoo Finance から指定銘柄の日足 OHLCV を取得する。

    戻り値: (date, open, high, low, close, volume) のリスト（日付昇順）。
    送出:
        StockFetchError — Yahoo Finance への通信に失敗したとき
        LookupError — 該当社種にデータがなかったとき
    """
    import yfinance as yf  # 遅延 import（モジュール docstring 参照）

    try:
        df = yf.Ticker(symbol).history(period=period, interval='1d', auto_adjust=False)
    except Exception as exc:
        raise StockFetchError(f'Yahoo Finance の取得に失敗しました: {exc}') from exc

    if df is None or df.empty:
        raise LookupError(f'該当社種 {symbol} の株価データがありませんでした')

    # OHLC いずれかが欠損（NaN）の行は除外する（例: 当日の不完全な日次データ）
    df = df.dropna(subset=['Open', 'High', 'Low', 'Close'])
    if df.empty:
        raise LookupError(f'該当社種 {symbol} の株価データがありませんでした')

    index = df.index
    if index.tz is not None:
        index = index.tz_localize(None)

    rows = []
    for ts, row in zip(index, df.itertuples(index=False)):
        rows.append((
            ts.date(),
            _to_decimal(row.Open),
            _to_decimal(row.High),
            _to_decimal(row.Low),
            _to_decimal(row.Close),
            _to_volume(row.Volume),
        ))
    return rows


def fetch_and_save(symbol: str, period: str = '1mo') -> dict:
    """Yahoo Finance から日足 OHLC を取得して DB に upsert する。

    既存の (symbol, date) レコードは更新、新規レコードは一括作成する。
    """
    from .models import StockRecord

    rows = fetch_ohlcv(symbol, period)
    dates = [row[0] for row in rows]
    existing = {
        record.date: record
        for record in StockRecord.objects.filter(symbol=symbol, date__in=dates)
    }

    to_create = []
    updated = 0
    for date_, open_, high_, low_, close_, volume_ in rows:
        record = existing.get(date_)
        if record is None:
            to_create.append(StockRecord(
                symbol=symbol, date=date_, open=open_, high=high_,
                low=low_, close=close_, volume=volume_,
            ))
        else:
            record.open = open_
            record.high = high_
            record.low = low_
            record.close = close_
            record.volume = volume_
            record.save()
            updated += 1
    if to_create:
        StockRecord.objects.bulk_create(to_create)

    return {
        'symbol': symbol,
        'period': period,
        'fetched': len(rows),
        'created': len(to_create),
        'updated': updated,
        'start_date': rows[0][0].isoformat(),
        'end_date': rows[-1][0].isoformat(),
    }