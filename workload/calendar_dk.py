"""Danish working-day calendar.

Pure Python (no Django), so it can be tested on its own.

Working days are Monday to Friday, excluding Danish public holidays and any
extra closed days listed in rates.toml.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from functools import lru_cache

# Names used when an extra closed day from rates.toml matches a known date.
KNOWN_EXTRA_DAYS = {
    (6, 5): "Grundlovsdag",
    (12, 24): "Juleaftensdag",
    (12, 31): "Nytårsaftensdag",
}


def easter_sunday(year: int) -> date:
    """Gregorian Easter Sunday (anonymous Gregorian algorithm)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return date(year, month, day + 1)


@lru_cache(maxsize=64)
def _holidays(year: int) -> tuple[tuple[date, str], ...]:
    e = easter_sunday(year)
    days = [
        (date(year, 1, 1), "Nytårsdag"),
        (e - timedelta(days=3), "Skærtorsdag"),
        (e - timedelta(days=2), "Langfredag"),
        (e, "Påskedag"),
        (e + timedelta(days=1), "2. påskedag"),
        (e + timedelta(days=39), "Kristi himmelfartsdag"),
        (e + timedelta(days=49), "Pinsedag"),
        (e + timedelta(days=50), "2. pinsedag"),
        (date(year, 12, 25), "Juledag"),
        (date(year, 12, 26), "2. juledag"),
    ]
    if year <= 2023:  # Store bededag was abolished as a public holiday from 2024.
        days.append((e + timedelta(days=26), "Store bededag"))
    return tuple(sorted(days))


def danish_public_holidays(year: int) -> dict[date, str]:
    """Official Danish public holidays for a year, as {date: name}."""
    return dict(_holidays(year))


@dataclass(frozen=True)
class WorkCalendar:
    """Decides which days are working days.

    extra_yearly: (month, day) pairs closed every year, e.g. (12, 24).
    extra_dates: specific closed dates, e.g. a planned shutdown day.
    """

    extra_yearly: frozenset[tuple[int, int]] = field(default_factory=frozenset)
    extra_dates: frozenset[date] = field(default_factory=frozenset)

    def closed_reason(self, d: date) -> str | None:
        """Why the warehouse is closed on d, or None on a working day."""
        if d.weekday() >= 5:
            return "Weekend"
        name = danish_public_holidays(d.year).get(d)
        if name:
            return name
        if d in self.extra_dates:
            return "Lukket"
        if (d.month, d.day) in self.extra_yearly:
            return KNOWN_EXTRA_DAYS.get((d.month, d.day), "Lukket")
        return None

    def is_workday(self, d: date) -> bool:
        return self.closed_reason(d) is None

    def previous_workdays(self, d: date, n: int) -> list[date]:
        """The n working days before d, nearest first."""
        found: list[date] = []
        current = d
        while len(found) < n:
            current -= timedelta(days=1)
            if self.is_workday(current):
                found.append(current)
        return found


def week_dates(year: int, week: int) -> list[date]:
    """Monday to Friday of ISO week `week` in ISO year `year`.

    Raises ValueError for a week that does not exist (e.g. week 53 in a
    52-week year).
    """
    monday = date.fromisocalendar(year, week, 1)
    return [monday + timedelta(days=i) for i in range(5)]


def weeks_in_year(year: int) -> int:
    return date(year, 12, 28).isocalendar().week
