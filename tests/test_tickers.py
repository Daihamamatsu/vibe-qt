# tests/test_tickers.py
"""東証銘柄リスト CSV の読み取り・全銘柄一括取得のテスト（Issue #65）。

リポジトリのルートディレクトリから実行する:

    pip install -r requirements-dev.txt
    python -m pytest tests/ -v
"""
import datetime
import sys
from unittest import mock

import pandas as pd
import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from stockapp.app.models import StockMeta, StockRecord
from stockapp.app.tickers import fetch_all, load_ticker_list, tse_to_yahoo_symbol
from stockapp.app.yahoo import save_ohlcv_rows

# backend/data/data_j.csv と同じレイアウト（先頭 4 列のみ機能に必要）
CSV_HEADER = (
    '日付,コード,銘柄名,市場・商品区分,33業種コード,33業種区分,'
    '17業種コード,17業種区分,規模コード,規模区分'
)


def _write_ticker_csv(path, rows):
    """銘柄リスト CSV を書き出す。rows = [(code, name, market), ...]"""
    lines = [CSV_HEADER]
    for code, name, market in rows:
        lines.append(f'20260831,{code},{name},{market},50,水産・農林業,1,食品,6,TOPIX Small 1')
    path.write_text('\n'.join(lines) + '\n', encoding='utf-8')
    return str(path)


class _FakeRow:
    """df.itertuples(index=False) の行の最小限の代替（大文字カラム名）。"""

    def __init__(self, open_, high_, low_, close_, volume_):
        self.Open = open_
        self.High = high_
        self.Low = low_
        self.Close = close_
        self.Volume = volume_


class _FakeIndex:
    """pandas index の最小限の代替（反復可能 + tz 属性）。"""

    def __init__(self, dates):
        self._dates = dates
        self.tz = None

    def __iter__(self):
        return iter(self._dates)


class _FakeDataFrame:
    """pandas DataFrame の最小限の代替（fetch_ohlcv が触る API のみ）。"""

    def __init__(self, rows):
        self._rows = rows
        self.empty = len(rows) == 0

    def dropna(self, subset=None):
        return self

    @property
    def index(self):
        # 実データ（pandas Timestamp）と同様に .date() が使える datetime を返す
        return _FakeIndex([datetime.datetime(2026, 9, 9 + i) for i in range(len(self._rows))])

    def itertuples(self, index=False):
        return [_FakeRow(*row) for row in self._rows]


def _make_fake_df():
    """日足 OHLCV 3 営業日分の Fake DataFrame を生成する。"""
    return _FakeDataFrame([
        (150.0, 155.0, 149.0, 154.0, 1000),
        (151.0, 156.0, 150.0, 155.0, 1100),
        (152.0, 157.0, 151.0, 156.0, 1200),
    ])


class _BulkFakeTicker:
    """yfinance.Ticker の代替（銘柄情報取得だけを担当する）。"""

    def __init__(self, symbol):
        self.symbol = symbol

    @property
    def info(self):
        return {}


def _make_bulk_download_df(symbols, **kwargs):
    """yf.download の銘柄階層付きDataFrameを生成する。"""
    fields = ['Open', 'High', 'Low', 'Close', 'Volume']
    columns = pd.MultiIndex.from_product([symbols, fields])
    values = []
    for day in range(3):
        row = []
        for symbol in symbols:
            if symbol == '9999.T':
                row.extend([None] * len(fields))
            elif symbol == '8888.T':
                row.extend([100000000, 100000000, 100000000, 100000000, 1000])
            else:
                row.extend([150 + day, 155 + day, 149 + day, 154 + day, 1000 + day * 100])
        values.append(row)
    index = pd.date_range('2026-09-09', periods=3, freq='D')
    return pd.DataFrame(values, index=index, columns=columns)


@pytest.fixture
def fake_bulk_yfinance():
    """sys.modules の yfinance を download ベースのモックに差し替える。"""
    fake = mock.MagicMock()
    fake.Ticker.side_effect = _BulkFakeTicker
    fake.download.side_effect = _make_bulk_download_df
    with mock.patch.dict(sys.modules, {'yfinance': fake}):
        yield fake


