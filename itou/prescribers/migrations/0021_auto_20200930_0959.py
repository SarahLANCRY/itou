# Generated by Django 3.1.1 on 2020-09-30 07:59

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("prescribers", "0020_auto_20200924_1420"),
    ]

    operations = [
        migrations.AlterField(
            model_name="prescriberorganization",
            name="kind",
            field=models.CharField(
                choices=[
                    ("PE", "Pôle emploi"),
                    ("CAP_EMPLOI", "CAP emploi"),
                    ("ML", "Mission locale"),
                    ("DEPT", "Service social du conseil départemental"),
                    ("DEPT_BRSA", "Dispositif conventionné par le conseil départemental pour le suivi BRSA"),
                    ("SPIP", "SPIP - Service pénitentiaire d'insertion et de probation"),
                    ("PJJ", "PJJ - Protection judiciaire de la jeunesse"),
                    ("CCAS", "CCAS - Centre communal d'action sociale ou centre intercommunal d'action sociale"),
                    ("PLIE", "PLIE - Plan local pour l'insertion et l'emploi"),
                    ("CHRS", "CHRS - Centre d'hébergement et de réinsertion sociale"),
                    ("CIDFF", "CIDFF - Centre d'information sur les droits des femmes et des familles"),
                    ("PREVENTION", "Service ou club de prévention"),
                    ("AFPA", "AFPA - Agence nationale pour la formation professionnelle des adultes"),
                    ("PIJ_BIJ", "PIJ-BIJ - Point/Bureau information jeunesse"),
                    ("CAF", "CAF - Caisse d'allocation familiale"),
                    ("CADA", "CADA - Centre d'accueil de demandeurs d'asile"),
                    ("ASE", "ASE - Aide sociale à l'enfance"),
                    ("CAVA", "CAVA - Centre d'adaptation à la vie active"),
                    ("CPH", "CPH - Centre provisoire d'hébergement"),
                    ("CHU", "CHU - Centre d'hébergement d'urgence"),
                    (
                        "OACAS",
                        "OACAS - Structure porteuse d'un agrément national organisme d'accueil communautaire et d'activité solidaire",  # noqa E501 line too long
                    ),
                    ("OTHER", "Autre"),
                ],
                default="OTHER",
                max_length=20,
                verbose_name="Type",
            ),
        ),
    ]
