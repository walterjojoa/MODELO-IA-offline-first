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


def test_a_flat_pond_comes_back_empty():
    flat = readings([9.0, 9.1, 8.9, 9.2, 8.8, 9.0, 9.1, 8.9, 9.0, 9.1, 8.9, 9.0, 9.2, 8.8, 9.1, 9.0])
    response = client.post("/tendencias", json={"lecturas": flat, "rangos": [OXYGEN_RANGE]},
                           headers=KEY)
    assert response.status_code == 200 and response.json() == []


def test_the_ranges_are_optional_and_then_there_is_no_date():
    response = client.post("/tendencias", json={"lecturas": falling()}, headers=KEY)
    [found] = response.json()
    assert found["dias_al_limite"] is None
    assert found["limite"] is None


def test_too_little_history_is_a_valid_empty_answer_and_not_an_error():
    response = client.post("/tendencias", json={"lecturas": readings([9.0, 8.5, 8.0])}, headers=KEY)
    assert response.status_code == 200 and response.json() == []


def test_tendencias_needs_the_key():
    assert client.post("/tendencias", json={"lecturas": falling()}).status_code == 401


def test_tendencias_rejects_an_empty_list():
    assert client.post("/tendencias", json={"lecturas": []}, headers=KEY).status_code == 422


# ---------- /combinaciones ----------

def coupled(n=40, extra=None):
    rows = []
    for i in range(n):
        phase = math.sin(i * math.pi / 4)
        rows.append({"registrado_en": (START + timedelta(hours=6 * i)).isoformat(),
                     "temp_c": round(14.5 + 2.5 * phase, 2),
                     "ph": round(7.2 + 0.35 * phase, 3)})
    if extra:
        rows.append({"registrado_en": (START + timedelta(hours=6 * n)).isoformat(), **extra})
    return rows


def test_a_combination_never_seen_comes_back_with_its_distance():
    body = {"lecturas": coupled(extra={"temp_c": 12.2, "ph": 7.52})}
    response = client.post("/combinaciones", json=body, headers=KEY)
    assert response.status_code == 200
    found = response.json()
    assert found["variables"] == ["temp_c", "ph"]
    assert found["distancia"] > found["corte"]
    assert "no se había visto" in found["mensaje"]


def test_a_reading_that_follows_the_pattern_comes_back_null():
    body = {"lecturas": coupled(extra={"temp_c": 16.9, "ph": 7.54})}
    assert client.post("/combinaciones", json=body, headers=KEY).json() is None


def test_without_enough_history_it_comes_back_null_and_not_an_error():
    """
    Null covers both "it follows the pattern" and "I cannot tell yet", and that is a limitation
    worth knowing: the pond's own readings are the only reference there is.
    """
    body = {"lecturas": coupled(n=10, extra={"temp_c": 12.2, "ph": 7.52})}
    response = client.post("/combinaciones", json=body, headers=KEY)
    assert response.status_code == 200 and response.json() is None


def test_combinaciones_needs_the_key():
    assert client.post("/combinaciones", json={"lecturas": coupled()}).status_code == 401


# ---------- /proyeccion-lote ----------

def batch_body(**extra):
    body = {
        "fecha_siembra": "2026-06-01",
        "cantidad_inicial": 10000,
        "peso_inicial_g": 5.0,
        "biometrias": [
            {"registrado_en": "2026-06-01T06:00:00+00:00", "peso_promedio_g": 5.0, "muestra": 30},
            {"registrado_en": "2026-07-31T06:00:00+00:00", "peso_promedio_g": 28.0, "muestra": 30},
        ],
        "mortalidades": [{"registrado_en": "2026-06-15T06:00:00+00:00", "cantidad": 300}],
        "lecturas": [{"registrado_en": (datetime(2026, 6, 1, tzinfo=timezone.utc)
                                        + timedelta(days=i)).isoformat(), "temp_c": 12.4}
                     for i in range(61)],
        "dias_adelante": 30,
        "peso_objetivo_g": 250.0,
    }
    body.update(extra)
    return body
