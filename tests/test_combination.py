import math
import random
from datetime import datetime, timedelta, timezone

from app.anomalies import check as anomaly_check
from app.anomalies import VARIABLES
from app.combination import MIN_HISTORY, cutoff_for, distance, evaluate, solve

FLOORS = [VARIABLES["temp_c"].resolution, VARIABLES["ph"].resolution]

START = datetime(2026, 10, 1, 6, tzinfo=timezone.utc)


def coupled(n=40, seed=7):
    """
    A pond where temperature and pH move together, over the daily cycle.

    Not an invention of the example: at midday the water warms and the algae consume CO2, and both
    push the pH up. So in this pond cold water comes with low pH and warm water with high pH, and
    never the other way round.

    It has to be a cycle and not a rising ramp. On a ramp from 12 to 17 °C, a reading of 12.3 at the
    end is genuinely surprising and anomalies.py flags it — correctly — which would make the test
    below pass for the wrong reason. On a cycle, 12.2 °C happens every night and 7.52 pH every
    noon, so each value on its own is unremarkable and only the pairing is new. That is the case
    this module is for.
    """
    rng = random.Random(seed)
    rows = []
    for i in range(n):
        phase = math.sin(i * math.pi / 4)  # eight readings per cycle, six hours apart
        rows.append({
            "registrado_en": START + timedelta(hours=6 * i),
            "temp_c": round(14.5 + 2.5 * phase + rng.uniform(-0.1, 0.1), 2),
            "ph": round(7.2 + 0.35 * phase + rng.uniform(-0.02, 0.02), 3),
        })
    return rows


def with_newest(history, **values):
    newest = {"registrado_en": history[-1]["registrado_en"] + timedelta(hours=6)}
    newest.update(values)
    return history + [newest]
