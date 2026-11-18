"""Menú principal: temporadas, partidos y alineaciones (docs/LIVE_READINESS.md §2.1-2.2)."""
from __future__ import annotations

import json
import sqlite3
from functools import lru_cache
from typing import Optional

from copilot import seasons
from copilot.graphics import payloads as P
from copilot.graphics.build import CODES

#: formación de la propuesta automática cuando no hay historial de alineaciones (4-3-3)
FORMATION = ["GK", "RB", "CB", "CB", "LB", "DM", "CM", "CM", "RW", "ST", "LW"]
NEAR = {"RB": ["RB", "CB", "LB"], "LB": ["LB", "CB", "RB"], "CB": ["CB", "DM", "RB", "LB"], "DM": ["DM", "CM"],
        "CM": ["CM", "AM", "DM"], "AM": ["AM", "CM"], "RW": ["RW", "LW", "AM", "ST"], "LW": ["LW", "RW", "AM", "ST"],
        "ST": ["ST", "RW", "LW", "AM"], "GK": ["GK"]}
MAX_BENCH = 15


class LineupError(ValueError):
    pass


@lru_cache(maxsize=8)
def roster(season: str) -> dict:
    return json.loads(seasons.roster_path(season).read_text(encoding="utf-8"))


def teams_by_id(season: str) -> dict[str, dict]:
    return {t["id"]: t for t in roster(season)["teams"]}


def team_ref(t: dict) -> P.TeamRef:
    return P.TeamRef(id=t["id"], name=t["name"], short=CODES.get(t["id"], t.get("short", t["id"])[:3].upper()),
                     colors=t.get("colors", {}), crest=f"/api/img/crest/{t['id']}.svg")


def player_ref(p: dict, team: dict) -> P.PlayerRef:
    return P.PlayerRef(id=p["id"], name=p["name"], known_as=p.get("known_as") or p["name"], number=p.get("number"),
                       position=p["position"], line=p["line"], team=team_ref(team), avatar=f"/api/img/player/{p['id']}.svg")


def split_match(season: str, match_id: str) -> tuple[str, str]:
    pair = match_id.split("/")[-1]
    ids = teams_by_id(season)
    for a in ids:
        if pair.startswith(a + "-") and pair[len(a) + 1:] in ids:
            return a, pair[len(a) + 1:]
    raise LineupError(f"El partido {match_id} no corresponde a dos equipos de la temporada {season}")


def season_list(current: Optional[str]) -> list[P.SeasonInfoOut]:
    out = []
    for s in seasons.installed():
        i = seasons.info(s)
        out.append(P.SeasonInfoOut(season=s, teams=i.teams, players=i.players, has_results=i.has_results,
                                   has_stats=i.has_stats, current=s == current))
    return out


def match_list(season: str, provider) -> list[P.MatchListItem]:
    ids = teams_by_id(season)
    try:
        matches = provider.matches(season)
    except Exception:
        matches = []
    out = []
    for m in matches:
        if m.home not in ids or m.away not in ids:
            continue
        out.append(P.MatchListItem(id=m.id, season=season, round=m.round, date=m.date, home=team_ref(ids[m.home]),
                                   away=team_ref(ids[m.away]), home_goals=m.home_goals, away_goals=m.away_goals,
                                   has_lineup=seasons.lineup_path(m.id).exists()))
    return sorted(out, key=lambda x: (x.round, x.date, x.id))


def _usage(season: str, team: str, before_round: Optional[int]) -> dict[str, int]:
    """Titularidades de cada jugador antes de esa jornada, si hay base de estadísticas de la temporada."""
    db = seasons.synth_db(season)
    if not db.exists():
        return {}
    try:
        with sqlite3.connect(f"file:{db}?mode=ro", uri=True) as c:
            q = "select player, sum(started) from lineups where team=?" + (" and round<?" if before_round else "") + " group by player"
            args = (team, before_round) if before_round else (team,)
            return {p: n or 0 for p, n in c.execute(q, args)}
    except sqlite3.Error:
        return {}


