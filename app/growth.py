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
