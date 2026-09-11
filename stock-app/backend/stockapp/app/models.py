from django.db import models

class StockRecord(models.Model):
    symbol = models.CharField(max_length=10)
    date = models.DateField()
    close = models.DecimalField(max_digits=12, decimal_places=4)

    class Meta:
        # Django 4.1+ で非推奨の unique_together を制約定義に置き換え
        constraints = [
            models.UniqueConstraint(
                fields=('symbol', 'date'),
                name='stockrecord_symbol_date_uniq',
            ),
        ]