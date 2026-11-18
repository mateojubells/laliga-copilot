"""Generador de la base SQLite sintética de una temporada de LaLiga (por defecto la activa, seasons.current()).

    .venv/bin/python -m data.synth.generate [--season 2024-25] [--seed 20240831] [--out data/synth/out/laliga-<t>.sqlite]
                                            [--rounds 1-4]

Necesita las plantillas (data/rosters/<t>.json) y los resultados (data/real/es.1.<t>.json) de la temporada. Lo que es
específico de un partido con verdad de campo (eval/gold/barca-valladolid.truth.json) solo se aplica si ese partido
existe en la temporada.

El marcador de cada partido es el REAL (openfootball); todo lo demás (alineaciones, eventos con coordenadas, xG,
tarjetas...) es ficticio y reproducible bit a bit con la misma semilla. La tabla `meta` lleva synthetic=1.
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from copilot import seasons  # noqa: E402
from copilot.data.openfootball import OpenFootballProvider, resolve_team, team_index  # noqa: E402
from copilot.data.synthetic import sources_hash  # noqa: E402
from data.synth import lineups as L  # noqa: E402
from data.synth import model as M  # noqa: E402
from data.synth.matchsim import Ctx, simulate_match  # noqa: E402

VERSION = "1.0"
DEFAULT_SEED = 20240831
TRUTH = ROOT / "eval" / "gold" / "barca-valladolid.truth.json"

#: calibración del volumen de tiros (ver README en el docstring de model): xG medio de gol y de tiro sin gol
GOAL_XG = 0.192
NG_XG = 0.0826
NG_SCALE = 1.0

SCHEMA = """
CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE matches (id TEXT PRIMARY KEY, season TEXT, round INTEGER, date TEXT, home TEXT, away TEXT,
  home_goals INTEGER, away_goals INTEGER, ht_home INTEGER, ht_away INTEGER, ht_real INTEGER, added1 INTEGER,
  added2 INTEGER, formation_home TEXT, formation_away TEXT);
CREATE TABLE players (id TEXT PRIMARY KEY, team TEXT, name TEXT, known_as TEXT, number INTEGER, position TEXT,
  line TEXT, foot TEXT);
CREATE TABLE lineups (match TEXT, round INTEGER, team TEXT, player TEXT, slot TEXT, side TEXT, started INTEGER,
  minute_in INTEGER, minute_out INTEGER, minutes INTEGER, t_on INTEGER, t_off INTEGER, number INTEGER,
  PRIMARY KEY (match, player));
CREATE TABLE events (id INTEGER PRIMARY KEY, match TEXT, round INTEGER, team TEXT, player TEXT, period INTEGER,
  minute INTEGER, added INTEGER, second INTEGER, t INTEGER, type TEXT, x REAL, y REAL, end_x REAL, end_y REAL,
  outcome TEXT, receiver TEXT, xg REAL, key_pass INTEGER, assist INTEGER, body TEXT, detail TEXT, link INTEGER);
