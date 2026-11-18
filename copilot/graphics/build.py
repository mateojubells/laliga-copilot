"""De GraphicRequest (qué enseñar) a Graphic (con todos los datos para pintarlo). docs/ARCHITECTURE.md §1 y §5.

Todo sale del DataProvider con el corte temporal del partido en curso (`until=match_id`): en directo en la J4 solo se
enseña lo ocurrido antes. Lo del propio partido sale de la timeline (MatchContext).
"""
from __future__ import annotations

import itertools
from typing import Any, Optional

from copilot import seasons
from copilot.graphics import payloads as P
from copilot.graphics.selector import GraphicRequest
from copilot.match.context import MatchContext

CODES = {"alaves": "ALA", "athletic": "ATH", "atletico": "ATM", "barcelona": "BAR", "betis": "BET", "celta": "CEL",
         "espanyol": "ESP", "getafe": "GET", "girona": "GIR", "las-palmas": "LPA", "leganes": "LEG", "mallorca": "MLL",
         "osasuna": "OSA", "rayo": "RAY", "real-madrid": "RMA", "real-sociedad": "RSO", "sevilla": "SEV",
         "valencia": "VAL", "valladolid": "VLL", "villarreal": "VIL"}
POSITION_ES = {"GK": "Portero", "RB": "Lateral derecho", "CB": "Central", "LB": "Lateral izquierdo", "DM": "Pivote",
               "CM": "Centrocampista", "AM": "Mediapunta", "RW": "Extremo derecho", "LW": "Extremo izquierdo", "ST": "Delantero"}
LINE_GROUP = {"GK": "Porteros", "DEF": "Defensas", "MID": "Centrocampistas", "FWD": "Delanteros"}
LABEL = {"goals": "Goles", "assists": "Asistencias", "xg": "xG", "xa": "xA", "shots": "Tiros", "shots_on_target": "Tiros a puerta",
         "passes": "Pases", "pass_pct": "Precisión de pase", "key_passes": "Pases clave", "dribbles": "Regates intentados",
         "dribbles_won": "Regates ganados", "recoveries": "Recuperaciones", "tackles": "Entradas", "interceptions": "Intercepciones",
         "clearances": "Despejes", "fouls": "Faltas cometidas", "fouled": "Faltas recibidas", "yellow": "Amarillas", "red": "Rojas",
         "saves": "Paradas", "touches": "Toques", "points": "Puntos", "goals_for": "Goles a favor", "goals_against": "Goles en contra",
         "xg_for": "xG a favor", "xg_against": "xG en contra", "possession": "Posesión", "clean_sheets": "Porterías a cero",
         "shots_against": "Tiros recibidos", "wins": "Victorias"}
PCT = {"pass_pct", "possession"}
DECIMAL = {"xg", "xa", "xg_for", "xg_against"}
LOWER_BETTER = {"fouls", "yellow", "red", "goals_against", "xg_against", "shots_against"}
BY_LINE = {"GK": ["saves", "passes", "pass_pct", "clearances", "recoveries", "touches"],
           "DEF": ["tackles", "interceptions", "clearances", "recoveries", "passes", "pass_pct"],
           "MID": ["passes", "pass_pct", "key_passes", "recoveries", "assists", "dribbles_won"],
           "FWD": ["goals", "assists", "xg", "shots", "key_passes", "dribbles_won"]}
BY_EVENT = {"gol": ["goals", "xg", "shots", "shots_on_target"], "tiro": ["shots", "shots_on_target", "xg", "goals"],
            "asistencia": ["assists", "key_passes", "xa"], "pase": ["passes", "pass_pct", "key_passes"],
            "centro": ["key_passes", "assists", "xa"], "regate": ["dribbles_won", "dribbles"],
            "falta": ["fouls", "fouled", "yellow"], "amarilla": ["yellow", "fouls", "red"], "roja": ["red", "yellow", "fouls"],
            "penalti": ["fouled", "fouls", "goals"], "parada": ["saves", "clean_sheets"], "robo": ["recoveries", "tackles", "interceptions"],
            "corner": ["key_passes", "assists"], "fuera_juego": ["shots", "goals"], "lesion": ["touches"], "palo": ["shots", "xg", "goals"],
            "perdida": ["passes", "pass_pct"], "despeje": ["clearances", "interceptions"], "cambio": ["goals", "assists"]}
