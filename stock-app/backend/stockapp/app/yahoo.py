"""Yahoo Finance（yfinance）から実株価の日足を取得して DB に保存するサービス。

注意: yfinance は重い依存（pandas 等）を含むため、未導入環境（テスト環境など）で
アプリ起動時に ImportError とならないよう、関数内で遅延 import する。
"""
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

# 取得エンドポイントで指定可能な期間（yfinance の period 値）
VALID_PERIODS = {'5d', '1mo', '3mo', '6mo', '1y', '2y', '5y'}

# 記号の許容文字（英大文字・数字・ドット・ハイフン・ハット・イコール、最大 10 文字 = モデルの max_length）
SYMBOL_RE = re.compile(r'^[A-Z0-9.\-^=]{1,10}$')

# StockRecord の DecimalField(max_digits=12, decimal_places=4) に保存できる株価の上限。
# 整数部 8 桁・小数部 4 桁のため、絶対値は 99,999,999.9999 まで。
MAX_STOCK_PRICE = Decimal('99999999.9999')


class StockFetchError(Exception):
    """Yahoo Finance からデータを取得できなかった（通信エラー等）ときに送出される。"""


def _to_decimal(value) -> Decimal:
    """株価をモデルの桁数（小数 4 桁）に丸める。

    Yahoo Finance の異常値や DB の桁数を超える値は、保存時の
    ``decimal.InvalidOperation`` で一括取得全体を停止させないため、
    StockFetchError として扱う。
    """
    try:
        price = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise StockFetchError(f'株価が数値として解釈できません: {value!r}') from exc
    if not price.is_finite() or price < 0 or price > MAX_STOCK_PRICE:
        raise StockFetchError(
            f'DB の桁数範囲外の株価です: {value!r} '
            f'(0〜{MAX_STOCK_PRICE})'
        )
    try:
        return price.quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP)
    except InvalidOperation as exc:
        raise StockFetchError(f'株価の丸めに失敗しました: {value!r}') from exc


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


def fetch_ohlcv_batch(symbols: list[str], period: str = '1mo') -> tuple[dict, dict]:
    """Yahoo Finance から複数銘柄の日足 OHLCV をまとめて取得する。

    ``yf.download`` の戻り値は通常、銘柄名と項目名の MultiIndex になる。
    ただし1銘柄だけの場合は通常の項目名になるため、両方の形式を扱う。

    戻り値は ``(rows_by_symbol, errors_by_symbol)``。データが存在しない銘柄は
    errors に含めず、呼び出し側で ``no_data`` として集計する。
    """
    if not symbols:
        return {}, {}

    try:
        import yfinance as yf  # 遅延 import
        df = yf.download(
            symbols,
            period=period,
            interval='1d',
            auto_adjust=False,
            group_by='ticker',
            threads=True,
            progress=False,
        )
    except Exception as exc:
        raise StockFetchError(f'Yahoo Finance の一括取得に失敗しました: {exc}') from exc

    if df is None or df.empty:
        return {}, {}

    rows_by_symbol = {}
    errors_by_symbol = {}
    columns = getattr(df, 'columns', None)
    is_multi_index = bool(columns is not None and getattr(columns, 'nlevels', 1) > 1)

    for symbol in symbols:
        try:
            if is_multi_index:
                # group_by='ticker' の通常形式（ticker, field）を優先し、
                # yfinanceの返却形式が逆でも銘柄名の階層を検出して対応する。
                level_values = [set(level) for level in columns.levels]
                if symbol in level_values[0]:
                    symbol_df = df[symbol]
                elif symbol in level_values[1]:
                    symbol_df = df.xs(symbol, axis=1, level=1)
                else:
                    continue
            else:
                if len(symbols) != 1:
                    continue
                symbol_df = df

            if symbol_df is None or symbol_df.empty:
                continue
            required = ['Open', 'High', 'Low', 'Close']
            if any(field not in symbol_df.columns for field in required):
                continue
            symbol_df = symbol_df.dropna(subset=required)
            if symbol_df.empty:
                continue

            index = symbol_df.index
            if index.tz is not None:
                index = index.tz_localize(None)
            rows = []
            for ts, row in zip(index, symbol_df.itertuples(index=False)):
                rows.append((
                    ts.date(),
                    _to_decimal(row.Open),
                    _to_decimal(row.High),
                    _to_decimal(row.Low),
                    _to_decimal(row.Close),
                    _to_volume(row.Volume),
                ))
            rows_by_symbol[symbol] = rows
        except StockFetchError as exc:
            errors_by_symbol[symbol] = exc
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            errors_by_symbol[symbol] = StockFetchError(
                f'株価データの変換に失敗しました: {exc}'
            )
    return rows_by_symbol, errors_by_symbol


