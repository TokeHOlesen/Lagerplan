import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PickSeries",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("date", models.DateField(db_index=True, verbose_name="dato")),
                (
                    "series_type",
                    models.CharField(
                        choices=[
                            ("mixed", "Blandet serie"),
                            ("dsv", "DSV-serie"),
                            ("large_mixed", "Stor serie, forskellige varer"),
                            ("large_same", "Stor serie, ens varer"),
                        ],
                        max_length=20,
                        verbose_name="type",
                    ),
                ),
                (
                    "items",
                    models.PositiveIntegerField(
                        validators=[django.core.validators.MinValueValidator(1)], verbose_name="antal stk."
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "updated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="+",
                        to=settings.AUTH_USER_MODEL,
                        verbose_name="senest ændret af",
                    ),
                ),
            ],
            options={
                "verbose_name": "plukserie",
                "verbose_name_plural": "plukserier",
                "ordering": ["date", "id"],
            },
        ),
    ]
