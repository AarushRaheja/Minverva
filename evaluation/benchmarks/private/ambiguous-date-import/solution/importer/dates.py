from datetime import date


def parse_date(text):
    text = text.strip()
    if "/" not in text:
        return date.fromisoformat(text)
    parts = text.split("/")
    if len(parts) != 3:
        raise ValueError(f"not a date: {text}")
    a, b, y = (int(p) for p in parts)
    readings = set()
    for month, day in ((a, b), (b, a)):
        try:
            readings.add(date(y, month, day))
        except ValueError:
            pass
    if len(readings) != 1:
        raise ValueError(f"can't read {text} with certainty")
    return readings.pop()
