"""米国銘柄一覧 CSV と一括取得のテスト。"""
from unittest import mock

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from stockapp.app.models import StockMeta, StockRecord
from stockapp.app.us_tickers import (
    fetch_all_us,
    fetch_listing_csv,
    load_listing_csv,
    load_us_ticker_list,
    save_listing_csv,
)
from stockapp.app.yahoo import RateLimitError


CSV = """symbol,name,exchange,assetType,ipoDate,delistingDate,status
AAPL,Apple Inc,NASDAQ,Stock,1980-12-12,null,Active
MSFT,Microsoft Corporation,NASDAQ,Stock,1986-03-13,null,Active
SPY,SPDR S&P 500 ETF Trust,NYSE ARCA,ETF,1993-01-22,null,Active
OLD,Old Corp,NYSE,Stock,2000-01-01,2020-01-01, delisted
AAPL,Duplicate,NASDAQ,Stock,1980-12-12,null,Active
"""


def test_load_us_ticker_list_filters_and_deduplicates():
    assert load_us_ticker_list(CSV) == [
        {'symbol': 'AAPL', 'name': 'Apple Inc', 'asset_type': 'Stock', 'exchange': 'NASDAQ'},
        {'symbol': 'MSFT', 'name': 'Microsoft Corporation', 'asset_type': 'Stock', 'exchange': 'NASDAQ'},
    ]
    assert len(load_us_ticker_list(CSV, asset_types=('Stock', 'ETF'))) == 3


def test_load_us_ticker_list_rejects_missing_columns():
    with pytest.raises(ValueError, match='必要な列'):
        load_us_ticker_list('symbol,name\nAAPL,Apple\n')


def test_fetch_listing_csv_returns_csv_response():
    response = mock.MagicMock()
    response.read.return_value = CSV.encode('utf-8')
    response.__enter__.return_value = response
    with mock.patch('stockapp.app.us_tickers.urlopen', return_value=response) as urlopen:
        assert fetch_listing_csv('secret') == CSV
    request = urlopen.call_args.args[0]
    assert 'function=LISTING_STATUS' in request.full_url
    assert 'apikey=secret' in request.full_url


def test_fetch_listing_csv_rejects_non_csv_response():
    response = mock.MagicMock()
    response.read.return_value = b'{"Note":"rate limit"}'
    response.__enter__.return_value = response
    with mock.patch('stockapp.app.us_tickers.urlopen', return_value=response):
        with pytest.raises(ValueError, match='CSV'):
            fetch_listing_csv('secret')


def test_listing_csv_can_be_saved_and_loaded(tmp_path):
    path = tmp_path / 'listing_status_us.csv'
    assert save_listing_csv(CSV, path) == path
    assert path.read_text(encoding='utf-8') == CSV
    assert load_listing_csv(path) == CSV


def test_load_listing_csv_rejects_invalid_file(tmp_path):
    path = tmp_path / 'invalid.csv'
    path.write_text('{"Note":"rate limit"}', encoding='utf-8')
    with pytest.raises(ValueError, match='形式が不正'):
        load_listing_csv(path)


@pytest.mark.django_db
def test_fetch_all_us_saves_csv_name_and_info():
    rows = [("2026-09-01", 100, 101, 99, 100, 1000)]
    with mock.patch(
        'stockapp.app.us_tickers.fetch_ohlcv_batch',
        return_value=({'AAPL': rows, 'MSFT': rows}, {}),
    ), \
            mock.patch('stockapp.app.us_tickers.fetch_stock_info', return_value={'shortName': 'Apple', 'sector': 'Technology'}):
        summary = fetch_all_us(csv_text=CSV, sleep=0)
    assert summary['ok'] == 2
    assert StockRecord.objects.filter(symbol='AAPL').count() == 1
    assert StockMeta.objects.get(symbol='AAPL').name == 'Apple Inc'
    assert StockMeta.objects.get(symbol='AAPL').info['shortName'] == 'Apple'


@pytest.mark.django_db
def test_fetch_all_us_stops_immediately_on_rate_limit(monkeypatch):
    """米国銘柄の一括取得は429発生後に保存や進捗通知を続行しないこと。"""
    progress = mock.Mock()
    monkeypatch.setattr(
        'stockapp.app.us_tickers.fetch_ohlcv_batch',
        mock.Mock(side_effect=RateLimitError('429 Too Many Requests')),
    )

    with pytest.raises(RateLimitError, match='429'):
        fetch_all_us(csv_text=CSV, sleep=0, progress_cb=progress)

    assert StockRecord.objects.count() == 0
    assert StockMeta.objects.count() == 0
    progress.assert_not_called()


@pytest.mark.django_db
def test_fetch_all_us_skip_info_only_saves_prices():
    rows = [("2026-09-01", 100, 101, 99, 100, 1000)]
    with mock.patch(
        'stockapp.app.us_tickers.fetch_ohlcv_batch',
        return_value=({'AAPL': rows, 'MSFT': rows}, {}),
    ), mock.patch('stockapp.app.us_tickers.fetch_stock_info') as fetch_info:
        summary = fetch_all_us(csv_text=CSV, sleep=0, skip_info=True)
    assert summary['ok'] == 2
    assert StockRecord.objects.count() == 2
    assert StockMeta.objects.count() == 0
    fetch_info.assert_not_called()


@pytest.mark.django_db
def test_fetch_tickers_us_command_uses_saved_csv_without_api_call(tmp_path):
    csv_path = tmp_path / 'listing_status_us.csv'
    csv_path.write_text(CSV, encoding='utf-8')
    rows = [("2026-09-01", 100, 101, 99, 100, 1000)]
    with mock.patch('stockapp.app.management.commands.fetch_tickers_us.fetch_listing_csv') as fetch_listing, \
            mock.patch('stockapp.app.us_tickers.fetch_ohlcv_batch', return_value=({'AAPL': rows, 'MSFT': rows}, {})), \
            mock.patch('stockapp.app.us_tickers.fetch_stock_info', return_value={}):
        call_command('fetch_tickers_us', csv=str(csv_path), limit=2, sleep=0, period='1d')
    fetch_listing.assert_not_called()
    assert StockMeta.objects.filter(symbol='AAPL').exists()
