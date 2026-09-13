"""stockapp/app/yahoo.py のユニットテスト (Issue #50)"""
import sys

import pytest

from stockapp.app.yahoo import StockFetchError, fetch_ohlcv


def test_fetch_ohlcv_import_failure_raises_stock_fetch_error(monkeypatch):
    """yfinance の import が失敗しても StockFetchError（502）で済ませ 500 にしない。"""
    # sys.modules のエントリを None にすると `import yfinance` は ImportError となる
    monkeypatch.setitem(sys.modules, 'yfinance', None)
    with pytest.raises(StockFetchError):
        fetch_ohlcv('AAPL')
