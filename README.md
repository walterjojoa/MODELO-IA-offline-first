# La Cocha - IA

Servicio de inteligencia artificial del proyecto La Cocha (truchicultura en El Encano).
Solo lo llama el backend: no tiene base de datos propia ni lo usa el frontend directamente.

| Nivel | Qué hace | Dónde vive |
|---|---|---|
| 1 | Sistema experto: rangos de pH, temperatura y oxígeno, ración de alimento | backend (`Rules.java`) y la app sin internet |
| 2 | Anomalías: valores raros *para ese estanque* aunque estén dentro del rango | **aquí** (`app/anomalies.py`) |
| 2 | Pronóstico de temperatura (Holt-Winters + Open-Meteo) | aquí, pendiente |
| 3 | Asistente que explica con datos del backend, nunca inventa números | aquí, pendiente |

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

## Correr en local

```
python -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest
set IA_API_KEY=algo-secreto
.venv\Scripts\uvicorn app.main:app --reload
```

Documentación interactiva en http://localhost:8000/docs
