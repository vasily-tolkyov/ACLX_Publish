def first_non_empty_upper(items: list[str | None]) -> str:
    """Return the first non-empty value uppercased.

    Empty input should return "N/A".
    """

    cleaned = [item.strip() for item in items if item is not None and item.strip()]
    return cleaned[0].upper()
