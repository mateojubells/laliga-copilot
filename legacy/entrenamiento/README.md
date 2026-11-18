# Entrenamiento del detector de situaciones

Genera `../situaciones.js` (modelo que usa `index.html`). Datos: **SoccerNet-Echoes** (transcripciones Whisper, CC BY 4.0)
+ etiquetas de acción de **SoccerNet** (`Labels-v2.json`). No se usa audio ni vídeo de ninguna retransmisión.

    python3 -m venv venv && venv/bin/pip install pyarrow scikit-learn numpy SoccerNet
    venv/bin/python download.py DIR            # ~120 MB de transcripciones + ~24 MB de etiquetas
    venv/bin/python langs.py DIR               # idioma por partido
    mkdir DIR/work && cp situations.py DIR/work/
    venv/bin/python extract.py DIR             # corpus en español -> DIR/work/es.jsonl
    venv/bin/python train.py DIR 20 5 8 8000   # ventana 20 s, paso 5 s, C=8, 8000 rasgos (imprime P/R/F1 por evento)
    venv/bin/python export.py DIR              # -> DIR/work/situaciones.js (copiar a la carpeta de la app)
    venv/bin/python eval_live.py DIR           # simula la app sobre los partidos de test

## Resultados (21 partidos de test, acierto si se detecta a ±15 s de la jugada real)
Corpus: 291 mitades en español (137 partidos con etiquetas), 70/15/15 % por partido. Clases entrenadas: gol, cambio, fuera de juego,
córner, falta, tiro, amarilla. F1 por evento ≈ 0,35–0,49 (gol ≈ 0,35; amarilla ≈ 0,49). Falta es la menos fiable.
Penalti, roja, VAR y lesión no tienen ejemplos suficientes (50 y 18 en todo el corpus): van por palabras clave en la app.
Limitaciones: transcripción automática (Whisper), temporadas 2014-17 y 2019-20, comentario de varias cadenas mezcladas.