EVENT_TITLE = {"gol": "Gol", "tiro": "Tiro", "parada": "Parada", "palo": "Al palo", "regate": "Regate", "falta": "Falta",
               "penalti": "Penalti", "mano": "Mano", "corner": "Córner", "fuera_juego": "Fuera de juego", "amarilla": "Amarilla",
               "roja": "Expulsión", "cambio": "Cambio", "lesion": "Lesión", "robo": "Recuperación", "perdida": "Pérdida",
               "despeje": "Despeje", "asistencia": "Asistencia", "pase": "Pase", "centro": "Centro", "ocasion": "Ocasión",
               "saque_banda": "Saque de banda", "saque_puerta": "Saque de puerta", "var": "VAR"}
ROLE_LABEL = {("falta", "actor"): "Falta cometida", ("falta", "victim"): "Falta recibida", ("penalti", "actor"): "Penalti cometido",
              ("penalti", "victim"): "Penalti provocado", ("regate", "actor"): "Regate", ("parada", "actor"): "Parada"}
THIS_MATCH = {"gol": ("gol", "goles"), "tiro": ("tiro", "tiros"), "regate": ("regate", "regates"), "falta": ("falta", "faltas"),
              "amarilla": ("amarilla", "amarillas"), "asistencia": ("asistencia", "asistencias"), "parada": ("parada", "paradas"),
              "robo": ("recuperación", "recuperaciones"), "pase": ("pase", "pases"), "centro": ("centro", "centros")}


def fmt(key: str, v: float) -> str:
    if key in PCT:
        return f"{round(v)} %"
    if key in DECIMAL:
        return f"{v:.1f}".replace(".", ",")
    return str(int(round(v)))


