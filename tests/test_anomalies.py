import random
from datetime import datetime, timedelta, timezone

from app.anomalies import MIN_HISTORY, check, evaluate

START = datetime(2026, 10, 1, tzinfo=timezone.utc)


def noisy(center, noise, n, seed=1):
    rng = random.Random(seed)
    return [round(center + rng.uniform(-noise, noise), 2) for _ in range(n)]


def test_normal_value_is_not_flagged():
    assert check("oxigeno_mg_l", noisy(9, 0.3, 30), 9.2) is None


def test_sudden_oxygen_drop_inside_rule_range_is_flagged():
    # 7 mg/L is still acceptable for the rules, but not for a pond that sits at 9 ± 0.3
    anomaly = check("oxigeno_mg_l", noisy(9, 0.3, 30), 7.0)
    assert anomaly is not None
    assert anomaly.score < 0
    assert anomaly.message.startswith("Oxígeno bajó de forma inusual: 7 mg/L")


def test_sudden_rise_says_subio():
    anomaly = check("temp_c", noisy(12, 0.2, 30), 15.0)
    assert anomaly is not None and "subió" in anomaly.message


def test_too_little_history_flags_nothing():
    assert check("ph", noisy(7, 0.1, MIN_HISTORY - 1), 9.0) is None


def test_flat_history_tolerates_small_steps():
    # Sensor that always read 12.0: without the resolution floor, 12.1 would be infinitely unusual
    assert check("temp_c", [12.0] * 30, 12.1) is None
    assert check("temp_c", [12.0] * 30, 14.0) is not None


def test_slow_trend_is_normal():
    # Water warming steadily through the morning: the EWMA lags, the bias corrects it
    rising = [10 + 0.1 * i for i in range(30)]
    assert check("temp_c", rising, 13.0) is None


def test_one_old_outlier_does_not_hide_a_new_one():
    history = noisy(9, 0.3, 30)
    history[10] = 3.0
    assert check("oxigeno_mg_l", history, 7.0) is not None


def test_evaluate_uses_newest_reading_and_skips_missing_values():
    readings = [{"registrado_en": START + timedelta(hours=i), "temp_c": t, "ph": None, "oxigeno_mg_l": 9.0}
                for i, t in enumerate(noisy(12, 0.2, 20))]
    # Sent out of order on purpose: the newest one must be the one evaluated
    readings.insert(0, {"registrado_en": START + timedelta(hours=99), "temp_c": 16.0, "ph": 7.0,
                        "oxigeno_mg_l": None})
    found = evaluate(readings)
    assert [a.variable for a in found] == ["temp_c"]
