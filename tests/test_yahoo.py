"""stockapp/app/yahoo.py のユニットテスト (Issue #50)"""
import datetime
import sys

import pytest

from stockapp.app.models import StockRecord
from stockapp.app.yahoo import StockFetchError, fetch_and_save, fetch_ohlcv, save_ohlcv_rows


def test_fetch_ohlcv_import_failure_raises_stock_fetch_error(monkeypatch):
    """yfinance の import が失敗しても StockFetchError（502）で済ませ 500 にしない。"""
    # sys.modules のエントリを None にすると `import yfinance` は ImportError となる
    monkeypatch.setitem(sys.modules, 'yfinance', None)
    with pytest.raises(StockFetchError):
        fetch_ohlcv('AAPL')


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

    fetch_ohlcv / fetch_stock_name を monkeypatch してネットワークに依存しない。
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
        'stockapp.app.yahoo.fetch_stock_name', lambda symbol: '')

    summary = fetch_and_save('8306.T', period='5d')

    assert summary['created'] == 1  # 翌日分のみ新規
    assert summary['updated'] == 1  # 同日分は上書き
    assert summary['fetched'] == 2
    intraday = StockRecord.objects.get(symbol='8306.T', date=day)
    assert intraday.close == pytest.approx(3668.0)
    assert intraday.volume == 41635100
    assert StockRecord.objects.get(symbol='8306.T', date=next_day).close == pytest.approx(3655.0)

