# Generated by Django 3.0.7 on 2020-06-21 16:23

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('django_ca', '0022_acmechallenge'),
    ]

    operations = [
        migrations.AddField(
            model_name='acmeaccountauthorization',
            name='status',
            field=models.CharField(choices=[('pending', 'pending'), ('valid', 'valid'), ('invalid', 'invalid'), ('deactivated', 'deactivated'), ('expired', 'expired'), ('revoked', 'revoked')], default='pending', max_length=12),
        ),
        migrations.AddField(
            model_name='acmeaccountauthorization',
            name='wildcard',
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name='acmechallenge',
            name='status',
            field=models.CharField(choices=[('http-01', 'HTTP Challenge'), ('dns-01', 'DNS Challenge'), ('tls-alpn-01', 'TLS ALPN Challenge')], default='pending', max_length=12),
        ),
    ]