"""
INDEXES = """
CREATE INDEX ix_ev_match ON events(match, type);
CREATE INDEX ix_ev_player ON events(player, type);
CREATE INDEX ix_ev_team ON events(team, type);
CREATE INDEX ix_ev_type ON events(type, round);
CREATE INDEX ix_lu_player ON lineups(player);
CREATE INDEX ix_lu_match ON lineups(match);
"""


def logical_date(season: str) -> str:
    """Fecha lógica de los datos: fin de la temporada (25 de mayo del año de cierre; no depende del reloj)."""
    return f"{int(season[:4]) + 1}-05-25"


def default_out(season: str | None = None) -> Path:
    return seasons.synth_db(season or seasons.current())


def parse_rounds(spec: str | None, all_rounds: list[int]) -> list[int]:
    if not spec:
        return all_rounds
    out: set[int] = set()
    for part in spec.split(","):
        if "-" in part:
            a, b = part.split("-")
            out |= set(range(int(a), int(b) + 1))
        else:
            out.add(int(part))
    return sorted(r for r in out if r in all_rounds)


def build_ctx(seed: int, season: str):
    roster = json.loads(seasons.roster_path(season).read_text(encoding="utf-8"))
    rosters = {t["id"]: t["players"] for t in roster["teams"]}
    attrs = {p["id"]: M.Attr(seed, p["id"], p.get("number"), p["line"]) for ps in rosters.values() for p in ps}
    of = OpenFootballProvider()
    matches = [m for m in of.matches(season) if m.home_goals is not None]  # los no jugados aún no tienen eventos
    if not matches:
        raise SystemExit(f"la temporada {season} no tiene ningún partido con resultado")
    table = of.standings(season)
    pts = np.array([r.points for r in table], float)
    gf = np.array([r.gf for r in table], float)
    ga = np.array([r.ga for r in table], float)
    strength = {r.team: dict(z=float((r.points - pts.mean()) / (pts.std() or 1.0)), att=float(r.gf / gf.mean()),
                             dfn=float(r.ga / ga.mean())) for r in table}
    tidx = {t: i for i, t in enumerate(sorted(rosters))}
    truth = json.loads(TRUTH.read_text(encoding="utf-8")) if TRUTH.exists() else None
    if truth and truth["match"] not in {m.id for m in matches}:  # el partido con verdad de campo no es de esta temporada
        truth = None
    cal = M.calibrate()
    g_tot = sum(m.home_goals + m.away_goals for m in matches if m.home_goals is not None)
    pen_miss_xg = 0.03 * 2 * len(matches) * M.PENALTY_XG
    n_ng_total = max(0.0, (g_tot * (1 - GOAL_XG) - pen_miss_xg) / NG_XG)
    b_ng = n_ng_total / (2 * len(matches)) * NG_SCALE
    ctx = Ctx(seed, rosters, attrs, strength, tidx, truth, cal, b_ng)
    return ctx, matches, roster


def _objcol(a):
    return a.tolist()


def _nan_none(a):
    o = a.astype(object)
    o[np.isnan(a)] = None
    return o.tolist()


def generate(seed: int = DEFAULT_SEED, out: Path | str | None = None, rounds: str | None = None,
             verbose: bool = True, season: str | None = None) -> Path:
    t0 = time.time()
    season = season or seasons.current()
    if season not in seasons.installed():
        raise SystemExit(f"temporada {season} no instalada (faltan plantillas en {seasons.roster_path(season)}); "
                         "ver docs/DATA_IMPORT.md")
    if not seasons.results_path(season).exists():
        raise SystemExit(f"temporada {season} sin resultados ({seasons.results_path(season)}); "
                         "ver docs/DATA_IMPORT.md")
    out = Path(out) if out else default_out(season)
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    if tmp.exists():
        tmp.unlink()
    ctx, matches, roster = build_ctx(seed, season)
    ht_real = {}
    raw = json.loads(seasons.results_path(season).read_text(encoding="utf-8"))["matches"]
    index = team_index(season)
    for r in raw:
        ht = (r.get("score") or {}).get("ht")
        if ht:
            ht_real[(resolve_team(r["team1"], season, index), resolve_team(r["team2"], season, index))] = ht
    all_rounds = sorted({m.round for m in matches})
    sel = set(parse_rounds(rounds, all_rounds))
    conn = sqlite3.connect(str(tmp))
    conn.executescript(SCHEMA)
    conn.executemany("INSERT INTO players VALUES (?,?,?,?,?,?,?,?)",
                     [(p["id"], t["id"], p["name"], p["known_as"], p.get("number"), p["position"], p["line"],
                       p.get("foot", "R")) for t in roster["teams"] for p in t["players"]])
    next_id = 1
    nm = 0
    for m in matches:
        if m.round not in sel:
            continue
        ht = ht_real.get((m.home, m.away))
        md = dict(id=m.id, round=m.round, home=m.home, away=m.away, home_goals=m.home_goals, away_goals=m.away_goals,
                  ht_home=ht[0] if ht else None, ht_away=ht[1] if ht else None)
        lus, cols, a1, a2, S = simulate_match(ctx, md)
        # --- eventos ordenados cronológicamente
        order = np.lexsort((cols["lid"], cols["t"]))
        n = len(order)
        rank = np.empty(n, np.int64)
        rank[order] = np.arange(n)
        c = {k: v[order] for k, v in cols.items()}
        link = np.where(c["link"] >= 0, rank[np.maximum(c["link"], 0)] + next_id, 0)
        per, mi, ad, sec = L.display_from_t(c["t"], a1)
        ids = np.arange(next_id, next_id + n)
        rows = zip(ids.tolist(), [m.id] * n, [m.round] * n, c["team"].tolist(), c["player"].tolist(), per.tolist(),
                   mi.tolist(), ad.tolist(), sec.tolist(), c["t"].tolist(), c["type"].tolist(), _nan_none(c["x"]),
                   _nan_none(c["y"]), _nan_none(c["ex"]), _nan_none(c["ey"]), c["outcome"].tolist(),
                   c["receiver"].tolist(), _nan_none(c["xg"]), c["key"].tolist(), c["assist"].tolist(),
                   c["body"].tolist(), c["detail"].tolist(), [None if v == 0 else v for v in link.tolist()])
        conn.executemany("INSERT INTO events VALUES (" + ",".join("?" * 23) + ")", rows)
        next_id += n
        # --- partido y alineaciones
        conn.execute("INSERT INTO matches VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                     (m.id, season, m.round, m.date, m.home, m.away, m.home_goals, m.away_goals,
                      S.ht[m.home], S.ht[m.away], 1 if ht else 0, a1, a2,
                      lus[m.home].formation, lus[m.away].formation))
        lrows = []
        for tm, lu in lus.items():
            benchset = set(lu.bench)
            for k, mem in enumerate(lu.members):
                if mem.t_on < 0 and k not in benchset:
                    continue
                played = mem.t_on >= 0
                lrows.append((m.id, m.round, tm, mem.p["id"], mem.pos if played else None,
                              M.FORMATIONS[lu.formation][mem.slot][1] if played else None, int(mem.started),
                              mem.min_in if played else None, mem.min_out if played else None,
                              (mem.min_out - mem.min_in) if played else 0, mem.t_on if played else None,
                              mem.t_off if played else None, mem.p.get("number")))
        conn.executemany("INSERT INTO lineups VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", lrows)
        nm += 1
        if verbose and nm % 38 == 0:
            print(f"  {nm} partidos, {next_id - 1} eventos, {time.time() - t0:.0f}s", flush=True)
    conn.executemany("INSERT INTO meta VALUES (?,?)", [
        ("seed", str(seed)), ("version", VERSION), ("logical_date", logical_date(season)), ("synthetic", "1"),
        ("season", season), ("rounds", ",".join(str(r) for r in sorted(sel))), ("n_matches", str(nm)),
        ("generator", "data.synth.generate"), ("sources_hash", sources_hash(season)),
        ("notice", "Datos de demostración: marcadores reales (openfootball); alineaciones y eventos ficticios")])
    conn.executescript(INDEXES)
    conn.commit()
    from copilot.data.synthetic import build_derived
    build_derived(conn)
    conn.commit()
    conn.execute("VACUUM")
    conn.close()
    if out.exists():
        out.unlink()
    tmp.rename(out)
    if verbose:
        print(f"OK {out} ({out.stat().st_size / 1e6:.1f} MB, {next_id - 1} eventos, {time.time() - t0:.1f}s)")
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", type=int, default=DEFAULT_SEED)
    ap.add_argument("--season", default=None, help="temporada instalada (por defecto la activa)")
    ap.add_argument("--out", default=None, help="por defecto data/synth/out/laliga-<temporada>.sqlite")
    ap.add_argument("--rounds", default=None, help="p. ej. 1-4 o 1,5,7-9 (por defecto, las 38)")
    a = ap.parse_args(argv)
    generate(a.seed, a.out, a.rounds, season=a.season)


if __name__ == "__main__":
    main()
