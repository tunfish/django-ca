# Generated by Django 3.1.3 on 2020-11-14 13:34

from django.db import migrations, models
import django.db.models.deletion
import django_ca.models


class Migration(migrations.Migration):

    dependencies = [
        ('django_ca', '0032_auto_20201026_1532'),
    ]

    operations = [
        migrations.AlterField(
            model_name='acmeaccount',
            name='pem',
            field=models.TextField(unique=True, validators=[django_ca.models.pem_validator], verbose_name='Public key'),
        ),
        migrations.AlterField(
            model_name='acmechallenge',
            name='auth',
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name='challenges', to='django_ca.acmeaccountauthorization'),
        ),
    ]
