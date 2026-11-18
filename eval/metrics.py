"""Métricas de NLU. Definiciones exactas en docs/ARCHITECTURE.md §8 (no cambiarlas a posteriori)."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Iterable, Optional

from copilot.types import TARGET_ROLES


@dataclass
class PRF:
    tp: int = 0
    fp: int = 0
    fn: int = 0

    def add(self, pred: Counter, gold: Counter) -> None:
        """pred y gold son multiconjuntos: dos eventos idénticos en la frase cuentan dos veces."""
        pred, gold = Counter(pred), Counter(gold)
        inter = sum((pred & gold).values())
        self.tp += inter
        self.fp += sum(pred.values()) - inter
        self.fn += sum(gold.values()) - inter

    @property
    def precision(self) -> float:
        return self.tp / (self.tp + self.fp) if self.tp + self.fp else 0.0

    @property
    def recall(self) -> float:
        return self.tp / (self.tp + self.fn) if self.tp + self.fn else 0.0

    @property
    def f1(self) -> float:
        p, r = self.precision, self.recall
        return 2 * p * r / (p + r) if p + r else 0.0

    def as_dict(self) -> dict:
        return {"p": round(self.precision, 4), "r": round(self.recall, 4), "f1": round(self.f1, 4),
                "tp": self.tp, "fp": self.fp, "fn": self.fn}


def entity_set(entities: Iterable[dict]) -> Counter:
    """Una entidad repetida en la frase cuenta una vez."""
    return Counter({(e["type"], e["id"]) for e in entities})


def event_key(ev: dict) -> tuple:
    """(tipo, modalidad, actor ∥ team_for, receiver ∥ victim ∥ out)."""
    roles = ev.get("roles") or {}
    target: Optional[str] = next((roles[r] for r in TARGET_ROLES if r in roles), None)
    return (ev["type"], ev.get("modality", "real"), roles.get("actor") or roles.get("team_for"), target)


def event_set(events: Iterable[dict]) -> Counter:
    return Counter(event_key(e) for e in events)


def chains_of(events: Iterable[dict]) -> list[tuple]:
    """Cadenas (≥2 eventos) como tuplas de claves ordenadas por 'order'.

    Una cadena con 'order' repetidos no está ordenada: se devuelve marcada como inválida (nunca casa con el oro).
    """
    by: dict[str, list[tuple[int, tuple]]] = defaultdict(list)
    for e in events:
        if e.get("chain"):
            by[e["chain"]].append((e.get("order", 0), event_key(e)))
    out = []
    for c, v in by.items():
        if len(v) < 2:
            continue
        orders = [o for o, _ in v]
        if len(set(orders)) != len(orders):
            out.append(("__orden_invalido__", c))
            continue
        out.append(tuple(k for _, k in sorted(v, key=lambda x: x[0])))
    return out


def score(examples: list[dict], predictions: list[dict]) -> dict:
    """examples/predictions: listas paralelas de dicts con 'entities' y 'events' (formato del oro)."""
    ent, evt, chn = PRF(), PRF(), PRF()
    by_tag: dict[str, PRF] = defaultdict(PRF)
    by_type: dict[str, PRF] = defaultdict(PRF)
    chains_total = chains_ok = 0
    for g, p in zip(examples, predictions):
        ge, pe = entity_set(g.get("entities", [])), entity_set(p.get("entities", []))
        ent.add(pe, ge)
        gv, pv = event_set(g.get("events", [])), event_set(p.get("events", []))
        evt.add(pv, gv)
        for t in g.get("tags", []):
            by_tag[t].add(pv, gv)
        for typ in {k[0] for k in list(gv) + list(pv)}:
            by_type[typ].add(Counter({k: n for k, n in pv.items() if k[0] == typ}),
                             Counter({k: n for k, n in gv.items() if k[0] == typ}))
        # cadenas: igualdad exacta de secuencia y emparejamiento uno a uno (multiconjunto de secuencias)
        gc, pc = Counter(chains_of(g.get("events", []))), Counter(chains_of(p.get("events", [])))
        chn.add(pc, gc)
        matched = pc & gc
        for seq, n in gc.items():
            if 2 <= len(seq) <= 3:
                chains_total += n
                chains_ok += matched.get(seq, 0)
    return {
        "n": len(examples),
        "entities": ent.as_dict(),
        "events": evt.as_dict(),
        "chains": {"ok": chains_ok, "total": chains_total,
                   "pct": round(100 * chains_ok / chains_total, 1) if chains_total else None,
                   "precision": round(chn.precision, 4), "predicted": chn.tp + chn.fp},
        "events_by_type": {k: v.as_dict() for k, v in sorted(by_type.items())},
        "events_by_tag": {k: v.as_dict() for k, v in sorted(by_tag.items())},
    }
