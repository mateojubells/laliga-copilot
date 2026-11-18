"""Ayudas para las pruebas: base completa reutilizable y generación de subconjuntos."""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from copilot.data.synthetic import sources_hash  # noqa: E402
from data.synth.generate import DEFAULT_SEED, default_out, generate  # noqa: E402

DEFAULT_OUT = default_out()  # base de la temporada activa

_FULL: Path | None = None


def full_db() -> Path:
    """Base completa con la semilla por defecto: reutiliza data/synth/out solo si coinciden semilla, nº de partidos y
    hash de las fuentes del generador (meta.sources_hash); si no, la regenera ahí."""
    global _FULL
    if _FULL is not None:
        return _FULL
    ok = False
    if DEFAULT_OUT.exists():
        try:
            c = sqlite3.connect(f"file:{DEFAULT_OUT}?mode=ro", uri=True)
            meta = dict(c.execute("SELECT key, value FROM meta"))
            ok = (meta.get("seed") == str(DEFAULT_SEED) and meta.get("n_matches") == "380"
                  and meta.get("sources_hash") == sources_hash()
                  and c.execute("SELECT 1 FROM sqlite_master WHERE name='pms'").fetchone() is not None
                  and "side" in [r[1] for r in c.execute("PRAGMA table_info(lineups)")])
            c.close()
        except sqlite3.Error:
            ok = False
    if not ok:
        generate(DEFAULT_SEED, DEFAULT_OUT, None, verbose=False)
    _FULL = DEFAULT_OUT
    return _FULL


def connect(path: Path | None = None) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path or full_db()}?mode=ro", uri=True)


_SEEDS: dict[int, Path] = {}


def seed_db(seed: int, directory: Path) -> Path:
    """Base completa de otra semilla, generada en `directory` (una vez por proceso)."""
    if seed == DEFAULT_SEED:
        return full_db()
    if seed not in _SEEDS:
        _SEEDS[seed] = generate(seed, Path(directory) / f"seed{seed}.sqlite", None, verbose=False)
    return _SEEDS[seed]
