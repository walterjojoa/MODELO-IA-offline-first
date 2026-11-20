"""Pruebas del asistente sin llamar a Anthropic: el cliente se reemplaza por uno falso."""

from types import SimpleNamespace

import anthropic
import httpx2
import pytest
from fastapi.testclient import TestClient

from app import assistant
from app.main import app

client = TestClient(app)
KEY = {"X-API-Key": "secreta"}
FARM = {"estanques": [{"nombre": "E1", "lotes": [{"codigo": "L1", "racion_diaria_kg": 2.4}]}]}


@pytest.fixture(autouse=True)
def key(monkeypatch):
    monkeypatch.setenv("IA_API_KEY", "secreta")


class FakeMessages:
    def __init__(self, response=None, error=None):
        self.response = response
        self.error = error
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.response


def fake_client(text="Dale 2,4 kg al día al lote L1.", stop_reason="end_turn", error=None):
    response = SimpleNamespace(
        stop_reason=stop_reason, model=assistant.MODEL,
        content=[SimpleNamespace(type="thinking", thinking=""), SimpleNamespace(type="text", text=text)])
    messages = FakeMessages(response, error)
    return SimpleNamespace(beta=SimpleNamespace(messages=messages)), messages


def api_error(cls, status):
    request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
    return cls("fallo", response=httpx2.Response(status, request=request), body=None)


# ---------- la conversación que se arma ----------

def test_the_farm_data_goes_with_the_last_question_only():
    history = [assistant.Turn("usuario", "hola"), assistant.Turn("asistente", "¡Hola!")]
    messages = assistant.build_messages("¿Cuánto les doy?", FARM, history)
    assert [m["role"] for m in messages] == ["user", "assistant", "user"]
    assert "<datos_finca>" in messages[-1]["content"] and "racion_diaria_kg" in messages[-1]["content"]
    assert messages[-1]["content"].endswith("¿Cuánto les doy?")
    assert "<datos_finca>" not in messages[0]["content"]


def test_a_history_that_starts_with_the_assistant_is_trimmed():
    messages = assistant.build_messages("¿y hoy?", FARM, [assistant.Turn("asistente", "Bienvenido")])
    assert [m["role"] for m in messages] == ["user"]


def test_two_turns_of_the_same_side_are_joined():
    history = [assistant.Turn("usuario", "a"), assistant.Turn("usuario", "b")]
    messages = assistant.build_messages("c", FARM, history)
    assert len(messages) == 1 and messages[0]["content"].startswith("a\n\nb")


# ---------- la llamada al modelo ----------

def test_ask_uses_opus_with_fallbacks_and_returns_only_the_text():
    fake, messages = fake_client()
    answer = assistant.ask("¿Cuánto les doy?", FARM, [], client=fake)
    assert answer.respuesta == "Dale 2,4 kg al día al lote L1."
    call = messages.calls[0]
    assert call["model"] == "claude-opus-5-5"
    assert call["fallbacks"] == "default" and "server-side-fallback-2026-07-01" in call["betas"]
    assert "thinking" not in call and "temperature" not in call


def test_a_refusal_becomes_a_polite_answer():
    fake, _ = fake_client(text="", stop_reason="refusal")
    assert "No puedo responder" in assistant.ask("x", FARM, [], client=fake).respuesta


def test_a_cut_answer_says_so():
    fake, _ = fake_client(stop_reason="max_tokens")
    assert "cortada" in assistant.ask("x", FARM, [], client=fake).respuesta


def test_a_bad_key_is_explained():
    fake, _ = fake_client(error=api_error(anthropic.AuthenticationError, 401))
    with pytest.raises(assistant.AssistantError, match="ANTHROPIC_API_KEY"):
        assistant.ask("x", FARM, [], client=fake)


def test_without_a_key_it_says_it_is_not_configured(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(assistant.AssistantError, match="no está configurado"):
        assistant.ask("x", FARM, [])


# ---------- la ruta ----------

def test_route_answers(monkeypatch):
    fake, messages = fake_client()
    monkeypatch.setattr(assistant.anthropic, "Anthropic", lambda **_: fake)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-prueba")
    r = client.post("/asistente", headers=KEY, json={
        "pregunta": "¿Cuánto les doy?", "datos_finca": FARM,
        "historial": [{"rol": "usuario", "texto": "hola"}, {"rol": "asistente", "texto": "¡Hola!"}]})
    assert r.status_code == 200, r.text
    assert r.json() == {"respuesta": "Dale 2,4 kg al día al lote L1.", "modelo": "claude-opus-5-5"}
    assert len(messages.calls[0]["messages"]) == 3


def test_route_without_anthropic_key_is_503(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    r = client.post("/asistente", headers=KEY, json={"pregunta": "hola"})
    assert r.status_code == 503 and "no está configurado" in r.json()["detail"]


def test_route_needs_the_key():
    assert client.post("/asistente", json={"pregunta": "hola"}).status_code == 401


def test_route_rejects_an_empty_question_and_a_strange_role():
    assert client.post("/asistente", headers=KEY, json={"pregunta": ""}).status_code == 422
    r = client.post("/asistente", headers=KEY,
                    json={"pregunta": "x", "historial": [{"rol": "sistema", "texto": "y"}]})
    assert r.status_code == 422


def test_health_says_whether_the_assistant_is_configured(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert client.get("/salud").json()["asistente"] is False
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-prueba")
    assert client.get("/salud").json()["asistente"] is True
