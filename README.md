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

## Tendencias

`anomalies.py` trata una tendencia lenta como normal **a propósito**, y tiene razón: su pregunta es
si una lectura sorprende, y el agua calentándose a lo largo de la mañana no sorprende. Pero eso deja
un caso sin cubrir, y es el caro. El oxígeno bajando de 8.5 a 6.2 en una semana no sorprende a nadie
—cada lectura está un poco por debajo de la anterior— y el nivel 1 tampoco se queja, porque 6.2
sigue por encima del crítico de 5.0. Nadie dice nada hasta el día en que cruza, que es el día en que
ya es tarde.

Por cada variable se toma la **pendiente de Theil-Sen**: la mediana de las pendientes de todas las
parejas de puntos. Theil-Sen y no mínimos cuadrados por lo mismo que `anomalies.py` usa medianas:
el cuidador saca el sensor del agua y esa lectura queda en el historial. Medido, en una serie que
baja 0.3 °C por día con una lectura así al final, **mínimos cuadrados reporta que el oxígeno sube**;
Theil-Sen devuelve la pendiente real.

El `acuerdo` —la fracción de parejas que coincide en el signo— separa una deriva real del ciclo del
día. La ventana tiene que cubrir **al menos tres días**, y ese número salió de medirlo: sobre 40
series simuladas de un día, las que **no** tenían tendencia sacaron más acuerdo (0.77 en el
percentil 95) que las que **sí** la tenían (0.67 en el percentil 5). En una ventana de un día no hay
umbral que sirva porque el orden está invertido. Con tres días, el corte de 0.65 detecta 92 % de las
tendencias reales y no avisó de más ni una vez.

```
POST /tendencias          (cabecera X-API-Key)
{"lecturas": [...], "rangos": [{"variable": "oxigeno_mg_l", "critico_min": 5.0, "critico_max": null}]}
-> [{"variable": "oxigeno_mg_l", "por_dia": -0.4, "acuerdo": 1.0, "dias_cubiertos": 6.0,
     "dias_al_limite": 3.0, "limite": 5.0, "urgente": false,
     "mensaje": "Oxígeno viene bajando 0.4 mg/L por día (6 días de datos). A este ritmo llega al límite de 5 mg/L en 3 días."}]
```

Sin `rangos` la pendiente se reporta igual, porque "el oxígeno viene bajando 0.4 por día" vale
saberlo solo; lo que no se puede calcular sin ellos es cuándo se vuelve un problema.

## Combinaciones

Una lectura puede tener todos sus valores dentro de lo que ese estanque hace y seguir siendo una que
ese estanque nunca produce. En un estanque donde la temperatura y el pH se mueven juntos —el sol del
mediodía calienta el agua y las algas suben el pH con él— 12 °C es corriente y 7.5 de pH también,
pero los dos juntos nunca pasan, porque el pH alto de ese estanque viene del mediodía y el agua de
mediodía no está a 12 °C. Que aparezca significa que algo distinto al ciclo del día está moviendo el
pH.

Se usa la **distancia de Mahalanobis** de la lectura nueva a la nube de las anteriores: la distancia
que cuenta la *forma* de la nube, así que un punto fuera de la relación entre las variables sale
lejos aunque cada coordenada esté cerca. El corte es la cola del 1 % de la chi cuadrado.

La dispersión de cada variable se pisa con la **resolución del sensor**, y eso hizo falta
descubrirlo con una prueba que fallaba: con una nube sin ruido, un punto cuatro milésimas fuera de la
curva salía a distancia 3.61 contra un corte de 3.04. Una desviación menor que lo que el instrumento
distingue no es una desviación. Es la misma idea que `anomalies.py` ya aplica a un estanque cuyas
lecturas nunca se movieron.

```
POST /combinaciones          (cabecera X-API-Key)
{"lecturas": [...]}
-> {"variables": ["temp_c", "ph"], "valores": [12.2, 7.52], "distancia": 6.4, "corte": 3.035,
    "mensaje": "Esta combinación no se había visto en el estanque: temperatura 12.2 °C, pH 7.52. ..."}
```

