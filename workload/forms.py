from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from django.forms import modelformset_factory

from .models import PickSeries

User = get_user_model()


class PickSeriesForm(forms.ModelForm):
    class Meta:
        model = PickSeries
        fields = ["series_type", "items"]
        widgets = {"items": forms.NumberInput(attrs={"min": 1, "step": 1, "inputmode": "numeric"})}


# One formset per day on the edit page. Empty extra rows are ignored on save.
PickSeriesFormSet = modelformset_factory(PickSeries, form=PickSeriesForm, extra=1, can_delete=True)


class UserCreateForm(UserCreationForm):
    is_admin = forms.BooleanField(
        label="Administrator",
        required=False,
        help_text="Kan redigere ugedata og administrere brugere.",
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "first_name", "last_name")

    def save(self, commit=True):
        user = super().save(commit=False)
        user.is_staff = self.cleaned_data["is_admin"]
        if commit:
            user.save()
        return user


class UserEditForm(forms.ModelForm):
    class Meta:
        model = User
        fields = ["first_name", "last_name", "is_staff", "is_active"]
        labels = {"is_staff": "Administrator", "is_active": "Aktiv"}
        help_texts = {
            "is_staff": "Kan redigere ugedata og administrere brugere.",
            "is_active": "Inaktive brugere kan ikke logge ind.",
        }

    def __init__(self, *args, editing_self=False, **kwargs):
        super().__init__(*args, **kwargs)
        if editing_self:
            # Prevents admins from locking themselves out.
            for name in ("is_staff", "is_active"):
                self.fields[name].disabled = True
                self.fields[name].help_text = "Du kan ikke ændre dette for din egen bruger."
