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
    try:
        import yfinance as yf  # 遅延 import（モジュール docstring 参照）
        df = yf.Ticker(symbol).history(period=period, interval='1d', auto_adjust=False)
    except Exception as exc:
        # yfinance 未導入（ModuleNotFoundError）も「Yahoo Finance への取得失敗」と扱う。
        # try 外で import すると未導入環境で 500 になっていた (Issue #50 運用確認)
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


def fetch_stock_name(symbol: str) -> str:
    """Yahoo Finance から銘柄の正式名称（会社名）を取得する。

    yfinance の Ticker.info を用い、shortName / longName を返す。
    通信失敗・未知シンボルなどは空文字を返す（例外は送出しない）—
    銘柄名は補完データのため、失敗しても株価取得の本体処理には影響させない (Issue #49)。
    """
    try:
        import yfinance as yf  # 遅延 import（モジュール docstring 参照）
        info = yf.Ticker(symbol).info
    except Exception:
        # 通信エラーに加え、yfinance 未導入環境（ModuleNotFoundError 等）でも空文字を返す
        return ''
    if not isinstance(info, dict):
        return ''
    name = info.get('shortName') or info.get('longName') or ''
    return str(name).strip()


def upsert_stock_meta(symbol: str, name: str) -> None:
    """銘柄名を StockMeta に保存し、お気に入り銘柄へも同期する (Issue #49, #50)。

    StockMeta の行は無いなら作成・あれば name を更新し、同じシンボルの
    FavoriteStock 行の name も常に StockMeta 側に合わせる（空文字の場合も
    含めて全面同期）。これによりお気に入りパネルは常に最新の銘柄名を
    表示できる。
    """
    from .models import FavoriteStock, StockMeta

    StockMeta.objects.update_or_create(symbol=symbol, defaults={'name': name})
    FavoriteStock.objects.filter(symbol=symbol).update(name=name)


def save_ohlcv_rows(symbol: str, rows: list) -> tuple:
    """日足 OHLCV 行を StockRecord に upsert する。

    rows は (date, open, high, low, close, volume) のリスト（日付昇順）。
    既存の (symbol, date) レコードは更新、新規レコードは一括作成する。
    (作成数, 更新数) を返す。
    """
    from .models import StockRecord

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
    return len(to_create), updated


def fetch_and_save(symbol: str, period: str = '1mo') -> dict:
    """Yahoo Finance から日足 OHLC を取得して DB に upsert する。

    既存の (symbol, date) レコードは更新、新規レコードは一括作成する。
    """
    rows = fetch_ohlcv(symbol, period)
    created, updated = save_ohlcv_rows(symbol, rows)

    # 銘柄名を取得してキャッシュ（best effort: 銘柄名取得の失敗が株価保存を妨げない）(Issue #49, #50)
    # upsert_stock_meta によりお気に入り銘柄の name も StockMeta と同期される
    upsert_stock_meta(symbol, fetch_stock_name(symbol))

    return {
        'symbol': symbol,
        'period': period,
        'fetched': len(rows),
        'created': created,
        'updated': updated,
        'start_date': rows[0][0].isoformat(),
        'end_date': rows[-1][0].isoformat(),
    }