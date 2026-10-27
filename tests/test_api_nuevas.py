"""The HTTP contract of the three routes added next to /anomalias and /pronostico-temperatura.

What matters here is not the arithmetic — test_trend, test_combination and test_growth cover that —
but the shape: that the field names are the Spanish ones the rest of the project uses, and that
"I could not tell" comes back as a valid answer and not as an error. If that last one broke, the
backend would end up logging the service's silence as a failure, or worse, reading it as "I checked
and everything is fine".
"""

import math
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)
START = datetime(2026, 10, 1, 6, tzinfo=timezone.utc)
