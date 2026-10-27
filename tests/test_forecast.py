import math
import random
from datetime import datetime, timedelta, timezone

from app.forecast import MIN_READINGS, fit, predict, smooth

START = datetime(2026, 9, 1, tzinfo=timezone.utc)
COLOMBIA = timedelta(hours=-5)


def air_series(days, seed=1):
    """Hourly air like El Encano: daily cycle 8-18 °C plus slow weather changes."""
    rng = random.Random(seed)
    hours = [START + timedelta(hours=h) for h in range(days * 24)]
    weather, air = 0.0, []
    for h in range(len(hours)):
        weather += rng.gauss(0, 0.15)
        weather *= 0.99
        air.append(13 + 5 * math.sin(2 * math.pi * (h % 24 - 9) / 24) + weather)
    return hours, air


def pond(hours, air, tau=24, a=4.0, b=0.6, noise=0.2, every=8, seed=2):
    """Manual readings every few hours from a pond that really follows W = a + b * smoothed air."""
    rng = random.Random(seed)
    s = smooth(air, tau)
    return [(hours[i], a + b * s[i] + rng.gauss(0, noise)) for i in range(0, len(hours), every)]


def test_recovers_how_the_pond_follows_the_air():
    hours, air = air_series(30)
    model = fit(hours, air, pond(hours, air))
    assert model.tau == 24
    assert abs(model.b - 0.6) < 0.1
    assert model.error < 0.3


def test_spring_fed_pond_barely_follows_the_air():
    hours, air = air_series(30)
    model = fit(hours, air, pond(hours, air, a=11, b=0.05))
    assert model.b < 0.15


def test_too_few_readings_gives_no_model():
    hours, air = air_series(30)
    readings = pond(hours, air)[-(MIN_READINGS - 1):]
    assert fit(hours, air, readings) is None


def test_readings_without_air_spin_up_are_ignored():
    hours, air = air_series(30)
    early = pond(hours, air, every=1)[:4 * 24]  # 96 readings, all in the first 4 days
    assert fit(hours, air, early) is None


def test_forecast_beats_just_repeating_the_last_reading():
    hours, air = air_series(33)
    cut = 30 * 24
    readings = pond(hours, air)
    past = [r for r in readings if r[0] < hours[cut]]
    future = [r for r in readings if r[0] >= hours[cut]]
    model = fit(hours[:cut], air[:cut], past)
    s = smooth(air, model.tau)
    by_hour = {h: model.a + model.b * v for h, v in zip(hours, s)}
    model_error = sum(abs(by_hour[t] - w) for t, w in future) / len(future)
    naive_error = sum(abs(past[-1][1] - w) for t, w in future) / len(future)
    # The readings carry 0.2 °C of noise (mean absolute ~0.16), so no model can do much better
    assert model_error < naive_error
    assert model_error < 0.3


def test_predict_groups_by_local_day_with_a_range():
    hours, air = air_series(33)
    model = fit(hours[:30 * 24], air[:30 * 24], pond(hours[:30 * 24], air[:30 * 24]))
    days = predict(model, hours, air, since=hours[30 * 24], utc_offset=COLOMBIA)
    # 72 UTC hours starting at midnight UTC = 19:00 local, so four local days, the first one short
    assert len(days) == 4
    assert all(d.low < d.mean < d.high for d in days)
    assert days[0].date == "2026-09-30"
