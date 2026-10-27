"""HTTP entry point. Only the backend calls this service (professor's diagram): it sends the pond's
recent readings and stores whatever comes back as alerts. This service has no database of its own."""

import hmac
import os
from dataclasses import asdict
from datetime import datetime

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from app import anomalies

VERSION = "0.1.0"

app = FastAPI(title="La Cocha - IA", version=VERSION)


def require_key(x_api_key: str | None = Header(default=None)) -> None:
    # Without IA_API_KEY configured nobody gets in: better a loud 401 than an open service
    expected = os.environ.get("IA_API_KEY", "")
    if not expected or not x_api_key or not hmac.compare_digest(x_api_key.strip(), expected.strip()):
        raise HTTPException(status_code=401, detail="Falta o no coincide X-API-Key")


class Reading(BaseModel):
    registrado_en: datetime
    temp_c: float | None = None
    ph: float | None = None
    oxigeno_mg_l: float | None = None


class AnalysisRequest(BaseModel):
    lecturas: list[Reading] = Field(min_length=1, max_length=500)


class AnomalyResponse(BaseModel):
    variable: str
    valor: float
    esperado: float
    puntaje: float
    mensaje: str


@app.get("/salud")
def health() -> dict:
    return {"estado": "ok", "version": VERSION}


@app.post("/anomalias", dependencies=[Depends(require_key)])
def detect(request: AnalysisRequest) -> list[AnomalyResponse]:
    """Evaluates the newest of the readings sent against the others."""
    found = anomalies.evaluate([r.model_dump() for r in request.lecturas])
    return [AnomalyResponse(variable=a.variable, valor=a.value, esperado=a.expected,
                            puntaje=a.score, mensaje=a.message) for a in found]
