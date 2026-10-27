"""Where a batch is heading: what it will weigh, when it reaches market weight, how many will be left.

This one is not a learned model, and saying so plainly matters more than it sounds: it is a growth
model from the literature whose parameter is fitted with the farm's own data. In a defence, the
difference between "we trained a model" and "we fitted a known model to this farm" is the difference
between a claim and a measurement.

## The model

The thermal growth coefficient (Iwama & Tautz, 1981), the standard in fish farming, resting on a
fact about trout: they do not grow with time, they grow with accumulated *heat*. A month at 14 °C is
worth more than a month at 9 °C, and the arithmetic says it:

    W2^(1/3) = W1^(1/3) + (TGC / 1000) * T * days

with weight in grams and T in degrees. Rearranged, it gives the coefficient of *this* farm from two
weighings and the temperature between them. That is what makes it useful here: the number from the
literature gets it started, and by the second biometry the model is talking about the real pond
rather than an average trout from somewhere else.

La Cocha sits at 2,760 m and the water is cold, so the fitted coefficient is expected to come out
below the reference. That it can be measured at all is, in itself, a result.

It pairs with forecast.py, which predicts the water temperature for the coming days: the forecast
says how warm the water will be, and this says what that warmth is worth in grams.

## What cannot be known, and is said instead of hidden

Survival is worked out from the *recorded* mortalities, and that has a limit worth writing down: a
fry that dies and decomposes, or that a bird takes, is never recorded. So the survival that comes
out of here is a **ceiling**, not a measurement. The real measurement is the fry counter: comparing
what it delivers at harvest against what was stocked is the only thing that closes the account. That
the system has both and they can be contrasted is exactly what the thesis sets out to measure, which
is why the ceiling is reported as a ceiling instead of dressed up as a figure.

Whatever cannot be worked out is not worked out, and `notes` says what is missing. A projection for
a batch with no weighings and no temperatures would be a number invented with the face of a forecast.
"""

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from statistics import median

REFERENCE_TGC = 2.0
"""
Reference coefficient for rainbow trout, with the same warning the project already puts on the rule
ranges, because it is just as true: a reference value without a citation, to be adjusted with the
producer and cited from AUNAP/FAO before the pilot. It only rules until the batch has two weighings.
"""

MIN_DAYS_BETWEEN_WEIGHINGS = 7.0
"""Under a week the difference in weight is more sampling error than growth: weighing thirty fry out
of ten thousand has a spread of its own, and in five days growth does not beat it."""

POOR_GROWTH_FRACTION = 0.6
"""
Below this fraction of the reference the batch is deemed to be growing badly. Not a measured value:
a criterion, named so the producer can move it once there are several cycles to compare against.
"""

RECENT_DAYS = 7.0
"""
"Recently" is a fixed week, not a fraction of the batch's life.

The first version compared the last third against the first two, and that dilutes exactly the case
that matters: an outbreak kills over four or five days, and in a two-month batch the last third is
twenty days, fifteen of them quiet. Measured on the same test batch, the third gave 2.6 times the
earlier rate and the week gives 9.5, which is what is actually happening. A week is also the unit a
pond gets looked at in.
"""

MIN_EARLIER_DAYS = 7.0
"""Some history before the window is needed to have anything to compare against."""

ACCELERATION_FACTOR = 2.0
MIN_RECENT_DEATHS = 5
"""
Both are needed. Without the absolute floor, going from one death to three is a "tripling" that
means nothing.
"""

EXPECTED_SURVIVAL_PCT = 80.0
"""What a well-run batch of fry is expected to reach. Same standing as the reference TGC: it
orients, it does not validate."""

SECONDS_PER_DAY = 86400.0


@dataclass(frozen=True)
class Weighing:
    """A sample weighing. `sample` is how many fish were weighed, when it was recorded."""
    at: datetime
    average_g: float
    sample: int | None = None


@dataclass(frozen=True)
class Death:
    at: datetime
    quantity: int


@dataclass(frozen=True)
class Temperature:
    at: datetime
    celsius: float


