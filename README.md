# La Cocha - IA

Servicio de inteligencia artificial del proyecto La Cocha (truchicultura en El Encano).
Solo lo llama el backend: no tiene base de datos propia ni lo usa el frontend directamente.

| Nivel | Qué hace | Dónde vive |
|---|---|---|
| 1 | Sistema experto: rangos de pH, temperatura y oxígeno, ración de alimento | backend (`Rules.java`) y la app sin internet |
| 2 | Anomalías: valores raros *para ese estanque* aunque estén dentro del rango | **aquí** (`app/anomalies.py`) |
| 2 | Tendencias: hacia dónde va una variable y cuándo cruzaría el límite | **aquí** (`app/trend.py`) |
| 2 | Combinaciones: lecturas que ninguna variable sola delata | **aquí** (`app/combination.py`) |
| 2 | Pronóstico de la temperatura del agua a partir de la del aire (Open-Meteo) | **aquí** (`app/forecast.py`) |
| 2 | Proyección del lote: peso, fecha de cosecha y supervivencia | **aquí** (`app/growth.py`) |
| 3 | Asistente que explica con datos del backend, nunca inventa números | aquí, pendiente |

Los tres detectores de agua responden preguntas distintas y **no se pisan**:

| Módulo | La pregunta que responde | Lo que atrapa |
|---|---|---|
| `anomalies.py` | ¿esta lectura sorprende para este estanque? | un salto |
| `trend.py` | ¿hacia dónde va, y cuánto falta para que sea un problema? | una deriva |
| `combination.py` | ¿esta lectura es una que este estanque nunca produce? | una pareja de valores nueva |

## Anomalías

Por cada variable se compara la lectura nueva con las anteriores del mismo estanque:
una media móvil exponencial (EWMA) da el valor esperado y la desviación absoluta mediana (MAD)
de sus errores dice cuánto se mueve normalmente ese estanque. Si la puntuación robusta
`0.6745 · (error − sesgo) / MAD` pasa de 3.5 (Iglewicz y Hoaglin, 1993), es anomalía.
Hacen falta al menos 12 lecturas previas; se usan las últimas 48.

```
POST /anomalias          (cabecera X-API-Key)
{"lecturas": [{"registrado_en": "2026-10-26T08:00:00Z", "temp_c": 12.1, "ph": 7.0, "oxigeno_mg_l": 9.0}, ...]}
-> [{"variable": "oxigeno_mg_l", "valor": 6.5, "esperado": 9.01, "puntaje": -12.9, "mensaje": "Oxígeno bajó de forma inusual: 6.5 mg/L (lo normal en este estanque ahora: 9.01 mg/L)"}]
```

Se evalúa la lectura más reciente; la respuesta vacía `[]` significa que todo está normal.

## Pronóstico de temperatura del agua

El agua sigue a la temperatura del aire, pero más despacio. El modelo es un retardo de primer orden
(la idea del modelo air2water, Piccolroaz et al. 2013, reducida a lo que permiten pocas lecturas):

```
aire suavizado  S(t) = S(t-1) + k · (aire(t) − S(t-1)),   k = 1 − e^(−1/τ)
agua            W(t) = a + b · S(t)
```

`τ` (horas) dice qué tan lento reacciona el estanque; `a` y `b` traducen aire en agua para ese
estanque (uno de manantial casi no sigue al aire: `b` pequeño). Para cada `τ` candidato se ajustan
`a` y `b` por mínimos cuadrados y gana el que menos se equivoca con las lecturas. La temperatura del
aire (pasada y pronosticada, por hora) viene gratis de Open-Meteo para El Encano.

No se usa Holt-Winters ni redes neuronales porque necesitan lecturas del agua cada hora durante días;
el cuidador anota dos o tres al día. Este modelo necesita unas 10 lecturas de los últimos 87 días.

```
POST /pronostico-temperatura          (cabecera X-API-Key)
{"lecturas": [{"registrado_en": "...", "temp_c": 12.1}, ...], "dias": 2}
-> {"dias": [{"fecha": "2026-10-27", "minima": 11.5, "maxima": 12.4, "promedio": 12.0}, ...],
    "error_tipico": 0.2, "reaccion_horas": 36, "lecturas_usadas": 30, "mensaje": "..."}
```

Si faltan lecturas responde `"dias": []` con el motivo en `mensaje`; si Open-Meteo no responde, 503.
Las coordenadas se cambian con las variables `LATITUD` y `LONGITUD`.

## Correr en local

```
python -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest
set IA_API_KEY=algo-secreto
.venv\Scripts\uvicorn app.main:app --reload
```

Documentación interactiva en http://localhost:8000/docs
