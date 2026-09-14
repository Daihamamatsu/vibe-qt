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

from .yahoo import StockFetchError, fetch_ohlcv, save_ohlcv_rows, upsert_stock_meta

# 銘柄リスト CSV の既定パス（backend/data/data_j.csv）
DEFAULT_CSV_PATH = Path(__file__).resolve().parents[2] / 'data' / 'data_j.csv'

# CSV のカラム位置（モジュール docstring のレイアウト参照）
COL_DATE = 0
COL_CODE = 1
COL_NAME = 2
COL_MARKET = 3


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
              sleep: float = 0.5, progress_cb=None) -> dict:
    """銘柄リスト CSV の全銘柄について日足株価を一括取得して DB に保存する。

    - 各銘柄の東証コードを Yahoo シンボル（.T 付き）に変換し、`period` 期間の日足を取得
    - StockRecord に upsert。銘柄名は CSV 側のを StockMeta に保存する
      （Yahoo の `.info` 銘柄名取得をスキップ → 1 銘柄あたり HTTP 1 往復を削減）
    - データのない銘柄（LookupError、ETF・ETN に多い）と取得失敗
      （StockFetchError、通信エラー等）は集計して次の銘柄へ継続する
    - 銘柄間の `sleep` 秒の待機で Yahoo Finance のレート制限を回避する

    戻り値はサマリ dict:
        total / ok / no_data / failed / created / updated / errors
    """
    if csv_path is None:
        csv_path = DEFAULT_CSV_PATH
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
    for i, ticker in enumerate(tickers, start=1):
        symbol = tse_to_yahoo_symbol(ticker['code'])
        try:
            rows = fetch_ohlcv(symbol, period)
        except LookupError:
            summary['no_data'] += 1
            summary['errors'].append(
                {'code': ticker['code'], 'symbol': symbol, 'reason': '株価データなし'})
        except StockFetchError as exc:
            summary['failed'] += 1
            summary['errors'].append(
                {'code': ticker['code'], 'symbol': symbol, 'reason': str(exc)})
        else:
            created, updated = save_ohlcv_rows(symbol, rows)
            upsert_stock_meta(symbol, ticker['name'])
            summary['ok'] += 1
            summary['created'] += created
            summary['updated'] += updated
        if progress_cb is not None:
            progress_cb(i, total, ticker, summary)
        if sleep and i < total:
            time.sleep(sleep)
    return summary
