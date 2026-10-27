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
KEY = {"X-API-Key": "secreta"}


@pytest.fixture(autouse=True)
def key(monkeypatch):
    monkeypatch.setenv("IA_API_KEY", "secreta")


def readings(values, hours=6.0, variable="oxigeno_mg_l"):
    return [{"registrado_en": (START + timedelta(hours=hours * i)).isoformat(), variable: v}
            for i, v in enumerate(values)]


def falling(per_day=0.4, days=6.0, n=24, start=8.6):
    step = days * 24 / (n - 1)
    return [{"registrado_en": (START + timedelta(hours=step * i)).isoformat(),
             "oxigeno_mg_l": round(start - per_day * (step * i) / 24, 3)} for i in range(n)]


OXYGEN_RANGE = {"variable": "oxigeno_mg_l", "critico_min": 5.0, "critico_max": None}


# ---------- /tendencias ----------

def test_a_drift_comes_back_with_its_date():
    response = client.post("/tendencias", json={"lecturas": falling(), "rangos": [OXYGEN_RANGE]},
                           headers=KEY)
    assert response.status_code == 200
    [found] = response.json()
    assert found["variable"] == "oxigeno_mg_l"
    assert found["por_dia"] < 0
    assert found["dias_al_limite"] is not None
    assert found["limite"] == 5.0
    assert "bajando" in found["mensaje"]
    assert set(found) == {"variable", "por_dia", "acuerdo", "dias_cubiertos", "dias_al_limite",
                          "limite", "urgente", "mensaje"}
