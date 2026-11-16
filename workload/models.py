from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models


class PickSeries(models.Model):
    """One pick series on one day. A day can have any number of them.

    Everything else (hours, collection, storage) is calculated from these rows
    when a page is shown, so nothing derived is stored.
    """

    class Type(models.TextChoices):
        # The keys must match [pick_series] in rates.toml.
        MIXED = "mixed", "Blandet serie"
        DSV = "dsv", "DSV-serie"
        LARGE_MIXED = "large_mixed", "Stor serie, forskellige varer"
        LARGE_SAME = "large_same", "Stor serie, ens varer"
        CUSHIONS = "cushions", "Hynder"

    date = models.DateField("dato", db_index=True)
    series_type = models.CharField("type", max_length=20, choices=Type.choices)
    items = models.PositiveIntegerField("antal stk.", validators=[MinValueValidator(1)])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="senest ændret af",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        ordering = ["date", "id"]
        verbose_name = "plukserie"
        verbose_name_plural = "plukserier"

    def __str__(self):
        return f"{self.date:%d-%m-%Y}: {self.get_series_type_display()}, {self.items} stk."
