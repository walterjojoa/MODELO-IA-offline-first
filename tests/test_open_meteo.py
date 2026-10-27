from datetime import datetime, timezone

from app.open_meteo import parse


def payload(values):
    return {"hourly": {"time": [f"2026-10-26T{h:02d}:00" for h in range(len(values))],
                       "temperature_2m": values}}


def test_hours_are_utc():
    hours, air = parse(payload([10.5, 11.0]))
    assert hours[0] == datetime(2026, 10, 26, 0, tzinfo=timezone.utc)
    assert air == [10.5, 11.0]


def test_gap_repeats_previous_value_and_leading_gap_is_dropped():
    hours, air = parse(payload([None, 9.0, None, 12.0]))
    assert air == [9.0, 9.0, 12.0]
    assert hours[0].hour == 1
