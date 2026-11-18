"""Selector de grafismo (docs/ARCHITECTURE.md §1): de lo entendido a QUÉ enseñar, sin tocar datos.

Emite GraphicRequest (tipo + sujetos + motivo). El servidor los convierte en payloads con el DataProvider.
Principio: en antena, una tarjeta de más molesta más que una de menos. Cada regla tiene prioridad y enfriamiento.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from copilot.match.context import MatchContext
from copilot.types import MatchEvent, NluResult


@dataclass
class GraphicRequest:
    kind: str
    subject: Optional[str] = None  # jugador o equipo
    other: Optional[str] = None
    event_type: Optional[str] = None
    role: Optional[str] = None
    priority: int = 50
    ttl_ms: int = 12000
    trigger: str = ""  # "event:gol", "entity", "query", "pair"
    t: float = 0.0
    text: str = ""
    trace_id: str = ""
    event_id: Optional[str] = None
    key: tuple = ()  # (tipo, modalidad, actor, objetivo) del evento disparador, para evaluar
    auto: bool = False  # sale a antena sin operador (prioridad ≥ AUTO_THRESHOLD); el resto son propuestas

    def dedup_key(self) -> tuple:
        return (self.kind, self.subject, self.other, self.event_type)


#: evento -> (prioridad, ttl ms, enfriamiento s para el mismo sujeto+tipo)
EVENT_RULES: dict[str, tuple[int, int, float]] = {
    "gol": (100, 20000, 150), "roja": (95, 15000, 300), "penalti": (92, 15000, 120), "cambio": (85, 14000, 600),
    "amarilla": (80, 12000, 300), "lesion": (60, 10000, 240), "parada": (62, 10000, 90), "palo": (60, 9000, 90),
    "regate": (52, 9000, 120), "fuera_juego": (48, 8000, 180),
    # "tiro" y "falta" NO generan propuesta: en la 1.ª parte del audio real 4 de 11 y 2 de 5 eran erróneas (se dicen
    # de pasada, en hipótesis o sobre otro jugador). El mapa de tiros y la situación de falta se piden a la carta.
    "corner": (45, 9000, 240), "asistencia": (70, 12000, 150),
}
#: por debajo de esta confianza (sujeto heredado del contexto, no dicho en la frase) no se propone nada salvo
#: los hechos mayores: una propuesta dudosa cada pocos segundos quema al operador.
MIN_CONFIDENCE = 0.8
MAJOR = {"gol", "cambio", "roja", "penalti", "amarilla"}
#: A partir de esta prioridad la tarjeta sale sola; por debajo se PROPONE al operador (cola), que decide.
#: Solo salen solas las que casi nunca fallan: gol, expulsión, penalti, cambio, amarilla y peticiones de dato.
AUTO_THRESHOLD = 80
PAIR_COOLDOWN_S = 300.0
ENTITY_COOLDOWN_S = 240.0
ENTITY_FOCUS_S = 25.0  # nombrado 3 veces en este rato → ficha
ENTITY_FOCUS_N = 3
QUERY_KIND = {"gol": "player_card", "asistencia": "player_card", "tiro": "shot_map", "pase": "pass_network",
              "regate": "situation", "falta": "situation", "amarilla": "situation", "roja": "situation",
              "penalti": "situation", "parada": "situation", "corner": "situation"}


@dataclass
class Selector:
    ctx: MatchContext
    min_priority: int = 0
    _last: dict[tuple, float] = field(default_factory=dict)
    _mentions: dict[str, list[float]] = field(default_factory=dict)
    _pairs: dict[tuple, list[float]] = field(default_factory=dict)
    _carded: set = field(default_factory=set)  # eventos que ya tienen tarjeta

    def forget(self, me: MatchEvent) -> None:
        """Un hecho retirado no debe dejar gastado el enfriamiento ni la marca de 'ya tiene tarjeta'."""
        self._carded.discard(me.id)
        for subject in (me.roles.get("actor"), me.roles.get("victim"), me.team):
            self._last.pop(("ev", me.type, subject), None)

    def _cool(self, key: tuple, t: float, seconds: float) -> bool:
        last = self._last.get(key)
        if last is not None and t - last < seconds:
            return False
        self._last[key] = t
        return True

    def on_result(self, res: NluResult, changes: list[tuple[str, MatchEvent]], t: Optional[float] = None,
                  partial: bool = False) -> list[GraphicRequest]:
        """partial=True: la frase aún no está cerrada. Solo se atienden peticiones de dato y hechos nuevos del partido
        (la ruta rápida); lo que depende de contar menciones espera al final para no contar dos veces."""
        t = (res.t1 or res.t0) if t is None else t
        out: list[GraphicRequest] = []
        base = dict(t=t, text=res.text[:200], trace_id=res.trace_id)

        # 1) peticiones de dato: siempre se atienden
        for it in res.intents:
            if partial:
                break  # una petición se atiende al cerrar la frase (el sujeto puede llegar al final)
            if it.type == "stat_query" and it.subject:
                kind = QUERY_KIND.get(it.topic or "", "player_card")
                if self._cool(("query", it.subject, it.topic), t, 20):
                    out.append(GraphicRequest(kind, it.subject, event_type=it.topic, priority=90, ttl_ms=15000,
                                              trigger="query", **base))

        # 2) hechos nuevos del partido
        for action, me in changes:
            if action == "retract":
                continue
            rule = EVENT_RULES.get(me.type)
            if not rule:
                continue
            prio, ttl, cool = rule
            actor = me.roles.get("actor")
            target = me.roles.get("receiver") or me.roles.get("victim") or me.roles.get("out")
            subject = actor or (me.roles.get("victim") if me.type in ("falta", "penalti") else None) or me.team
            if subject is None:
                continue
            if me.id in self._carded:
                continue  # el mismo hecho no saca dos tarjetas (aunque luego se complete)
            if me.type not in MAJOR and (me.confidence < MIN_CONFIDENCE or not actor):
                continue
            if me.type == "gol" and not actor:
                continue  # se espera a saber quién marca (llega como "update")
            if me.type == "cambio" and not (actor and me.roles.get("out")) and action == "new":
                continue
            if not self._cool(("ev", me.type, subject), t, cool):
                continue
            self._carded.add(me.id)
            key = (me.type, "real", actor or me.roles.get("team_for"), target)
            if me.type == "gol":
                out.append(GraphicRequest("player_card" if actor else "team_card", subject, event_type="gol", priority=prio,
                                          ttl_ms=ttl, trigger="event:gol", event_id=me.id, key=key, **base))
            elif me.type == "cambio":
                if actor and me.roles.get("out"):
                    out.append(GraphicRequest("comparison", actor, me.roles["out"], event_type="cambio", priority=prio,
                                              ttl_ms=ttl, trigger="event:cambio", event_id=me.id, key=key, **base))
                elif actor:
                    out.append(GraphicRequest("player_card", actor, event_type="cambio", priority=prio - 10, ttl_ms=ttl,
                                              trigger="event:cambio", event_id=me.id, key=key, **base))
            elif me.type == "asistencia" and actor and target:
                out.append(GraphicRequest("connection", actor, target, event_type="asistencia", priority=prio, ttl_ms=ttl,
                                          trigger="event:asistencia", event_id=me.id, key=key, **base))
            elif me.type == "tiro" and actor:
                out.append(GraphicRequest("shot_map", actor, event_type="tiro", priority=prio, ttl_ms=ttl,
                                          trigger="event:tiro", event_id=me.id, key=key, **base))
            else:
                role = "actor" if actor else "victim" if me.roles.get("victim") else "team"
                out.append(GraphicRequest("situation", subject, target if actor else None, event_type=me.type, role=role,
                                          priority=prio, ttl_ms=ttl, trigger=f"event:{me.type}", event_id=me.id, key=key, **base))

        if partial:
            for r in out:
                r.auto = r.priority >= AUTO_THRESHOLD
            return [r for r in out if r.auto]  # con un parcial solo sale lo que saldría solo a antena
        # 3) dos jugadores que se buscan: conexión (pases repetidos entre la misma pareja)
        for ev in res.events:
            a, b = ev.roles.get("actor"), ev.roles.get("receiver")
            if ev.type in ("pase", "centro") and ev.modality == "real" and a and b and \
                    self.ctx.team_of.get(a) == self.ctx.team_of.get(b):
                pair = tuple(sorted((a, b)))
                ts = [x for x in self._pairs.get(pair, []) if t - x <= 180] + [t]
                self._pairs[pair] = ts
                if len(ts) >= 2 and self._cool(("pair", pair), t, PAIR_COOLDOWN_S):
                    out.append(GraphicRequest("connection", a, b, event_type="pase", priority=58, ttl_ms=11000,
                                              trigger="pair", key=(ev.type, "real", a, b), **base))

        # 4) un jugador que acapara la narración: su ficha
        shown = {r.subject for r in out} | {r.other for r in out}
        for ent in res.entities:
            if ent.type != "player" or ent.via == "coref":
                continue
            ts = [x for x in self._mentions.get(ent.id, []) if t - x <= ENTITY_FOCUS_S] + [t]
            self._mentions[ent.id] = ts
            if len(ts) >= ENTITY_FOCUS_N and ent.id not in shown and self._cool(("ent", ent.id), t, ENTITY_COOLDOWN_S):
                out.append(GraphicRequest("player_card", ent.id, priority=35, ttl_ms=9000, trigger="entity", **base))
        for r in out:
            r.auto = r.priority >= AUTO_THRESHOLD
        return [r for r in out if r.priority >= self.min_priority]