# --- tse_to_yahoo_symbol -----------------------------------------------------


def test_tse_to_yahoo_symbol():
    """東証コードに .T サフィックスが付与されること。"""
    assert tse_to_yahoo_symbol('1301') == '1301.T'
    assert tse_to_yahoo_symbol('130A') == '130A.T'
    assert tse_to_yahoo_symbol('130a') == '130a.T'


# --- load_ticker_list --------------------------------------------------------


def test_load_ticker_list(tmp_path):
    """CSV の全行が (code, name, market) 付きで読み込まれること。"""
    csv_path = _write_ticker_csv(tmp_path / 'tickers.csv', [
        ('1301', '極洋', 'プライム（内国株式）'),
        ('130A', 'レイアウトテスト', 'グロース（内国株式）'),
    ])
    tickers = load_ticker_list(csv_path)
    assert tickers == [
        {'code': '1301', 'name': '極洋', 'market': 'プライム（内国株式）'},
        {'code': '130A', 'name': 'レイアウトテスト', 'market': 'グロース（内国株式）'},
    ]


def test_load_ticker_list_skips_empty_code(tmp_path):
    """コードが空の行はスキップされること。"""
    csv_path = _write_ticker_csv(tmp_path / 'tickers.csv', [
        ('1301', '極洋', 'プライム（内国株式）'),
    ])
    with open(csv_path, 'a', encoding='utf-8') as f:
        f.write('20260831,,,PRO Market,-,-,-,-,-,-\n')
    tickers = load_ticker_list(csv_path)
    assert [t['code'] for t in tickers] == ['1301']


# --- save_ohlcv_rows ---------------------------------------------------------


def test_save_ohlcv_rows_upsert(db):
    """save_ohlcv_rows は初回 create、再実行時は update されること。"""
    base = datetime.date(2026, 9, 9)
    rows = [
        (base + datetime.timedelta(days=i), 100 + i, 110 + i, 90 + i, 105 + i, 1000 + i)
        for i in range(3)
    ]
    created, updated = save_ohlcv_rows('1301.T', rows)
    assert (created, updated) == (3, 0)

    # 再実行時は全行が update される
    created, updated = save_ohlcv_rows('1301.T', rows)
    assert (created, updated) == (0, 3)
    assert StockRecord.objects.filter(symbol='1301.T').count() == 3
# --- fetch_all ---------------------------------------------------------------


def test_fetch_all_saves_records_and_meta(db, fake_bulk_yfinance, tmp_path):
    """全銘柄取得成功時: 日足が upsert され、CSV の銘柄名が StockMeta に入る。"""
    csv_path = _write_ticker_csv(tmp_path / 'tickers.csv', [
        ('1301', '極洋', 'プライム（内国株式）'),
        ('130A', 'レイアウトテスト', 'プライム（内国株式）'),
    ])
    summary = fetch_all(csv_path=csv_path, period='1y', sleep=0)

    assert summary['total'] == 2
    assert summary['ok'] == 2
    assert summary['no_data'] == 0
    assert summary['failed'] == 0
    assert summary['created'] == 6  # 2 銘柄 x 3 日
    assert summary['updated'] == 0
    assert StockRecord.objects.filter(symbol='1301.T').count() == 3
    assert StockRecord.objects.filter(symbol='130A.T').count() == 3
    # 銘柄名は CSV 由来（Yahoo の .info は参照しない）
    assert StockMeta.objects.get(symbol='1301.T').name == '極洋'
    assert StockMeta.objects.get(symbol='130A.T').name == 'レイアウトテスト'


