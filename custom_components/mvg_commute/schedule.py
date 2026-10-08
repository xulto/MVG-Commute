"""Polling window check. No Home Assistant imports, so it can be tested on its own."""

from __future__ import annotations

from datetime import datetime, time, timedelta

WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def is_active(now: datetime, start: time, end: time, days: list[str]) -> bool:
    """Whether local time `now` falls in the window starting on one of `days`.

    start == end means all day. A window that ends before it starts runs past
    midnight and belongs to the day it started on.
    """
    t = now.time()
    if start == end:
        day = now
    elif start < end:
        if not start <= t < end:
            return False
        day = now
    elif t >= start:
        day = now
    elif t < end:
        day = now - timedelta(days=1)
    else:
        return False
    return WEEKDAYS[day.weekday()] in days
