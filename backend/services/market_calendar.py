"""NYSE calendar — holidays and early closes (America/New_York dates)."""

from __future__ import annotations

from datetime import date, time

_REGULAR_CLOSE = time(16, 0)

# Full-day NYSE closures (date in America/New_York)
NYSE_HOLIDAYS: frozenset[date] = frozenset({
    date(2025, 1, 1),
    date(2025, 1, 20),
    date(2025, 2, 17),
    date(2025, 4, 18),
    date(2025, 5, 26),
    date(2025, 6, 19),
    date(2025, 7, 4),
    date(2025, 9, 1),
    date(2025, 11, 27),
    date(2025, 12, 25),
    date(2026, 1, 1),
    date(2026, 1, 19),
    date(2026, 2, 16),
    date(2026, 4, 3),
    date(2026, 5, 25),
    date(2026, 6, 19),
    date(2026, 7, 3),
    date(2026, 9, 7),
    date(2026, 11, 26),
    date(2026, 12, 25),
})

NYSE_EARLY_CLOSE: dict[date, time] = {
    date(2025, 11, 28): time(13, 0),
    date(2025, 12, 24): time(13, 0),
    date(2026, 11, 27): time(13, 0),
    date(2026, 12, 24): time(13, 0),
}


def is_nyse_holiday(day: date) -> bool:
    return day in NYSE_HOLIDAYS


def regular_close_for_day(day: date) -> time:
    return NYSE_EARLY_CLOSE.get(day, _REGULAR_CLOSE)
