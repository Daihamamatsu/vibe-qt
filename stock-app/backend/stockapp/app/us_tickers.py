"""Alpha Vantage の米国銘柄一覧を使った株価・メタ情報取得サービス。"""
import csv
import io
import os
import time
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from .yahoo import (
    StockFetchError,
    fetch_ohlcv_batch,
    fetch_stock_info,
    save_ohlcv_rows,
    upsert_stock_meta,
)

LISTING_STATUS_URL = 'https://www.alphavantage.co/query'
DEFAULT_LISTING_CSV_PATH = Path(__file__).resolve().parents[2] / 'data' / 'listing_status_us.csv'
DEFAULT_BATCH_SIZE = 100
DEFAULT_ASSET_TYPES = ('Stock',)
DEFAULT_STATUS = 'Active'


def fetch_listing_csv(api_key: str, url: str = LISTING_STATUS_URL) -> str:
    """Alpha Vantage の LISTING_STATUS CSV を取得する。"""
    if not api_key or not api_key.strip():
        raise ValueError('Alpha Vantage API キーが指定されていません')
    query = urlencode({'function': 'LISTING_STATUS', 'apikey': api_key.strip()})
    request = Request(f'{url}?{query}', headers={'User-Agent': 'vibe-qt/1.0'})
    try:
        with urlopen(request, timeout=30) as response:
            body = response.read()
    except Exception as exc:
        raise ValueError(f'Alpha Vantage の銘柄一覧取得に失敗しました: {exc}') from exc
    try:
        text = body.decode('utf-8-sig')
    except UnicodeDecodeError as exc:
        raise ValueError('Alpha Vantage の応答を UTF-8 として読めません') from exc
    if not text.strip() or not text.lstrip().startswith('symbol,'):
        raise ValueError('Alpha Vantage が銘柄一覧 CSV ではない応答を返しました')
    return text


def save_listing_csv(csv_text: str, csv_path) -> Path:
    """銘柄一覧 CSV を UTF-8 で保存する。"""
    path = Path(csv_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(csv_text, encoding='utf-8', newline='')
    return path


def load_listing_csv(csv_path) -> str:
    """保存済みの銘柄一覧 CSV を読み込む。"""
    path = Path(csv_path)
    try:
        csv_text = path.read_text(encoding='utf-8-sig')
    except OSError as exc:
        raise ValueError(f'米国銘柄一覧 CSV を読み込めません: {path}') from exc
    if not csv_text.strip() or not csv_text.lstrip().startswith('symbol,'):
        raise ValueError(f'米国銘柄一覧 CSV の形式が不正です: {path}')
    return csv_text


def load_us_ticker_list(csv_text: str, asset_types=DEFAULT_ASSET_TYPES,
                        status: str = DEFAULT_STATUS) -> list[dict]:
    """米国銘柄 CSV を検証・絞り込みし、重複を除いた一覧を返す。"""
    reader = csv.DictReader(io.StringIO(csv_text))
    required = {'symbol', 'name', 'assetType', 'status'}
    if not reader.fieldnames or not required.issubset(reader.fieldnames):
        raise ValueError('銘柄一覧 CSV に必要な列がありません')
    allowed_types = {value.strip() for value in asset_types if value.strip()}
    tickers = []
    seen = set()
    for row in reader:
        symbol = (row.get('symbol') or '').strip().upper()
        if not symbol or symbol in seen:
            continue
        if (row.get('status') or '').strip() != status:
            continue
        if allowed_types and (row.get('assetType') or '').strip() not in allowed_types:
            continue
        if len(symbol) > 10 or any(char not in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-^=' for char in symbol):
            continue
        seen.add(symbol)
        tickers.append({
            'symbol': symbol,
            'name': (row.get('name') or '').strip(),
            'asset_type': (row.get('assetType') or '').strip(),
            'exchange': (row.get('exchange') or '').strip(),
        })
    return tickers


def fetch_all_us(api_key: str | None = None, csv_text: str | None = None,
                 period: str = '1y', limit: int | None = None,
                 sleep: float = 0.5, batch_size: int = DEFAULT_BATCH_SIZE,
                 asset_types=DEFAULT_ASSET_TYPES, status: str = DEFAULT_STATUS,
                 skip_info: bool = False, progress_cb=None) -> dict:
    """米国銘柄の株価と ``Ticker.info`` を取得して DB に保存する。"""
    if batch_size < 1:
        raise ValueError('batch_size は1以上で指定してください')
    if csv_text is None:
        csv_text = fetch_listing_csv(api_key or os.environ.get('ALPHA_VANTAGE_API_KEY', ''))
    tickers = load_us_ticker_list(csv_text, asset_types=asset_types, status=status)
    if limit is not None:
        tickers = tickers[:limit]
    summary = {'total': len(tickers), 'ok': 0, 'no_data': 0, 'failed': 0,
               'created': 0, 'updated': 0, 'errors': []}
    for batch_start in range(0, len(tickers), batch_size):
        batch = tickers[batch_start:batch_start + batch_size]
        symbols = [ticker['symbol'] for ticker in batch]
        try:
            rows_by_symbol, errors_by_symbol = fetch_ohlcv_batch(symbols, period)
        except StockFetchError as exc:
            rows_by_symbol = {}
            errors_by_symbol = {symbol: exc for symbol in symbols}
        for offset, ticker in enumerate(batch):
            symbol = ticker['symbol']
            error = errors_by_symbol.get(symbol)
            rows = rows_by_symbol.get(symbol)
            if error is not None:
                summary['failed'] += 1
                summary['errors'].append({'symbol': symbol, 'reason': str(error)})
            elif not rows:
                summary['no_data'] += 1
                summary['errors'].append({'symbol': symbol, 'reason': '株価データなし'})
            else:
                try:
                    created, updated = save_ohlcv_rows(symbol, rows)
                    if not skip_info:
                        upsert_stock_meta(
                            symbol,
                            name=ticker['name'],
                            info=fetch_stock_info(symbol),
                        )
                except Exception as exc:
                    summary['failed'] += 1
                    summary['errors'].append({'symbol': symbol, 'reason': str(exc)})
                else:
                    summary['ok'] += 1
                    summary['created'] += created
                    summary['updated'] += updated
            if progress_cb is not None:
                progress_cb(batch_start + offset + 1, len(tickers), ticker, summary)
        if sleep and batch_start + batch_size < len(tickers):
            time.sleep(sleep)
    return summary