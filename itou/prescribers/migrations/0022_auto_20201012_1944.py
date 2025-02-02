# Generated by Django 3.1.2 on 2020-10-12 17:44

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("prescribers", "0021_auto_20200930_0959"),
    ]

    operations = [
        migrations.AlterField(
            model_name="prescriberorganization",
            name="code_safir_pole_emploi",
            field=models.CharField(
                blank=True,
                help_text="Code unique d'une agence Pole emploi.",
                max_length=5,
                null=True,
                unique=True,
                validators=[
                    django.core.validators.RegexValidator(
                        "^[0-9]{5}$", "Le code SAFIR doit être composé de 5 chiffres."
                    )
                ],
                verbose_name="Code Safir",
            ),
        ),
    ]