def test_fetch_all_prefers_csv_name_over_yahoo_name(db, fake_bulk_yfinance, tmp_path, monkeypatch):
    """CSVの日本語銘柄名が Yahoo Finance の英語名より優先されること。"""
    csv_path = _write_ticker_csv(tmp_path / 'tickers.csv', [
        ('1961', '三機工業', 'プライム（内国株式）'),
    ])
    monkeypatch.setattr(
        'stockapp.app.tickers.fetch_stock_info',
        lambda symbol: {
            'longName': 'Sanki Engineering Co., Ltd.',
            'shortName': 'SANKI ENGINEERING CO',
            'sector': 'Industrials',
        },
    )

    fetch_all(csv_path=csv_path, period='1y', sleep=0)

    meta = StockMeta.objects.get(symbol='1961.T')
    assert meta.name == '三機工業'
    assert meta.sector == 'Industrials'


def test_fetch_all_continues_on_no_data_and_failure(db, fake_bulk_yfinance, tmp_path):
    """データなし・通信失敗の銘柄は集計して続きが継続されること。"""
    csv_path = _write_ticker_csv(tmp_path / 'tickers.csv', [
        ('1301', '極洋', 'プライム（内国株式）'),
        ('8888', '通信失敗テスト', 'グロース（内国株式）'),
        ('9999', 'データなしテスト', 'ETF・ETN'),
    ])
    summary = fetch_all(csv_path=csv_path, period='1y', sleep=0)

    assert summary['total'] == 3
    assert summary['ok'] == 1
    assert summary['no_data'] == 1
    assert summary['failed'] == 1
    assert summary['created'] == 3
    # 成功分のみ保存され、失敗分は StockRecord にも StockMeta にも残らない
    assert StockRecord.objects.count() == 3
    assert StockRecord.objects.filter(symbol='8888.T').count() == 0
    assert StockRecord.objects.filter(symbol='9999.T').count() == 0
    assert StockMeta.objects.count() == 1
    # エラーは銘柄ごとに記録される
    assert [e['code'] for e in summary['errors']] == ['8888', '9999']


def test_fetch_all_continues_when_price_exceeds_decimal_field_range(db, fake_bulk_yfinance, tmp_path, monkeypatch):
    """1銘柄の株価桁あふれで一括取得全体が停止しないこと。"""
    csv_path = _write_ticker_csv(tmp_path / 'tickers.csv', [
        ('1301', '極洋', 'プライム（内国株式）'),
        ('130A', '後続銘柄', 'プライム（内国株式）'),
    ])

    monkeypatch.setattr(
        'stockapp.app.tickers.fetch_ohlcv_batch',
        lambda symbols, period: (
            {
                '1301.T': [(datetime.date(2026, 9, 9), 100000000, 100000000,
                           100000000, 100000000, 1000)],
                '130A.T': [(datetime.date(2026, 9, 9), 100, 110, 90, 105, 1000)],
            },
            {},
        ),
    )
    summary = fetch_all(csv_path=csv_path, period='1y', sleep=0)

    assert summary['ok'] == 1
    assert summary['failed'] == 1
    assert summary['errors'][0]['code'] == '1301'
    assert StockRecord.objects.filter(symbol='130A.T').count() == 1


def test_fetch_all_limit(db, fake_bulk_yfinance, tmp_path):
    """limit 指定時は先頭 N 件のみ処理されること。"""
    csv_path = _write_ticker_csv(tmp_path / 'tickers.csv', [
        ('1301', '極洋', 'プライム（内国株式）'),
        ('130A', 'レイアウトテスト', 'プライム（内国株式）'),
    ])
    summary = fetch_all(csv_path=csv_path, period='1y', sleep=0, limit=1)

    assert summary['total'] == 1
    assert summary['ok'] == 1
    assert StockRecord.objects.count() == 3
    assert StockRecord.objects.filter(symbol='1301.T').count() == 3
    assert StockRecord.objects.filter(symbol='130A.T').count() == 0


