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
