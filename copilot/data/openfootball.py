"""Resultados REALES de Primera División (openfootball/football.json), gratis y sin clave.

Ficheros en data/real/: es.1.<temporada>.json (las que haya instaladas: copilot/seasons.py). openfootball no trae el
marcador de la J38 de 2024-25 (10 partidos con `score` vacío): se completa con data/real/es.1.2024-25.supplement.json
(matriz de resultados de Wikipedia, contrastada con los otros 370 partidos); cualquier temporada puede llevar un
`es.1.<temporada>.supplement.json` con el mismo formato. Solo implementa teams, matches, standings y h2h;
el resto de la interfaz lanza NotImplementedError (openfootball solo trae resultados).
"""
from __future__ import annotations

import json
import re
import unicodedata
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Optional

from copilot import seasons
from copilot.types import H2H, MatchInfo, StandingRow, Team

ROOT = Path(__file__).resolve().parents[2]

#: nombre de openfootball -> id canónico (explícita, comprobada por tests/test_providers.py).
TEAM_IDS: dict[str, str] = {
    "Athletic Club": "athletic",
    "CA Osasuna": "osasuna",
    "CD Leganés": "leganes",
    "Club Atlético de Madrid": "atletico",
    "Deportivo Alavés": "alaves",
    "FC Barcelona": "barcelona",
    "Getafe CF": "getafe",
    "Girona FC": "girona",
    "RC Celta de Vigo": "celta",
    "RCD Espanyol de Barcelona": "espanyol",
    "RCD Mallorca": "mallorca",
    "Rayo Vallecano de Madrid": "rayo",
    "Real Betis Balompié": "betis",
    "Real Madrid CF": "real-madrid",
    "Real Sociedad de Fútbol": "real-sociedad",
    "Real Valladolid CF": "valladolid",
    "Sevilla FC": "sevilla",
    "UD Las Palmas": "las-palmas",
    "Valencia CF": "valencia",
    "Villarreal CF": "villarreal",
    # equipos de temporadas anteriores que ya no están en la plantilla actual (solo para históricos)
    "Cádiz CF": "cadiz",
    "Elche CF": "elche",
    "Granada CF": "granada",
    "UD Almería": "almeria",
}


_GENERIC = {"cf", "fc", "cd", "ud", "rcd", "rc", "sd", "ad", "ca", "club", "de", "del", "la", "el", "deportivo",
            "balompie", "futbol", "sad", "real"}


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()
    return " ".join(re.findall(r"[a-z0-9]+", s))


def _core(s: str) -> str:
    """Nombre sin palabras genéricas de club ("Deportivo Alavés" -> "alaves")."""
    return " ".join(w for w in _norm(s).split() if w not in _GENERIC)


def team_index(season: str) -> dict[str, str]:
    """nombre normalizado (name, short, aliases, id) -> id de equipo, según las plantillas instaladas de la temporada."""
    return index_from_roster(json.loads(seasons.roster_path(season).read_text(encoding="utf-8")))


def index_from_roster(d: dict) -> dict[str, str]:
    """Igual que team_index, desde un diccionario de plantillas ya cargado. Si hay dos equipos con el mismo nombre
    normalizado no se indexa ninguno (ambiguo)."""
    seen: dict[str, set[str]] = defaultdict(set)
    for t in d["teams"]:
        for a in [t["id"], t["name"], t["short"], *t.get("aliases", [])]:
            for k in (_norm(a), _core(a)):
                if k:
                    seen[k].add(t["id"])
    return {k: next(iter(v)) for k, v in seen.items() if len(v) == 1}


def resolve_team(name: str, season: Optional[str] = None, index: Optional[dict[str, str]] = None) -> Optional[str]:
    """Nombre de openfootball -> id de equipo. Primero la tabla fija TEAM_IDS; después los nombres/alias de las
    plantillas de la temporada (equipos ascendidos o nuevos). None si no se reconoce."""
    if name in TEAM_IDS:
        return TEAM_IDS[name]
    if index is None:
        if not season or season not in seasons.installed():
            return None
        index = team_index(season)
    return index.get(_norm(name)) or index.get(_core(name))


