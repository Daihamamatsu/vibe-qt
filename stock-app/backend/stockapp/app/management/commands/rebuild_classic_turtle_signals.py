"""DB内の株価データから古典タートルズシグナルを再構築する管理コマンド。"""

from django.core.management.base import BaseCommand, CommandError

from stockapp.app.classic_turtle import rebuild_symbol_signals
from stockapp.app.models import StockRecord


class Command(BaseCommand):
    help = 'DB内の株価データだけを使って古典タートルズシグナルを再構築する'

    def add_arguments(self, parser):
        parser.add_argument(
            '--symbol',
            help='指定銘柄だけ再構築する（例: 1301.T）',
        )
        parser.add_argument(
            '--limit',
            type=int,
            help='先頭から指定件数の銘柄だけ再構築する',
        )

    def handle(self, *args, **options):
        symbol = options.get('symbol')
        limit = options.get('limit')
        if limit is not None and limit < 1:
            raise CommandError('--limit は1以上で指定してください')

        if symbol:
            symbols = [symbol.strip().upper()]
        else:
            symbols = list(
                StockRecord.objects.values_list('symbol', flat=True)
                .distinct()
                .order_by('symbol')
            )
            if limit is not None:
                symbols = symbols[:limit]

        total_signals = 0
        for index, current_symbol in enumerate(symbols, start=1):
            count = rebuild_symbol_signals(current_symbol)
            total_signals += count
            self.stdout.write(f'[{index}/{len(symbols)}] {current_symbol}: signals={count}')

        self.stdout.write(self.style.SUCCESS(
            f'完了: symbols={len(symbols)} signals={total_signals}'
        ))