`null` significa que no hay nada que reportar, y cubre dos cosas: que la lectura sigue el patrón, o
que todavía no hay historia para saberlo (hacen falta 20 lecturas completas). Solo cuentan las
lecturas que traen **todas** las variables: rellenar un hueco con el promedio de la columna
inventaría una combinación que nadie midió, y la combinación es justo lo que aquí se juzga.

## Proyección del lote

Esto **no** es un modelo aprendido, y decirlo así importa más de lo que suena: es un modelo de
crecimiento de la literatura al que se le ajusta un parámetro con los datos de la finca. En una
sustentación, la diferencia entre "entrenamos un modelo" y "ajustamos un modelo conocido a esta
finca" es la diferencia entre una afirmación y una medición.

Se usa el **coeficiente térmico de crecimiento** (Iwama y Tautz, 1981), que descansa en un hecho de
la trucha: no crece con el tiempo, crece con el calor acumulado.

```
W2^(1/3) = W1^(1/3) + (TGC / 1000) · T · días
```

Despejando, dos biometrías y la temperatura entre ellas dan el coeficiente de *esta* finca. El valor
de la literatura sirve para arrancar; a la segunda biometría el modelo ya habla del estanque real.
La Cocha está a 2.760 m y el agua es fría, así que es de esperar que el ajustado salga por debajo del
de referencia, y que eso se pueda medir es en sí un resultado. Con más de dos biometrías se toma la
**mediana** de los pares, que es lo que impide que un pesaje con mala muestra defina el lote.

Se empareja con `forecast.py`: el pronóstico dice qué tan tibia va a estar el agua, y esto dice
cuánto vale esa tibieza en gramos.

```
POST /proyeccion-lote          (cabecera X-API-Key)
{"fecha_siembra": "2026-06-01", "cantidad_inicial": 10000, "biometrias": [...],
 "mortalidades": [...], "lecturas": [...], "dias_adelante": 30, "peso_objetivo_g": 250}
-> {"tgc": 1.78, "tgc_ajustado": true, "peso_actual_g": 28.0, "peso_proyectado_g": 50.6,
    "dias_para_objetivo": 148, "fecha_objetivo": "2027-03-24", "supervivencia_pct": 93.0,
    "hallazgos": [...], "notas": [...]}
```

### Dos cosas que este módulo no sabe, y las dice

**La supervivencia es un techo, no una medición.** Sale de las mortalidades *registradas*, y un
alevino que muere y se descompone nunca se registra. La medición de verdad es el contador: comparar
lo que entrega al cosechar contra lo que se sembró es lo único que cierra la cuenta. Que el sistema
tenga las dos cosas y se puedan contrastar es justo lo que la tesis mide, y por eso el techo se
reporta como techo.

**Lo que no se puede calcular va en `notas`, no como cero.** Un peso proyectado de 0 g y un peso
proyectado desconocido no son lo mismo, y quien lea la pantalla tiene que notar la diferencia. Un
lote sin biometrías ni temperatura no recibe un pronóstico inventado: recibe qué falta registrar.

Además del peso, busca dos cosas en los números del lote. Que **crezca muy por debajo de lo que el
agua permite** es el hallazgo más útil: descarta la temperatura y apunta a ración, densidad o
sanidad, que es lo que el cuidador puede cambiar. Y que la **mortalidad se haya acelerado**, mirando
la última semana contra todo lo anterior. "Reciente" es una semana fija y no una fracción de la vida
del lote, porque un brote mata en cuatro o cinco días: medido sobre el mismo lote de prueba, el
último tercio daba 2.6 veces la tasa anterior y la semana da 9.5, que es lo que de verdad pasa. Un
lote puede llevar 95 % de supervivencia acumulada y estar en plena mortandad esta semana.

## Correr en local

```
python -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt
.venv\Scripts\python -m pytest
set IA_API_KEY=algo-secreto
.venv\Scripts\uvicorn app.main:app --reload
```

Documentación interactiva en http://localhost:8000/docs
