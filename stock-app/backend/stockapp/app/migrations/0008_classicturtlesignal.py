from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [('app', '0007_stockmeta_info_favoritestock_sector')]

    operations = [
        migrations.CreateModel(
            name='ClassicTurtleSignal',
            fields=[
                ('id', models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('symbol', models.CharField(max_length=10)),
                ('date', models.DateField()),
                ('system', models.CharField(choices=[('system1', 'System 1'), ('system2', 'System 2')], max_length=7)),
                ('side', models.CharField(choices=[('long', 'Long'), ('short', 'Short')], max_length=5)),
                ('price', models.DecimalField(decimal_places=4, max_digits=12)),
                ('n', models.DecimalField(decimal_places=4, max_digits=12)),
                ('volume', models.BigIntegerField(blank=True, null=True)),
                ('turnover', models.DecimalField(blank=True, decimal_places=4, max_digits=24, null=True)),
                ('strategy_version', models.CharField(default='classic-v1', max_length=20)),
            ],
            options={
                'constraints': [models.UniqueConstraint(fields=('symbol', 'date', 'strategy_version'), name='classicturtlesignal_symbol_date_version_uniq')],
                'indexes': [
                    models.Index(fields=('date', 'system', 'side'), name='classic_signal_filter_idx'),
                    models.Index(fields=('symbol', 'date'), name='classic_signal_symbol_date_idx'),
                ],
            },
        ),
    ]