"""AI level 2: where a variable is heading, and when it would reach the rule's critical limit.

This module exists because of a deliberate decision in anomalies.py. That one treats a slow trend as
normal — `test_slow_trend_is_normal` asserts it — and it is right to: its question is "is this
reading surprising?", and water warming through the morning is not surprising. The EWMA lags, the
bias corrects it, nothing is flagged.

But that leaves one case uncovered, and it is the expensive one. Oxygen falling from 8.5 to 6.2 over
a week never surprises anybody: every reading is a little below the last, and the EWMA follows it
down. The rules (level 1) do not complain either, because 6.2 is still above the critical 5.0. So
nothing says anything until the day it crosses, which is the day it is already too late. The two
modules answer different questions and together they cover both:

    anomalies.py  is this reading surprising for this pond?        -> a jump
    trend.py      where is this pond heading, and how long until   -> a drift
                  it is a problem?

Method, per variable, over the readings in the window:
- Theil-Sen slope: the median of the slopes of every pair of points.
- "agreement": the share of those pairs that agree in sign with the median. It separates a real
  drift from the daily cycle.
- The slope is projected to the critical limit the rules give, which turns it into a date.

Theil-Sen instead of least squares for the same reason anomalies.py uses medians: the caretaker
pulls the sensor out of the water and the reading of the air stays in the history. Measured on a
series falling 0.3 °C per day with one such reading at the end, least squares reports the oxygen
**rising**; Theil-Sen returns the real slope to three decimals.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta
from statistics import median

from app.anomalies import VARIABLES, fmt

MIN_READINGS = 12
"""Fewer than this and the median of the pairs is as noisy as the readings themselves."""

MIN_DAYS = 3.0
"""
The window has to cover at least three days, and this is the number that had to be measured rather
than chosen.

The problem is the daily cycle: water warms at midday and cools at night, and pH and oxygen follow.
Over a short window that swing is indistinguishable from a drift. Measured over 40 simulated series
of one day, the ones **without** any trend scored higher agreement (0.77 at the 95th percentile)
than the ones **with** a real trend (0.67 at the 5th). In a one-day window there is no threshold
that works, because the order is inverted.

From three days on, whole cycles cancel out and the two groups separate.
"""

MIN_AGREEMENT = 0.65
"""
With a three-day window the thresholds were swept:

    0.60 -> catches 97 % of real trends, but calls 5 % of flat series a trend
    0.65 -> catches 92 %, and never called a flat series a trend
    0.70 -> catches 71 %, gaining nothing in precision

0.65 it is. The 5 % of the looser threshold reads like little, but it is the caretaker getting one
false alarm in twenty: by the third they stop looking at them, and then none of this is worth
anything. Losing the 8 % noisiest trends costs less than losing their trust.
"""

HORIZON_DAYS = 7
"""Beyond a week the straight line says more about the line than about the pond."""

URGENT_DAYS = 2
"""Closer than this and it stops being something to watch and becomes something to do today."""
