# Cómo empezar (en local)

## 1. Requisitos
- Python 3 (para el servidor local y para refrescar datos).
- Google Chrome o Microsoft Edge (para el micrófono).

## 2. Arrancar
Descomprime el zip, entra en la carpeta y ejecuta:

    python3 -m http.server 8765

Abre http://localhost:8765 en Chrome. Pulsa **M** y permite el micrófono.
Sin micro: escribe frases en "Simular voz" (por ejemplo: "el Barça como visitante" o "el historial").

## 3. Uso
1. Elige el partido arriba.
2. Habla: di un equipo, un goleador o un dato ("racha", "en casa", "defensa", "clasificación", "historial").
3. Teclas: ←/→ elegir tarjeta · ↑/↓ cambiar dato · Espacio mantener · X quitar · C limpiar · 1/2 local/visitante · 3 historial · 4 tabla · S congelar voz · ? ayuda.

## 4. Actualizar datos
    python3 build_data.py
Necesita internet (descarga de GitHub/openfootball). Regenera `data.js`.

## 5. Trabajar con tu agente en local
Abre esta carpeta en Claude Code (o tu chat local) y dile, por ejemplo:
- "Lee CLAUDE.md y explícame el proyecto."
- "Añade un dato nuevo a las tarjetas de equipo: ..."
- "Conecta la API de API-Football con mi clave en una variable de entorno."
El archivo `CLAUDE.md` le da todo el contexto.
