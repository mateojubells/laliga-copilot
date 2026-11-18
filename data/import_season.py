"""Importador de temporadas: valida e instala plantillas y resultados de una temporada de LaLiga.

    .venv/bin/python -m data.import_season --season 2025-26 [--rosters FICHERO.json] [--results FICHERO.json]
                                           [--fetch] [--no-stats]

* `--rosters`: plantillas en el formato de data/rosters/2024-25.json (ver docs/DATA_IMPORT.md).
* `--results`: resultados en el formato openfootball (data/real/es.1.2024-25.json).
* `--fetch`: descarga los resultados de openfootball/football.json (gratis, sin clave).
* Sin `--no-stats` genera las estadísticas de demostración (data.synth.generate --season).

Todo se valida ANTES de escribir nada: si hay un error no se instala nada y se imprime la ruta de cada fallo.
Es idempotente: volver a ejecutarlo con los mismos ficheros deja el mismo resultado.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from pydantic import ValidationError  # noqa: E402

from copilot import seasons  # noqa: E402
from copilot.data.openfootball import index_from_roster, resolve_team  # noqa: E402
from copilot.types import Player, Team  # noqa: E402

FETCH_URL = "https://raw.githubusercontent.com/openfootball/football.json/master/{season}/es.1.json"
LINE_OF = {"GK": "GK", "RB": "DEF", "CB": "DEF", "LB": "DEF", "DM": "MID", "CM": "MID", "AM": "MID",
           "RW": "FWD", "LW": "FWD", "ST": "FWD"}
MIN_PLAYERS, MIN_GK = 11, 2
_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_ROUND = re.compile(r"^Matchday \d+$")


class ImportFailed(Exception):
    """La validación o la instalación falló; `errors` lleva un mensaje por problema (con su ruta)."""

    def __init__(self, errors: list[str]):
        super().__init__("\n".join(errors))
        self.errors = errors


@dataclass
class Summary:
    season: str
    teams: int = 0
    players: int = 0
    matches: int = 0
    played: int = 0
    stats: bool = False
    stats_path: Optional[Path] = None
    notes: list[str] = field(default_factory=list)

    def text(self) -> str:
        return (f"Temporada {self.season} instalada\n"
                f"  equipos:        {self.teams}\n  jugadores:      {self.players}\n"
                f"  partidos:       {self.matches} ({self.played} con resultado)\n"
                f"  estadísticas:   {'sí (' + str(self.stats_path) + ')' if self.stats else 'no'}"
                + "".join(f"\n  nota: {n}" for n in self.notes))


# ------------------------------------------------------------------ validación
def validate_season_name(season: str) -> list[str]:
    m = re.fullmatch(r"(\d{4})-(\d{2})", season or "")
    if not m:
        return [f"--season {season!r}: formato AAAA-AA (p. ej. 2025-26)"]
    if (int(m.group(1)) + 1) % 100 != int(m.group(2)):
        return [f"--season {season!r}: los años no son consecutivos (¿{m.group(1)}-{(int(m.group(1)) + 1) % 100:02d}?)"]
    return []


def _pyd(path: str, err: ValidationError) -> list[str]:
    out = []
    for e in err.errors():
        loc = ".".join(str(x) for x in e["loc"])
        out.append(f"{path}{'.' + loc if loc else ''}: {e['msg']} (valor: {e.get('input')!r})"[:300])
    return out


def validate_rosters(d: object, season: str) -> list[str]:
    """Lista de errores (vacía = válido). Cada mensaje empieza por la ruta del fallo: teams[3].players[7]..."""
    if not isinstance(d, dict) or not isinstance(d.get("teams"), list) or not d["teams"]:
        return ["rosters: se esperaba un objeto con una lista `teams` no vacía"]
    errs: list[str] = []
    if "season" in d and d["season"] != season:
        errs.append(f"rosters.season: es {d['season']!r} pero se importa {season!r}")
    team_ids: set[str] = set()
    player_ids: set[str] = set()
    for i, t in enumerate(d["teams"]):
        base = f"teams[{i}]"
        if not isinstance(t, dict):
            errs.append(f"{base}: se esperaba un objeto")
            continue
        tid = t.get("id")
        base = f"teams[{i}] (id={tid})"
        try:
            Team(**{k: v for k, v in t.items() if k != "players"})
        except ValidationError as e:
            errs += _pyd(base, e)
        except TypeError as e:
            errs.append(f"{base}: {e}")
        if isinstance(tid, str):
            if not _SLUG.match(tid):
                errs.append(f"{base}.id: debe ser un slug en minúsculas (a-z, 0-9 y guiones), p. ej. 'real-madrid'")
            if tid in team_ids:
                errs.append(f"{base}.id: duplicado")
            team_ids.add(tid)
        players = t.get("players")
        if not isinstance(players, list):
            errs.append(f"{base}.players: se esperaba una lista")
            continue
        gk, numbers = 0, {}
        for j, p in enumerate(players):
            pb = f"{base}.players[{j}]"
            if not isinstance(p, dict):
                errs.append(f"{pb}: se esperaba un objeto")
                continue
            pid = p.get("id")
            pb = f"{pb} (id={pid})"
            try:
                Player(**p)
            except ValidationError as e:
                errs += _pyd(pb, e)
            except TypeError as e:
                errs.append(f"{pb}: {e}")
            if isinstance(pid, str):
                if not re.fullmatch(r"[a-z0-9-]+/[a-z0-9-]+", pid):
                    errs.append(f"{pb}.id: formato 'equipo/slug' (minúsculas, sin acentos ni espacios)")
                elif isinstance(tid, str) and pid.split("/")[0] != tid:
                    errs.append(f"{pb}.id: el prefijo debe ser el id de su equipo ('{tid}/...')")
                if pid in player_ids:
                    errs.append(f"{pb}.id: duplicado")
                player_ids.add(pid)
            if isinstance(tid, str) and p.get("team") != tid:
                errs.append(f"{pb}.team: es {p.get('team')!r}, debería ser {tid!r}")
            pos, line = p.get("position"), p.get("line")
            if pos in LINE_OF and line in ("GK", "DEF", "MID", "FWD") and LINE_OF[pos] != line:
                errs.append(f"{pb}.line: {line!r} no es coherente con position {pos!r} (debería ser {LINE_OF[pos]!r})")
            gk += pos == "GK"
            n = p.get("number")
            if isinstance(n, int):
                if n in numbers:
                    errs.append(f"{pb}.number: el dorsal {n} ya lo lleva {numbers[n]}")
                numbers[n] = pid
        if len(players) < MIN_PLAYERS:
            errs.append(f"{base}.players: {len(players)} jugadores, mínimo {MIN_PLAYERS}")
        if gk < MIN_GK:
            errs.append(f"{base}.players: {gk} porteros (position GK), mínimo {MIN_GK}")
    return errs


def validate_results(d: object, roster: dict) -> tuple[list[str], int, int]:
    """(errores, partidos, partidos con resultado). Todos los equipos deben existir en las plantillas (id o alias)."""
    if not isinstance(d, dict) or not isinstance(d.get("matches"), list) or not d["matches"]:
        return ["results: se esperaba un objeto con una lista `matches` no vacía (formato openfootball)"], 0, 0
    index = index_from_roster(roster)
    ids = {t["id"] for t in roster["teams"]}
    errs: list[str] = []
    unknown: dict[str, list[int]] = {}
    seen: set[tuple[str, str]] = set()
    played = 0
    for i, m in enumerate(d["matches"]):
        base = f"matches[{i}]"
        if not isinstance(m, dict):
            errs.append(f"{base}: se esperaba un objeto")
            continue
        for k in ("round", "date", "team1", "team2"):
            if not isinstance(m.get(k), str) or not m[k]:
                errs.append(f"{base}.{k}: falta o no es texto")
        if isinstance(m.get("round"), str) and not _ROUND.match(m["round"]):
            errs.append(f"{base}.round: {m['round']!r} no tiene el formato 'Matchday N'")
        if isinstance(m.get("date"), str) and not re.fullmatch(r"\d{4}-\d{2}-\d{2}", m["date"]):
            errs.append(f"{base}.date: {m['date']!r} no es AAAA-MM-DD")
        ft = (m.get("score") or {}).get("ft") if isinstance(m.get("score") or {}, dict) else None
        if ft is not None:
            if not (isinstance(ft, list) and len(ft) == 2 and all(isinstance(x, int) and x >= 0 for x in ft)):
                errs.append(f"{base}.score.ft: se esperaba [goles_local, goles_visitante] (enteros >= 0), hay {ft!r}")
            else:
                played += 1
        teams = []
        for k in ("team1", "team2"):
            name = m.get(k)
            if isinstance(name, str):
                tid = resolve_team(name, None, index)
                if tid is None or tid not in ids:
                    unknown.setdefault(name, []).append(i)
                teams.append(tid)
        if len(teams) == 2 and None not in teams:
            if teams[0] == teams[1]:
                errs.append(f"{base}: {m['team1']!r} juega contra sí mismo")
            if tuple(teams) in seen:
                errs.append(f"{base}: partido repetido {m['team1']} - {m['team2']}")
            seen.add(tuple(teams))  # type: ignore[arg-type]
    for name, where in sorted(unknown.items()):
        errs.append(f"equipo sin plantilla: {name!r} (matches[{where[0]}].team1/team2"
                    f"{', +%d más' % (len(where) - 1) if len(where) > 1 else ''}); añádelo a las plantillas o "
                    f"pon ese nombre en `name`, `short` o `aliases` de su equipo")
    return errs, len(d["matches"]), played


# ------------------------------------------------------------------ E/S
def _read_json(path: Path, what: str) -> object:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ImportFailed([f"{what}: no existe {path}"])
    except json.JSONDecodeError as e:
        raise ImportFailed([f"{what} ({path}): JSON inválido en la línea {e.lineno}, columna {e.colno}: {e.msg}"])


def _write_atomic(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, path)


def fetch_results(season: str, opener: Callable = urllib.request.urlopen) -> dict:
    """Descarga es.1.json de openfootball para la temporada (sin clave)."""
    url = FETCH_URL.format(season=season)
    try:
        with opener(url, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except Exception as e:  # red, 404 (la temporada no existe en openfootball), JSON
        raise ImportFailed([f"--fetch: no se pudo descargar {url}: {e}"])


NO_ROSTERS_HELP = (
    "No hay plantillas de {season}: {path} no existe y no se pasó --rosters.\n"
    "  Crea el fichero con el formato de data/rosters/2024-25.json (ver docs/DATA_IMPORT.md) y vuelve a ejecutar con\n"
    "  --rosters FICHERO.json. Puedes partir de la plantilla anterior y editarla (altas, bajas, dorsales).\n"
    "  data/rosters/build_rosters.py NO sirve para otra temporada: está hecho a mano para 2024-25 (páginas de\n"
    "  Wikipedia con formatos distintos por club, tablas de posiciones, pies y apodos curados).")


def import_season(season: str, *, rosters: Path | str | None = None, results: Path | str | None = None,
                  fetch: bool = False, stats: bool = True, out: Callable[[str], None] = print,
                  opener: Callable = urllib.request.urlopen) -> Summary:
    errs = validate_season_name(season)
    if errs:
        raise ImportFailed(errs)
    if results and fetch:
        raise ImportFailed(["--results y --fetch son excluyentes"])

    # 1. plantillas: las del fichero o las ya instaladas
    rpath = seasons.roster_path(season)
    if rosters:
        roster = _read_json(Path(rosters), "rosters")
        errs = validate_rosters(roster, season)
        if errs:
            raise ImportFailed([f"rosters ({rosters}): {e}" for e in errs])
        roster = {"season": season, **{k: v for k, v in roster.items() if k != "season"}}  # type: ignore[union-attr]
    elif rpath.exists():
        roster = _read_json(rpath, "rosters")
        errs = validate_rosters(roster, season)
        if errs:
            raise ImportFailed([f"rosters ({rpath}): {e}" for e in errs])
    else:
        raise ImportFailed([NO_ROSTERS_HELP.format(season=season, path=rpath)])

    # 2. resultados: fichero, descarga o los ya instalados
    res_text: Optional[str] = None
    res_n = res_played = 0
    summary = Summary(season)
    if fetch:
        out(f"Descargando {FETCH_URL.format(season=season)} ...")
        raw = fetch_results(season, opener)
        res_text = json.dumps(raw, ensure_ascii=False, indent=2) + "\n"
    elif results:
        rp = Path(results)
        _read_json(rp, "results")
        res_text = rp.read_text(encoding="utf-8")
    if res_text is not None:
        errs, res_n, res_played = validate_results(json.loads(res_text), roster)  # type: ignore[arg-type]
        if errs:
            raise ImportFailed([f"results: {e}" for e in errs])
    elif seasons.results_path(season).exists():
        errs, res_n, res_played = validate_results(_read_json(seasons.results_path(season), "results"), roster)  # type: ignore[arg-type]
        if errs:
            raise ImportFailed([f"results ({seasons.results_path(season)}): {e}" for e in errs])
    else:
        summary.notes.append("sin resultados: no hay clasificación ni estadísticas de demostración "
                             "(usa --results FICHERO o --fetch)")

    # 3. instalar (todo validado)
    if rosters:
        _write_atomic(rpath, json.dumps(roster, ensure_ascii=False, indent=1) + "\n")
        out(f"Plantillas instaladas: {rpath}")
    if res_text is not None:
        dest = seasons.results_path(season)
        if not (dest.exists() and dest.read_text(encoding="utf-8") == res_text):
            _write_atomic(dest, res_text)
        out(f"Resultados instalados: {dest}")
    _clear_caches()

    # 4. estadísticas de demostración
    if stats and res_n:
        from data.synth.generate import generate
        out(f"Generando estadísticas de demostración de {season} (tarda un rato)...")
        summary.stats_path = generate(season=season, verbose=False)
        summary.stats = True
    elif stats and not res_n:
        summary.notes.append("estadísticas no generadas: faltan resultados")
    else:
        summary.stats = seasons.synth_db(season).exists()
        summary.stats_path = seasons.synth_db(season) if summary.stats else None
        if summary.stats:
            summary.notes.append("estadísticas ya existentes (no se regeneran con --no-stats)")

    summary.teams = len(roster["teams"])  # type: ignore[index]
    summary.players = sum(len(t["players"]) for t in roster["teams"])  # type: ignore[index]
    summary.matches, summary.played = res_n, res_played
    if season not in seasons.installed():  # no debería ocurrir
        raise ImportFailed([f"{season} no aparece en seasons.installed() tras instalar"])
    if len(roster["teams"]) != 20:  # type: ignore[index]
        summary.notes.append(f"{len(roster['teams'])} equipos (Primera tiene 20)")  # type: ignore[index]
    return summary


def _clear_caches() -> None:
    """Si el importador se usa dentro de un proceso con motor/diccionarios cargados, que los rehaga."""
    from copilot.nlu import engine, gazetteer
    gazetteer.clear_caches()
    engine.clear_caches()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Valida e instala una temporada (plantillas, resultados y estadísticas).")
    ap.add_argument("--season", required=True, help="AAAA-AA, p. ej. 2025-26")
    ap.add_argument("--rosters", help="fichero de plantillas (formato data/rosters/2024-25.json)")
    ap.add_argument("--results", help="fichero de resultados (formato openfootball es.1.json)")
    ap.add_argument("--fetch", action="store_true", help="descargar los resultados de openfootball/football.json")
    ap.add_argument("--no-stats", action="store_true", help="no generar las estadísticas de demostración")
    a = ap.parse_args(argv)
    try:
        s = import_season(a.season, rosters=a.rosters, results=a.results, fetch=a.fetch, stats=not a.no_stats)
    except ImportFailed as e:
        print(f"No se instaló nada. {len(e.errors)} problema(s):", file=sys.stderr)
        for m in e.errors:
            print(f"  - {m}", file=sys.stderr)
        return 1
    print(s.text())
    return 0


if __name__ == "__main__":
    sys.exit(main())
