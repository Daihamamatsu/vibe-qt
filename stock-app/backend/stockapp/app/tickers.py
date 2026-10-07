"""東証上場銘柄リスト（CSV）の読み取りと全銘柄株価の一括取得サービス。

プロジェクトに同梱の銘柄リスト CSV（backend/data/data_j.csv、東証「上場銘柄一覧」）
を読み取り、各銘柄を Yahoo Finance（yfinance）経由で日足 OHLCV 取得して
StockRecord に upsert する（実行は `fetch_tickers_j` 管理コマンド、Issue #65）。

銘柄リスト CSV のカラムは東証「上場銘柄一覧」と同一（全 10 列）。
本サービスが参照するのは先頭 4 列まで:

    日付, コード, 銘柄名, 市場・商品区分, 33業種コード, ..., 規模区分
"""
import csv
import time
from pathlib import Path

from .yahoo import (
    StockFetchError,
    fetch_ohlcv_batch,
    fetch_stock_info,
    save_ohlcv_rows,
    upsert_stock_meta,
)

# 銘柄リスト CSV の既定パス（backend/data/data_j.csv）
DEFAULT_CSV_PATH = Path(__file__).resolve().parents[2] / 'data' / 'data_j.csv'

# CSV のカラム位置（モジュール docstring のレイアウト参照）
COL_DATE = 0
COL_CODE = 1
COL_NAME = 2
COL_MARKET = 3
BATCH_SIZE = 100


def tse_to_yahoo_symbol(code: str) -> str:
    """東証コードを Yahoo Finance シンボルに変換する（末尾に .T を付与）。

    例: `1301` -> `1301.T`
    """
    return f'{code}.T'


def load_ticker_list(csv_path) -> list:
    """銘柄リスト CSV を読み、{'code', 'name', 'market'} のリストを返す（CSV の行順）。

    コードが空の行（ヘッダ行・空行）はスキップする。
    """
    tickers = []
    with open(csv_path, newline='', encoding='utf-8') as f:
        reader = csv.reader(f)
        next(reader, None)  # ヘッダ行をスキップ
        for row in reader:
            if len(row) <= COL_CODE:
                continue
            code = row[COL_CODE].strip().upper()
            if not code:
                continue
            name = row[COL_NAME].strip() if len(row) > COL_NAME else ''
            market = row[COL_MARKET].strip() if len(row) > COL_MARKET else ''
            tickers.append({'code': code, 'name': name, 'market': market})
    return tickers


def fetch_all(csv_path=None, period: str = '1y', limit: int = None,
              sleep: float = 0.5, progress_cb=None,
              batch_size: int = BATCH_SIZE, skip_info: bool = False) -> dict:
    """銘柄リスト CSV の全銘柄について日足株価を一括取得して DB に保存する。

    - 東証コードを Yahoo シンボル（.T 付き）へ変換し、複数銘柄単位で日足を取得
    - StockRecord に upsert。通常は CSV 側の銘柄名と Yahoo の `.info` を
      StockMeta に保存する
    - skip_info=True の場合は Ticker.info の取得と StockMeta の更新を省略し、
      株価だけを更新する
    - データのない銘柄（LookupError、ETF・ETN に多い）と取得失敗
      （StockFetchError、通信エラー等）は集計して次の銘柄へ継続する
    - バッチ間の `sleep` 秒の待機で Yahoo Finance のレート制限を回避する

    戻り値はサマリ dict:
        total / ok / no_data / failed / created / updated / errors
    """
    if csv_path is None:
        csv_path = DEFAULT_CSV_PATH
    if batch_size < 1:
        raise ValueError('batch_size は1以上で指定してください')
    tickers = load_ticker_list(csv_path)
    if limit is not None:
        tickers = tickers[:limit]

    summary = {
        'total': len(tickers),
        'ok': 0,
        'no_data': 0,
        'failed': 0,
        'created': 0,
        'updated': 0,
        'errors': [],
    }
    total = len(tickers)
    for batch_start in range(0, total, batch_size):
        batch = tickers[batch_start:batch_start + batch_size]
        symbols = [tse_to_yahoo_symbol(ticker['code']) for ticker in batch]
        try:
            rows_by_symbol, errors_by_symbol = fetch_ohlcv_batch(symbols, period)
        except StockFetchError as exc:
            rows_by_symbol = {}
            errors_by_symbol = {symbol: exc for symbol in symbols}

        for offset, ticker in enumerate(batch):
            i = batch_start + offset + 1
            symbol = symbols[offset]
            error = errors_by_symbol.get(symbol)
            rows = rows_by_symbol.get(symbol)
            if error is not None:
                summary['failed'] += 1
                summary['errors'].append(
                    {'code': ticker['code'], 'symbol': symbol, 'reason': str(error)})
            elif not rows:
                summary['no_data'] += 1
                summary['errors'].append(
                    {'code': ticker['code'], 'symbol': symbol, 'reason': '株価データなし'})
            else:
                try:
                    created, updated = save_ohlcv_rows(symbol, rows)
                except StockFetchError as exc:
                    summary['failed'] += 1
                    summary['errors'].append(
                        {'code': ticker['code'], 'symbol': symbol, 'reason': str(exc)})
                else:
                    if not skip_info:
                        # 一括取得でも info 全体を保存する。info 取得失敗時は CSV 名を残す。
                        upsert_stock_meta(symbol, name=ticker['name'], info=fetch_stock_info(symbol))
                    summary['ok'] += 1
                    summary['created'] += created
                    summary['updated'] += updated
            if progress_cb is not None:
                progress_cb(i, total, ticker, summary)
        if sleep and batch_start + batch_size < total:
            time.sleep(sleep)
    return summary
