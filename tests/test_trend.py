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
