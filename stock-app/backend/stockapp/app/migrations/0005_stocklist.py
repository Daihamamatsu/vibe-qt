# 手書き移行（Issue #50）: お気に入りを複数リスト構造に変更
"""
- StockList モデルを作成し、初期 10 リスト（リスト1〜リスト10）をシードする
- FavoriteStock に list FK を追加し、既存のお気に入りは リスト1 へ所属させる
- (list, symbol) 一意制約に変更（symbol のみ unique は廃止）
"""
import django.db.models.deletion
from django.db import migrations, models


def seed_default_lists(apps, schema_editor):
    """初期 10 リストを幂等地に作成する（既存ならスキップ）。"""
    StockList = apps.get_model('app', 'StockList')
    for i in range(1, 11):
        StockList.objects.get_or_create(name=f'リスト{i}')


def unseed_default_lists(apps, schema_editor):
    """ロールバック時: 所属行が残らないシードリストを削除する。"""
    StockList = apps.get_model('app', 'StockList')
    FavoriteStock = apps.get_model('app', 'FavoriteStock')
    in_use = set(FavoriteStock.objects.values_list('list__name', flat=True))
    for i in range(1, 11):
        name = f'リスト{i}'
        if name not in in_use:
            StockList.objects.filter(name=name).delete()


def assign_legacy_favorites(apps, schema_editor):
    """既存のお気に入り（list 未設定行）を リスト1 に所属させる。"""
    StockList = apps.get_model('app', 'StockList')
    FavoriteStock = apps.get_model('app', 'FavoriteStock')
    first = StockList.objects.filter(name='リスト1').first()
    if first is None:
        return
    FavoriteStock.objects.filter(list__isnull=True).update(list=first)


def clear_legacy_favorites(apps, schema_editor):
    """ロールバック時: リスト1 への所属を解除する（field 削除前に null 化）。"""
    StockList = apps.get_model('app', 'StockList')
    FavoriteStock = apps.get_model('app', 'FavoriteStock')
    first = StockList.objects.filter(name='リスト1').first()
    if first is not None:
        FavoriteStock.objects.filter(list=first).update(list=None)


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0004_favoritestock'),
    ]

    operations = [
        # 1) StockList テーブル作成
        migrations.CreateModel(
            name='StockList',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=50, unique=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
        ),
        # 2) 初期 10 リストをシード
        migrations.RunPython(seed_default_lists, unseed_default_lists),
        # 3) FavoriteStock に nullable な list FK を追加
        migrations.AddField(
            model_name='favoritestock',
            name='list',
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to='app.stocklist',
            ),
        ),
        # 4) 既存行を リスト1 へ所属させる
        migrations.RunPython(assign_legacy_favorites, clear_legacy_favorites),
        # 5) list FK を必須化（ロールバック時は先で null 化される）
        migrations.AlterField(
            model_name='favoritestock',
            name='list',
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name='favorites',
                to='app.stocklist',
            ),
        ),
        # 6) symbol の unique を外す
        migrations.AlterField(
            model_name='favoritestock',
            name='symbol',
            field=models.CharField(max_length=10),
        ),
        # 7) (list, symbol) 一意制約を追加
        migrations.AddConstraint(
            model_name='favoritestock',
            constraint=models.UniqueConstraint(
                fields=('list', 'symbol'),
                name='unique_favorite_per_list',
            ),
        ),
    ]