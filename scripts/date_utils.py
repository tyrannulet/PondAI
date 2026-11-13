from datetime import date


def validate_date_range(date_from: str, date_to: str) -> tuple[date, date]:
    """Validate the inclusive calendar period before looking up or fetching data."""
    if any(not isinstance(value, str) or len(value) != 10 for value in (date_from, date_to)):
        raise ValueError("Dates must use YYYY-MM-DD.")
    start, end = date.fromisoformat(date_from), date.fromisoformat(date_to)
    if start.isoformat() != date_from or end.isoformat() != date_to:
        raise ValueError("Dates must use YYYY-MM-DD.")
    if start > end:
        raise ValueError("The start date must not follow the end date.")
    return start, end
