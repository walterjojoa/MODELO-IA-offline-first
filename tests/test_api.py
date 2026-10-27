from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

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
