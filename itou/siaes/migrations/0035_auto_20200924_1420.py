# Generated by Django 3.1.1 on 2020-09-24 12:20

from django.conf import settings
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("siaes", "0034_auto_20200914_1702"),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name="siaemembership",
            unique_together={("user_id", "siae_id")},
        ),
    ]