class Builder:
    def __init__(self, provider: Any, ctx: MatchContext, season: Optional[str] = None):
        if not season:  # la del partido si está instalada; si no, la activa
            season = seasons.season_of(ctx.match_id) if seasons.season_of(ctx.match_id) in seasons.installed() \
                else seasons.current()
        self.p, self.ctx, self.season = provider, ctx, season
        self.until = ctx.match_id
        self._teams = {t.id: t for t in provider.teams(season)}
        self._players = {pl.id: pl for tid in self._teams for pl in provider.squad(tid, season)}
        try:
            self.round = int(ctx.match_id.split("/")[1][1:])
        except Exception:
            self.round = None
        self._n = 0

    # ------------------------------------------------------------------ piezas
    def team(self, tid: str) -> P.TeamRef:
        t = self._teams[tid]
        return P.TeamRef(id=t.id, name=t.name, short=CODES.get(t.id, t.short[:3].upper()), colors=t.colors,
                         crest=f"/api/img/crest/{t.id}.svg")

    def player(self, pid: str) -> P.PlayerRef:
        pl = self._players[pid]
        return P.PlayerRef(id=pl.id, name=pl.name, known_as=pl.known_as, number=pl.number, position=pl.position, line=pl.line,
                           team=self.team(pl.team), avatar=f"/api/img/player/{pl.id}.svg")

    def scope(self, match: bool = False) -> P.Scope:
        if match:
            return P.Scope(kind="match", label="Este partido", season=self.season, match=self.ctx.match_id)
        label = f"LaLiga {self.season}" + (f" · hasta la J{self.round - 1}" if self.round and self.round > 1 else "")
        return P.Scope(kind="season", label=label, season=self.season, until_round=self.round)

    def stat(self, key: str, sv: Any, highlight: bool = False) -> P.Stat:
        return P.Stat(key=key, label=LABEL.get(key, key), value=sv.value, display=fmt(key, sv.value), per90=sv.per90,
                      percentile=sv.percentile, highlight=highlight)

    def match_line(self, pid: str) -> Optional[str]:
        line = self.ctx.player_line(pid)
        parts = [f"{n} {THIS_MATCH[k][0] if n == 1 else THIS_MATCH[k][1]}" for k, n in line.items() if k in THIS_MATCH]
        return " · ".join(parts[:4]) or None

    def _this_match(self, pid: str, event_type: Optional[str]) -> list[P.Stat]:
        line = self.ctx.player_line(pid)
        out = []
        for k, n in line.items():
            if k in THIS_MATCH and (event_type is None or k == event_type or len(out) < 3):
                out.append(P.Stat(key=k, label=THIS_MATCH[k][1].capitalize(), value=n, display=str(n), highlight=k == event_type))
        return out

    # ------------------------------------------------------------------ payloads
    def player_card(self, pid: str, event_type: Optional[str] = None) -> P.PlayerCard:
        pl = self._players[pid]
        ps = self.p.player_season(pid, self.season, until=self.until)
        first = [k for k in BY_EVENT.get(event_type or "", []) if k in ps.stats]
        keys = list(dict.fromkeys(first[:2] + BY_LINE[pl.line]))[:6]
        stats = [self.stat(k, ps.stats[k], highlight=bool(first) and k == first[0]) for k in keys if k in ps.stats]
        today = self.ctx.player_line(pid)
        for st in stats:  # los goles y asistencias de hoy se suman a la cifra de temporada (es lo que el espectador espera ver)
            add = today.get({"goals": "gol", "assists": "asistencia"}.get(st.key, ""), 0)
            if add:
                st.value += add
                st.display = fmt(st.key, st.value)
                st.per90 = st.percentile = None
        best = max((s for s in stats if s.percentile is not None), key=lambda s: s.percentile or 0, default=None)
        headline = None
        if ps.matches == 0:
            headline = "Aún sin minutos esta temporada"
        elif event_type == "gol" and "goals" in ps.stats:
            total = int(ps.stats["goals"].value) + self.ctx.player_line(pid).get("gol", 0)
            headline = f"{total} {'gol' if total == 1 else 'goles'} en LaLiga contando el de hoy" if total else None
        elif best is not None and (best.percentile or 0) >= 85:
            headline = f"Entre los mejores {LINE_GROUP[pl.line].lower()} en {best.label.lower()}"
        return P.PlayerCard(player=self.player(pid), scope=self.scope(), headline=headline, stats=stats,
                            percentile_context=P.PercentileContext(group=f"{LINE_GROUP[pl.line]} de LaLiga", n=0, min_minutes=0)
                            if ps.matches else None, match_line=self.match_line(pid))

    def team_card(self, tid: str) -> P.TeamCard:
        ts = self.p.team_season(tid, self.season, until=self.until)
        row = next((r for r in self.p.standings(self.season, until_round=(self.round or 39) - 1) if r.team == tid), None)
        keys = ["goals_for", "goals_against", "xg_for", "possession", "pass_pct", "shots"]
        return P.TeamCard(team=self.team(tid), scope=self.scope(), position=row.pos if row else None,
                          points=row.points if row else None, form=row.form[-5:] if row else [],
                          stats=[self.stat(k, ts.stats[k]) for k in keys if k in ts.stats])

    def pass_network(self, tid: str, highlight: tuple[str, ...] = ()) -> P.PassNetworkG:
        net = self.p.pass_network(tid, season=self.season, until=self.until)
        ids = {n.player for n in net.nodes}
        counts = sorted((e.count for e in net.edges), reverse=True)
        min_passes = counts[min(len(counts) - 1, 17)] if counts else 1
        nodes = [P.NetNode(player=self.player(n.player), x=n.x, y=n.y, passes=n.passes, touches=n.touches,
                           highlight=n.player in highlight) for n in net.nodes]
        edges = [P.NetEdge(a=e.a, b=e.b, count=e.count, highlight=e.a in highlight and e.b in highlight)
                 for e in net.edges if e.count >= min_passes and e.a in ids and e.b in ids]
        hub = max(net.nodes, key=lambda n: n.passes, default=None)
        headline = f"{self._players[hub.player].known_as}, por quien pasa todo: {hub.passes} pases" if hub else None
        return P.PassNetworkG(team=self.team(tid), scope=self.scope(), nodes=nodes, edges=edges, min_passes=min_passes, headline=headline)

    def connection(self, a: str, b: str) -> P.ConnectionG:
        c = self.p.connection(a, b, season=self.season, until=self.until)
        arrows = [P.Arrow(x=e.x, y=e.y, end_x=e.end_x or e.x, end_y=e.end_y or e.y,
                          kind="assist" if e.assist else "key_pass" if e.key_pass else "pass") for e in c.sample[:40]]

        def mean(side: str) -> tuple[float, float]:
            pts = [(e.x, e.y) if e.player == side else (e.end_x or e.x, e.end_y or e.y) for e in c.sample]
            return (round(sum(x for x, _ in pts) / len(pts), 1), round(sum(y for _, y in pts) / len(pts), 1)) if pts else (52.5, 34.0)

        ka, kb = self._players[a].known_as, self._players[b].known_as
        total = c.a_to_b + c.b_to_a
        if total == 0:
            headline = f"{ka} y {kb} aún no han coincidido esta temporada"
        elif c.rank_for_a and c.rank_for_a <= 3:
            headline = f"{ka} → {kb}: su socio n.º {c.rank_for_a}"
        else:
            headline = f"{ka} y {kb}: {total} pases entre ellos"
        return P.ConnectionG(a=self.player(a), b=self.player(b), scope=self.scope(), a_to_b=c.a_to_b, b_to_a=c.b_to_a,
                             key_passes=c.key_passes, assists=c.assists, rank_for_a=c.rank_for_a or 0, headline=headline,
                             arrows=arrows, a_pos=mean(a), b_pos=mean(b))

    def _shots(self, **who) -> list[P.Shot]:
        evs = self.p.events(types=["shot"], season=self.season, until=self.until, **who)
        return [P.Shot(x=e.x, y=e.y, xg=e.xg or 0.0, outcome=e.outcome if e.outcome in ("goal", "saved", "off", "blocked", "post") else "off",
                       minute=e.minute, player=e.player, player_name=self._players[e.player].known_as if e.player in self._players else "",
                       body=e.body) for e in evs]

    def shot_map(self, subject: str) -> P.ShotMap:
        is_player = subject in self._players
        shots = self._shots(player_id=subject) if is_player else self._shots(team_id=subject)
        goals, on = sum(s.outcome == "goal" for s in shots), sum(s.outcome in ("goal", "saved") for s in shots)
        xg = sum(s.xg for s in shots)
        totals = [P.Stat(key="shots", label="Tiros", value=len(shots), display=str(len(shots))),
                  P.Stat(key="shots_on_target", label="A puerta", value=on, display=str(on)),
                  P.Stat(key="goals", label="Goles", value=goals, display=str(goals), highlight=True),
                  P.Stat(key="xg", label="xG", value=xg, display=fmt("xg", xg)),
                  P.Stat(key="xg_shot", label="xG por tiro", value=xg / len(shots) if shots else 0,
                         display=f"{(xg / len(shots) if shots else 0):.2f}".replace(".", ","))]
        return P.ShotMap(subject=self.player(subject) if is_player else self.team(subject),
                         subject_type="player" if is_player else "team", scope=self.scope(), shots=shots[-120:], totals=totals)

    def heat_map(self, subject: str, cols: int = 24, rows: int = 16) -> P.HeatMap:
        is_player = subject in self._players
        types = ["pass", "dribble", "recovery", "shot", "tackle", "interception", "clearance"]
        evs = self.p.events(types=types, season=self.season, until=self.until, **({"player_id": subject} if is_player else {"team_id": subject}))
        grid = [0.0] * (cols * rows)
        thirds, lanes = [0, 0, 0], [0, 0, 0]
        for e in evs:
            c, r = min(cols - 1, max(0, int(e.x / 105 * cols))), min(rows - 1, max(0, int(e.y / 68 * rows)))
            grid[r * cols + c] += 1
            thirds[min(2, int(e.x / 35))] += 1
            lanes[min(2, int(e.y / (68 / 3)))] += 1
        mx, n = max(grid) or 1.0, len(evs) or 1
        zones = [P.Stat(key=k, label=l, value=100 * v / n, display=f"{round(100 * v / n)} %") for k, l, v in (
            ("third_def", "Tercio defensivo", thirds[0]), ("third_mid", "Tercio medio", thirds[1]), ("third_att", "Tercio de ataque", thirds[2]),
            ("lane_right", "Banda derecha", lanes[0]), ("lane_center", "Carril central", lanes[1]), ("lane_left", "Banda izquierda", lanes[2]))]
        top = max(zones[3:], key=lambda z: z.value)
        return P.HeatMap(subject=self.player(subject) if is_player else self.team(subject), subject_type="player" if is_player else "team",
                         scope=self.scope(), metric="touches", cols=cols, rows=rows, grid=[round(v / mx, 3) for v in grid], total=len(evs),
                         zones=zones, headline=f"{round(top.value)} % de sus acciones por {top.label.lower()}" if evs else None)

    def comparison(self, a: str, b: str, event_type: Optional[str] = None) -> P.Comparison:
        is_player = a in self._players
        if is_player:
            sa, sb = (self.p.player_season(x, self.season, until=self.until).stats for x in (a, b))
            la, lb = self._players[a].line, self._players[b].line
            keys = BY_LINE[la] if la == lb else ["goals", "assists", "shots", "key_passes", "passes", "recoveries"]
        else:
            sa, sb = (self.p.team_season(x, self.season, until=self.until).stats for x in (a, b))
            keys = ["points", "goals_for", "goals_against", "xg_for", "possession", "pass_pct", "shots"]
        rows = []
        for k in keys:
            if k not in sa or k not in sb:
                continue
            va, vb = sa[k].value, sb[k].value
            hib = k not in LOWER_BETTER
            better = "tie" if va == vb else ("a" if (va > vb) == hib else "b")
            rows.append(P.ComparisonRow(key=k, label=LABEL.get(k, k), a=self.stat(k, sa[k]), b=self.stat(k, sb[k]), better=better, higher_is_better=hib))
        ref = self.player if is_player else self.team
        headline = "Cambio: entra {} por {}".format(self._players[a].known_as, self._players[b].known_as) if event_type == "cambio" else None
        return P.Comparison(subject_type="player" if is_player else "team", a=ref(a), b=ref(b), scope=self.scope(), rows=rows[:7], headline=headline)

    def standings(self, highlight: tuple[str, ...] = (), window: str = "full") -> P.Standings:
        table = self.p.standings(self.season, until_round=(self.round or 39) - 1)
        rows = []
        for r in table:
            zone = "champions" if r.pos <= 4 else "europa" if r.pos <= 6 else "conference" if r.pos == 7 else "relegation" if r.pos >= 18 else None
            rows.append(P.StandingsRowG(pos=r.pos, team=self.team(r.team), played=r.played, won=r.won, drawn=r.drawn, lost=r.lost, gf=r.gf,
                                        ga=r.ga, gd=r.gf - r.ga, points=r.points, form=r.form[-5:], zone=zone, highlight=r.team in highlight))
        if window == "top":
            rows = rows[:8]
        return P.Standings(scope=self.scope(), rows=rows, window=window if window in ("full", "top", "around") else "full")

    def h2h(self, a: str, b: str) -> P.H2HG:
        h = self.p.h2h(a, b, until=self.until)
        last = [P.H2HMatch(season=m.season, date=m.date, home=self.team(m.home), away=self.team(m.away), home_goals=m.home_goals or 0,
                           away_goals=m.away_goals or 0) for m in h.last[:5] if m.home in self._teams and m.away in self._teams]
        return P.H2HG(a=self.team(a), b=self.team(b), played=h.played, a_wins=h.a_wins, draws=h.draws, b_wins=h.b_wins,
                      a_goals=h.a_goals, b_goals=h.b_goals, last=last)

    def situation(self, subject: str, event_type: str, other: Optional[str] = None, role: Optional[str] = None) -> P.Situation:
        is_player = subject in self._players
        if is_player:
            st = self.p.player_season(subject, self.season, until=self.until).stats
            keys = [k for k in BY_EVENT.get(event_type, []) if k in st] or BY_LINE[self._players[subject].line][:3]
            if role == "victim" and "fouled" in st:
                keys = ["fouled"] + [k for k in keys if k != "fouled"]
        else:
            st = self.p.team_season(subject, self.season, until=self.until).stats
            keys = [k for k in BY_EVENT.get(event_type, []) if k in st] or ["goals_for", "shots", "possession"]
        stats = [self.stat(k, st[k], highlight=i == 0) for i, k in enumerate(keys[:4])]
        shots = self._shots(player_id=subject)[-40:] if is_player and event_type in ("tiro", "palo", "gol") else []
        return P.Situation(event_type=event_type, title=EVENT_TITLE.get(event_type, event_type.capitalize()),
                           subject=self.player(subject) if is_player else self.team(subject), subject_type="player" if is_player else "team",
                           other=self.player(other) if other in self._players else None,
                           role_label=ROLE_LABEL.get((event_type, role or "actor")), scope=self.scope(), stats=stats,
                           this_match=self._this_match(subject, event_type) if is_player else [], shots=shots)

    def timeline(self) -> P.Timeline:
        items = []
        for e in self.ctx.events:
            if e.type not in ("gol", "cambio", "amarilla", "roja", "penalti") and e.status == "auto":
                continue  # el frontend, en antena, solo pinta los approved/edited; el operador ve todos
            ids = [v for r, v in e.roles.items() if v in self._players]
            who = " por ".join(self._players[i].known_as for i in ids[:2]) if e.type == "cambio" else (self._players[ids[0]].known_as if ids else "")
            items.append(P.TimelineItem(id=e.id, minute=e.minute, period=e.period, t_audio=e.t_audio, type=e.type,
                                        label=f"{EVENT_TITLE.get(e.type, e.type)}{' · ' + who if who else ''}",
                                        team=self.team(e.team) if e.team in self._teams else None, players=[self.player(i) for i in ids[:2]],
                                        status=e.status, major=e.type in ("gol", "roja", "penalti", "cambio")))
        return P.Timeline(home=self.team(self.ctx.home), away=self.team(self.ctx.away), items=items,
                          minute=max((i.minute or 0 for i in items), default=None))

    def scorebug(self, t: Optional[float] = None) -> P.Scorebug:
        c = self.ctx
        return P.Scorebug(home=self.team(c.home), away=self.team(c.away), home_goals=c.score[c.home], away_goals=c.score[c.away],
                          minute=c.clock.minute(t) if t is not None else None, period=c.clock.period(t) if t is not None else None)

    def match_state(self, t: Optional[float] = None) -> P.MatchState:
        c = self.ctx
        return P.MatchState(match=c.match_id, home=self.team(c.home), away=self.team(c.away), home_goals=c.score[c.home],
                            away_goals=c.score[c.away], period=c.clock.period(t) if t is not None else 0,
                            minute=c.clock.minute(t) if t is not None else None)

    # ------------------------------------------------------------------ entrada única
    def payload(self, kind: str, subject: Optional[str] = None, other: Optional[str] = None, event_type: Optional[str] = None,
                role: Optional[str] = None) -> Any:
        c = self.ctx
        if kind == "player_card":
            return self.player_card(subject, event_type)  # type: ignore[arg-type]
        if kind == "team_card":
            return self.team_card(subject or c.home)
        if kind == "pass_network":
            tid = self._players[subject].team if subject in self._players else (subject or c.home)
            return self.pass_network(tid, tuple(x for x in (subject, other) if x in self._players))
        if kind == "connection":
            return self.connection(subject, other)  # type: ignore[arg-type]
        if kind == "shot_map":
            return self.shot_map(subject or c.home)
        if kind == "heat_map":
            return self.heat_map(subject or c.home)
        if kind == "comparison":
            if subject is None:
                subject, other = c.home, c.away
            return self.comparison(subject, other, event_type)  # type: ignore[arg-type]
        if kind == "standings":
            return self.standings((c.home, c.away))
        if kind == "h2h":
            return self.h2h(subject or c.home, other or c.away)
        if kind == "situation":
            return self.situation(subject, event_type or "falta", other, role)  # type: ignore[arg-type]
        if kind == "timeline":
            return self.timeline()
        if kind == "scorebug":
            return self.scorebug()
        raise ValueError(f"grafismo desconocido: {kind}")

    def graphic(self, req: GraphicRequest, ts: Optional[dict] = None) -> P.Graphic:
        self._n += 1
        payload = self.payload(req.kind, req.subject, req.other, req.event_type, req.role)
        return P.Graphic(id=f"g-{self._n:04d}", kind=req.kind, priority=req.priority, ttl_ms=req.ttl_ms,
                         state="on_air" if req.auto else "proposed",
                         reason={"trigger": req.trigger, "text": req.text, "trace_id": req.trace_id, "event_id": req.event_id},
                         payload=payload, demo_data=req.kind not in ("standings", "h2h", "scorebug", "timeline"), ts=ts or {})
