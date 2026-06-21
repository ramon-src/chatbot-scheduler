"""Pure period resolver for agenda queries. Week starts Sunday."""

from datetime import datetime, timedelta
from unicodedata import combining, normalize

# Canonical period -> also matched by PT-BR aliases below.
_ALIASES: dict[str, str] = {
    "today": "today",
    "hoje": "today",
    "tomorrow": "tomorrow",
    "amanha": "tomorrow",
    "this week": "this_week",
    "esta semana": "this_week",
    "essa semana": "this_week",
    "next week": "next_week",
    "proxima semana": "next_week",
    "this month": "this_month",
    "este mes": "this_month",
    "esse mes": "this_month",
    "all future": "all_future",
    "todos": "all_future",
    "futuro": "all_future",
}


def _normalize(period: str) -> str:
    """Lowercase, strip accents, collapse -/_/space to single space."""
    text = normalize("NFKD", period.strip().lower())
    text = "".join(c for c in text if not combining(c))
    # Treat hyphens and underscores as spaces so canonical keys like
    # "this_week" and aliases like "esta semana" all map to the same form.
    for ch in ("-", "_"):
        text = text.replace(ch, " ")
    return " ".join(text.split())  # collapse repeated whitespace


def _start_of_day(dt: datetime) -> datetime:
    return dt.replace(hour=0, minute=0, second=0, microsecond=0)


def calculate_date_range(period: str, now: datetime) -> tuple[datetime, datetime]:
    """Resolve a named period to a [start, end) range in now's timezone.

    start is inclusive at 00:00; end is exclusive at the next boundary's 00:00.
    Recognized values (case-insensitive, accents tolerated):
      today, tomorrow, this_week, next_week, this_month, all_future
    PT-BR aliases: hoje, amanha, esta/essa semana, proxima semana,
      este/esse mes, todos, futuro.
    Week starts Sunday. Unknown period raises ValueError.
    """
    key = _normalize(period)
    canonical = _ALIASES.get(key)
    if canonical is None:
        raise ValueError(f"Unknown period: {period!r}")

    today = _start_of_day(now)

    if canonical == "today":
        return today, today + timedelta(days=1)
    if canonical == "tomorrow":
        return today + timedelta(days=1), today + timedelta(days=2)
    if canonical == "this_week":
        # Python weekday(): Mon=0..Sun=6. Days since Sunday = (weekday + 1) % 7.
        days_since_sunday = (today.weekday() + 1) % 7
        start = today - timedelta(days=days_since_sunday)
        return start, start + timedelta(days=7)
    if canonical == "next_week":
        days_since_sunday = (today.weekday() + 1) % 7
        start = today - timedelta(days=days_since_sunday) + timedelta(days=7)
        return start, start + timedelta(days=7)
    if canonical == "this_month":
        start = today.replace(day=1)
        if start.month == 12:
            end = start.replace(year=start.year + 1, month=1)
        else:
            end = start.replace(month=start.month + 1)
        return start, end
    if canonical == "all_future":
        return today, today + timedelta(days=366)

    raise ValueError(f"Unknown period: {period!r}")  # unreachable
