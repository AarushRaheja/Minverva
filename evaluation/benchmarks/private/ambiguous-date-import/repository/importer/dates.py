from datetime import date


def parse_date(text):
    return date.fromisoformat(text.strip())