def propose(season: str, match_id: str, team: str) -> P.TeamLineup:
    t = teams_by_id(season)[team]
    try:
        rnd = int(match_id.split("/")[1][1:])
    except (IndexError, ValueError):
        rnd = None
    use = _usage(season, team, rnd)
    players = sorted(t["players"], key=lambda p: (-use.get(p["id"], 0), p.get("number") or 99))
    starting: list[str] = []
    for slot in FORMATION:
        pick = next((p for pos in NEAR[slot] for p in players if p["position"] == pos and p["id"] not in starting
                     and (slot == "GK") == (p["position"] == "GK")), None)
        if pick:
            starting.append(pick["id"])
    for p in players:  # rellena si faltan posiciones
        if len(starting) >= 11:
            break
        if p["id"] not in starting and p["position"] != "GK":
            starting.append(p["id"])
    bench = [p["id"] for p in players if p["id"] not in starting][:12]
    gk_bench = [p["id"] for p in players if p["position"] == "GK" and p["id"] not in starting and p["id"] not in bench]
    if gk_bench and not any(teams_by_id(season)[team] and p["position"] == "GK" for p in t["players"] if p["id"] in bench):
        bench = bench[:11] + gk_bench[:1]
    return P.TeamLineup(starting=starting, bench=bench)


def lineup(season: str, match_id: str) -> P.LineupProposal:
    home, away = split_match(season, match_id)
    ids = teams_by_id(season)
    squads = {tid: [player_ref(p, ids[tid]) for p in sorted(ids[tid]["players"], key=lambda p: p.get("number") or 99)]
              for tid in (home, away)}
    f = seasons.lineup_path(match_id)
    if f.exists():
        saved = json.loads(f.read_text(encoding="utf-8")).get("lineups", {})
        if home in saved and away in saved:
            return P.LineupProposal(match=match_id, source="saved", squads=squads,
                                    teams={tid: P.TeamLineup(starting=saved[tid]["starting"], bench=saved[tid].get("bench", []))
                                           for tid in (home, away)})
    return P.LineupProposal(match=match_id, source="proposed", squads=squads,
                            teams={tid: propose(season, match_id, tid) for tid in (home, away)})


def validate(cfg: P.SessionConfig) -> None:
    if cfg.season not in seasons.installed():
        raise LineupError(f"La temporada {cfg.season} no está instalada")
    home, away = split_match(cfg.season, cfg.match)
    ids = teams_by_id(cfg.season)
    for tid in (home, away):
        lu = cfg.lineups.get(tid)
        name = ids[tid]["name"]
        if lu is None:
            raise LineupError(f"Falta la alineación de {name}")
        squad = {p["id"]: p for p in ids[tid]["players"]}
        allp = lu.starting + lu.bench
        unknown = [x for x in allp if x not in squad]
        if unknown:
            raise LineupError(f"{name}: jugadores que no son de la plantilla: {', '.join(unknown)}")
        if len(set(allp)) != len(allp):
            raise LineupError(f"{name}: hay jugadores repetidos entre titulares y banquillo")
        if len(lu.starting) != 11:
            raise LineupError(f"{name}: hacen falta 11 titulares y hay {len(lu.starting)}")
        gks = sum(squad[x]["position"] == "GK" for x in lu.starting)
        if gks != 1:
            raise LineupError(f"{name}: entre los titulares tiene que haber exactamente 1 portero y hay {gks}")
        if len(lu.bench) > MAX_BENCH:
            raise LineupError(f"{name}: como mucho {MAX_BENCH} suplentes")
    for tid in cfg.lineups:
        if tid not in (home, away):
            raise LineupError(f"Sobra la alineación de {tid}: no juega este partido")


def save_lineup(cfg: P.SessionConfig) -> None:
    home, away = split_match(cfg.season, cfg.match)
    f = seasons.lineup_path(cfg.match)
    f.parent.mkdir(parents=True, exist_ok=True)
    data = json.loads(f.read_text(encoding="utf-8")) if f.exists() else {}  # se conservan los demás campos
    data.update({"match": cfg.match, "home": home, "away": away,
                 "lineups": {tid: cfg.lineups[tid].model_dump() for tid in (home, away)}})
    data.setdefault("_doc", "Alineación confirmada por el operador en el menú principal antes del partido.")
    f.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
