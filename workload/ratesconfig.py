"""Reading and validating rates.toml.

Pure Python (no Django). The Django side (workload/rates.py) adds caching and
automatic reloading when the file changes.
"""

from __future__ import annotations

import tomllib
from datetime import date
from pathlib import Path
from typing import Any

from .calculation import HANDLING_KEYS, ONE_PIECE_TASKS, SERIES_TYPES, Rates, default_task_overrides
from .calendar_dk import WorkCalendar


class RatesError(ValueError):
    """rates.toml is missing a value or has an invalid one."""


def _section(data: dict, name: str, required: bool = True) -> dict:
    section = data.get(name)
    if section is None and not required:
        return {}
    if not isinstance(section, dict):
        raise RatesError(f"missing section [{name}]")
    return section


def _number(section: dict, key: str, where: str, *, minimum: float = 0.0,
            maximum: float | None = None, exclusive_min: bool = False) -> float:
    if key not in section:
        raise RatesError(f"missing value {where}.{key}")
    value = section[key]
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise RatesError(f"{where}.{key} must be a number, got {value!r}")
    value = float(value)
    if value < minimum or (exclusive_min and value == minimum):
        raise RatesError(f"{where}.{key} must be {'above' if exclusive_min else 'at least'} {minimum:g}, got {value:g}")
    if maximum is not None and value > maximum:
        raise RatesError(f"{where}.{key} must be at most {maximum:g}, got {value:g}")
    return value


def _check_keys(section: dict, allowed: tuple[str, ...], where: str) -> None:
    unknown = sorted(set(section) - set(allowed))
    if unknown:
        raise RatesError(f"unknown key(s) in [{where}]: {', '.join(unknown)}")


def _parse_closed_days(values: Any) -> WorkCalendar:
    if not isinstance(values, list):
        raise RatesError("calendar.extra_closed_days must be a list of strings")
    yearly: set[tuple[int, int]] = set()
    dates: set[date] = set()
    for raw in values:
        if not isinstance(raw, str):
            raise RatesError(f"calendar.extra_closed_days: {raw!r} is not a string")
        try:
            if len(raw) == 5:  # MM-DD, every year
                month, day = (int(p) for p in raw.split("-"))
                date(2000, month, day)  # validates (2000 is a leap year)
                yearly.add((month, day))
            else:  # YYYY-MM-DD, one specific day
                dates.add(date.fromisoformat(raw))
        except ValueError:
            raise RatesError(f"calendar.extra_closed_days: {raw!r} is not MM-DD or YYYY-MM-DD") from None
    return WorkCalendar(extra_yearly=frozenset(yearly), extra_dates=frozenset(dates))


