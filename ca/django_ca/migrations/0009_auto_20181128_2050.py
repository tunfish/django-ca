# Generated by Django 2.1.3 on 2018-11-28 20:50

import datetime
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('django_ca', '0008_auto_20171203_2001'),
    ]

    operations = [
        migrations.AddField(
            model_name='certificate',
            name='valid_from',
            field=models.DateTimeField(default=datetime.datetime(2018, 11, 28, 20, 50, 23, 447354)),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='certificateauthority',
            name='valid_from',
            field=models.DateTimeField(default=datetime.datetime(2018, 11, 28, 20, 50, 47, 196936)),
            preserve_default=False,
        ),
    ]