def parse_until(until, default_season: Optional[str] = None) -> Optional[tuple[str, int]]:
    """until -> (temporada, jornada). Solo cuenta lo ocurrido en jornadas ESTRICTAMENTE anteriores."""
    if until is None:
        return None
    default_season = default_season or seasons.current()
    if isinstance(until, int):
        return (default_season, until)
    parts = str(until).split("/")
    if len(parts) >= 2 and parts[1].startswith("J"):
        return (parts[0], int(parts[1][1:]))
    return (default_season, int(until))


def match_id(season: str, rnd: int, home: str, away: str) -> str:
    return f"{season}/J{rnd:02d}/{home}-{away}"


def compute_standings(results: Iterable[tuple[int, str, str, int, int]], team_ids: Iterable[str],
                      until_round: Optional[int] = None) -> list[StandingRow]:
    """results = (jornada, local, visitante, goles_local, goles_visitante). until_round es INCLUSIVA.

    Desempate (reglamento de LaLiga): puntos, mini-liga entre empatados (puntos, diferencia), diferencia de goles
    global, goles a favor, id.
    """
    team_ids = list(team_ids)
    res = sorted((r for r in results if until_round is None or r[0] <= until_round), key=lambda r: r[0])
    tab = {t: dict(p=0, w=0, d=0, l=0, gf=0, ga=0, form=[]) for t in team_ids}
    for _, h, a, hg, ag in res:
        for t, gf, ga in ((h, hg, ag), (a, ag, hg)):
            r = tab[t]
            r["gf"] += gf
            r["ga"] += ga
            if gf > ga:
                r["w"] += 1; r["p"] += 3; r["form"].append("W")
            elif gf == ga:
                r["d"] += 1; r["p"] += 1; r["form"].append("D")
            else:
                r["l"] += 1; r["form"].append("L")

    def mini(group: list[str]) -> dict[str, tuple[int, int]]:
        g = set(group)
        pts = {t: 0 for t in group}
        gd = {t: 0 for t in group}
        for _, h, a, hg, ag in res:
            if h in g and a in g:
                gd[h] += hg - ag
                gd[a] += ag - hg
                if hg > ag:
                    pts[h] += 3
                elif hg < ag:
                    pts[a] += 3
                else:
                    pts[h] += 1; pts[a] += 1
        return {t: (pts[t], gd[t]) for t in group}

    by_pts: dict[int, list[str]] = defaultdict(list)
    for t in team_ids:
        by_pts[tab[t]["p"]].append(t)
    order: list[str] = []
    for p in sorted(by_pts, reverse=True):
        grp = by_pts[p]
        m = mini(grp) if len(grp) > 1 else {grp[0]: (0, 0)}
        grp.sort(key=lambda t: (-m[t][0], -m[t][1], -(tab[t]["gf"] - tab[t]["ga"]), -tab[t]["gf"], t))
        order += grp
    rows = []
    for i, t in enumerate(order, 1):
        r = tab[t]
        rows.append(StandingRow(pos=i, team=t, played=r["w"] + r["d"] + r["l"], won=r["w"], drawn=r["d"],
                                lost=r["l"], gf=r["gf"], ga=r["ga"], points=r["p"], form=r["form"][-5:]))
    return rows


def load_roster_teams(season: Optional[str] = None) -> list[Team]:
    d = json.loads(seasons.roster_path(season or seasons.current()).read_text(encoding="utf-8"))
    out = []
    for t in d["teams"]:
        out.append(Team(id=t["id"], name=t["name"], short=t["short"], aliases=t.get("aliases", []),
                        colors=t.get("colors", {}), coach=t.get("coach"), stadium=t.get("stadium")))
    return out


