from django.db import models

class StockRecord(models.Model):
    symbol = models.CharField(max_length=10)
    date = models.DateField()
    close = models.DecimalField(max_digits=12, decimal_places=4)

    class Meta:
        unique_together = ('symbol', 'date')