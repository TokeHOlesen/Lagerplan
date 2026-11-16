"""Turns calculation results into ready-to-render values for the templates.

Pure Python (no Django). Numbers are formatted here in Danish style
(1.234,5), and CSS sizes are formatted with a dot, so templates never have to
do arithmetic or worry about localisation.
"""

from __future__ import annotations

import calendar as pycal
import math
from collections.abc import Mapping, Sequence
from datetime import date

from .calculation import GOOD, OVER, SEGMENT_KEYS, TIGHT, VERY_TIGHT, DayResult, employees_needed

WEEKDAYS = ("Mandag", "Tirsdag", "Onsdag", "Torsdag", "Fredag", "Lørdag", "Søndag")
WEEKDAYS_SHORT = ("Ma", "Ti", "On", "To", "Fr")
MONTHS = ("januar", "februar", "marts", "april", "maj", "juni", "juli",
          "august", "september", "oktober", "november", "december")

SEGMENT_LABELS = {
    "picking": "Pluk",
    "forklift": "Truck",
    "wrapping": "Strækfilm",
    "booking": "Booking",
    "labeling": "Etikettering",
    "collection": "Udlevering",
    "surcharge": "Pladsmangeltillæg",
}
STATUS_LABELS = {GOOD: "God", TIGHT: "Stram", VERY_TIGHT: "Meget stram", OVER: "Overkapacitet"}

_DANISH = str.maketrans({",": ".", ".": ","})


def fmt_num(value: float, decimals: int = 1) -> str:
    """1234.5 -> '1.234,5'."""
    return f"{value:,.{decimals}f}".translate(_DANISH)


def fmt_int(value: float) -> str:
    return fmt_num(round(value), 0)


def css_pct(value: float) -> str:
    return f"{max(0.0, value):.3f}"


def fmt_date_range(start: date, end: date) -> str:
    if start.year != end.year:
        return (f"{start.day}. {MONTHS[start.month - 1]} {start.year} – "
                f"{end.day}. {MONTHS[end.month - 1]} {end.year}")
    if start.month != end.month:
        return f"{start.day}. {MONTHS[start.month - 1]} – {end.day}. {MONTHS[end.month - 1]} {end.year}"
    return f"{start.day}.–{end.day}. {MONTHS[end.month - 1]} {end.year}"


def nice_axis(max_value: float, max_intervals: int = 5) -> tuple[float, list[float]]:
    """A round axis top and tick values for a chart whose largest value is max_value."""
    if max_value <= 0:
        max_value = 10.0
    raw_step = max_value / max_intervals
    magnitude = 10 ** math.floor(math.log10(raw_step))
    step = magnitude * 10
    for factor in (1, 2, 2.5, 5, 10):
        if factor * magnitude >= raw_step - 1e-12:
            step = factor * magnitude
            break
    intervals = math.ceil(max_value / step - 1e-9)
    ticks = [round(i * step, 6) for i in range(intervals + 1)]
    return ticks[-1], ticks


