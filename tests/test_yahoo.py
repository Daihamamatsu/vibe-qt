"""stockapp/app/yahoo.py のユニットテスト (Issue #50)"""
import datetime
import logging
import sys

import pytest

from stockapp.app.models import ClassicTurtleSignal, StockRecord
from stockapp.app.yahoo import (
    RateLimitError,
    StockFetchError,
    fetch_and_save,
    fetch_ohlcv,
    fetch_ohlcv_batch,
    save_ohlcv_rows,
)


def test_fetch_ohlcv_import_failure_raises_stock_fetch_error(monkeypatch):
    """yfinance の import が失敗しても StockFetchError（502）で済ませ 500 にしない。"""
    # sys.modules のエントリを None にすると `import yfinance` は ImportError となる
    monkeypatch.setitem(sys.modules, 'yfinance', None)
    with pytest.raises(StockFetchError):
        fetch_ohlcv('AAPL')


def test_fetch_ohlcv_raises_rate_limit_error_for_429(monkeypatch):
    """yfinanceの429は通常の取得失敗と区別して送出すること。"""
    fake_yfinance = type(
        'FakeYFinance',
        (),
        {'Ticker': staticmethod(lambda symbol: type(
            'FakeTicker', (), {
                'history': lambda self, **kwargs: (_ for _ in ()).throw(
                    RuntimeError('429 Too Many Requests')),
            })(),
        )},
    )
    monkeypatch.setitem(sys.modules, 'yfinance', fake_yfinance)

    with pytest.raises(RateLimitError, match='429'):
        fetch_ohlcv('AAPL')


def test_fetch_ohlcv_batch_raises_rate_limit_error_for_429(monkeypatch):
    """yf.downloadの429は銘柄別エラーへ変換せず即時送出すること。"""
    fake_yfinance = type(
        'FakeYFinance',
        (),
        {'download': staticmethod(lambda *args, **kwargs: (_ for _ in ()).throw(
            RuntimeError('429 Too Many Requests')))},
    )
    monkeypatch.setitem(sys.modules, 'yfinance', fake_yfinance)

    with pytest.raises(RateLimitError, match='429'):
        fetch_ohlcv_batch(['AAPL', 'MSFT'])


def test_fetch_ohlcv_batch_raises_rate_limit_error_for_yfinance_log(monkeypatch):
    """yfinanceが429をログ出力して正常復帰しても専用例外を送出すること。"""
    import pandas as pd

    frame = pd.DataFrame(
        {'Open': [100], 'High': [110], 'Low': [90], 'Close': [105], 'Volume': [1000]},
        index=pd.DatetimeIndex(['2026-09-09']),
    )

    def download(*args, **kwargs):
        logging.getLogger('yfinance').warning(
            'Crumb fetch rate-limited (HTTP 429), continuing without crumb')
        return frame

    fake_yfinance = type('FakeYFinance', (), {'download': staticmethod(download)})
    monkeypatch.setitem(sys.modules, 'yfinance', fake_yfinance)

    with pytest.raises(RateLimitError, match='レート制限'):
        fetch_ohlcv_batch(['AAPL'])


def test_fetch_stock_info_raises_rate_limit_error_for_429(monkeypatch):
    """Ticker.infoの429を空辞書へ変換せず即時送出すること。"""
    class YFRateLimitError(Exception):
        pass

    class FakeTicker:
        @property
        def info(self):
            raise YFRateLimitError('Too Many Requests')

    fake_yfinance = type('FakeYFinance', (), {
        'Ticker': staticmethod(lambda symbol: FakeTicker()),
    })
    monkeypatch.setitem(sys.modules, 'yfinance', fake_yfinance)

    from stockapp.app.yahoo import fetch_stock_info

    with pytest.raises(RateLimitError, match='レート制限'):
        fetch_stock_info('AAPL')


def test_save_ohlcv_rows_rejects_price_outside_decimal_field_range(db):
    """DBのDecimalField範囲を超える株価を保存しないこと。"""
    with pytest.raises(StockFetchError, match='桁数範囲外'):
        save_ohlcv_rows('AAPL', [
            (datetime.date(2026, 9, 15), 100000000, 100000000, 99999999, 100000000, 1000),
        ])


def test_fetch_ohlcv_batch_converts_multi_index_download_result(monkeypatch):
    """yf.download の銘柄・項目MultiIndexを銘柄別の行へ変換すること。"""
    import pandas as pd

    symbols = ['1301.T', '130A.T']
    columns = pd.MultiIndex.from_product([symbols, ['Open', 'High', 'Low', 'Close', 'Volume']])
    frame = pd.DataFrame(
        [[100, 110, 90, 105, 1000, 200, 210, 190, 205, 2000]],
        index=pd.DatetimeIndex(['2026-09-09']),
        columns=columns,
    )
    fake_yfinance = type('FakeYFinance', (), {'download': staticmethod(lambda *args, **kwargs: frame)})
    monkeypatch.setitem(sys.modules, 'yfinance', fake_yfinance)

    rows_by_symbol, errors_by_symbol = fetch_ohlcv_batch(symbols, period='1y')

    assert not errors_by_symbol
    assert rows_by_symbol['1301.T'][0][:5] == (
        datetime.date(2026, 9, 9), 100, 110, 90, 105,
    )
    assert rows_by_symbol['130A.T'][0][5] == 2000


