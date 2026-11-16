from collections import defaultdict
from datetime import date, timedelta

from django.contrib import messages
from django.contrib.auth import get_user_model, update_session_auth_hash
from django.contrib.auth.forms import SetPasswordForm
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from . import presentation
from .calculation import compute_days, lookback_start
from .calendar_dk import week_dates
from .forms import PickSeriesFormSet, UserCreateForm, UserEditForm
from .models import PickSeries
from .permissions import admin_required, can_manage
from .rates import get_rates

User = get_user_model()


# --- helpers -----------------------------------------------------------------

def _week_or_404(year: int, week: int) -> list[date]:
    try:
        return week_dates(year, week)
    except ValueError:
        raise Http404("Ugen findes ikke.")


def _compute(dates: list[date]):
    """Calculation results for the given dates, reading only the rows needed."""
    rates = get_rates()
    picks: dict[date, list[tuple[str, int]]] = defaultdict(list)
    rows = PickSeries.objects.filter(date__gte=lookback_start(dates[0], rates), date__lte=dates[-1])
    for d, series_type, items in rows.values_list("date", "series_type", "items"):
        picks[d].append((series_type, items))
    return compute_days(dates, picks, rates), rates


def _week_nav(dates: list[date]) -> dict:
    monday = dates[0]
    year, week, _ = monday.isocalendar()
    prev_year, prev_week, _ = (monday - timedelta(days=7)).isocalendar()
    next_year, next_week, _ = (monday + timedelta(days=7)).isocalendar()
    today_year, today_week, _ = timezone.localdate().isocalendar()
    return {
        "year": year,
        "week": week,
        "prev_year": prev_year,
        "prev_week": prev_week,
        "next_year": next_year,
        "next_week": next_week,
        "today_year": today_year,
        "today_week": today_week,
        "is_current": (year, week) == (today_year, today_week),
        "range_label": presentation.fmt_date_range(dates[0], dates[-1]),
    }


# --- week and calendar ---------------------------------------------------------

def home(request):
    year, week, _ = timezone.localdate().isocalendar()
    return redirect("week", year=year, week=week)


def week_view(request, year, week):
    dates = _week_or_404(year, week)
    results, _ = _compute(dates)
    context = presentation.build_week(dates, results)
    context.update(_week_nav(dates))
    return render(request, "workload/week.html", context)


def year_current(request):
    return redirect("year", year=timezone.localdate().year)


def year_view(request, year):
    if not 2000 <= year <= 2100:
        raise Http404
    first = date(year, 1, 1)
    dates = [first + timedelta(days=i) for i in range((date(year + 1, 1, 1) - first).days)]
    results, _ = _compute(dates)
    today = timezone.localdate()
    return render(request, "workload/year.html", {
        "year": year,
        "prev_year": year - 1,
        "next_year": year + 1,
        "today_year": today.year,
        "today_week": tuple(today.isocalendar())[1],
        "today_iso_year": tuple(today.isocalendar())[0],
        "months": presentation.build_year(year, results, today),
        "weekdays": presentation.WEEKDAYS_SHORT,
    })


@admin_required
def week_edit(request, year, week):
    dates = _week_or_404(year, week)
    rates = get_rates()
    data = request.POST if request.method == "POST" else None

    days = []
    for d in dates:
        reason = rates.calendar.closed_reason(d)
        formset = None
        if not reason:
            formset = PickSeriesFormSet(
                data,
                queryset=PickSeries.objects.filter(date=d).order_by("id"),
                prefix=f"d{d:%Y%m%d}",
            )
        days.append({
            "date": d,
            "weekday": presentation.WEEKDAYS[d.weekday()],
            "date_label": f"{d.day}. {presentation.MONTHS[d.month - 1]}",
            "closed": reason,
            "formset": formset,
        })

    if request.method == "POST":
        formsets = [(day["date"], day["formset"]) for day in days if day["formset"] is not None]
        valid = [fs.is_valid() for _, fs in formsets]  # validate all, so every error shows
        if all(valid):
            with transaction.atomic():
                for d, fs in formsets:
                    instances = fs.save(commit=False)
                    for obj in fs.deleted_objects:
                        obj.delete()
                    for obj in instances:
                        obj.date = d
                        obj.updated_by = request.user
                        obj.save()
            messages.success(request, "Ugen er gemt.")
            return redirect("week", year=year, week=week)
        messages.error(request, "Ugen blev ikke gemt. Ret fejlene markeret nedenfor.")

    context = {"days": days}
    context.update(_week_nav(dates))
    return render(request, "workload/week_edit.html", context)


# --- user management (admins) -------------------------------------------------

def _managed_user_or_403(request, pk):
    target = get_object_or_404(User, pk=pk)
    if not can_manage(request.user, target):
        raise PermissionDenied
    return target


@admin_required
def user_list(request):
    users = User.objects.order_by("-is_active", "username")
    rows = [{"user": u, "manageable": can_manage(request.user, u)} for u in users]
    return render(request, "workload/user_list.html", {"rows": rows})


@admin_required
def user_create(request):
    form = UserCreateForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        messages.success(request, f"Brugeren {user.username} er oprettet.")
        return redirect("user_list")
    return render(request, "workload/user_form.html", {
        "form": form,
        "title": "Ny bruger",
        "submit_label": "Opret bruger",
    })


@admin_required
def user_edit(request, pk):
    target = _managed_user_or_403(request, pk)
    form = UserEditForm(request.POST or None, instance=target, editing_self=target.pk == request.user.pk)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"Brugeren {target.username} er opdateret.")
        return redirect("user_list")
    return render(request, "workload/user_form.html", {
        "form": form,
        "title": f"Redigér {target.username}",
        "submit_label": "Gem",
    })


@admin_required
def user_password(request, pk):
    target = _managed_user_or_403(request, pk)
    form = SetPasswordForm(target, request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        if target.pk == request.user.pk:
            update_session_auth_hash(request, target)  # stay logged in
        messages.success(request, f"Ny adgangskode er sat for {target.username}. Giv den til brugeren.")
        return redirect("user_list")
    return render(request, "workload/user_form.html", {
        "form": form,
        "title": f"Ny adgangskode til {target.username}",
        "submit_label": "Sæt adgangskode",
    })
