#!/usr/bin/env bash
# Instala en espacio de usuario (sin sudo) todo lo que necesita el proyecto, dentro de .tools/ :
#   uv (Python moderno + entornos), Node LTS (binario oficial) y ffmpeg (binario estático vía imageio-ffmpeg).
# Idempotente: si ya está, no hace nada.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TOOLS="$ROOT/.tools"; BIN="$TOOLS/bin"
mkdir -p "$BIN"
export PATH="$BIN:$TOOLS/node/bin:$PATH"

if [ ! -x "$BIN/uv" ]; then
  echo "[bootstrap] instalando uv en $BIN"
  curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR="$BIN" UV_NO_MODIFY_PATH=1 INSTALLER_NO_MODIFY_PATH=1 sh >/dev/null
fi

NODE_MAJOR="${NODE_MAJOR:-22}"
if [ ! -x "$TOOLS/node/bin/node" ]; then
  echo "[bootstrap] instalando Node $NODE_MAJOR (binario oficial) en $TOOLS/node"
  ARCH="$(uname -m)"; [ "$ARCH" = "x86_64" ] && ARCH="x64"
  OS="$(uname -s | tr '[:upper:]' '[:lower:]')"
  BASE="https://nodejs.org/dist/latest-v${NODE_MAJOR}.x"
  TMP="$(mktemp -d)"
  curl -fsSL "$BASE/SHASUMS256.txt" -o "$TMP/SHASUMS256.txt"
  FILE="$(grep -o "node-v[0-9.]*-${OS}-${ARCH}\.tar\.gz" "$TMP/SHASUMS256.txt" | head -1)"
  curl -fsSL "$BASE/$FILE" -o "$TMP/$FILE"
  (cd "$TMP" && grep " $FILE\$" SHASUMS256.txt | shasum -a 256 -c - >/dev/null)
  mkdir -p "$TOOLS/node" && tar -xzf "$TMP/$FILE" -C "$TOOLS/node" --strip-components=1
  rm -rf "$TMP"
fi

if [ ! -d "$ROOT/.venv" ]; then
  echo "[bootstrap] creando entorno Python 3.12 (.venv)"
  (cd "$ROOT" && uv venv --python 3.12 .venv >/dev/null)
fi
echo "[bootstrap] sincronizando dependencias Python"
(cd "$ROOT" && uv pip install --python .venv/bin/python -q -r requirements.txt)

if [ ! -x "$BIN/ffmpeg" ]; then
  echo "[bootstrap] enlazando ffmpeg estático"
  FF="$("$ROOT/.venv/bin/python" -c 'import imageio_ffmpeg;print(imageio_ffmpeg.get_ffmpeg_exe())')"
  ln -sf "$FF" "$BIN/ffmpeg"
fi

if [ -f "$ROOT/web/package.json" ] && [ ! -d "$ROOT/web/node_modules" ]; then
  echo "[bootstrap] instalando dependencias del frontend"
  (cd "$ROOT/web" && npm install --no-audit --no-fund --silent)
fi
echo "[bootstrap] listo: $(uv --version), node $(node --version), $(ffmpeg -version 2>/dev/null | head -1 | cut -d' ' -f1-3)"