def parse_rates(data: dict) -> Rates:
    pick_section = _section(data, "pick_series")
    _check_keys(pick_section, SERIES_TYPES, "pick_series")
    pick = {t: _number(pick_section, t, "pick_series") for t in SERIES_TYPES}

    handling_section = _section(data, "handling")
    _check_keys(handling_section, (*HANDLING_KEYS, "collection"), "handling")
    handling = {k: _number(handling_section, k, "handling") for k in HANDLING_KEYS}
    collection_rate = _number(handling_section, "collection", "handling")

    collection_section = _section(data, "collection")
    _check_keys(collection_section, ("schedule", "freed_during_day"), "collection")
    schedule_raw = collection_section.get("schedule")
    if not isinstance(schedule_raw, list) or not 1 <= len(schedule_raw) <= 10:
        raise RatesError("collection.schedule must be a list of 1 to 10 shares")
    schedule = tuple(_number({"schedule": v}, "schedule", "collection", maximum=1) for v in schedule_raw)
    if abs(sum(schedule) - 1.0) > 1e-6:
        raise RatesError(f"collection.schedule must add up to 1.0, got {sum(schedule):g}")
    freed_during_day = (
        _number(collection_section, "freed_during_day", "collection", maximum=1)
        if "freed_during_day" in collection_section else 0.5
    )

    per_100_section = _section(data, "pallets_per_100")
    _check_keys(per_100_section, SERIES_TYPES, "pallets_per_100")
    pallets_per_100 = {t: _number(per_100_section, t, "pallets_per_100") for t in per_100_section}
    per_series_section = _section(data, "pallets_per_series", required=False)
    _check_keys(per_series_section, SERIES_TYPES, "pallets_per_series")
    pallets_per_series = {t: _number(per_series_section, t, "pallets_per_series") for t in per_series_section}
    missing = [t for t in SERIES_TYPES if t not in pallets_per_100 and t not in pallets_per_series]
    if missing:
        raise RatesError("no pallet figure for " + ", ".join(missing)
                         + ": add it under [pallets_per_100] or [pallets_per_series]")

    storage = _section(data, "storage")
    if "pallets_per_100" in storage:
        raise RatesError("storage.pallets_per_100 has been replaced by the [pallets_per_100] section, "
                         "with one value per pick series type")
    _check_keys(storage, ("capacity", "tight_above", "very_tight_above",
                          "tight_surcharge", "very_tight_surcharge", "over_capacity_surcharge"), "storage")
    capacity = storage.get("capacity")
    if isinstance(capacity, bool) or not isinstance(capacity, int) or capacity <= 0:
        raise RatesError("storage.capacity must be a whole number above 0")
    tight_above = _number(storage, "tight_above", "storage", maximum=1)
    very_tight_above = _number(storage, "very_tight_above", "storage", maximum=1)
    if not tight_above < very_tight_above:
        raise RatesError("storage.tight_above must be below storage.very_tight_above")
    tight_surcharge = _number(storage, "tight_surcharge", "storage")
    very_tight_surcharge = _number(storage, "very_tight_surcharge", "storage")
    # Optional, so an older rates.toml keeps working: then over capacity uses the very tight surcharge.
    over_capacity_surcharge = (_number(storage, "over_capacity_surcharge", "storage")
                               if "over_capacity_surcharge" in storage else very_tight_surcharge)

    calendar_section = _section(data, "calendar", required=False)
    _check_keys(calendar_section, ("extra_closed_days",), "calendar")
    calendar = _parse_closed_days(calendar_section.get("extra_closed_days", []))

    # Optional so that an older rates.toml without this section keeps working.
    staffing = _section(data, "staffing", required=False)
    _check_keys(staffing, ("hours_per_employee",), "staffing")
    hours_per_employee = (
        _number(staffing, "hours_per_employee", "staffing", exclusive_min=True, maximum=24)
        if "hours_per_employee" in staffing else 7.5
    )

    one_piece_section = _section(data, "one_piece_handling", required=False)
    _check_keys(one_piece_section, SERIES_TYPES, "one_piece_handling")
    one_piece = {}
    for series_type, tasks in one_piece_section.items():
        where = f"one_piece_handling.{series_type}"
        if not isinstance(tasks, list) or not all(isinstance(t, str) for t in tasks):
            raise RatesError(f"{where} must be a list of task names")
        unknown = sorted(set(tasks) - set(ONE_PIECE_TASKS))
        if unknown:
            raise RatesError(f"{where}: unknown task(s) {', '.join(unknown)}; "
                             f"choose from {', '.join(ONE_PIECE_TASKS)}")
        one_piece[series_type] = frozenset(tasks)

    # Optional: the defaults are 27 per 100 pcs and 1 per cushion series.
    estimate_section = _section(data, "pallet_estimate", required=False)
    _check_keys(estimate_section, ("per_100", "per_series"), "pallet_estimate")
    estimate_per_100 = (_number(estimate_section, "per_100", "pallet_estimate")
                        if "per_100" in estimate_section else 27.0)
    if "per_series" in estimate_section:
        per_series_raw = estimate_section["per_series"]
        if not isinstance(per_series_raw, dict):
            raise RatesError("pallet_estimate.per_series must be a table, e.g. { cushions = 1 }")
        _check_keys(per_series_raw, SERIES_TYPES, "pallet_estimate.per_series")
        estimate_per_series = {t: _number(per_series_raw, t, "pallet_estimate.per_series")
                               for t in per_series_raw}
    else:
        estimate_per_series = {"cushions": 1.0}

    # Optional: without the section, the default booking times apply.
    if "task_overrides" in data:
        overrides_section = _section(data, "task_overrides")
        _check_keys(overrides_section, HANDLING_KEYS, "task_overrides")
        task_overrides = {}
        for task, by_type in overrides_section.items():
            where = f"task_overrides.{task}"
            if not isinstance(by_type, dict):
                raise RatesError(f"[{where}] must list series types, e.g. mixed = {{ per_100 = 0.35 }}")
            _check_keys(by_type, SERIES_TYPES, where)
            task_overrides[task] = {}
            for series_type, spec in by_type.items():
                w = f"{where}.{series_type}"
                if not isinstance(spec, dict) or not spec:
                    raise RatesError(f"{w} must be like {{ per_100 = 0.35 }} or {{ per_series = 0.12 }}")
                _check_keys(spec, ("per_100", "per_series"), w)
                task_overrides[task][series_type] = (
                    _number(spec, "per_100", w) if "per_100" in spec else 0.0,
                    _number(spec, "per_series", w) if "per_series" in spec else 0.0,
                )
    else:
        task_overrides = default_task_overrides()

    return Rates(
        pick=pick,
        handling=handling,
        collection=collection_rate,
        schedule=schedule,
        freed_during_day=freed_during_day,
        capacity=capacity,
        pallets_per_100=pallets_per_100,
        pallets_per_series=pallets_per_series,
        tight_above=tight_above,
        very_tight_above=very_tight_above,
        tight_surcharge=tight_surcharge,
        very_tight_surcharge=very_tight_surcharge,
        over_capacity_surcharge=over_capacity_surcharge,
        calendar=calendar,
        hours_per_employee=hours_per_employee,
        one_piece=one_piece,
        estimate_per_100=estimate_per_100,
        estimate_per_series=estimate_per_series,
        task_overrides=task_overrides,
    )