class OpenFootballProvider:
    synthetic = False

    def __init__(self, real_dir: Path | str | None = None):
        self._real_dir = Path(real_dir) if real_dir else None
        self._matches: dict[str, list[MatchInfo]] = {}

    @property
    def real_dir(self) -> Path:
        return self._real_dir or seasons.REAL

    def seasons(self) -> list[str]:
        """Temporadas con resultados en el directorio de este proveedor."""
        if self._real_dir is None:
            return seasons.results_seasons()
        return sorted(p.name[len("es.1."):-len(".json")] for p in self._real_dir.glob("es.1.*.json")
                      if re.fullmatch(r"\d{4}-\d{2}", p.name[len("es.1."):-len(".json")]))

    # ------------------------------------------------------------- carga
    def _load(self, season: str) -> list[MatchInfo]:
        if season in self._matches:
            return self._matches[season]
        path = self.real_dir / f"es.1.{season}.json"
        if not path.exists():
            raise ValueError(f"temporada sin datos reales: {season}")
        raw = json.loads(path.read_text(encoding="utf-8"))["matches"]
        sup: dict[tuple[str, str], list[int]] = {}
        sp = self.real_dir / f"es.1.{season}.supplement.json"
        if sp.exists():
            for m in json.loads(sp.read_text(encoding="utf-8"))["matches"]:
                sup[(m["home"], m["away"])] = m["ft"]
        index = team_index(season) if season in seasons.installed() else None
        unknown = sorted({n for m in raw for n in (m["team1"], m["team2"]) if resolve_team(n, season, index) is None})
        if unknown:
            raise ValueError(f"{path.name}: equipos sin id (añádelos como name/short/alias en "
                             f"{seasons.roster_path(season).name}): {', '.join(unknown)}")
        out = []
        for m in raw:
            h, a = resolve_team(m["team1"], season, index), resolve_team(m["team2"], season, index)
            rnd = int(m["round"].split()[-1])
            ft = (m.get("score") or {}).get("ft") or sup.get((h, a))
            out.append(MatchInfo(id=match_id(season, rnd, h, a), season=season, round=rnd, date=m["date"],
                                 home=h, away=a, home_goals=ft[0] if ft else None,
                                 away_goals=ft[1] if ft else None, synthetic=False))
        out.sort(key=lambda m: (m.round, m.date, m.id))
        self._matches[season] = out
        return out

    # ------------------------------------------------------------- interfaz implementada
    def teams(self, season: str) -> list[Team]:
        if season in seasons.installed():
            return load_roster_teams(season)
        ids = sorted({m.home for m in self._load(season)})
        names = {v: k for k, v in TEAM_IDS.items()}
        return [Team(id=i, name=names[i], short=names[i]) for i in ids]

    def matches(self, season: str, team_id: Optional[str] = None) -> list[MatchInfo]:
        ms = self._load(season)
        if team_id:
            ms = [m for m in ms if team_id in (m.home, m.away)]
        return list(ms)

    def standings(self, season: str, until_round: Optional[int] = None) -> list[StandingRow]:
        ms = self._load(season)
        ids = sorted({m.home for m in ms})
        res = [(m.round, m.home, m.away, m.home_goals, m.away_goals) for m in ms if m.home_goals is not None]
        return compute_standings(res, ids, until_round)

    def h2h(self, team_a: str, team_b: str, *, until=None) -> H2H:
        cut = parse_until(until)
        found: list[MatchInfo] = []
        for s in self.seasons():
            try:
                season_matches = self._load(s)
            except ValueError:  # temporada con equipos sin id: no aporta al cara a cara
                continue
            for m in season_matches:
                if {m.home, m.away} != {team_a, team_b} or m.home_goals is None:
                    continue
                if cut is not None and (m.season, m.round) >= cut:
                    continue
                found.append(m)
        found.sort(key=lambda m: (m.season, m.round))
        aw = dr = bw = ag = bg = 0
        for m in found:
            ga, gb = (m.home_goals, m.away_goals) if m.home == team_a else (m.away_goals, m.home_goals)
            ag += ga; bg += gb
            if ga > gb: aw += 1
            elif ga < gb: bw += 1
            else: dr += 1
        return H2H(a=team_a, b=team_b, played=len(found), a_wins=aw, draws=dr, b_wins=bw, a_goals=ag, b_goals=bg,
                   last=list(reversed(found))[:5])

    # ------------------------------------------------------------- no soportado
    def squad(self, team_id, season):
        raise NotImplementedError("openfootball solo trae resultados")

    def player_season(self, player_id, season, *, until=None):
        raise NotImplementedError("openfootball solo trae resultados")

    def team_season(self, team_id, season, *, until=None):
        raise NotImplementedError("openfootball solo trae resultados")

    def events(self, match_id=None, *, player_id=None, team_id=None, types=None, season=None, until=None):
        raise NotImplementedError("openfootball solo trae resultados")

    def pass_network(self, team_id, *, match_id=None, season=None, until=None):
        raise NotImplementedError("openfootball solo trae resultados")

    def connection(self, a, b, *, season, until=None):
        raise NotImplementedError("openfootball solo trae resultados")
