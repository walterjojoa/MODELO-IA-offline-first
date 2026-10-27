from datetime import date, datetime, timedelta, timezone

import pytest

from app.growth import (MIN_DAYS_BETWEEN_WEIGHINGS, POOR_GROWTH_FRACTION, REFERENCE_TGC,
                        Batch, Death, Temperature, Weighing, fit_tgc, project, weight_after)

UTC = timezone.utc
STOCKED = date(2026, 6, 1)