def load_rates(path: str | Path) -> Rates:
    """Read and validate a rates file. Raises RatesError or OSError."""
    with open(path, "rb") as f:
        try:
            data = tomllib.load(f)
        except tomllib.TOMLDecodeError as exc:
            raise RatesError(f"not valid TOML: {exc}") from None
    return parse_rates(data)


def describe(rates: Rates) -> str:
    """Human-readable summary, used by `manage.py check_rates`."""
    lines = ["Pick series (man-hours per 100 pcs):"]
    lines += [f"  {t:<12} {rates.pick[t]:g}" for t in SERIES_TYPES]
    lines.append("Handling (man-hours per 100 pcs):")
    lines += [f"  {k:<12} {rates.handling[k]:g}" for k in HANDLING_KEYS]
    lines.append(f"  {'collection':<12} {rates.collection:g}")
    for task, by_type in rates.task_overrides.items():
        for t, (per_100, per_series) in by_type.items():
            parts = ([f"{per_100:g} per 100 pcs"] if per_100 else []) + ([f"{per_series:g} per series"] if per_series else [])
            lines.append(f"  {task} for {t}: {' + '.join(parts) or '0'} (overrides the rate above)")
    for t, tasks in rates.one_piece.items():
        listed = ", ".join(k for k in ONE_PIECE_TASKS if k in tasks)
        lines.append(f"  {t} counts as 1 piece per series for: {listed}")
    lines.append("Collection schedule: " + ", ".join(
        f"{s:.0%} after {i} working day{'s' if i > 1 else ''}" for i, s in enumerate(rates.schedule, 1)))
    lines.append(f"  {rates.freed_during_day:.0%} of a day's collected pallets free space during that day")
    lines.append("Pallets per pick series:")
    for t in SERIES_TYPES:
        parts = []
        if t in rates.pallets_per_100:
            parts.append(f"{rates.pallets_per_100[t]:g} per 100 pcs")
        if t in rates.pallets_per_series:
            parts.append(f"{rates.pallets_per_series[t]:g} per series")
        lines.append(f"  {t:<12} {' + '.join(parts)}")
    lines.append(f"Storage: {rates.capacity} pallet spaces")
    shown = [f"{rates.estimate_per_100:g} per 100 pcs"]
    shown += [f"{t}: {v:g} per series" for t, v in rates.estimate_per_series.items()]
    lines.append("Pallet estimate shown with 'Stk. til pluk': " + ", ".join(shown))
    lines.append(f"  tight above {rates.tight_above:.0%} (+{rates.tight_surcharge:.0%}), "
                 f"very tight above {rates.very_tight_above:.0%} (+{rates.very_tight_surcharge:.0%}), "
                 f"over capacity above 100% (+{rates.over_capacity_surcharge:.0%})")
    lines.append(f"Staffing: {rates.hours_per_employee:g} hours per employee per day")
    extra = sorted(f"{m:02d}-{d:02d}" for m, d in rates.calendar.extra_yearly)
    extra += sorted(d.isoformat() for d in rates.calendar.extra_dates)
    lines.append("Extra closed days: " + (", ".join(extra) if extra else "none"))
    return "\n".join(lines)
