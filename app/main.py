"""HTTP entry point. Only the backend calls this service (professor's diagram): it sends the pond's
recent readings and stores whatever comes back as alerts. This service has no database of its own."""

import hmac
import os
from datetime import date, datetime, timedelta, timezone
from urllib.error import URLError

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from app import anomalies, combination, forecast, growth, open_meteo, trend

VERSION = "0.3.0"
COLOMBIA = timedelta(hours=-5)
"""Colombia has no daylight saving time, so a fixed offset is exact."""

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


@app.get("/", include_in_schema=False)
def home() -> RedirectResponse:
    # Opening the bare address in a browser showed {"detail":"Not Found"}, which looked like a broken deploy
    return RedirectResponse("/docs")


@app.get("/salud")
def health() -> dict:
    return {"estado": "ok", "version": VERSION}


@app.post("/anomalias", dependencies=[Depends(require_key)])
def detect(request: AnalysisRequest) -> list[AnomalyResponse]:
    """Evaluates the newest of the readings sent against the others."""
    found = anomalies.evaluate([r.model_dump() for r in request.lecturas])
    return [AnomalyResponse(variable=a.variable, valor=a.value, esperado=a.expected,
                            puntaje=a.score, mensaje=a.message) for a in found]


class ForecastRequest(BaseModel):
    lecturas: list[Reading] = Field(min_length=1, max_length=5000)
    dias: int = Field(default=2, ge=1, le=7)


class DayResponse(BaseModel):
    fecha: str
    minima: float
    maxima: float
    promedio: float


class ForecastResponse(BaseModel):
    dias: list[DayResponse]
    error_tipico: float | None
    """°C the model typically missed the pond's own readings by; the min-max range already includes it."""
    reaccion_horas: float | None
    """How slowly the pond follows the air (tau): a spring-fed pond reacts in days, a shallow one in hours."""
    lecturas_usadas: int
    mensaje: str


@app.post("/pronostico-temperatura", dependencies=[Depends(require_key)])
def water_forecast(request: ForecastRequest) -> ForecastResponse:
    """Water temperature for the coming days, learned from the pond's readings and the air at El Encano."""
    try:
        hours, air = open_meteo.air_temperature(request.dias + 1)
    except (URLError, TimeoutError, ValueError, KeyError) as e:
        raise HTTPException(status_code=503, detail="No se pudo consultar el clima (Open-Meteo)") from e
    readings = [(r.registrado_en.astimezone(timezone.utc), r.temp_c)
                for r in request.lecturas if r.temp_c is not None]
    model = forecast.fit(hours, air, readings)
    if model is None:
        return ForecastResponse(
            dias=[], error_tipico=None, reaccion_horas=None, lecturas_usadas=0,
            mensaje=f"Faltan lecturas: se necesitan al menos {forecast.MIN_READINGS} de temperatura "
                    f"en los últimos {open_meteo.PAST_DAYS - forecast.SPIN_UP.days} días")
    now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
    days = forecast.predict(model, hours, air, since=now, utc_offset=COLOMBIA)[:request.dias + 1]
    return ForecastResponse(
        dias=[DayResponse(fecha=d.date, minima=d.low, maxima=d.high, promedio=d.mean) for d in days],
        error_tipico=round(model.error, 2), reaccion_horas=model.tau, lecturas_usadas=model.readings,
        mensaje="La mínima y la máxima de cada día ya incluyen el margen de error del modelo (80 %)")


class Range(BaseModel):
    """One row of the backend's parametros_rango. Without it a trend cannot be turned into a date."""
    variable: str
    critico_min: float | None = None
    critico_max: float | None = None


class TrendRequest(BaseModel):
    lecturas: list[Reading] = Field(min_length=1, max_length=500)
    rangos: list[Range] = Field(default_factory=list)


class TrendResponse(BaseModel):
    variable: str
    por_dia: float
    acuerdo: float
    """Share of the compared pairs agreeing on the direction: it tells a drift from the daily cycle."""
    dias_cubiertos: float
    dias_al_limite: float | None
    limite: float | None
    urgente: bool
    mensaje: str


@app.post("/tendencias", dependencies=[Depends(require_key)])
def trends(request: TrendRequest) -> list[TrendResponse]:
    """
    Where each variable is heading, and when it would reach the rules' critical limit.

    It answers what /anomalias deliberately does not: that one treats a slow trend as normal,
    because its question is whether a reading is surprising. Oxygen falling 0.4 mg/L a day never
    surprises anybody and is still on its way to a problem.
    """
    ranges = {r.variable: r.model_dump() for r in request.rangos}
    found = trend.evaluate([r.model_dump() for r in request.lecturas], ranges)
    return [TrendResponse(variable=t.variable, por_dia=t.per_day, acuerdo=t.agreement,
                          dias_cubiertos=t.days_covered, dias_al_limite=t.days_to_limit,
                          limite=t.limit, urgente=t.urgent, mensaje=t.message) for t in found]


class CombinationResponse(BaseModel):
    variables: list[str]
    valores: list[float]
    distancia: float
    corte: float
    mensaje: str


@app.post("/combinaciones", dependencies=[Depends(require_key)])
def combinations(request: AnalysisRequest) -> CombinationResponse | None:
    """
    Whether the newest reading is a combination this pond has never produced.

    Null means there is nothing to report, which covers both "the reading follows the pattern" and
    "there is not enough history to tell": the pond's own readings are the only reference, and
    without twenty complete ones there is no shape to compare against.
    """
    found = combination.evaluate([r.model_dump() for r in request.lecturas])
    if found is None:
        return None
    return CombinationResponse(variables=list(found.variables), valores=list(found.values),
                               distancia=found.distance, corte=found.cutoff, mensaje=found.message)


class WeighingInput(BaseModel):
    registrado_en: datetime
    peso_promedio_g: float
    muestra: int | None = None
