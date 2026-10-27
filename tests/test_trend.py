import math
import random
from datetime import datetime, timedelta, timezone

from app.anomalies import check as anomaly_check
from app.trend import MIN_AGREEMENT, MIN_DAYS, MIN_READINGS, check, evaluate, slope

START = datetime(2026, 10, 1, 6, tzinfo=timezone.utc)

OXYGEN = {"critico_min": 5.0, "critico_max": None}
TEMPERATURE = {"critico_min": 6.0, "critico_max": 18.0}


def series(values, hours=6.0, start=START):
    """(time, value) pairs, one every `hours`."""
    return [(start + timedelta(hours=hours * i), v) for i, v in enumerate(values)]


def falling(per_day, days=6.0, n=24, start=8.6):
    """A value dropping steadily, sampled evenly over `days`."""
    step = days * 24 / (n - 1)
    return [(START + timedelta(hours=step * i), start - per_day * (step * i) / 24) for i in range(n)]


def daily_cycle(days, swing=0.3, drift_per_day=0.0, base=7.2, seed=None):
    """
    Hourly readings with the sun's cycle on top, which is the noise a trend has to beat.

    The range is inclusive so the series really spans `days`. With `range(days * 24)` the last
    reading falls an hour short, the window measures 2.96 days, and `check` rejects it for being
    under MIN_DAYS — which made the test below pass for the wrong reason.
    """
    rng = random.Random(seed) if seed is not None else None
    out = []
    for hour in range(int(days * 24) + 1):
        value = base + swing * math.sin(hour * math.pi / 12) - drift_per_day * hour / 24
        if rng:
            value += rng.uniform(-0.05, 0.05)
        out.append((START + timedelta(hours=hour), round(value, 3)))
    return out


# ---------- the slope itself ----------

def test_slope_finds_a_clean_drop():
    days = [float(i) for i in range(10)]
    values = [9.0 - 0.4 * i for i in range(10)]
    per_day, agreement = slope(days, values)
    assert round(per_day, 6) == -0.4
    assert agreement == 1.0


def test_least_squares_would_invert_the_sign_with_one_bad_reading():
    """
    The measurement that decides the method, and the reason anomalies.py's medians are not enough
    here either.

    Twelve readings dropping 0.3 °C a day, and the last one taken with the sensor already out of the
    water. Least squares reports the oxygen **rising**; Theil-Sen returns the real slope. Saying
    "it is going up" while the pond empties of oxygen is the one mistake that cannot be made.
    """
    days = [float(i) for i in range(12)]
    values = [9.0 - 0.3 * i for i in range(12)]
    values[11] = 21.0

    robust, _ = slope(days, values)
    mean_x, mean_y = sum(days) / 12, sum(values) / 12
    least_squares = (sum((x - mean_x) * (y - mean_y) for x, y in zip(days, values))
                     / sum((x - mean_x) ** 2 for x in days))

    assert round(robust, 6) == -0.3
    assert least_squares > 0


def test_slope_needs_two_distinct_times():
    assert slope([3.0], [9.0]) is None
    assert slope([3.0, 3.0], [9.0, 8.0]) is None


# ---------- what the anomaly detector lets through on purpose ----------

def test_the_drift_that_anomalies_does_not_flag_is_flagged_here():
    """
    The hole this module fills, with both detectors run side by side on the same data.

    Oxygen falls 0.4 mg/L a day for six days, from 8.6 to 6.2. Every reading is a little below the
    last, so nothing is ever surprising and anomalies.py says nothing — correctly. And 6.2 is still
    above the rules' critical 5.0, so level 1 says nothing either. Between them, a pond on its way
    to a problem that nobody mentions until the day it arrives.
    """
    points = falling(per_day=0.4, days=6.0)
    values = [value for _, value in points]
    assert values[-1] > OXYGEN["critico_min"], "the limit must not have been crossed yet"

    assert anomaly_check("oxigeno_mg_l", values[:-1], values[-1]) is None

    trend = check("oxigeno_mg_l", points, **{"critical_min": OXYGEN["critico_min"]})
    assert trend is not None
    assert trend.per_day < 0
    assert trend.days_to_limit is not None and trend.days_to_limit <= 7
    assert "bajando" in trend.message and "límite de 5" in trend.message


