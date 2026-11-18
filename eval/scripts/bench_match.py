"""Banco del partido real (docs/ARCHITECTURE.md §8): goles y cambios detectados y atribuidos, y tarjetas erróneas.

Reproduce la transcripción de referencia completa. Las cifras se dan por parte: 1.ª parte = dev, 2.ª parte = test.
(Todos los cambios del Barça–Valladolid fueron en la 2.ª parte: en dev no hay cambios que medir.)
"""
from __future__ import annotations

import json
from pathlib import Path

from eval.gold_tools import iter_gold
from eval.metrics import event_key
from eval.scripts import replay

ROOT = Path(__file__).resolve().parents[2]
MATCH = "2024-25/J04/barcelona-valladolid"
#: §8: ±120 s alrededor de cuando se narra. El minuto oficial marca el inicio del minuto y la narración (streamer con
#: retraso de emisión) llega después: la ventana se centra 60 s más tarde → [−60, +180] s respecto al minuto oficial.
WIN_BEFORE, WIN_AFTER = 60.0, 180.0


def expected_t(meta: dict, minute: int, added: int = 0) -> float:
    return meta["kickoff"] + (minute + added) * 60 if minute <= 45 else meta["second_half_start"] + (minute - 45 + added) * 60


def run(split: str = "dev", engine=None, verbose: bool = False, **_) -> dict:
    if engine is None or not hasattr(engine, "gaz"):
        from copilot.nlu.engine import Engine
        try:
            engine = Engine() if engine is None else engine
        except Exception:
            return {}
    ref, meta = replay.load_reference()
    truth = json.loads((ROOT / "eval/gold/barca-valladolid.truth.json").read_text())
    H = meta["first_half_end"]
    in_split = (lambda t: t < H) if split == "dev" else (lambda t: t >= H)
    utts = replay.utterances(ref, H)
    rr = replay.run(engine, MATCH, utts, meta)

    used: set[str] = set()
    goals_ok = goals_n = subs_ok = subs_n = 0
    detail = []
    for g in truth["goals"]:
        te = expected_t(meta, g["minute"], g.get("added") or 0)
        if not in_split(te):
            continue
        goals_n += 1
        hit = next((e for e in rr.events if e.type == "gol" and e.status != "discarded" and e.id not in used
                    and e.roles.get("actor") == g["scorer"] and te - WIN_BEFORE <= e.t_audio <= te + WIN_AFTER), None)
        if hit:
            used.add(hit.id)
            goals_ok += 1
        detail.append(("gol", g["minute"], g["scorer"], bool(hit)))
    for s in truth["substitutions"]:
        te = expected_t(meta, s["minute"])
        if not in_split(te):
            continue
        subs_n += 1
        hit = next((e for e in rr.events if e.type == "cambio" and e.status != "discarded" and e.id not in used
                    and e.roles.get("actor") == s["in"] and e.roles.get("out") == s["out"]
                    and te - WIN_BEFORE <= e.t_audio <= te + WIN_AFTER), None)
        if hit:
            used.add(hit.id)
            subs_ok += 1
        detail.append(("cambio", s["minute"], f"{s['in']} por {s['out']}", bool(hit)))
    false_goals = sum(1 for e in rr.events if e.type == "gol" and e.status != "discarded" and e.id not in used
                      and in_split(e.t_audio) and e.t_audio < meta["full_time"] + 60)

    # tarjetas erróneas en los tramos revisados
    gold = [r for r in iter_gold() if r.get("source") == "audio" and r.get("split") == split and r.get("reviewed")]
    wins = [(a, b) for a, b, _ in meta.get("reviewed_windows", []) if in_split(a)]
    minutes = sum(b - a for a, b in wins) / 60

    def ents_near(t: float, tol: float) -> set:
        return {e["id"] for r in gold if r["t0"] - tol <= t <= r["t1"] + tol for e in r["entities"]}

    def keys_near(t: float, tol: float) -> set:
        return {event_key(e) for r in gold if r["t0"] - tol <= t <= r["t1"] + tol for e in r["events"]}

    cards = [c for c in rr.cards if any(a <= c.t < b for a, b in wins)]
    wrong = []
    for c in cards:
        if c.event_id in used:
            continue  # tarjeta de un gol o cambio que ocurrió de verdad y con el protagonista correcto
        if c.trigger.startswith("event:"):
            near = keys_near(c.t, 5.0)
            ok = c.key in near
        else:
            ids = ents_near(c.t, 3.0)
            ok = c.subject in ids and (c.other is None or c.other in ids or c.trigger != "pair")
        if not ok:
            wrong.append(c)
    retracted = [e for e in rr.retracted if any(a <= e.t_audio < b for a, b in wins)]
    auto = [c for c in cards if c.auto]
    n_wrong = len(wrong) + len(retracted)  # §8: toda tarjeta mostrada (automática o propuesta) y toda retirada
    out = {
        "match.goals": round(goals_ok / goals_n, 3) if goals_n else None,
        "match.subs": round(subs_ok / subs_n, 3) if subs_n else None,
        "match.goals_detail": f"{goals_ok}/{goals_n}",
        "match.subs_detail": f"{subs_ok}/{subs_n}",
        "match.false_goals": false_goals,
        # criterio de aceptación: TODAS las tarjetas (las que salen solas y las propuestas al operador)
        "match.fp_per_10min": round(10 * n_wrong / minutes, 2) if minutes else None,
        "match.cards_per_10min": round(10 * len(cards) / minutes, 2) if minutes else None,
        # desglose: solo las que salen SOLAS a antena (lo que vería el espectador sin operador)
        "match.onair_fp_per_10min": round(10 * (sum(1 for c in wrong if c.auto) + len(retracted)) / minutes, 2) if minutes else None,
        "match.onair_cards_per_10min": round(10 * len(auto) / minutes, 2) if minutes else None,
        "match.reviewed_min": round(minutes, 1),
    }
    if verbose and split == "dev":  # el detalle de la 2.ª parte no se inspecciona
        for d in detail:
            print("  ", d)
        for e in rr.events:
            if e.type in ("gol", "cambio") and in_split(e.t_audio):
                print(f"   {e.t_audio:7.0f}s {e.minute}' {e.type} {e.roles} {e.status} | {e.text[:70]}")
        for c in wrong:
            print(f"   {'ERRÓNEA' if c.auto else 'prop. errónea'} {c.t:7.0f}s {c.kind} {c.subject} {c.other} {c.trigger} {c.key} | {c.text[:80]}")
    return out


if __name__ == "__main__":
    import sys
    print(run(split=sys.argv[1] if len(sys.argv) > 1 else "dev", verbose=True))
