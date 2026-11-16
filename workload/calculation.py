"""Workload calculation engine.

Pure Python (no Django), so every rule can be unit-tested directly.

Rules (all rates come from rates.toml):

* Picking: items x the series type's rate / 100, summed over the day's series.
* Forklift, wrapping, booking, labeling: items picked that day x rate / 100.
* Collection: items picked on earlier working days are collected according to
  the collection schedule (default 60 % / 30 % / 10 % on the 1st, 2nd and 3rd
  working day after picking). Hours = items collected that day x rate / 100.
* One-piece handling: for the tasks listed under a type in `one_piece`, a
  series of that type counts as a single piece whatever its size (cushions:
  forklift, wrapping, booking and collection). Picking and any task not
  listed use the actual number of pieces.
* Storage: each pick series makes pallets according to its type: a number
  per 100 pcs (`pallets_per_100`), a fixed number per series regardless of
  items (`pallets_per_series`), or both added together. Pallets leave on the
  same schedule as the items. Pallets are collected throughout the day, so a
  share (`freed_during_day`, default 50 %) of the pallets collected on a day
  no longer counts toward that day's storage. The storage figure for a day is
  that day's pallets, plus earlier pallets not yet collected, minus that
  share of the pallets collected that day.
* Task overrides: a task's time can be set per series type in
  `task_overrides`, as hours per 100 pcs and/or hours per series. An
  override replaces the [handling] rate and one-piece handling for that task
  and type. Default: booking is 0.35 h per 100 pcs for mixed series and
  0.12 h per series for every other type.
* Pallet estimate shown next to the day's pieces: a simpler figure, not used
  for storage. `estimate_per_100` pallets per 100 pcs for every type, except
  types in `estimate_per_series`, which make a fixed number per series.
* Storage status (share of capacity occupied): <= tight_above is good,
  <= very_tight_above is tight, above that very tight, above 100 % over
  capacity. Each level has its own surcharge (tight_surcharge,
  very_tight_surcharge, over_capacity_surcharge). The surcharge is applied
  last, to the day's total.
* Staffing: the day's total hours / hours_per_employee (7.5), rounded up to
  whole employees for display.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date

from .calendar_dk import WorkCalendar

SERIES_TYPES = ("mixed", "dsv", "large_mixed", "large_same", "cushions")
HANDLING_KEYS = ("forklift", "wrapping", "booking", "labeling")
# Tasks that a series type can be set to count as one piece for.
ONE_PIECE_TASKS = (*HANDLING_KEYS, "collection")
# Order of the stacked bar, bottom to top.
SEGMENT_KEYS = ("picking", "forklift", "wrapping", "booking", "labeling", "collection", "surcharge")

GOOD = "good"
TIGHT = "tight"
VERY_TIGHT = "very_tight"
OVER = "over"

# picks_by_date maps a date to that day's series as (series_type, items) pairs.
PicksByDate = Mapping[date, Sequence[tuple[str, int]]]


@dataclass(frozen=True)
class Rates:
    pick: Mapping[str, float]          # man-hours per 100 items, per series type
    handling: Mapping[str, float]      # man-hours per 100 items picked
    collection: float                  # man-hours per 100 items collected
    schedule: tuple[float, ...]        # share collected 1, 2, 3 ... working days after picking
    capacity: int                      # pallet spaces
    pallets_per_100: Mapping[str, float]     # pallets per 100 items, per series type
    pallets_per_series: Mapping[str, float]  # fixed pallets per series, per series type
    tight_above: float                 # occupancy share above which storage is tight
    very_tight_above: float            # occupancy share above which storage is very tight
    tight_surcharge: float
    very_tight_surcharge: float
    over_capacity_surcharge: float
    calendar: WorkCalendar = field(default_factory=WorkCalendar)
    hours_per_employee: float = 7.5    # length of a standard working day
    # Share of a day's collected pallets counted as gone during that day (collected early or midday).
    freed_during_day: float = 0.5
    # Pallet estimate shown next to "Stk. til pluk" (display only, not used for storage).
    estimate_per_100: float = 27.0
    estimate_per_series: Mapping[str, float] = field(default_factory=lambda: {"cushions": 1.0})
    # task -> series type -> (hours per 100 pcs, hours per series); replaces the [handling] rate.
    task_overrides: Mapping[str, Mapping[str, tuple[float, float]]] = field(
        default_factory=lambda: default_task_overrides())
    # Series type -> tasks for which one series counts as one piece, whatever its size.
    one_piece: Mapping[str, frozenset[str]] = field(default_factory=dict)


def default_task_overrides() -> dict[str, dict[str, tuple[float, float]]]:
    booking = {t: (0.0, 0.12) for t in SERIES_TYPES}
    booking["mixed"] = (0.35, 0.0)
    return {"booking": booking}


@dataclass
class DayResult:
    date: date
    closed_reason: str | None = None
    items_picked: int = 0
    items_collected: float = 0.0       # collected during this day
    items_awaiting: float = 0.0        # still waiting for collection at the end of the day
    pallets_new: float = 0.0           # estimated pallets made ready today (display only)
    pallets: float = 0.0               # pallets in the warehouse during the day
    pallets_awaiting: float = 0.0      # pallets still waiting for collection at the end of the day
    employees: float = 0.0             # total hours / hours per employee (not rounded)
    occupancy: float = 0.0             # pallets / capacity (1.0 = full)
    storage_status: str | None = None
    surcharge_rate: float = 0.0
    hours: dict[str, float] = field(default_factory=lambda: dict.fromkeys(SEGMENT_KEYS, 0.0))

    @property
    def is_workday(self) -> bool:
        return self.closed_reason is None

    @property
    def subtotal(self) -> float:
        return sum(v for k, v in self.hours.items() if k != "surcharge")

    @property
    def total(self) -> float:
        return sum(self.hours.values())


def lookback_start(first: date, rates: Rates) -> date:
    """Earliest date whose picks can affect `first` (for database queries)."""
    previous = rates.calendar.previous_workdays(first, len(rates.schedule))
    return previous[-1] if previous else first


def storage_status(occupancy: float, rates: Rates) -> tuple[str, float]:
    """(status, surcharge rate) for an occupancy share."""
    occupancy = round(occupancy, 9)  # avoid float noise at the exact thresholds
    if occupancy > 1:
        return OVER, rates.over_capacity_surcharge
    if occupancy > rates.very_tight_above:
        return VERY_TIGHT, rates.very_tight_surcharge
    if occupancy > rates.tight_above:
        return TIGHT, rates.tight_surcharge
    return GOOD, 0.0


def series_pallets(series_type: str, items: int, rates: Rates) -> float:
    """Pallets created by one pick series."""
    return (rates.pallets_per_series.get(series_type, 0.0)
            + items * rates.pallets_per_100.get(series_type, 0.0) / 100)


def task_hours(task: str, series_type: str, items: int, rates: Rates) -> float:
    """Hours one pick series needs for a handling task (forklift, wrapping, booking, labeling)."""
    override = rates.task_overrides.get(task, {}).get(series_type)
    if override is not None:
        per_100, per_series = override
        return items * per_100 / 100 + per_series
    return task_pieces(task, series_type, items, rates) * rates.handling[task] / 100


def estimated_pallets(series: Sequence[tuple[str, int]], rates: Rates) -> float:
    """Estimated pallets made ready from a day's pick series (display only)."""
    total = 0.0
    for series_type, items in series:
        if series_type in rates.estimate_per_series:
            total += rates.estimate_per_series[series_type]
        else:
            total += items * rates.estimate_per_100 / 100
    return total


