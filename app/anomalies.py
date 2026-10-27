"""AI level 2: readings that are unusual for this pond, even when they are inside the rule ranges.

Level 1 (Rules.java in the backend) answers "is this value acceptable for trout?". This module answers
"is this value normal for THIS pond right now?": oxygen falling from 9 to 7 mg/L is still fine by the
rules, but it is a jump the caretaker should look at.

Method, per variable, over the previous readings of the pond:
- EWMA (exponentially weighted moving average) = the value we expected now.
- The one-step errors of that EWMA tell how much this pond normally moves; their median is the usual
  bias (a slow trend makes the EWMA lag) and their MAD (median absolute deviation) the usual spread.
- robust z = 0.6745 * (error - bias) / MAD; |z| > 3.5 is an anomaly (Iglewicz & Hoaglin, 1993).
Medians instead of mean/standard deviation so that one bad reading in the history does not hide the next.
"""

from dataclasses import dataclass
from statistics import median

ALPHA = 0.3
"""Weight of the newest reading in the EWMA: higher follows changes faster but forgets sooner."""
THRESHOLD = 3.5
MIN_HISTORY = 12
"""With fewer previous readings there is no "normal" to compare against yet, so nothing is flagged."""
WINDOW = 48
"""Only the last readings count: what was normal last month says little about today."""


@dataclass(frozen=True)
class Variable:
    label: str
    unit: str
    resolution: float
    """Smallest change the sensor can show. It is the minimum spread, so a pond whose readings never
    moved does not raise an alert for the first 0.1 °C."""


VARIABLES = {
    "temp_c": Variable("Temperatura", " °C", 0.1),
    "ph": Variable("pH", "", 0.05),
    "oxigeno_mg_l": Variable("Oxígeno", " mg/L", 0.1),
}


@dataclass(frozen=True)
class Anomaly:
    variable: str
    value: float
    expected: float
    score: float
    """Robust z: how many "usual movements" away from the expected value. Its sign is the direction."""
    message: str


def check(variable: str, history: list[float], value: float) -> Anomaly | None:
    """history is the variable's previous readings, oldest first; value is the new one."""
    if len(history) < MIN_HISTORY:
        return None
    history = history[-WINDOW:]
    level = history[0]
    errors = []
    for x in history[1:]:
        errors.append(x - level)
        level = ALPHA * x + (1 - ALPHA) * level
    bias = median(errors)
    spread = max(median(abs(e - bias) for e in errors), VARIABLES[variable].resolution)
    expected = level + bias
    score = 0.6745 * (value - expected) / spread
    if abs(score) <= THRESHOLD:
        return None
    v = VARIABLES[variable]
    direction = "subió" if score > 0 else "bajó"
    message = (f"{v.label} {direction} de forma inusual: {fmt(value)}{v.unit} "
               f"(lo normal en este estanque ahora: {fmt(expected)}{v.unit})")
    return Anomaly(variable, value, round(expected, 2), round(score, 1), message)


def evaluate(readings: list[dict]) -> list[Anomaly]:
    """Checks the newest reading against the ones before it. Missing values are skipped, as in the rules."""
    readings = sorted(readings, key=lambda r: r["registrado_en"])
    *previous, newest = readings
    found = []
    for variable in VARIABLES:
        value = newest.get(variable)
        if value is None:
            continue
        history = [r[variable] for r in previous if r.get(variable) is not None]
        anomaly = check(variable, history, value)
        if anomaly:
            found.append(anomaly)
    return found


def fmt(x: float) -> str:
    """19.0 -> "19", 6.25 -> "6.25", like the backend's alert messages."""
    return f"{round(x, 2):g}"
