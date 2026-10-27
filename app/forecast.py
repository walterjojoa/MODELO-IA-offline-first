"""Water temperature forecast from air temperature.

Water follows the air, but slower: a pond does not warm up at noon as fast as the air above it, and it
keeps part of yesterday's heat at night. So the model is a first-order lag (the idea behind air2water,
Piccolroaz et al., 2013, reduced to what a few manual readings can fit):

    smoothed air  S(t) = S(t-1) + k * (air(t) - S(t-1)),   k = 1 - exp(-1 / tau)
    water         W(t) = a + b * S(t)

tau (hours) says how slowly the pond reacts; a and b translate air into water for THIS pond (a spring-fed
pond barely follows the air: small b). For each candidate tau, a and b come from least squares; the tau
that misses the readings the least wins. Then the same equation runs over the air forecast.

Why not Holt-Winters or a neural network: both need hourly water readings for days on end. The caretaker
writes down two or three a day by hand. This model needs about ten, because the air series (Open-Meteo,
hourly, free) carries the shape of the day and the week; the readings only have to fix a, b and tau.
"""

import math
from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import linear_regression

MIN_READINGS = 10
"""Below this, a, b and tau are guesses fitted to noise."""
TAUS = (3, 6, 12, 24, 36, 48, 72, 96, 120)
SPIN_UP = timedelta(days=5)
"""Air history needed before a reading for the smoothed air to have forgotten its arbitrary start."""
Z80 = 1.2816
"""80 % of a normal distribution lies within this many standard errors: the "between X and Y" range."""


@dataclass(frozen=True)
class Model:
    tau: float
    a: float
    b: float
    error: float
    """Root mean square error over the readings (°C): how much the model typically misses."""
    readings: int


@dataclass(frozen=True)
class Day:
    date: str
    low: float
    high: float
    mean: float


def smooth(air: list[float], tau: float) -> list[float]:
    k = 1 - math.exp(-1 / tau)
    level = air[0]
    out = []
    for value in air:
        level += k * (value - level)
        out.append(level)
    return out


def fit(hours: list[datetime], air: list[float], readings: list[tuple[datetime, float]]) -> Model | None:
    """hours/air: consecutive hourly air temperatures, oldest first. readings: (time, water °C).

    Readings without SPIN_UP of air before them, or after the last air hour, are left out.
    """
    first, step = hours[0], timedelta(hours=1)
    index = {}
    for when, water in readings:
        i = int((when - first) / step)
        if when - first >= SPIN_UP and i < len(hours):
            index[i] = water  # two readings in the same hour: the later one stays
    if len(index) < MIN_READINGS:
        return None
    positions, water = list(index), list(index.values())
    best = None
    for tau in TAUS:
        smoothed = smooth(air, tau)
        x = [smoothed[i] for i in positions]
        if max(x) - min(x) < 1e-9:
            continue  # flat air: no slope to fit
        b, a = linear_regression(x, water)
        error = math.sqrt(sum((a + b * xi - w) ** 2 for xi, w in zip(x, water)) / len(water))
        if best is None or error < best.error:
            best = Model(tau, a, b, error, len(water))
    return best


def predict(model: Model, hours: list[datetime], air: list[float], since: datetime,
            utc_offset: timedelta) -> list[Day]:
    """Daily low/high/mean of the predicted water temperature for the hours at or after `since`.

    Days are cut at local midnight (utc_offset), since that is the day the caretaker means.
    """
    smoothed = smooth(air, model.tau)
    days: dict[str, list[float]] = {}
    for when, s in zip(hours, smoothed):
        if when >= since:
            days.setdefault((when + utc_offset).date().isoformat(), []).append(model.a + model.b * s)
    margin = Z80 * model.error
    return [Day(date, round(min(v) - margin, 1), round(max(v) + margin, 1), round(sum(v) / len(v), 1))
            for date, v in days.items()]