def test_a_jump_is_the_other_module_s_business():
    # A pond sitting flat with one reading far below: no drift to report, and anomalies.py has it
    flat = [9.0, 9.1, 8.9, 9.2, 8.8, 9.0, 9.1, 8.9, 9.0, 9.1, 8.9, 9.0, 9.2, 8.8, 9.1, 6.0]
    assert check("oxigeno_mg_l", series(flat), critical_min=5.0) is None
    assert anomaly_check("oxigeno_mg_l", flat[:-1], flat[-1]) is not None


# ---------- the window, which had to be measured ----------

def test_one_day_of_the_daily_cycle_would_invent_a_trend():
    """
    Why MIN_DAYS exists, demonstrated instead of asserted.

    A clean daily cycle with no trend at all scores more agreement than the minimum demanded. If a
    one-day window were accepted, the service would report a drop that does not exist every time the
    caretaker measured through a single day.
    """
    points = daily_cycle(days=1)
    days = [(when - START).total_seconds() / 86400 for when, _ in points]
    _, agreement = slope(days, [v for _, v in points])
    assert agreement > MIN_AGREEMENT


def test_three_days_of_the_daily_cycle_report_nothing():
    points = daily_cycle(days=MIN_DAYS)
    # It has to be silent because the cycles cancelled out, not because the window was too short
    assert (points[-1][0] - points[0][0]).total_seconds() / 86400 >= MIN_DAYS
    days = [(when - START).total_seconds() / 86400 for when, _ in points]
    _, agreement = slope(days, [v for _, v in points])
    assert agreement < MIN_AGREEMENT
    assert check("ph", points, critical_min=6.0, critical_max=9.0) is None


def test_a_drift_hidden_under_the_daily_cycle_is_found():
    # 0.25 units a day, which is little and would never cross a fixed threshold in time
    points = daily_cycle(days=MIN_DAYS, drift_per_day=0.25, base=7.6)
    trend = check("ph", points, critical_min=6.0, critical_max=9.0)
    assert trend is not None and trend.per_day < 0


def test_a_window_shorter_than_three_days_reports_nothing():
    assert check("oxigeno_mg_l", falling(per_day=0.4, days=2.0), critical_min=5.0) is None


def test_too_few_readings_report_nothing():
    assert check("oxigeno_mg_l", falling(per_day=0.4, days=6.0, n=MIN_READINGS - 1),
                 critical_min=5.0) is None


# ---------- how urgent it is ----------

def test_about_to_cross_is_urgent():
    # From 5.6 falling 0.4 a day: a day and a half from the critical 5.0
    points = falling(per_day=0.4, days=6.0, start=8.0)
    trend = check("oxigeno_mg_l", points, critical_min=5.0)
    assert trend is not None and trend.urgent
    assert "mañana" in trend.message


def test_a_far_away_limit_is_reported_without_a_date():
    # 0.05 a day from 8.6: the critical limit is more than seventy days off
    trend = check("oxigeno_mg_l", falling(per_day=0.05, days=6.0), critical_min=5.0)
    assert trend is not None
    assert trend.days_to_limit is None
    assert not trend.urgent
    assert "límite" not in trend.message


def test_without_limits_the_slope_is_still_reported():
    trend = check("oxigeno_mg_l", falling(per_day=0.4, days=6.0))
    assert trend is not None
    assert trend.days_to_limit is None
    assert "bajando" in trend.message


def test_a_limit_already_crossed_is_the_rules_business():
    # Below the critical 5.0 already: level 1 is shouting about it, no date to add
    trend = check("oxigeno_mg_l", falling(per_day=0.4, days=6.0, start=6.5), critical_min=5.0)
    assert trend is not None and trend.days_to_limit is None


def test_a_rise_heads_for_the_upper_limit():
    rising = [(START + timedelta(hours=6 * i), 12.0 + 0.5 * i * 0.25) for i in range(24)]
    trend = check("temp_c", rising, critical_min=6.0, critical_max=18.0)
    assert trend is not None
    assert trend.per_day > 0 and "subiendo" in trend.message


# ---------- evaluate ----------

def test_evaluate_looks_at_every_variable_and_skips_missing_values():
    readings = []
    for i, (when, oxygen) in enumerate(falling(per_day=0.4, days=6.0)):
        readings.append({"registrado_en": when, "oxigeno_mg_l": oxygen,
                         "temp_c": 12.0 if i % 2 else None, "ph": None})
    found = evaluate(readings, {"oxigeno_mg_l": OXYGEN, "temp_c": TEMPERATURE})
    assert [t.variable for t in found] == ["oxigeno_mg_l"]
