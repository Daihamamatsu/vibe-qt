"""東証上場銘柄全銘柄の株価を一括登録する管理コマンド（Issue #65）。

使い方:
    python manage.py fetch_tickers_j [--csv PATH] [--period 1y] [--limit N] [--sleep 秒]

銘柄リスト CSV（既定: backend/data/data_j.csv）を読み、各銘柄を
Yahoo Finance（yfinance）から日足取得して StockRecord に upsert する。
再実行は upsert 意味論で安全（中断後の再開・差分更新に使える）。
"""
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from stockapp.app.tickers import DEFAULT_CSV_PATH, fetch_all
from stockapp.app.yahoo import VALID_PERIODS

# 進捗表示の間隔（銘柄数）
PROGRESS_EVERY = 25


class Command(BaseCommand):
    help = '東証上場銘柄全銘柄の直近1年分の日足株価を DB へ一括登録する（銘柄リスト CSV, Issue #65）'

    def add_arguments(self, parser):
        parser.add_argument(
            '--csv', default=str(DEFAULT_CSV_PATH),
            help='銘柄リスト CSV のパス（既定: %(default)s）')
        parser.add_argument(
            '--period', default='1y',
            help='取得期間（%s のいずれか。既定: 1y）' % ', '.join(sorted(VALID_PERIODS)))
        parser.add_argument(
            '--limit', type=int, default=None,
            help='先頭 N 件の銘柄のみ処理する（動作確認用）')
        parser.add_argument(
            '--sleep', type=float, default=0.5,
            help='銘柄間の待機秒数（Yahoo Finance のレート制限対策。既定: %(default)s）')

    def handle(self, *args, **options):
        csv_path = Path(options['csv'])
        period = options['period']
        if period not in VALID_PERIODS:
            raise CommandError(f'無効な取得期間です: {period}')
        if not csv_path.exists():
            raise CommandError(f'銘柄リスト CSV が見つかりません: {csv_path}')

        def progress(i, total, ticker, summary):
            if i % PROGRESS_EVERY == 0 or i == total:
                self.stdout.write(
                    f'[{i}/{total}] {ticker["code"]} ... '
                    f'ok={summary["ok"]} no_data={summary["no_data"]} failed={summary["failed"]}'
                )

        summary = fetch_all(
            csv_path=csv_path,
            period=period,
            limit=options['limit'],
            sleep=options['sleep'],
            progress_cb=progress,
        )
        self.stdout.write(self.style.SUCCESS(
            f"完了: total={summary['total']} ok={summary['ok']} "
            f"no_data={summary['no_data']} failed={summary['failed']} "
            f"created={summary['created']} updated={summary['updated']}"
        ))
        # エラー一覧は先頭 20 件まで表示
        for err in summary['errors'][:20]:
            self.stdout.write(f"  {err['code']} ({err['symbol']}): {err['reason']}")
        if len(summary['errors']) > 20:
            self.stdout.write(f"  ...（残り {len(summary['errors']) - 20} 件は省略）")
