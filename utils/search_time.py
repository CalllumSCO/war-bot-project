import re
from datetime import datetime, timedelta
from typing import Optional, Tuple


def parse_search_time(raw: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """
    Parse a search time string. Returns (value, error_message).

    Accepts ASAP, 0–23, or 00–23. Also accepts legacy 7PM / 11AM.
    """
    if not raw:
        return "ASAP", None

    raw_input = raw.strip().upper()

    if raw_input in ("ASAP", "NOW"):
        return "ASAP", None

    if re.fullmatch(r"\d{1,2}", raw_input):
        hour = int(raw_input)
        if hour < 0 or hour > 23:
            return None, "Pick **Right away** or an hour from **00** to **23**."
        return f"{hour:02d}", None

    if re.fullmatch(r"(1[0-2]|[1-9])(AM|PM)", raw_input):
        return raw_input, None

    return None, "Pick **Right away** or an hour from **00** to **23**."


def format_search_time(search_time: Optional[str]) -> str:
    """Friendly display for embeds and messages."""
    if not search_time or str(search_time).upper() in ("ASAP", "NOW"):
        return "Right away"
    raw = str(search_time).strip().upper()
    if re.fullmatch(r"\d{1,2}", raw):
        return f"{int(raw):02d}:00"
    return str(search_time)


def hour_from_search_time(search_time: Optional[str]) -> Optional[int]:
    if not search_time:
        return None
    raw = str(search_time).strip().upper()
    if raw in ("ASAP", "NOW"):
        return None
    if re.fullmatch(r"\d{1,2}", raw):
        hour = int(raw)
        return hour if 0 <= hour <= 23 else None
    match = re.fullmatch(r"(1[0-2]|[1-9])(AM|PM)", raw)
    if not match:
        return None
    hour = int(match.group(1)) % 12
    if match.group(2) == "PM":
        hour += 12
    return hour


def _parse_anchor(created_at: Optional[str], now: datetime) -> datetime:
    if not created_at:
        return now
    try:
        text = created_at.strip()
        if text.endswith("Z"):
            text = text[:-1]
        return datetime.fromisoformat(text)
    except ValueError:
        return now


def unlock_at_for_search_time(
    search_time: Optional[str],
    *,
    created_at: Optional[str] = None,
    now: Optional[datetime] = None,
) -> Optional[datetime]:
    """
    When opponent search becomes available.

    ASAP → immediately (None means already unlocked).
    Hour labels unlock at the next occurrence of that hour on/after party creation.
    """
    now = now or datetime.now()
    hour = hour_from_search_time(search_time)
    if hour is None:
        return None

    created = _parse_anchor(created_at, now)
    unlock = created.replace(hour=hour, minute=0, second=0, microsecond=0)
    if created > unlock:
        unlock = unlock + timedelta(days=1)
    return unlock


def opponent_search_unlocked(
    search_time: Optional[str],
    *,
    created_at: Optional[str] = None,
    now: Optional[datetime] = None,
) -> bool:
    """True when Looking For Opponents is allowed for this search time."""
    now = now or datetime.now()
    unlock_at = unlock_at_for_search_time(search_time, created_at=created_at, now=now)
    if unlock_at is None:
        return True
    return now >= unlock_at
