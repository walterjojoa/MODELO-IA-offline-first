import math
import random
from datetime import datetime, timedelta, timezone

from app.anomalies import check as anomaly_check
from app.anomalies import VARIABLES
from app.combination import MIN_HISTORY, cutoff_for, distance, evaluate, solve

FLOORS = [VARIABLES["temp_c"].resolution, VARIABLES["ph"].resolution]