def test_fetch_ohlcv_batch_supports_single_symbol_columns(monkeypatch):
    """単一銘柄時の通常カラム形式も変換できること。"""
    import pandas as pd

    frame = pd.DataFrame(
        {'Open': [100], 'High': [110], 'Low': [90], 'Close': [105], 'Volume': [1000]},
        index=pd.DatetimeIndex(['2026-09-09']),
    )
    fake_yfinance = type('FakeYFinance', (), {'download': staticmethod(lambda *args, **kwargs: frame)})
    monkeypatch.setitem(sys.modules, 'yfinance', fake_yfinance)

    rows_by_symbol, errors_by_symbol = fetch_ohlcv_batch(['1301.T'], period='1y')

    assert not errors_by_symbol
    assert len(rows_by_symbol['1301.T']) == 1


def test_fetch_ohlcv_batch_passes_one_day_period_to_yfinance(monkeypatch):
    """1d指定をyfinanceへそのまま渡すこと。"""
    import pandas as pd

    frame = pd.DataFrame(
        {'Open': [100], 'High': [110], 'Low': [90], 'Close': [105], 'Volume': [1000]},
        index=pd.DatetimeIndex(['2026-09-09']),
    )
    calls = []

    def recording_download(*args, **kwargs):
        calls.append(kwargs)
        return frame

    fake_yfinance = type('FakeYFinance', (), {'download': staticmethod(recording_download)})
    monkeypatch.setitem(sys.modules, 'yfinance', fake_yfinance)

    fetch_ohlcv_batch(['AAPL'], period='1d')
    assert calls[0]['period'] == '1d'


# ---------------------------------------------------------------------------
# 同日（イントレーダ）レコードの upsert: 引け後最終値の上書き
# ---------------------------------------------------------------------------

def test_save_ohlcv_rows_updates_existing_intraday_row(db):
    """引け後に取得した同日の最終値が、日中（引け前）に保存した行を上書きすること。

    既存の (symbol, date) レコードは更新される（新規作成されない）。
    実害の値（8306.T, 2026-09-15）で回帰テストする:
    日中保存 close=3689 / volume=21,892,300 → 引け後最終 close=3668 / volume=41,635,100。
    """
    day = datetime.date(2026, 9, 15)
    StockRecord.objects.create(
        symbol='8306.T', date=day,
        open=3714.0, high=3735.0, low=3640.0,
        close=3689.0, volume=21892300,
    )

    created, updated = save_ohlcv_rows('8306.T', [
        (day, 3714.0, 3735.0, 3640.0, 3668.0, 41635100),
    ])

    assert (created, updated) == (0, 1)
    assert StockRecord.objects.filter(symbol='8306.T', date=day).count() == 1
    record = StockRecord.objects.get(symbol='8306.T', date=day)
    assert record.close == pytest.approx(3668.0)
    assert record.volume == 41635100


def test_fetch_and_save_updates_intraday_row_after_close(db, monkeypatch):
    """引け後の fetch_and_save が同日行を最終値へ更新し、翌日分のみ新規作成すること。

    fetch_ohlcv / fetch_stock_info を monkeypatch してネットワークに依存しない。
    同日は update（1 件）、翌日以降は create（1 件）になること。
    """
    day = datetime.date(2026, 9, 15)
    next_day = datetime.date(2026, 9, 16)
    StockRecord.objects.create(
        symbol='8306.T', date=day,
        open=3714.0, high=3735.0, low=3640.0,
        close=3689.0, volume=21892300,
    )

    rows = [
        (day, 3714.0, 3735.0, 3640.0, 3668.0, 41635100),
        (next_day, 3670.0, 3690.0, 3630.0, 3655.0, 38000000),
    ]
    monkeypatch.setattr(
        'stockapp.app.yahoo.fetch_ohlcv', lambda symbol, period='1mo': rows)
    monkeypatch.setattr(
        'stockapp.app.yahoo.fetch_stock_info', lambda symbol: {})

    summary = fetch_and_save('8306.T', period='5d')

    assert summary['created'] == 1  # 翌日分のみ新規
    assert summary['updated'] == 1  # 同日分は上書き
    assert summary['fetched'] == 2
    intraday = StockRecord.objects.get(symbol='8306.T', date=day)
    assert intraday.close == pytest.approx(3668.0)
    assert intraday.volume == 41635100
    assert StockRecord.objects.get(symbol='8306.T', date=next_day).close == pytest.approx(3655.0)
    assert not ClassicTurtleSignal.objects.filter(symbol='8306.T').exists()

