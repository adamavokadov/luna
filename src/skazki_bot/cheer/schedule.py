"""Pure scheduling rules for Luna's warm messages (no I/O, easy to test)."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta, tzinfo
from typing import Literal

Daypart = Literal["morning", "day", "evening"]

FREQUENCIES = ("off", "weekly", "few", "daily")
DEFAULT_FREQUENCY = "off"  # a proactive message needs consent


def daypart(local_hour: int) -> Daypart:
    """Morning 05-10, day 11-16, evening 17-04 (local hours)."""
    if 5 <= local_hour < 11:
        return "morning"
    if 11 <= local_hour < 17:
        return "day"
    return "evening"


def personal_hour(user_id: int, window_start: int, window_end: int) -> int:
    """Each user gets a stable hour inside the window, so messages do not all go out at once."""
    return window_start + (user_id % (window_end - window_start))


def is_due(
    *,
    now: datetime,
    tz: tzinfo,
    user_id: int,
    freq: str,
    last_at: datetime | None,
    window_start: int,
    window_end: int,
    gaps: Mapping[str, timedelta],
) -> bool:
    """Is it time to send this user a warm message?

    Due when: the frequency is active, local time is inside the daytime window and not before the
    user's personal hour (so a bot that was down still catches up later in the window), and the
    minimum gap since the previous message has passed.
    """
    gap = gaps.get(freq)
    if gap is None:  # "off" or an unknown value
        return False
    local = now.astimezone(tz)
    if not window_start <= local.hour < window_end:
        return False
    if local.hour < personal_hour(user_id, window_start, window_end):
        return False
    return last_at is None or now - last_at >= gap
