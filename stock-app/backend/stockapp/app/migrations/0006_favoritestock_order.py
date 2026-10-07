from django.db import migrations, models


def initialize_favorite_order(apps, schema_editor):
    """既存のお気に入りを登録日時順に並べ、順序番号を初期化する。"""
    FavoriteStock = apps.get_model('app', 'FavoriteStock')
    list_ids = FavoriteStock.objects.values_list('list_id', flat=True).distinct()
    for list_id in list_ids:
        favorites = FavoriteStock.objects.filter(list_id=list_id).order_by('created_at', 'id')
        for order, favorite in enumerate(favorites):
            FavoriteStock.objects.filter(pk=favorite.pk).update(order=order)


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0005_stocklist'),
    ]

    operations = [
        migrations.AddField(
            model_name='favoritestock',
            name='order',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.RunPython(initialize_favorite_order, migrations.RunPython.noop),
    ]