def test_fetch_all_updates_on_rerun(db, fake_bulk_yfinance, tmp_path):
    """再実行時は upsert により更新され、重複レコードは増えないこと。"""
    csv_path = _write_ticker_csv(tmp_path / 'tickers.csv', [
        ('1301', '極洋', 'プライム（内国株式）'),
    ])
    first = fetch_all(csv_path=csv_path, period='1y', sleep=0)
    assert (first['created'], first['updated']) == (3, 0)

    second = fetch_all(csv_path=csv_path, period='1y', sleep=0)
    assert (second['created'], second['updated']) == (0, 3)
    assert StockRecord.objects.count() == 3


def test_fetch_all_skip_info_only_updates_prices(db, fake_bulk_yfinance, tmp_path):
    """skip_info 指定時は株価だけ保存し、銘柄メタ情報を取得・更新しないこと。"""
    csv_path = _write_ticker_csv(tmp_path / 'tickers.csv', [
        ('1301', '極洋', 'プライム（内国株式）'),
    ])
    summary = fetch_all(csv_path=csv_path, period='5d', sleep=0, skip_info=True)

    assert summary['ok'] == 1
    assert StockRecord.objects.count() == 3
    assert StockMeta.objects.count() == 0


# --- fetch_tickers_j 管理コマンド --------------------------------------------


def test_fetch_tickers_j_command(db, fake_bulk_yfinance, tmp_path):
    """管理コマンドが CSV を読み一括登録し、サマリを出力すること。"""
    csv_path = _write_ticker_csv(tmp_path / 'tickers.csv', [
        ('1301', '極洋', 'プライム（内国株式）'),
        ('8888', '通信失敗テスト', 'グロース（内国株式）'),
        ('9999', 'データなしテスト', 'ETF・ETN'),
    ])
    out = []

    class _Collector:
        """stdout.write の収集用スタブ。"""

        def write(self, text):
            out.append(text)

    call_command(
        'fetch_tickers_j',
        csv=csv_path,
        period='1y',
        sleep=0,
        stdout=_Collector(),
    )
    assert StockRecord.objects.count() == 3
    assert StockMeta.objects.count() == 1
    # サマリ行が出力されている
    assert any('total=3' in line for line in out)
    assert any('ok=1' in line for line in out)
    assert any('no_data=1' in line for line in out)
    assert any('failed=1' in line for line in out)


def test_fetch_tickers_j_command_skip_info(db, fake_bulk_yfinance, tmp_path):
    """--skip-info 指定時は株価だけを登録すること。"""
    csv_path = _write_ticker_csv(tmp_path / 'tickers.csv', [
        ('1301', '極洋', 'プライム（内国株式）'),
    ])

    call_command(
        'fetch_tickers_j',
        csv=csv_path,
        period='5d',
        sleep=0,
        skip_info=True,
    )

    assert StockRecord.objects.count() == 3
    assert StockMeta.objects.count() == 0


def test_fetch_tickers_j_command_invalid_period(db, fake_bulk_yfinance, tmp_path):
    """無効な --period は CommandError となること。"""
    csv_path = _write_ticker_csv(tmp_path / 'tickers.csv', [
        ('1301', '極洋', 'プライム（内国株式）'),
    ])
    with pytest.raises(CommandError):
        call_command('fetch_tickers_j', csv=csv_path, period='9y', sleep=0)


def test_fetch_tickers_j_command_invalid_batch_size(db, fake_bulk_yfinance, tmp_path):
    """0以下の--batch-sizeはCommandErrorとなること。"""
    csv_path = _write_ticker_csv(tmp_path / 'tickers.csv', [
        ('1301', '極洋', 'プライム（内国株式）'),
    ])
    with pytest.raises(CommandError, match='batch-size'):
        call_command('fetch_tickers_j', csv=csv_path, batch_size=0, sleep=0)


def test_fetch_tickers_j_command_missing_csv(db, fake_bulk_yfinance, tmp_path):
    """存在しない CSV パスは CommandError となること。"""
    with pytest.raises(CommandError):
        call_command(
            'fetch_tickers_j',
            csv=str(tmp_path / 'not_found.csv'),
            period='1y',
            sleep=0,
        )

