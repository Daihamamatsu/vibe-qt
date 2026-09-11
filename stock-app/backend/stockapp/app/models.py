from django.db import models

class StockRecord(models.Model):
    symbol = models.CharField(max_length=10)
    date = models.DateField()
    # yfinance で取得する日足 OHLC（close のみ手入力した既存レコードのため null 許可）
    open = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    high = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    low = models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True)
    close = models.DecimalField(max_digits=12, decimal_places=4)
    volume = models.BigIntegerField(null=True, blank=True)

    class Meta:
        # Django 4.1+ で非推奨の unique_together を制約定義に置き換え
        constraints = [
            models.UniqueConstraint(
                fields=('symbol', 'date'),
                name='stockrecord_symbol_date_uniq',
            ),
        ]