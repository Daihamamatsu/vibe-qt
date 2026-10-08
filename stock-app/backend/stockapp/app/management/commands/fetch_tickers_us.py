"""Alpha Vantage の米国銘柄一覧から株価・Ticker.infoを一括登録する管理コマンド。"""
import os

from django.core.management.base import BaseCommand, CommandError

from stockapp.app.us_tickers import (
    DEFAULT_ASSET_TYPES,
    DEFAULT_BATCH_SIZE,
    DEFAULT_LISTING_CSV_PATH,
    fetch_all_us,
    fetch_listing_csv,
    load_listing_csv,
    save_listing_csv,
)
from stockapp.app.yahoo import VALID_PERIODS


class Command(BaseCommand):
    help = 'Alpha Vantage の米国銘柄一覧から株価と Ticker.info を一括登録する'

    def add_arguments(self, parser):
        parser.add_argument('--api-key', default=os.environ.get('ALPHA_VANTAGE_API_KEY', 'demo'),
                            help='Alpha Vantage API キー（既定: 環境変数または demo）')
        parser.add_argument('--csv', default=str(DEFAULT_LISTING_CSV_PATH),
                            help='銘柄一覧 CSV の保存・読み込み先')
        parser.add_argument('--refresh', action='store_true',
                            help='Alpha Vantage から CSV を再取得して上書きする')
        parser.add_argument('--period', default='1y')
        parser.add_argument('--limit', type=int, default=None)
        parser.add_argument('--sleep', type=float, default=0.5)
        parser.add_argument('--batch-size', type=int, default=DEFAULT_BATCH_SIZE)
        parser.add_argument('--asset-type', default=','.join(DEFAULT_ASSET_TYPES),
                            help='対象 assetType（カンマ区切り、既定: Stock）')
        parser.add_argument('--status', default='Active')
        parser.add_argument('--skip-info', action='store_true',
                            help='Ticker.info の取得と StockMeta 更新を省略する')

    def handle(self, *args, **options):
        if options['period'] not in VALID_PERIODS:
            raise CommandError(f"無効な取得期間です: {options['period']}")
        if options['batch_size'] < 1:
            raise CommandError('--batch-size は1以上で指定してください')
        csv_path = options['csv']
        try:
            if options['refresh'] or not os.path.exists(csv_path):
                csv_text = fetch_listing_csv(options['api_key'])
                save_listing_csv(csv_text, csv_path)
                self.stdout.write(f'銘柄一覧 CSV を保存しました: {csv_path}')
            else:
                csv_text = load_listing_csv(csv_path)
                self.stdout.write(f'保存済みの銘柄一覧 CSV を使用します: {csv_path}')
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        def progress(i, total, ticker, summary):
            if i % 25 == 0 or i == total:
                self.stdout.write(
                    f'[{i}/{total}] {ticker["symbol"]} ... '
                    f'ok={summary["ok"]} no_data={summary["no_data"]} failed={summary["failed"]}'
                )

        try:
            summary = fetch_all_us(
                api_key=options['api_key'], period=options['period'], limit=options['limit'],
                csv_text=csv_text,
                sleep=options['sleep'], batch_size=options['batch_size'],
                asset_types=options['asset_type'].split(','), status=options['status'],
                skip_info=options['skip_info'], progress_cb=progress,
            )
        except (ValueError, OSError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(
            f"完了: total={summary['total']} ok={summary['ok']} "
            f"no_data={summary['no_data']} failed={summary['failed']} "
            f"created={summary['created']} updated={summary['updated']}"
        ))
        for error in summary['errors'][:20]:
            self.stdout.write(f"  {error['symbol']}: {error['reason']}")