def task_pieces(task: str, series_type: str, items: int, rates: Rates) -> int:
    """Pieces a series counts as for a handling task (1 for one-piece handling)."""
    return 1 if task in rates.one_piece.get(series_type, ()) else items


def _day_totals(series: Sequence[tuple[str, int]], rates: Rates) -> tuple[int, float, int]:
    """(items, pallets, pieces counted for collection) for one day's pick series."""
    items = sum(n for _, n in series)
    pallets = sum(series_pallets(t, n, rates) for t, n in series)
    collection_pieces = sum(task_pieces("collection", t, n, rates) for t, n in series)
    return items, pallets, collection_pieces


def compute_day(d: date, picks_by_date: PicksByDate, rates: Rates) -> DayResult:
    reason = rates.calendar.closed_reason(d)
    if reason:
        return DayResult(date=d, closed_reason=reason)

    result = DayResult(date=d)
    series = picks_by_date.get(d, ())
    items_today = sum(items for _, items in series)
    result.items_picked = items_today
    result.pallets_new = round(estimated_pallets(series, rates), 6)

    # Cumulative share collected after k collection days: cum[0] = 0, cum[1] = 0.6, ...
    cumulative = [0.0]
    for share in rates.schedule:
        cumulative.append(cumulative[-1] + share)

    # k = number of working days since the pick (0 = picked today).
    pick_days = [d, *rates.calendar.previous_workdays(d, len(rates.schedule))]
    collected = collected_pieces = awaiting = pallets_present = pallets_awaiting = 0.0
    for k, pick_day in enumerate(pick_days):
        items, pallets, collection_pieces = _day_totals(picks_by_date.get(pick_day, ()), rates)
        if not items:
            continue
        if k >= 1:
            collected += items * rates.schedule[k - 1]
            collected_pieces += collection_pieces * rates.schedule[k - 1]
        # Counted during day k: everything not collected on days 1..k-1, minus the share
        # of today's collection that leaves during the day.
        present = 1.0 if k == 0 else (
            1.0 - cumulative[k - 1] - rates.freed_during_day * rates.schedule[k - 1])
        remaining = 1.0 - cumulative[k]
        pallets_present += pallets * present
        awaiting += items * remaining
        pallets_awaiting += pallets * remaining

    result.items_collected = round(collected, 6)
    result.items_awaiting = max(0.0, round(awaiting, 6))
    result.pallets = round(pallets_present, 6)
    result.pallets_awaiting = max(0.0, round(pallets_awaiting, 6))
    result.occupancy = result.pallets / rates.capacity

    hours = result.hours
    hours["picking"] = sum(items * rates.pick[t] for t, items in series) / 100
    for key in HANDLING_KEYS:
        hours[key] = sum(task_hours(key, t, items, rates) for t, items in series)
    hours["collection"] = collected_pieces * rates.collection / 100

    result.storage_status, result.surcharge_rate = storage_status(result.occupancy, rates)
    hours["surcharge"] = result.subtotal * result.surcharge_rate  # applied last
    result.employees = result.total / rates.hours_per_employee
    return result


def employees_needed(employees: float) -> int:
    """Whole employees needed to cover a fractional need (9.2 -> 10)."""
    return math.ceil(round(employees, 6))


def compute_days(dates: Iterable[date], picks_by_date: PicksByDate, rates: Rates) -> dict[date, DayResult]:
    """Results for each date. picks_by_date must cover lookback_start(min(dates)) onwards."""
    return {d: compute_day(d, picks_by_date, rates) for d in dates}