def build_week(dates: Sequence[date], results: Mapping[date, DayResult]) -> dict:
    """Context for the week page: bars, per-day figures, details table, totals."""
    day_results = [results[d] for d in dates]
    top, ticks = nice_axis(max(r.total for r in day_results))

    days = []
    for r in day_results:
        day = {
            "date": r.date,
            "weekday": WEEKDAYS[r.date.weekday()],
            "short_date": f"{r.date.day}/{r.date.month}",
            "closed": r.closed_reason,
        }
        if r.is_workday:
            day.update(
                total=fmt_num(r.total),
                employees=employees_needed(r.employees),
                employees_exact=fmt_num(r.employees),
                items=fmt_int(r.items_picked),
                pallets_new=fmt_int(r.pallets_new),
                has_pallets_new=r.pallets_new > 0,
                pallets=fmt_int(r.pallets),
                occupancy=fmt_int(r.occupancy * 100),
                status=r.storage_status,
                status_label=STATUS_LABELS[r.storage_status],
                has_surcharge=r.surcharge_rate > 0,
                surcharge_pct=fmt_int(r.surcharge_rate * 100),
                surcharge_hours=fmt_num(r.hours["surcharge"]),
                has_hours=r.total > 0,
                bar_height=css_pct(r.total / top * 100),
                segments=[
                    {
                        "key": key,
                        "label": SEGMENT_LABELS[key],
                        "hours": fmt_num(r.hours[key]),
                        "height": css_pct(r.hours[key] / top * 100),
                    }
                    for key in SEGMENT_KEYS
                    if r.hours[key] > 0
                ],
            )
        days.append(day)

    workdays = [r for r in day_results if r.is_workday]

    def row(label: str, values: list[str], total: str, strong: bool = False) -> dict:
        return {"label": label, "values": values, "total": total, "strong": strong}

    def per_day(fn) -> list[str]:
        return [fn(r) if r.is_workday else "–" for r in day_results]

    details = [
        row(SEGMENT_LABELS[key], per_day(lambda r, k=key: fmt_num(r.hours[k])),
            fmt_num(sum(r.hours[key] for r in workdays)))
        for key in SEGMENT_KEYS
    ]
    details.append(row("Mandetimer i alt", per_day(lambda r: fmt_num(r.total)),
                       fmt_num(sum(r.total for r in workdays)), strong=True))
    week_employee_days = sum(r.employees for r in workdays)
    details.append(row("Medarbejdere (præcist)", per_day(lambda r: fmt_num(r.employees)),
                       fmt_num(week_employee_days)))
    details.append(row("Stk. til pluk", per_day(lambda r: fmt_int(r.items_picked)),
                       fmt_int(sum(r.items_picked for r in workdays))))
    details.append(row("Lagerudnyttelse", per_day(lambda r: f"{fmt_int(r.occupancy * 100)} %"), ""))

    return {
        "days": days,
        "ticks": [
            {"label": fmt_num(t, 0 if float(t).is_integer() else 1), "bottom": css_pct(t / top * 100)}
            for t in ticks
        ],
        "legend": [{"key": k, "label": SEGMENT_LABELS[k]} for k in SEGMENT_KEYS],
        "details": details,
        "detail_headers": [f"{WEEKDAYS[d.weekday()]} {d.day}/{d.month}" for d in dates],
        "week_hours": fmt_num(sum(r.total for r in workdays)),
        "week_items": fmt_int(sum(r.items_picked for r in workdays)),
        # Average daily staffing over the week's open days, and the busiest day's need.
        "week_employees_avg": fmt_num(week_employee_days / len(workdays) if workdays else 0),
        "week_employees_max": max((employees_needed(r.employees) for r in workdays), default=0),
        "has_data": any(r.total > 0 for r in workdays),
    }


def build_year(year: int, results: Mapping[date, DayResult], today: date) -> list[dict]:
    """Twelve small month calendars (Monday to Friday) with ISO week numbers."""
    cal = pycal.Calendar(firstweekday=0)
    current_week = tuple(today.isocalendar())[:2]
    months = []
    for month in range(1, 13):
        weeks = []
        for week in cal.monthdatescalendar(year, month):
            workweek = week[:5]
            if not any(d.month == month for d in workweek):
                continue
            iso_year, iso_week, _ = week[0].isocalendar()
            cells = []
            for d in workweek:
                cell = {"day": "", "in_month": d.month == month, "today": d == today,
                        "status": "", "closed": False, "title": ""}
                if d.month == month:
                    cell["day"] = d.day
                    r = results.get(d)
                    if r is None or not r.is_workday:
                        cell["closed"] = r is not None
                        cell["title"] = r.closed_reason if r else ""
                    elif r.total > 0:
                        cell["status"] = r.storage_status
                        cell["title"] = (f"{fmt_num(r.total)} mandetimer · "
                                         f"{employees_needed(r.employees)} medarbejdere · "
                                         f"lager {STATUS_LABELS[r.storage_status].lower()}")
                    else:
                        cell["title"] = "Ingen plukserier"
                cells.append(cell)
            weeks.append({
                "iso_year": iso_year,
                "week": iso_week,
                "days": cells,
                "current": (iso_year, iso_week) == current_week,
            })
        months.append({"name": MONTHS[month - 1].capitalize(), "weeks": weeks})
    return months
