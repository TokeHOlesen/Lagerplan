from django.db import migrations, models


class Migration(migrations.Migration):
    """Adds the "Hynder" (cushions) pick series type. Existing data is unchanged."""

    dependencies = [
        ("workload", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="pickseries",
            name="series_type",
            field=models.CharField(
                choices=[
                    ("mixed", "Blandet serie"),
                    ("dsv", "DSV-serie"),
                    ("large_mixed", "Stor serie, forskellige varer"),
                    ("large_same", "Stor serie, ens varer"),
                    ("cushions", "Hynder"),
                ],
                max_length=20,
                verbose_name="type",
            ),
        ),
    ]