@dataclass(frozen=True)
class Batch:
    stocked_on: date | None = None
    stocked_quantity: int | None = None
    stocked_weight_g: float | None = None


@dataclass(frozen=True)
class Finding:
    kind: str
    """crecimiento | mortalidad"""
    urgent: bool
    score: float
    message: str


@dataclass(frozen=True)
class Projection:
    days_ahead: int
    # --- growth ---
    tgc: float | None = None
    tgc_fitted: bool = False
    """False means it is the reference value from the literature, not this farm's."""
    mean_temp_c: float | None = None
    current_weight_g: float | None = None
    projected_weight_g: float | None = None
    days_to_target: int | None = None
    target_date: date | None = None
    # --- survival: a ceiling, not a measurement (see the module docstring) ---
    current_quantity: int | None = None
    projected_quantity: int | None = None
    survival_pct: float | None = None
    deaths_per_day: float | None = None
    # --- the rest ---
    findings: list[Finding] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def fmt(x: float) -> str:
    """19.0 -> "19", 6.25 -> "6.25", like the rest of the service's messages."""
    return f"{round(x, 2):g}"


def _days(start: datetime, end: datetime) -> float:
    return (end - start).total_seconds() / SECONDS_PER_DAY


def mean_temperature(temperatures: list[Temperature], start: datetime, end: datetime) -> float | None:
    """
    The stretch's temperature, by median.

    Median and not mean for the usual reason: a reading taken with the sensor out of the water moves
    a short stretch's mean by several degrees, and here the temperature multiplies the projected
    growth directly.
    """
    inside = [t.celsius for t in temperatures if start <= t.at <= end]
    return median(inside) if inside else None


def fit_tgc(weighings: list[Weighing],
            temperatures: list[Temperature]) -> tuple[float | None, int]:
    """
    This farm's coefficient, from whatever weighings it has.

    With more than two, the coefficient of each consecutive pair is worked out and the median taken,
    which is what stops one weighing with a bad sample from defining the whole batch's growth.

    Returns (coefficient, how many pairs could be used).
    """
    coefficients = []
    for before, after in zip(weighings, weighings[1:]):
        days = _days(before.at, after.at)
        if days < MIN_DAYS_BETWEEN_WEIGHINGS:
            continue
        if before.average_g <= 0 or after.average_g <= 0:
            continue
        temperature = mean_temperature(temperatures, before.at, after.at)
        if temperature is None or temperature <= 0:
            continue
        growth = after.average_g ** (1 / 3) - before.average_g ** (1 / 3)
        coefficients.append(1000.0 * growth / (temperature * days))

    if not coefficients:
        return None, 0
    return median(coefficients), len(coefficients)


def weight_after(weight_g: float, tgc: float, celsius: float, days: float) -> float:
    """The weight after that many days at that temperature. Never below zero."""
    root = weight_g ** (1 / 3) + (tgc / 1000.0) * celsius * days
    return max(root, 0.0) ** 3


def days_until(weight_g: float, target_g: float, tgc: float, celsius: float) -> float | None:
    """Days left to the target weight. None if it is already past, or will never get there."""
    if target_g <= weight_g:
        return 0.0
    if tgc <= 0 or celsius <= 0:
        return None
    return 1000.0 * (target_g ** (1 / 3) - weight_g ** (1 / 3)) / (tgc * celsius)


def project(batch: Batch,
            weighings: list[Weighing] | None = None,
            deaths: list[Death] | None = None,
            temperatures: list[Temperature] | None = None,
            days_ahead: int = 30,
            target_weight_g: float | None = None,
            now: datetime | None = None) -> Projection:
    """What can be said about this batch with what it has recorded."""
    weighings = sorted(weighings or [], key=lambda w: w.at)
    deaths = sorted(deaths or [], key=lambda d: d.at)
    temperatures = sorted(temperatures or [], key=lambda t: t.at)
    if now is None:
        reference = weighings or deaths or temperatures
        now = max(item.at for item in reference) if reference else datetime.now(tz=None)

    findings: list[Finding] = []
    notes: list[str] = []
    growth = _project_growth(batch, weighings, temperatures, days_ahead, target_weight_g,
                             now, findings, notes)
    survival = _project_survival(batch, deaths, days_ahead, now, findings, notes)
    return Projection(days_ahead=days_ahead, findings=findings, notes=notes, **growth, **survival)


