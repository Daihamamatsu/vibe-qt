from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('app', '0006_favoritestock_order'),
    ]

    operations = [
        migrations.AddField(
            model_name='stockmeta',
            name='info',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name='stockmeta',
            name='sector',
            field=models.CharField(blank=True, default='', max_length=200),
        ),
        migrations.AddField(
            model_name='favoritestock',
            name='sector',
            field=models.CharField(blank=True, default='', max_length=200),
        ),
    ]