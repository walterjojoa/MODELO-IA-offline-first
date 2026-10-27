import math
from datetime import datetime, timedelta, timezone
from urllib.error import URLError

import pytest
from fastapi.testclient import TestClient

from app import open_meteo
from app.forecast import smooth
from app.main import app

client = TestClient(app)
START = datetime(2026, 10, 1, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def key(monkeypatch):
    monkeypatch.setenv("IA_API_KEY", "secreta")


def body(last_oxygen):
    values = [9.0, 9.2, 8.8, 9.1, 8.9, 9.0, 9.3, 8.7, 9.1, 9.0, 8.9, 9.2, 9.0, 8.8, 9.1, last_oxygen]
    return {"lecturas": [{"registrado_en": (START + timedelta(hours=i)).isoformat(), "oxigeno_mg_l": v}
                         for i, v in enumerate(values)]}


def test_health_needs_no_key():
    assert client.get("/salud").json()["estado"] == "ok"


def test_anomaly_comes_back_in_spanish_contract():
    response = client.post("/anomalias", json=body(6.5), headers={"X-API-Key": "secreta"})
    assert response.status_code == 200
    [anomaly] = response.json()
    assert anomaly["variable"] == "oxigeno_mg_l"
    assert anomaly["valor"] == 6.5
    assert set(anomaly) == {"variable", "valor", "esperado", "puntaje", "mensaje"}


def test_normal_reading_returns_empty_list():
    response = client.post("/anomalias", json=body(9.0), headers={"X-API-Key": "secreta"})
    assert response.json() == []


def test_wrong_or_missing_key_is_401():
    assert client.post("/anomalias", json=body(6.5)).status_code == 401
    assert client.post("/anomalias", json=body(6.5), headers={"X-API-Key": "otra"}).status_code == 401


def test_unconfigured_key_rejects_everyone(monkeypatch):
    monkeypatch.delenv("IA_API_KEY")
    assert client.post("/anomalias", json=body(6.5), headers={"X-API-Key": ""}).status_code == 401


def test_empty_list_is_422():
    response = client.post("/anomalias", json={"lecturas": []}, headers={"X-API-Key": "secreta"})
    assert response.status_code == 422


def fake_air(monkeypatch, days_back=40, days_ahead=3):
    """Air from Open-Meteo replaced by a daily cycle around the current time."""
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    hours = [now + timedelta(hours=h) for h in range(-days_back * 24, days_ahead * 24)]
    air = [13 + 5 * math.sin(2 * math.pi * h.hour / 24) for h in hours]
    monkeypatch.setattr(open_meteo, "air_temperature", lambda days: (hours, air))
    return hours, air


def water_readings(hours, air, count):
    s = smooth(air, 24)
    past = [i for i, h in enumerate(hours) if h < datetime.now(timezone.utc)]
    picked = past[-count * 8::8]
    return {"lecturas": [{"registrado_en": hours[i].isoformat(), "temp_c": round(4 + 0.6 * s[i], 2)}
                         for i in picked], "dias": 2}


def test_forecast_returns_days_with_range(monkeypatch):
    hours, air = fake_air(monkeypatch)
    response = client.post("/pronostico-temperatura", json=water_readings(hours, air, 20),
                           headers={"X-API-Key": "secreta"})
    assert response.status_code == 200
    data = response.json()
    assert data["lecturas_usadas"] == 20
    assert data["reaccion_horas"] == 24
    assert 2 <= len(data["dias"]) <= 3
    assert all(d["minima"] <= d["promedio"] <= d["maxima"] for d in data["dias"])


def test_forecast_with_few_readings_explains_why(monkeypatch):
    hours, air = fake_air(monkeypatch)
    response = client.post("/pronostico-temperatura", json=water_readings(hours, air, 5),
                           headers={"X-API-Key": "secreta"})
    data = response.json()
    assert data["dias"] == []
    assert data["mensaje"].startswith("Faltan lecturas")


def test_forecast_when_weather_service_is_down_is_503(monkeypatch):
    def down(days):
        raise URLError("sin internet")
    monkeypatch.setattr(open_meteo, "air_temperature", down)
    response = client.post("/pronostico-temperatura", json={"lecturas": [{"registrado_en": START.isoformat(),
                           "temp_c": 12}]}, headers={"X-API-Key": "secreta"})
    assert response.status_code == 503


def test_forecast_needs_key():
    assert client.post("/pronostico-temperatura", json={"lecturas": []}).status_code == 401
