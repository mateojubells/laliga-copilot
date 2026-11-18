"""Estado del partido y timeline (docs/ARCHITECTURE.md §1, §5).

Recibe lo que entiende el NLU frase a frase y decide qué es un HECHO NUEVO del partido: deduplica (un gol se canta
muchas veces), completa (primero "¡gol!", segundos después "de Raphinha"), retira (gol anulado) y lleva el marcador.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from itertools import permutations
from typing import Optional

from copilot.types import MatchEvent, NluResult

MAJOR = {"gol", "cambio", "roja", "penalti", "amarilla"}
#: segundos durante los que la misma tupla se considera repetición del mismo hecho
DEDUP_S = {"gol": 150.0, "cambio": 600.0, "amarilla": 300.0, "roja": 600.0, "penalti": 120.0}
DEFAULT_DEDUP_S = 12.0
#: Tras un gol, durante este rato se siguen comentando goles (repeticiones, resúmenes, "lleva dos"). Un gol NUEVO en
#: ese periodo tiene que cantarse como tal; una simple mención no mueve el marcador.
RECAP_S = 600.0
_SUNG = re.compile(r"(?:^|[.!?¡] ?)\s*(?:go+l\b|golazo)|\bgo+l[,!. ]+go+l\b|acaba de marcar|vuelve a marcar|"
                   r"ha vuelto a marcar|otro gol|otra vez gol|marca el (?:primero|segundo|tercero|cuarto|quinto|sexto|septimo|séptimo)|"
                   r"hace el (?:primero|segundo|tercero|cuarto|quinto|sexto|septimo|séptimo)|se adelanta|empata", re.I)


@dataclass
class Clock:
    """Reloj del partido a partir del tiempo de la fuente de audio."""
    kickoff: Optional[float] = None
    second_half: Optional[float] = None
    first_half_end: Optional[float] = None
    full_time: Optional[float] = None
    added: Optional[int] = None  # minutos de descuento anunciados en el periodo en curso

    def halftime(self, t: float) -> bool:
        return (self.first_half_end is not None and t >= self.first_half_end
                and (self.second_half is None or t < self.second_half))

    def seconds(self, t: float) -> float:
        """Segundos de partido en el instante t (45:00 = 2700). Parado en el descanso y tras el final."""
        p = self.period(t)
        if p == 0:
            return 0.0
        if p == 1:
            end = self.first_half_end if self.halftime(t) else t
            return max(0.0, end - self.kickoff)  # type: ignore[operator]
        if p == 2:
            return 2700.0 + max(0.0, t - self.second_half)  # type: ignore[operator]
        if self.second_half is not None:
            return 2700.0 + max(0.0, self.full_time - self.second_half)  # type: ignore[operator]
        return max(0.0, self.full_time - self.kickoff)  # type: ignore[operator]

    def running(self, t: float) -> bool:
        return self.period(t) in (1, 2) and not self.halftime(t)

    def period(self, t: float) -> int:
        if self.kickoff is None or t < self.kickoff:
            return 0
        if self.full_time is not None and t >= self.full_time:
            return 3
        if self.second_half is not None and t >= self.second_half:
            return 2
        return 1

    def minute(self, t: float) -> Optional[int]:
        p = self.period(t)
        if p == 1:
            return int(self.seconds(t) // 60) + 1
        if p == 2:
            return 45 + int((t - self.second_half) // 60) + 1  # type: ignore[operator]
        return None


@dataclass
class MatchContext:
    match_id: str
    home: str
    away: str
    team_of: dict[str, str] = field(default_factory=dict)  # jugador -> equipo
    clock: Clock = field(default_factory=Clock)
    events: list[MatchEvent] = field(default_factory=list)
    score: dict[str, int] = field(default_factory=dict)
    on_pitch: dict[str, set[str]] = field(default_factory=dict)  # equipo -> jugadores en el campo (si hay alineación)
    bench: dict[str, set[str]] = field(default_factory=dict)
    position: dict[str, tuple[str, str]] = field(default_factory=dict)  # jugador -> (posición, línea)
    _n: int = 0
    _sub_pool: list[dict] = field(default_factory=list)  # menciones sueltas de quien entra / quien sale

    def __post_init__(self) -> None:
        self.score = {self.home: 0, self.away: 0}

    # ------------------------------------------------------------------ ingestión
    def ingest(self, res: NluResult, t: Optional[float] = None) -> list[tuple[str, MatchEvent]]:
        """Devuelve [(acción, evento)] con acción ∈ new | update | retract."""
        t = res.t1 or res.t0 if t is None else t
        out: list[tuple[str, MatchEvent]] = []
        for ev in res.events:
            if ev.type == "inicio" and ev.modality == "real" and self.clock.kickoff is None:
                self.clock.kickoff = t
            if ev.type == "descanso" and ev.modality == "real" and self.clock.period(t) == 1 and self.clock.first_half_end is None \
                    and self.clock.kickoff is not None and t - self.clock.kickoff > 40 * 60:
                self.clock.first_half_end = t
            if ev.modality == "negated" and ev.type == "gol":
                last = self._last("gol", t, 150.0)
                if last is not None and (not ev.roles.get("actor") or ev.roles.get("actor") == last.roles.get("actor")):
                    last.status = "discarded"
                    self._recount()
                    out.append(("retract", last))
                continue
            if ev.modality != "real":
                continue
            if ev.type == "cambio":
                out += self._ingest_sub(ev, res, t)
                continue
            roles = dict(ev.roles)
            team = self._team(roles)
            if ev.fine == "autogol" and roles.get("actor") in self.team_of:
                team = self.away if self.team_of[roles["actor"]] == self.home else self.home  # cuenta para el rival
            prev = self._match(ev.type, roles, team, t)
            if prev is None and ev.type == "gol" and self._is_recap(roles, t, res.text):
                continue
            if prev is not None:
                changed = False
                for r, v in roles.items():
                    if r not in prev.roles and not (ev.type == "cambio" and v in prev.roles.values()):
                        prev.roles[r] = v  # type: ignore[index]
                        changed = True
                if prev.team is None and team:
                    prev.team, changed = team, True
                if changed:
                    self._recount()
                    out.append(("update", prev))
                continue
            self._n += 1
            me = MatchEvent(id=f"ev-{self._n:04d}", t_audio=t, minute=self.clock.minute(t), period=self.clock.period(t),
                            type=ev.type, fine=ev.fine, roles=roles, team=team, confidence=ev.confidence,
                            text=res.text[:200], trace_id=res.trace_id)
            self.events.append(me)
            if ev.type == "gol":
                self._recount()
            out.append(("new", me))
        return out

    # ------------------------------------------------------------------ cambios
    SUB_WINDOW_S = 100.0

    def _valid_sub(self, pid: Optional[str], role: str) -> bool:
        """Con alineación cargada: solo entra quien está en el banquillo y solo sale quien está en el campo."""
        if pid is None or pid not in self.team_of:
            return False
        team = self.team_of[pid]
        if team not in self.on_pitch:
            return True
        return pid in self.bench.get(team, set()) if role == "in" else pid in self.on_pitch[team]

    def _ingest_sub(self, ev, res: NluResult, t: float) -> list[tuple[str, MatchEvent]]:
        a, o = ev.roles.get("actor"), ev.roles.get("out")
        a = a if self._valid_sub(a, "in") else None
        o = o if self._valid_sub(o, "out") else None
        if a and o and self.team_of[a] != self.team_of[o]:
            o = None
        done = {v for e in self.events if e.type == "cambio" and e.status != "discarded" for v in e.roles.values()}
        a = None if a in done else a
        o = None if o in done else o
        out: list[tuple[str, MatchEvent]] = []
        if a and o:
            self._sub_pool = [x for x in self._sub_pool if x["id"] not in (a, o)]
            out.append(("new", self._new_sub(a, o, t, ev, res)))
        else:
            for pid, role in ((a, "in"), (o, "out")):
                if pid and not any(x["id"] == pid for x in self._sub_pool):
                    self._sub_pool.append({"id": pid, "role": role, "t": t, "team": self.team_of[pid]})
        self._sub_pool = [x for x in self._sub_pool if t - x["t"] <= self.SUB_WINDOW_S]
        out += [("new", me) for me in self._pair_pool(t, ev, res)]
        return out

    def _pair_pool(self, t: float, ev, res: NluResult) -> list[MatchEvent]:
        """Empareja "entran A, B y C" con "se van D, E y F": mismo equipo y, entre varios, por posición."""
        made = []
        for team in {x["team"] for x in self._sub_pool}:
            ins = [x for x in self._sub_pool if x["team"] == team and x["role"] == "in"]
            outs = [x for x in self._sub_pool if x["team"] == team and x["role"] == "out"]
            if not ins or not outs:
                continue
            if len(ins) != len(outs) and (len(ins) > 1 or len(outs) > 1) and t - max(x["t"] for x in ins + outs) < 20:
                continue  # lista aún incompleta: se espera a que termine de decirla

            def score(i, o, ki, ko):
                pi, po = self.position.get(i["id"], ("", "")), self.position.get(o["id"], ("", ""))
                return (3 if pi[0] and pi[0] == po[0] else 2 if pi[1] and pi[1] == po[1] else 0) + (0.5 if ki == ko else 0)

            # asignación que maximiza la afinidad de posición; a igualdad, el orden en que se nombraron
            n = min(len(ins), len(outs))
            best = max(permutations(range(len(outs)), n) if len(outs) <= 5 else [tuple(range(n))],
                       key=lambda perm: sum(score(ins[k], outs[perm[k]], k, perm[k]) for k in range(n)))
            for k in range(n):
                i, o = ins[k], outs[best[k]]
                self._sub_pool = [x for x in self._sub_pool if x["id"] not in (i["id"], o["id"])]
                made.append(self._new_sub(i["id"], o["id"], t, ev, res))
        return made

    def _new_sub(self, a: str, o: str, t: float, ev, res: NluResult) -> MatchEvent:
        self._n += 1
        team = self.team_of[a]
        me = MatchEvent(id=f"ev-{self._n:04d}", t_audio=t, minute=self.clock.minute(t), period=self.clock.period(t), type="cambio",
                        fine=ev.fine, roles={"actor": a, "out": o}, team=team, confidence=ev.confidence, text=res.text[:200],
                        trace_id=res.trace_id)
        self.events.append(me)
        if team in self.on_pitch:
            self.on_pitch[team].discard(o)
            self.on_pitch[team].add(a)
            self.bench[team].discard(a)
        return me

    def _is_recap(self, roles: dict[str, str], t: float, text: str) -> bool:
        """¿Se está recordando un gol reciente en vez de cantar uno nuevo?"""
        last = self._last("gol", t, RECAP_S)
        if last is None:
            return False
        a = roles.get("actor")
        same_or_unknown = a is None or last.roles.get("actor") is None or a == last.roles.get("actor")
        return same_or_unknown and not _SUNG.search(text)

    def _team(self, roles: dict[str, str]) -> Optional[str]:
        for r in ("actor", "out", "receiver"):
            if roles.get(r) in self.team_of:
                return self.team_of[roles[r]]
        return roles.get("team_for")

    def _last(self, typ: str, t: float, window: float) -> Optional[MatchEvent]:
        for e in reversed(self.events):
            if e.type == typ and e.status != "discarded" and t - e.t_audio <= window:
                return e
        return None

    def _match(self, typ: str, roles: dict[str, str], team: Optional[str], t: float) -> Optional[MatchEvent]:
        """¿Es repetición o complemento de un hecho reciente?"""
        window = DEDUP_S.get(typ, DEFAULT_DEDUP_S)
        for e in reversed(self.events):
            if t - e.t_audio > window:
                break
            if e.type != typ or e.status == "discarded":
                continue
            if typ == "cambio":
                a, o = roles.get("actor"), roles.get("out")
                ea, eo = e.roles.get("actor"), e.roles.get("out")
                same = (a and a == ea) or (o and o == eo)
                completes = t - e.t_audio <= 45 and ((a and not ea and o is None and eo and a != eo) or
                                                     (o and not eo and a is None and ea and o != ea))
                clash = (a and ea and a != ea) or (o and eo and o != eo)
                if (same or completes) and not clash:
                    return e
                continue
            a, ea = roles.get("actor"), e.roles.get("actor")
            if typ == "gol":
                if a and ea and a != ea:
                    continue
                if (team and e.team and team != e.team) and not (a and ea):
                    continue
                return e
            if a == ea or a is None or ea is None:
                return e
        return None

    def _recount(self) -> None:
        self.score = {self.home: 0, self.away: 0}
        for e in self.events:
            if e.type == "gol" and e.status != "discarded" and e.team in self.score:
                self.score[e.team] += 1

    # ------------------------------------------------------------------ operador
    def edit(self, event_id: str, **changes) -> Optional[MatchEvent]:
        for e in self.events:
            if e.id == event_id:
                for k, v in changes.items():
                    setattr(e, k, v)
                if e.status == "auto":
                    e.status = "edited"
                self._recount()
                return e
        return None

    def add(self, **fields) -> MatchEvent:
        self._n += 1
        me = MatchEvent(id=f"ev-{self._n:04d}", source="operator", status="approved", **fields)
        self.events.append(me)
        self.events.sort(key=lambda e: e.t_audio)
        self._recount()
        return me

    def player_line(self, pid: str) -> dict[str, int]:
        """Lo que lleva un jugador en este partido según la timeline."""
        out: dict[str, int] = {}
        for e in self.events:
            if e.status != "discarded" and e.roles.get("actor") == pid:
                out[e.type] = out.get(e.type, 0) + 1
        return out