def _contains_japanese(value: str) -> bool:
    """文字列に日本語の文字が含まれるか判定する。"""
    return bool(re.search(r'[ぁ-んァ-ヶ一-龯々]', value))


def _to_json_value(value):
    """Ticker.info を JSONField に保存できる値へ再帰的に変換する。"""
    if isinstance(value, dict):
        return {str(key): _to_json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_json_value(item) for item in value]
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def select_stock_name(info: dict, fallback: str = '') -> str:
    """Ticker.info から日本語名を優先して表示名を選ぶ。"""
    candidates = [
        info.get('longNameJa'),
        info.get('shortNameJa'),
        info.get('displayNameJa'),
        info.get('longName'),
        info.get('shortName'),
        info.get('displayName'),
        info.get('name'),
    ]
    values = [str(value).strip() for value in candidates if value]
    japanese = next((value for value in values if _contains_japanese(value)), None)
    return japanese or (values[0] if values else str(fallback).strip())


def select_stock_sector(info: dict) -> str:
    """Ticker.info から表示用のセクター名を選ぶ。"""
    return str(info.get('sectorDisp') or info.get('sector') or '').strip()


def fetch_stock_info(symbol: str) -> dict:
    """Yahoo Finance の Ticker.info 全体を取得する（失敗時は空辞書）。"""
    try:
        import yfinance as yf  # 遅延 import
        info = yf.Ticker(symbol).info
    except Exception:
        return {}
    if not isinstance(info, dict):
        return {}
    return _to_json_value(info)


def fetch_stock_name(symbol: str) -> str:
    """Yahoo Finance から日本語名を優先した銘柄名を取得する。"""
    return select_stock_name(fetch_stock_info(symbol))


def upsert_stock_meta(symbol: str, name: str = '', info: dict | None = None,
                      sector: str | None = None) -> None:
    """銘柄メタ情報を保存し、お気に入り銘柄へ同期する。

    name が指定されている場合は、表示名として最優先する。東証銘柄CSVの
    日本語名を Yahoo Finance の英語名より優先するために使用する。
    """
    from .models import FavoriteStock, StockMeta

    normalized_info = _to_json_value(info) if isinstance(info, dict) else {}
    selected_name = str(name).strip() or select_stock_name(normalized_info)
    selected_sector = sector if sector is not None else select_stock_sector(normalized_info)
    StockMeta.objects.update_or_create(
        symbol=symbol,
        defaults={
            'name': selected_name,
            'sector': selected_sector,
            'info': normalized_info,
        },
    )
    FavoriteStock.objects.filter(symbol=symbol).update(
        name=selected_name,
        sector=selected_sector,
    )


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
        # 呼び出し元が直接渡した行も、Yahoo取得経由の行と同じ範囲検証を行う。
        open_ = _to_decimal(open_)
        high_ = _to_decimal(high_)
        low_ = _to_decimal(low_)
        close_ = _to_decimal(close_)
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
    from .models import StockMeta

    rows = fetch_ohlcv(symbol, period)
    created, updated = save_ohlcv_rows(symbol, rows)

    # 既存のCSV由来・手動設定の銘柄名は、GUIから再取得しても上書きしない。
    # 既存名が空の場合だけTicker.infoから名前を補完する。
    existing_meta = StockMeta.objects.filter(symbol=symbol).only('name').first()
    existing_name = existing_meta.name if existing_meta else ''
    upsert_stock_meta(
        symbol,
        name=existing_name,
        info=fetch_stock_info(symbol),
    )

    return {
        'symbol': symbol,
        'period': period,
        'fetched': len(rows),
        'created': created,
        'updated': updated,
        'start_date': rows[0][0].isoformat(),
        'end_date': rows[-1][0].isoformat(),
    }