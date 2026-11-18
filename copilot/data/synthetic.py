"""Proveedor de datos de demostración: lee el SQLite generado por data/synth/generate.py.

Todos los agregados se calculan desde la tabla `events` (más `lineups` para minutos/titularidades). La tabla `pms`
(estadísticas por partido y jugador) es DERIVADA: se recalcula con build_derived() desde events y, si falta, se
crea en memoria al abrir. Ninguna cifra de temporada se guarda aparte.

Cada instancia atiende UNA temporada (`season`, por defecto la de la base o seasons.current()); la base por defecto es
seasons.synth_db(season). `until`: id de partido ("2024-25/J04/barcelona-valladolid") o nº de jornada; solo cuenta lo ocurrido en jornadas
ESTRICTAMENTE anteriores (until=4 -> J1-J3). `standings(until_round=N)` es inclusivo (clasificación tras N jornadas).

Definición de "touches": pases + pases recibidos (completos) + tiros + regates + recuperaciones + intercepciones +
despejes + paradas. "shots_on_target": tiros con resultado goal o saved. "pass_pct": 0-100.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import warnings
from pathlib import Path
from typing import Optional

import numpy as np

from copilot import seasons
from copilot.data.openfootball import (ROOT, OpenFootballProvider, compute_standings, load_roster_teams,
                                       parse_until)
from copilot.types import (H2H, Connection, MatchInfo, PassEdge, PassNetwork, PassNode, PitchEvent, Player,
                           PlayerSeason, StandingRow, StatValue, Team, TeamSeason)

MIN_MINUTES_SHARE = 0.30


#: fuentes cuyo contenido determina los datos generados (se guarda su hash en meta.sources_hash)
_HASHED_SYNTH = ("generate.py", "lineups.py", "matchsim.py", "model.py")


def sources_hash(season: Optional[str] = None) -> str:
    """Hash del código del generador + plantillas y resultados de LA temporada + verdad de campo (si es de ella)."""
    season = season or seasons.current()
    files = [ROOT / "data" / "synth" / n for n in _HASHED_SYNTH]
    files.append(seasons.roster_path(season))
    files.append(seasons.results_path(season))
    files.append(seasons.REAL / f"es.1.{season}.supplement.json")
    files.append(ROOT / "eval" / "gold" / "barca-valladolid.truth.json")
    files.append(ROOT / "copilot" / "data" / "openfootball.py")
    h = hashlib.sha256()
    for f in files:
        h.update(f.name.encode() + b"\0")
        h.update(f.read_bytes() if f.exists() else b"<missing>")
        h.update(b"\0")
    return h.hexdigest()[:16]


class SyntheticDataMissing(RuntimeError):
    """El SQLite sintético no existe: ejecuta `make data` (python -m data.synth.generate)."""


PMS_COLS = ["passes", "pass_ok", "key_passes", "assists", "shots", "sot", "goals", "xg", "dribbles", "dribbles_won",
            "recoveries", "tackles", "interceptions", "clearances", "fouls", "yellow", "red", "saves", "fouled",
            "received", "xa"]


def build_derived(conn: sqlite3.Connection, temp: bool = False) -> None:
    """(Re)calcula pms (jugador x partido) desde events."""
    pre = "TEMP " if temp else ""
    if not temp:
        conn.execute("DROP TABLE IF EXISTS pms")
    conn.execute(f"CREATE {pre}TABLE pms (match TEXT, round INTEGER, team TEXT, player TEXT, "
                 + ", ".join(f"{c} REAL" for c in PMS_COLS) + ", PRIMARY KEY(match, player))")
    acc: dict[tuple, dict] = {}

    def row(m, r, t, p):
        k = (m, p)
        if k not in acc:
            acc[k] = dict(round=r, team=t, **{c: 0.0 for c in PMS_COLS})
        return acc[k]

    q = """SELECT match, round, team, player,
      SUM(type='pass'), SUM(type='pass' AND outcome='complete'), SUM(type='pass' AND key_pass=1),
      SUM(type='pass' AND assist=1), SUM(type='shot'), SUM(type='shot' AND outcome IN ('goal','saved')),
      SUM(type='shot' AND outcome='goal'), SUM(CASE WHEN type='shot' THEN xg ELSE 0 END), SUM(type='dribble'),
      SUM(type='dribble' AND outcome='won'), SUM(type='recovery'), SUM(type='tackle'), SUM(type='interception'),
      SUM(type='clearance'), SUM(type='foul'), SUM(type='card' AND detail='yellow'),
      SUM(type='card' AND detail='red'), SUM(type='save')
      FROM events WHERE type != 'sub' GROUP BY match, player"""
    names = ["passes", "pass_ok", "key_passes", "assists", "shots", "sot", "goals", "xg", "dribbles", "dribbles_won",
             "recoveries", "tackles", "interceptions", "clearances", "fouls", "yellow", "red", "saves"]
    for r in conn.execute(q):
        d = row(r[0], r[1], r[2], r[3])
        for n, v in zip(names, r[4:]):
            d[n] = float(v or 0)
    tm = {(m, p): t for m, p, t in conn.execute("SELECT match, player, team FROM lineups")}
    rnd = {m: r for m, r in conn.execute("SELECT id, round FROM matches")}
    for col, sql in (("fouled", "SELECT match, receiver, COUNT(*) FROM events WHERE type='foul' GROUP BY match, receiver"),
                     ("received", "SELECT match, receiver, COUNT(*) FROM events WHERE type='pass' AND outcome='complete' "
                                  "GROUP BY match, receiver"),
                     ("xa", "SELECT k.match, k.player, SUM(s.xg) FROM events k JOIN events s ON s.link = k.id "
                            "WHERE k.key_pass=1 AND s.type='shot' GROUP BY k.match, k.player")):
        for m, p, v in conn.execute(sql):
            d = row(m, rnd[m], tm.get((m, p)), p)
            d[col] = float(v or 0)
    conn.executemany(f"INSERT INTO pms VALUES (?,?,?,?," + ",".join("?" * len(PMS_COLS)) + ")",
                     [(m, d["round"], d["team"], p, *[d[c] for c in PMS_COLS]) for (m, p), d in sorted(acc.items())])
    if not temp:
        conn.execute("CREATE INDEX IF NOT EXISTS ix_pms_player ON pms(player, round)")
        conn.execute("CREATE INDEX IF NOT EXISTS ix_pms_team ON pms(team, round)")


STAT_ORDER = ["goals", "assists", "xg", "xa", "shots", "shots_on_target", "passes", "pass_pct", "key_passes",
              "dribbles", "dribbles_won", "recoveries", "tackles", "interceptions", "clearances", "fouls", "fouled",
              "yellow", "red", "saves", "touches"]


def _stats_from(r: dict) -> dict[str, float]:
    """r: sumas de pms -> estadísticas con nombre."""
    passes = r["passes"]
    return dict(
        goals=r["goals"], assists=r["assists"], xg=r["xg"], xa=r["xa"], shots=r["shots"], shots_on_target=r["sot"],
        passes=passes, pass_pct=(100.0 * r["pass_ok"] / passes) if passes else 0.0, key_passes=r["key_passes"],
        dribbles=r["dribbles"], dribbles_won=r["dribbles_won"], recoveries=r["recoveries"], tackles=r["tackles"],
        interceptions=r["interceptions"], clearances=r["clearances"], fouls=r["fouls"], fouled=r["fouled"],
        yellow=r["yellow"], red=r["red"], saves=r["saves"],
        touches=passes + r["received"] + r["shots"] + r["dribbles"] + r["recoveries"] + r["interceptions"]
        + r["clearances"] + r["saves"])


def _pct(pool: np.ndarray, v: float) -> int:
    n = len(pool)
    if n == 0:
        return -1
    lo = int(np.searchsorted(pool, v, "left"))
    hi = int(np.searchsorted(pool, v, "right"))
    return int(round(100.0 * (lo + 0.5 * (hi - lo)) / n))


class SyntheticProvider:
    synthetic = True

    def __init__(self, db_path: Path | str | None = None, season: Optional[str] = None):
        self._season = season
        self._db_path = Path(db_path) if db_path else None
        self._conn: Optional[sqlite3.Connection] = None
        self._lock = threading.RLock()
        self._cache: dict = {}
        self._real = OpenFootballProvider()
        self._roster: Optional[dict] = None

    # ------------------------------------------------------------- infraestructura
    @property
    def season(self) -> str:
        """Temporada que atiende: la indicada; si no, la que dice la base (meta.season); si no, seasons.current()."""
        if self._season is None:
            if self._db_path is not None and self._db_path.exists():
                try:
                    c = sqlite3.connect(f"file:{self._db_path}?mode=ro", uri=True)
                    try:
                        row = c.execute("SELECT value FROM meta WHERE key='season'").fetchone()
                    finally:
                        c.close()
                    if row:
                        self._season = row[0]
                except sqlite3.Error:
                    pass
            if self._season is None:
                self._season = seasons.current()
        return self._season

    @property
    def db_path(self) -> Path:
        return self._db_path or seasons.synth_db(self.season)

    def available(self) -> bool:
        return self.db_path.exists()

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            if not self.db_path.exists():
                raise SyntheticDataMissing(f"no existe {self.db_path}; ejecuta `make data`")
            c = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True, check_same_thread=False)
            has = c.execute("SELECT 1 FROM sqlite_master WHERE name='pms'").fetchone()
            if not has:
                build_derived(c, temp=True)
            self._conn = c
            self.stale_reason  # emite el aviso (RuntimeWarning) si la base es de otro código; no rompe el arranque
        return self._conn

    @property
    def stale_reason(self) -> Optional[str]:
        """None si la base se generó con el código/datos actuales; si no, el motivo (aviso, no error)."""
        if "stale" not in self._cache:
            reason = None
            if self.db_path.exists():
                got = self.meta().get("sources_hash")
                if got is None:
                    reason = "la base no registra el hash de las fuentes del generador; regenera con `make data`"
                elif got != sources_hash(self.season):
                    reason = (f"la base se generó con otro código/datos del generador ({got} != "
                              f"{sources_hash(self.season)}); "
                              "regenera con `make data`")
            self._cache["stale"] = reason
            if reason:
                warnings.warn(f"Datos de demostración obsoletos: {reason}", RuntimeWarning, stacklevel=2)
        return self._cache["stale"]

    @property
    def stale(self) -> bool:
        return self.stale_reason is not None

    def meta(self) -> dict[str, str]:
        with self._lock:
            return dict(self.conn.execute("SELECT key, value FROM meta"))

    def _q(self, sql: str, args=()):
        with self._lock:
            return self.conn.execute(sql, args).fetchall()

    def _check_season(self, season: Optional[str]):
        if season not in (None, self.season):
            raise ValueError(f"solo hay datos sintéticos de {self.season}")

    def _cut(self, until) -> Optional[int]:
        """Jornada de corte: se cuentan las jornadas < corte. None = todo."""
        c = parse_until(until)
        if c is None:
            return None
        if c[0] != self.season:
            return 0 if c[0] > self.season else 10 ** 6
        return c[1]

    def _rounds_before(self, cut) -> int:
        key = ("nr", cut)
        if key not in self._cache:
            sql = "SELECT COUNT(DISTINCT round) FROM matches" + ("" if cut is None else " WHERE round < ?")
            self._cache[key] = self._q(sql, () if cut is None else (cut,))[0][0]
        return self._cache[key]

    # ------------------------------------------------------------- plantillas
    def _load_roster(self) -> dict:
        if self._roster is None:
            self._roster = json.loads(seasons.roster_path(self.season).read_text(encoding="utf-8"))
        return self._roster

    def teams(self, season: str) -> list[Team]:
        self._check_season(season)
        return load_roster_teams(self.season)

    def squad(self, team_id: str, season: str) -> list[Player]:
        self._check_season(season)
        for t in self._load_roster()["teams"]:
            if t["id"] == team_id:
                keys = Player.model_fields.keys()
                return [Player(**{k: v for k, v in p.items() if k in keys}) for p in t["players"]]
        raise KeyError(team_id)

    # ------------------------------------------------------------- resultados
    def matches(self, season: str, team_id: Optional[str] = None) -> list[MatchInfo]:
        self._check_season(season)
        sql = "SELECT id, season, round, date, home, away, home_goals, away_goals FROM matches"
        args: tuple = ()
        if team_id:
            sql += " WHERE home=? OR away=?"
            args = (team_id, team_id)
        sql += " ORDER BY round, date, id"
        return [MatchInfo(id=r[0], season=r[1], round=r[2], date=r[3], home=r[4], away=r[5], home_goals=r[6],
                          away_goals=r[7], synthetic=False) for r in self._q(sql, args)]

    def standings(self, season: str, until_round: Optional[int] = None) -> list[StandingRow]:
        self._check_season(season)
        rows = self._q("SELECT round, home, away, home_goals, away_goals FROM matches WHERE home_goals IS NOT NULL")
        ids = sorted({r[1] for r in rows} | {r[2] for r in rows})
        return compute_standings(rows, ids, until_round)

    def h2h(self, team_a: str, team_b: str, *, until=None) -> H2H:
        return self._real.h2h(team_a, team_b, until=until)

    # ------------------------------------------------------------- agregados de jugador
    def _player_table(self, cut):
        key = ("pt", cut)
        with self._lock:
            if key in self._cache:
                return self._cache[key]
            w = "" if cut is None else " WHERE round < ?"
            a = () if cut is None else (cut,)
            sums = {}
            cols = ", ".join(f"SUM({c})" for c in PMS_COLS)
            for r in self.conn.execute(f"SELECT player, {cols} FROM pms{w} GROUP BY player", a):
                sums[r[0]] = dict(zip(PMS_COLS, r[1:]))
            lu = {}
            lw = "" if cut is None else " AND round < ?"
            for p, m, s_, mi in self.conn.execute(
                    "SELECT player, COUNT(*), SUM(started), SUM(minutes) FROM lineups WHERE minutes > 0" + lw
                    + " GROUP BY player", a):
                lu[p] = (m, int(s_ or 0), int(mi or 0))
            line = {p: ln for p, ln in self.conn.execute("SELECT id, line FROM players")}
            nr = self._rounds_before(cut)
            minimum = MIN_MINUTES_SHARE * 90 * nr
            pools: dict[str, dict[str, np.ndarray]] = {}
            for ln in ("GK", "DEF", "MID", "FWD"):
                members = [p for p in sums if line.get(p) == ln and lu.get(p, (0, 0, 0))[2] >= max(minimum, 1)]
                vals: dict[str, list] = {s: [] for s in STAT_ORDER}
                for p in members:
                    st = _stats_from(sums[p])
                    mi = lu[p][2]
                    for s in STAT_ORDER:
                        vals[s].append(st[s] if s == "pass_pct" else st[s] * 90.0 / mi)
                pools[ln] = {s: np.sort(np.array(v)) for s, v in vals.items()}
            self._cache[key] = (sums, lu, pools, line)
            return self._cache[key]

    def player_season(self, player_id: str, season: str, *, until=None) -> PlayerSeason:
        self._check_season(season)
        cut = self._cut(until)
        sums, lu, pools, line = self._player_table(cut)
        if player_id not in line:
            raise KeyError(player_id)
        matches, starts, minutes = lu.get(player_id, (0, 0, 0))
        st = _stats_from(sums.get(player_id, {c: 0.0 for c in PMS_COLS}))
        pool = pools[line[player_id]]
        out: dict[str, StatValue] = {}
        for s in STAT_ORDER:
            v = float(st[s])
            per90 = None if s == "pass_pct" else (round(v * 90.0 / minutes, 3) if minutes else 0.0)
            pc = None
            if minutes and not (s == "saves" and line[player_id] != "GK"):
                p = _pct(pool[s], v if s == "pass_pct" else v * 90.0 / minutes)
                pc = p if p >= 0 else None
            out[s] = StatValue(value=round(v, 3), per90=per90, percentile=pc)
        return PlayerSeason(player=player_id, season=season, matches=matches, starts=starts, minutes=minutes,
                            stats=out, synthetic=True)

    # ------------------------------------------------------------- agregados de equipo
    def _team_table(self, cut):
        key = ("tt", cut)
        with self._lock:
            if key in self._cache:
                return self._cache[key]
            w = "" if cut is None else " WHERE round < ?"
            a = () if cut is None else (cut,)
            cols = ", ".join(f"SUM({c})" for c in PMS_COLS)
            per_team = {}
            for r in self.conn.execute(f"SELECT team, {cols} FROM pms{w} GROUP BY team", a):
                per_team[r[0]] = dict(zip(PMS_COLS, r[1:]))
            rows = self.conn.execute(
                "SELECT m.home, m.away, m.home_goals, m.away_goals, "
                "(SELECT SUM(xg) FROM pms WHERE match=m.id AND team=m.home), "
                "(SELECT SUM(xg) FROM pms WHERE match=m.id AND team=m.away), "
                "(SELECT SUM(passes) FROM pms WHERE match=m.id AND team=m.home), "
                "(SELECT SUM(passes) FROM pms WHERE match=m.id AND team=m.away), "
                "(SELECT SUM(shots) FROM pms WHERE match=m.id AND team=m.home), "
                "(SELECT SUM(shots) FROM pms WHERE match=m.id AND team=m.away) FROM matches m"
                + ("" if cut is None else " WHERE m.round < ?"), a).fetchall()
            tt: dict[str, dict] = {}
            for t, d in per_team.items():
                tt[t] = dict(_stats_from(d), played=0, wins=0, draws=0, losses=0, points=0, goals_for=0, goals_against=0,
                             xg_for=0.0, xg_against=0.0, shots_against=0, clean_sheets=0, opp_passes=0)
            for h, aw, hg, ag, xh, xa_, ph, pa, sh, sa in rows:
                for t, gf, ga, xf, xc, pf, po, so in ((h, hg, ag, xh, xa_, ph, pa, sa), (aw, ag, hg, xa_, xh, pa, ph, sh)):
                    r = tt[t]
                    r["played"] += 1; r["goals_for"] += gf; r["goals_against"] += ga
                    r["xg_for"] += xf or 0; r["xg_against"] += xc or 0; r["opp_passes"] += po or 0
                    r["shots_against"] += so or 0
                    r["clean_sheets"] += int(ga == 0)
                    if gf > ga: r["wins"] += 1; r["points"] += 3
                    elif gf == ga: r["draws"] += 1; r["points"] += 1
                    else: r["losses"] += 1
            for t, r in tt.items():
                tot = r["passes"] + r["opp_passes"]
                r["possession"] = 100.0 * r["passes"] / tot if tot else 0.0
            self._cache[key] = tt
            return tt

    def team_season(self, team_id: str, season: str, *, until=None) -> TeamSeason:
        self._check_season(season)
        tt = self._team_table(self._cut(until))
        if team_id not in tt:
            raise KeyError(team_id)
        keys = ["points", "wins", "draws", "losses", "goals_for", "goals_against", "xg_for", "xg_against", "shots",
                "shots_on_target", "shots_against", "possession", "passes", "pass_pct", "key_passes", "dribbles",
                "dribbles_won", "recoveries", "tackles", "interceptions", "clearances", "fouls", "yellow", "red",
                "saves", "clean_sheets", "touches"]
        no_per = {"possession", "pass_pct"}
        out = {}
        for k in keys:
            v = float(tt[team_id][k])
            n = tt[team_id]["played"]
            per = None if k in no_per else (round(v / n, 3) if n else 0.0)
            pool = np.sort(np.array([(float(r[k]) if k in no_per else (float(r[k]) / r["played"] if r["played"] else 0.0))
                                     for r in tt.values()]))
            ref = v if k in no_per else (v / n if n else 0.0)
            out[k] = StatValue(value=round(v, 3), per90=per, percentile=_pct(pool, ref) if n else None)
        return TeamSeason(team=team_id, season=season, stats=out, synthetic=True)

    # ------------------------------------------------------------- eventos
    def _scope(self, cut, alias=""):
        return ("", ()) if cut is None else (f" AND {alias}round < ?", (cut,))

    def events(self, match_id: Optional[str] = None, *, player_id: Optional[str] = None,
               team_id: Optional[str] = None, types: Optional[list[str]] = None, season: Optional[str] = None,
               until=None) -> list[PitchEvent]:
        self._check_season(season)
        where, args = ["1=1"], []
        if match_id:
            where.append("match = ?"); args.append(match_id)
        if player_id:
            where.append("player = ?"); args.append(player_id)
        if team_id:
            where.append("team = ?"); args.append(team_id)
        if types:
            where.append("type IN (" + ",".join("?" * len(types)) + ")"); args += list(types)
        cut = self._cut(until)
        if cut is not None:
            where.append("round < ?"); args.append(cut)
        rows = self._q("SELECT id, match, team, player, minute, second, type, x, y, end_x, end_y, outcome, receiver, "
                       "xg, key_pass, assist, body, detail FROM events WHERE " + " AND ".join(where) + " ORDER BY id",
                       args)
        return [PitchEvent(id=r[0], match=r[1], team=r[2], player=r[3], minute=r[4], second=r[5], type=r[6], x=r[7],
                           y=r[8], end_x=r[9], end_y=r[10], outcome=r[11], receiver=r[12], xg=r[13],
                           key_pass=bool(r[14]), assist=bool(r[15]), body=r[16], detail=r[17]) for r in rows]

    # ------------------------------------------------------------- red de pases
    def pass_network(self, team_id: str, *, match_id: Optional[str] = None, season: Optional[str] = None,
                     until=None) -> PassNetwork:
        self._check_season(season)
        cut = self._cut(until)
        if match_id:
            ok = self._q("SELECT 1 FROM matches WHERE id = ?" + ("" if cut is None else " AND round < ?"),
                         (match_id,) if cut is None else (match_id, cut))
            sc = ("match = ?", (match_id,)) if ok else ("0", ())
            scope = match_id
            starters = [r[0] for r in self._q("SELECT player FROM lineups WHERE match=? AND team=? AND started=1 "
                                              "ORDER BY slot, player", (match_id, team_id))] if ok else []
        else:
            w, a = self._scope(cut)
            sc = ("1=1" + w, a)
            scope = season or self.season
            starters = [r[0] for r in self._q(
                "SELECT player FROM lineups WHERE team=? AND minutes>0" + w + " GROUP BY player "
                "ORDER BY SUM(started) DESC, SUM(minutes) DESC, player LIMIT 11", (team_id,) + a)]
        if not starters:
            return PassNetwork(team=team_id, scope=scope, nodes=[], edges=[], synthetic=True)
        ph = ",".join("?" * len(starters))
        pos: dict[str, list[float]] = {p: [0.0, 0.0, 0] for p in starters}
        for p, sx, sy, n in self._q(f"SELECT player, SUM(x), SUM(y), COUNT(*) FROM events WHERE type='pass' AND team=? "
                                    f"AND {sc[0]} AND player IN ({ph}) GROUP BY player", (team_id, *sc[1], *starters)):
            pos[p][0] += sx; pos[p][1] += sy; pos[p][2] += n
        for p, sx, sy, n in self._q(f"SELECT receiver, SUM(end_x), SUM(end_y), COUNT(*) FROM events WHERE type='pass' "
                                    f"AND outcome='complete' AND team=? AND {sc[0]} AND receiver IN ({ph}) "
                                    f"GROUP BY receiver", (team_id, *sc[1], *starters)):
            pos[p][0] += sx; pos[p][1] += sy; pos[p][2] += n
        agg = {r[0]: r[1:] for r in self._q(
            f"SELECT player, SUM(passes), SUM(received) + SUM(passes) + SUM(shots) + SUM(dribbles) + SUM(recoveries) + "
            f"SUM(interceptions) + SUM(clearances) + SUM(saves) FROM pms WHERE team=? AND "
            + sc[0].replace("match", "match") + f" AND player IN ({ph}) GROUP BY player", (team_id, *sc[1], *starters))}
        nodes = []
        for p in starters:
            sx, sy, n = pos[p]
            a_ = agg.get(p, (0, 0))
            nodes.append(PassNode(player=p, x=round(sx / n, 2) if n else 0.0, y=round(sy / n, 2) if n else 0.0,
                                  passes=int(a_[0] or 0), touches=int(a_[1] or 0)))
        edges = [PassEdge(a=a_, b=b, count=c) for a_, b, c in self._q(
            f"SELECT player, receiver, COUNT(*) FROM events WHERE type='pass' AND outcome='complete' AND team=? "
            f"AND {sc[0]} AND player IN ({ph}) AND receiver IN ({ph}) GROUP BY player, receiver "
            f"ORDER BY player, receiver", (team_id, *sc[1], *starters, *starters))]
        return PassNetwork(team=team_id, scope=scope, nodes=nodes, edges=edges, synthetic=True)

    # ------------------------------------------------------------- conexión entre dos jugadores
    def connection(self, a: str, b: str, *, season: str, until=None) -> Connection:
        self._check_season(season)
        cut = self._cut(until)
        w, args = self._scope(cut)
        base = "type='pass' AND outcome='complete'" + w
        rec = self._q(f"SELECT receiver, COUNT(*) c FROM events WHERE player=? AND {base} GROUP BY receiver "
                      f"ORDER BY c DESC, receiver", (a, *args))
        names = [r[0] for r in rec]
        a_to_b = dict(rec).get(b, 0)
        b_to_a = self._q(f"SELECT COUNT(*) FROM events WHERE player=? AND receiver=? AND {base}", (b, a, *args))[0][0]
        kp, asst = self._q(f"SELECT COALESCE(SUM(key_pass),0), COALESCE(SUM(assist),0) FROM events WHERE "
                           f"((player=? AND receiver=?) OR (player=? AND receiver=?)) AND {base}",
                           (a, b, b, a, *args))[0]
        rank = names.index(b) + 1 if b in names else len(names) + 1
        rows = self._q("SELECT id, match, team, player, minute, second, type, x, y, end_x, end_y, outcome, receiver, "
                       "xg, key_pass, assist, body, detail FROM events WHERE ((player=? AND receiver=?) OR "
                       f"(player=? AND receiver=?)) AND {base} ORDER BY id", (a, b, b, a, *args))
        pri = [r for r in rows if r[14] or r[15]]
        rest = [r for r in rows if not (r[14] or r[15])]
        room = max(0, 40 - len(pri))
        if len(pri) > 40:
            pri = [pri[int(i * len(pri) / 40)] for i in range(40)]
        if len(rest) > room:
            rest = [rest[int(i * len(rest) / room)] for i in range(room)] if room else []
        sample = [PitchEvent(id=r[0], match=r[1], team=r[2], player=r[3], minute=r[4], second=r[5], type=r[6], x=r[7],
                             y=r[8], end_x=r[9], end_y=r[10], outcome=r[11], receiver=r[12], xg=r[13],
                             key_pass=bool(r[14]), assist=bool(r[15]), body=r[16], detail=r[17])
                  for r in sorted(pri + rest, key=lambda r: r[0])]
        return Connection(a=a, b=b, season=season, a_to_b=a_to_b, b_to_a=b_to_a, key_passes=int(kp),
                          assists=int(asst), rank_for_a=rank, sample=sample, synthetic=True)

    def close(self):
        if self._conn is not None:
            self._conn.close()
            self._conn = None
