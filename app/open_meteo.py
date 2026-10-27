"""Hourly air temperature for the farm, past and forecast, from Open-Meteo (free, no key).

One call brings both: the past 92 days to fit the model and the coming days to predict with it.
"""

import json
import os
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import urlopen

URL = "https://api.open-meteo.com/v1/forecast"
PAST_DAYS = 92
"""The most this endpoint gives back; readings older than that cannot be paired with air."""

# El Encano, Laguna de La Cocha (Pasto, Nariño). Env vars for a farm somewhere else
LATITUDE = float(os.environ.get("LATITUD", "1.16"))
LONGITUDE = float(os.environ.get("LONGITUD", "-77.16"))


def parse(payload: dict) -> tuple[list[datetime], list[float]]:
    """Hours come in UTC (timezone=GMT in the request). A missing value repeats the previous one: the
    model needs one value per hour, and a gap of an hour or two in the air barely moves the water."""
    hours, air, last = [], [], None
    for time, value in zip(payload["hourly"]["time"], payload["hourly"]["temperature_2m"]):
        if value is None:
            if last is None:
                continue
            value = last
        hours.append(datetime.fromisoformat(time).replace(tzinfo=timezone.utc))
        air.append(float(value))
        last = value
    return hours, air


def air_temperature(forecast_days: int) -> tuple[list[datetime], list[float]]:
    query = urlencode({"latitude": LATITUDE, "longitude": LONGITUDE, "hourly": "temperature_2m",
                       "past_days": PAST_DAYS, "forecast_days": forecast_days, "timezone": "GMT"})
    with urlopen(f"{URL}?{query}", timeout=20) as response:
        return parse(json.load(response))
