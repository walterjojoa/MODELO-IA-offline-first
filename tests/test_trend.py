import math
import random
from datetime import datetime, timedelta, timezone

from app.anomalies import check as anomaly_check
from app.trend import MIN_AGREEMENT, MIN_DAYS, MIN_READINGS, check, evaluate, slope

START = datetime(2026, 10, 1, 6, tzinfo=timezone.utc)
