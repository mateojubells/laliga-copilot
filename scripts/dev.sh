#!/usr/bin/env bash
# Arranca todo: datos (si faltan), backend (FastAPI, :8765) y frontend (Vite, :5173). Ctrl+C lo para todo.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
export PATH="$ROOT/.tools/bin:$ROOT/.tools/node/bin:$PATH"
PORT="${COPILOT_PORT:-8765}"; WEB_PORT="${COPILOT_WEB_PORT:-5173}"
if [ ! -f data/synth/out/laliga-2024-25.sqlite ]; then
  echo "[dev] generando datos de demostración (unos segundos)…"
  .venv/bin/python -m data.synth.generate >/dev/null
fi
if [ ! -d web/node_modules ]; then (cd web && npm install --no-audit --no-fund --silent); fi
trap 'kill $(jobs -p) 2>/dev/null || true' EXIT INT TERM
.venv/bin/python -m uvicorn copilot.server.app:app --host 127.0.0.1 --port "$PORT" --log-level warning &
(cd web && npm run dev -- --port "$WEB_PORT" --strictPort >/dev/null 2>&1) &
for i in $(seq 1 60); do
  if curl -sf "http://127.0.0.1:$PORT/api/health" >/dev/null && curl -sf "http://localhost:$WEB_PORT/" >/dev/null; then break; fi
  sleep 0.5
done
cat <<MSG

  LaLiga Copilot en marcha
    Preparar partido .... http://localhost:$WEB_PORT/setup   (menú principal: temporada, partido, alineaciones, voz)
    Operador ............ http://localhost:$WEB_PORT/
    Salida de programa .. http://localhost:$WEB_PORT/program   (fuente de navegador en OBS, 1920×1080, fondo transparente)
    Galería ............. http://localhost:$WEB_PORT/gallery
    Estado .............. http://127.0.0.1:$PORT/api/health

  Ctrl+C para parar.
MSG
wait
