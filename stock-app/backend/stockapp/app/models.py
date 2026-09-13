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


class StockMeta(models.Model):
    """銘柄メタ情報（銘柄名など）。

    Yahoo Finance の株価データには銘柄名が含まれないため、Ticker.info から
    別途取得してこのテーブルにキャッシュする（Issue #49）。
    """

    symbol = models.CharField(max_length=10, unique=True)
    name = models.CharField(max_length=200, blank=True, default='')
    updated_at = models.DateTimeField(auto_now=True)


class StockList(models.Model):
    """銘柄リスト（Issue #50）。

    お気に入り銘柄を格納するリスト。初期状態で 10 個（リスト1〜リスト10）が
    シードされ、ユーザーは作成・名前変更・削除できる。銘柄は複数リストに
    所属できる（FavoriteStock が (list, symbol) で一意）。
    """

    name = models.CharField(max_length=50, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)


class FavoriteStock(models.Model):
    """お気に入り銘柄の所属（Issue #50）。

    1 行 = 1 個のリストへの銘柄所属。同じシンボルは複数リストに所属できる。
    銘柄名は StockMeta と同期する（yahoo.upsert_stock_meta が
    StockMeta 更新時に同じくこの行の name を更新する）。
    """

    list = models.ForeignKey(StockList, on_delete=models.CASCADE, related_name='favorites')
    symbol = models.CharField(max_length=10)
    name = models.CharField(max_length=200, blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        # 同一リスト内の重複登録を防ぐ（リスト間の重複は許容）
        constraints = [
            models.UniqueConstraint(
                fields=('list', 'symbol'),
                name='unique_favorite_per_list',
            ),
        ]