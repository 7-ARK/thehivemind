from datetime import UTC, datetime, timedelta


def range_bounds(time_range: str = "30d") -> tuple[datetime | None, datetime]:
    now = datetime.now(UTC)
    if time_range == "all":
        return None, now
    if time_range == "today":
        return now.replace(hour=0, minute=0, second=0, microsecond=0), now
    if time_range == "7d":
        return now - timedelta(days=7), now
    if time_range == "month":
        return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0), now
    return now - timedelta(days=30), now


def unix_bounds(time_range: str = "30d") -> tuple[int, int]:
    start, end = range_bounds(time_range)
    if start is None:
        start = end - timedelta(days=180)
    return int(start.timestamp()), int(end.timestamp())