def _project_growth(batch, weighings, temperatures, days_ahead, target, now, findings, notes) -> dict:
    empty = {"tgc": None, "tgc_fitted": False, "mean_temp_c": None, "current_weight_g": None,
             "projected_weight_g": None, "days_to_target": None, "target_date": None}

    if weighings:
        current = weighings[-1].average_g
        since = weighings[-1].at
    elif batch.stocked_weight_g and batch.stocked_on:
        current = batch.stocked_weight_g
        since = datetime.combine(batch.stocked_on, datetime.min.time(), tzinfo=now.tzinfo)
    else:
        notes.append("Sin biometrías ni peso de siembra no hay de dónde partir para proyectar el "
                     "crecimiento. Basta con registrar un pesaje de muestra.")
        return empty

    if current <= 0:
        notes.append("El peso registrado no es positivo, así que no se puede proyectar.")
        return empty

    celsius = mean_temperature(temperatures, since, now)
    if celsius is None and temperatures:
        celsius = median([t.celsius for t in temperatures])
    if celsius is None:
        notes.append("Sin lecturas de temperatura no se puede proyectar el crecimiento: la trucha "
                     "crece con el calor acumulado del agua, no con los días que pasan.")
        return empty

    tgc, pairs = fit_tgc(weighings, temperatures)
    fitted = tgc is not None
    if not fitted:
        tgc = REFERENCE_TGC
        if len(weighings) < 2:
            notes.append("El coeficiente de crecimiento es el de referencia, no el de esta finca. "
                         "Con una segunda biometría pasa a calcularse con los datos del lote.")
        else:
            notes.append(f"Las biometrías están demasiado juntas (hacen falta al menos "
                         f"{fmt(MIN_DAYS_BETWEEN_WEIGHINGS)} días entre dos) o les falta "
                         f"temperatura en el tramo, así que se usa el de referencia.")

    # A fitted coefficient at or below zero means the batch is losing weight. Projecting with it
    # would give a weight falling to zero, which is not a forecast but an absurd extrapolation.
    if fitted and tgc <= 0:
        findings.append(Finding("crecimiento", True, round(abs(tgc), 3),
                                f"El lote no está creciendo: entre las dos últimas biometrías el "
                                f"peso promedio bajó. Con el agua a {fmt(celsius)} °C debería estar "
                                f"subiendo. Revisar alimentación, densidad y sanidad."))
        notes.append("No se proyecta peso hacia adelante: con el lote perdiendo peso, la cuenta "
                     "daría un número sin sentido.")
        return {**empty, "tgc": round(tgc, 3), "tgc_fitted": True,
                "mean_temp_c": round(celsius, 2), "current_weight_g": round(current, 1)}

    if fitted and tgc < REFERENCE_TGC * POOR_GROWTH_FRACTION:
        findings.append(Finding("crecimiento", False, round(tgc / REFERENCE_TGC, 2),
                                f"El lote crece a {round(100 * tgc / REFERENCE_TGC)}% de lo que el "
                                f"agua a {fmt(celsius)} °C permitiría. La temperatura no es el "
                                f"problema: mirar ración, densidad del estanque y sanidad."))

    days_to_target = None
    target_date = None
    if target:
        left = days_until(current, target, tgc, celsius)
        if left is not None:
            days_to_target = int(round(left))
            # From the already-rounded days, so the date and the day count shown together cannot
            # end up saying different things
            target_date = (now + timedelta(days=days_to_target)).date()

    return {
        "tgc": round(tgc, 3),
        "tgc_fitted": fitted,
        "mean_temp_c": round(celsius, 2),
        "current_weight_g": round(current, 1),
        "projected_weight_g": round(weight_after(current, tgc, celsius, days_ahead), 1),
        "days_to_target": days_to_target,
        "target_date": target_date,
    }
