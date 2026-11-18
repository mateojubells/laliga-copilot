"""Registro único de temporadas y de dónde vive cada dato (docs/LIVE_READINESS.md §2.6).

Una temporada está "instalada" si existe su fichero de plantillas `data/rosters/<temporada>.json`. Opcionalmente tiene
resultados reales (`data/real/es.1.<temporada>.json`) y estadísticas de demostración
(`data/synth/out/laliga-<temporada>.sqlite`). Ningún otro módulo debe escribir rutas ni temporadas a mano.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parents[1]
ROSTERS = ROOT / "data" / "rosters"
REAL = ROOT / "data" / "real"
SYNTH = ROOT / "data" / "synth" / "out"
MATCHES = ROOT / "data" / "matches"
SESSIONS = ROOT / "data" / "sessions"
_SEASON_RE = re.compile(r"^\d{4}-\d{2}$")


def roster_path(season: str) -> Path:
    return ROSTERS / f"{season}.json"


def results_path(season: str) -> Path:
    return REAL / f"es.1.{season}.json"


def synth_db(season: str) -> Path:
    return SYNTH / f"laliga-{season}.sqlite"


def lineup_path(match_id: str) -> Path:
    return MATCHES / (match_id.replace("/", "-") + ".json")


def season_of(match_id: str) -> str:
    return match_id.split("/")[0]


def installed() -> list[str]:
    """Temporadas con plantillas, de la más reciente a la más antigua."""
    return sorted((p.stem for p in ROSTERS.glob("*.json") if _SEASON_RE.match(p.stem)), reverse=True)


def results_seasons() -> list[str]:
    """Temporadas con resultados reales descargados (sirven también para el cara a cara histórico)."""
    out = []
    for p in REAL.glob("es.1.*.json"):
        s = p.name[len("es.1."):-len(".json")]
        if _SEASON_RE.match(s):
            out.append(s)
    return sorted(out)


def current(cfg: Optional[dict] = None) -> str:
    """Temporada activa: la de la sesión/configuración si está instalada; si no, la más reciente instalada."""
    from copilot.config import settings
    cfg = cfg if cfg is not None else settings()
    want = cfg.get("season") or season_of(cfg.get("match", ""))
    seasons = installed()
    if want in seasons:
        return want
    if not seasons:
        raise RuntimeError("No hay ninguna temporada instalada en data/rosters/ (ver docs/DATA_IMPORT.md)")
    return seasons[0]


@dataclass
class SeasonInfo:
    season: str
    teams: int
    players: int
    has_results: bool
    has_stats: bool


def info(season: str) -> SeasonInfo:
    import json
    d = json.loads(roster_path(season).read_text(encoding="utf-8"))
    return SeasonInfo(season=season, teams=len(d["teams"]), players=sum(len(t["players"]) for t in d["teams"]),
                      has_results=results_path(season).exists(), has_stats=synth_db(season).exists())
