"""Banco de latencia fin de palabra → tarjeta (docs/ARCHITECTURE.md §8).

Usa la ejecución a VELOCIDAD REAL del motor de voz guardada por bench_asr (eval/asr/hyp/<motor>.<split>.json: para
cada palabra, el instante de reloj en que apareció por primera vez, en que quedó estable, y en que se emitió el final)
y pasa esos finales por la tubería real (NLU → partido → selector → constructor del grafismo), cronometrando cada
etapa en esta máquina. No hay transcripción "cacheada" en el sentido de saltarse el motor: los tiempos del motor son
los medidos en directo.

Se informa la latencia de cada tarjeta por tres caminos:
  final   — como funciona hoy el servidor: actúa cuando el motor cierra la frase.
  estable — si se actuara en cuanto la palabra disparadora queda estable (acuerdo local).
  primera — si se actuara en cuanto la palabra disparadora aparece en un parcial (con riesgo de retirada).
El pintado en el navegador se mide aparte (/api/metrics, etapa "paint") y se suma como constante PAINT_MS.

Límite conocido: el "fin de palabra" es el de la alineación del propio motor (t1 de la palabra), no el de la
referencia; un motor que retrasara sus marcas parecería más rápido. Whisper alinea con error típico < 200 ms.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

from copilot.graphics.build import Builder
from copilot.graphics.selector import Selector
from copilot.nlu.normalize import tokenize
from eval.scripts import replay

ROOT = Path(__file__).resolve().parents[2]
HYP = ROOT / "eval" / "asr" / "hyp"
MATCH = "2024-25/J04/barcelona-valladolid"
PAINT_MS = 35.0  # dos fotogramas a 60 Hz; la cifra medida en el navegador sale en /api/metrics


def pct(xs: list[float], q: float) -> float | None:
    if not xs:
        return None
    xs = sorted(xs)
    return round(xs[min(len(xs) - 1, int(round(q * (len(xs) - 1))))], 1)


def measure(cache: dict, engine=None, provider=None) -> dict:
    from copilot.data.composite import CompositeProvider
    from copilot.nlu.engine import Engine
    engine = engine or Engine()
    engine.reset(match_id=MATCH)
    _, meta = replay.load_reference()
    ctx = replay.make_context(MATCH, meta)
    sel = Selector(ctx)
    builder = Builder(provider or CompositeProvider(), ctx)
    rows = []
    stage = {"nlu": [], "select": [], "build": []}
    for win in cache["windows"]:
        for f in win["finals"]:
            words = f.get("words") or []
            if not words:
                continue
            text, spans, pos = "", [], 0
            for w in words:
                spans.append((pos, pos + len(w["w"])))
                text += w["w"] + " "
                pos += len(w["w"]) + 1
            toks = tokenize(text)

            def word_of(tok_i: int) -> dict:
                c = toks[min(tok_i, len(toks) - 1)].start
                return next((w for w, (a, b) in zip(words, spans) if a <= c < b), words[-1])

            t0 = time.perf_counter()
            res = engine.analyze(text.strip(), t0=f["t0"], t1=f["t1"], final=True)
            t1 = time.perf_counter()
            changes = ctx.ingest(res, f["t1"])
            reqs = sel.on_result(res, changes, f["t1"])
            t2 = time.perf_counter()
            stage["nlu"].append((t1 - t0) * 1000)
            stage["select"].append((t2 - t1) * 1000)
            for req in reqs:
                tb = time.perf_counter()
                try:
                    builder.graphic(req)
                except Exception:
                    continue
                build_ms = (time.perf_counter() - tb) * 1000
                stage["build"].append(build_ms)
                # palabra disparadora: la última entre el sujeto de la tarjeta y el evento que la provoca
                idx = [m.span[1] - 1 for m in res.entities if m.id in (req.subject, req.other) and m.span[1] > 0]
                idx += [e.span[1] - 1 for e in res.events if req.key and e.type == req.key[0]]
                trig = word_of(max(idx)) if idx else words[-1]
                pipe = (t2 - t0) * 1000 + build_ms + PAINT_MS
                rows.append({"auto": req.auto, "kind": req.kind, "trigger": req.trigger,
                             "final": (f["emit"] - trig["t1"]) * 1000 + pipe,
                             "stable": ((trig.get("stable") or f["emit"]) - trig["t1"]) * 1000 + pipe,
                             "first": ((trig.get("first") or f["emit"]) - trig["t1"]) * 1000 + pipe})
    out = {"n": len(rows), "engine": cache.get("tag")}
    for path in ("final", "stable", "first"):
        xs = [r[path] for r in rows]
        out[f"{path}_p50"], out[f"{path}_p95"] = pct(xs, 0.5), pct(xs, 0.95)
    for st, xs in stage.items():
        out[f"{st}_p95"] = pct(xs, 0.95)
    return out


def measure_live(cache: dict, provider=None) -> dict:
    """Como funciona el servidor: con cada parcial se adelantan los hechos seguros (ruta rápida) y el final completa.
    Los parciales se reconstruyen con las palabras del final que ya habían aparecido en cada instante (la caché no
    guarda el texto de cada parcial; las palabras que el motor escribió y luego corrigió no se ven: las retiradas
    reales solo se observan en directo, en /api/metrics → status.retracted)."""
    from copilot.data.composite import CompositeProvider
    from copilot.nlu.engine import Engine
    engine = Engine()
    engine.reset(match_id=MATCH)
    _, meta = replay.load_reference()
    ctx = replay.make_context(MATCH, meta)
    sel = Selector(ctx)
    builder = Builder(provider or CompositeProvider(), ctx)
    lat: dict[str, list[float]] = {"auto": [], "proposal": []}
    for win in cache["windows"]:
        for f in win["finals"]:
            words = f.get("words") or []
            if not words:
                continue
            steps = sorted({round(w.get("first") or f["emit"], 3) for w in words if (w.get("first") or f["emit"]) < f["emit"]})
            for tau, final in [(t, False) for t in steps] + [(f["emit"], True)]:
                ws = words if final else [w for w in words if (w.get("first") or f["emit"]) <= tau]
                text = " ".join(w["w"] for w in ws)
                spans, pos = [], 0
                for w in ws:
                    spans.append((pos, pos + len(w["w"])))
                    pos += len(w["w"]) + 1
                toks = tokenize(text)
                t0 = time.perf_counter()
                res = engine.analyze(text, t0=f["t0"], t1=ws[-1]["t1"], final=final)
                changes = ctx.ingest(res, ws[-1]["t1"])
                reqs = sel.on_result(res, changes, ws[-1]["t1"], partial=not final)
                for req in reqs:
                    try:
                        builder.graphic(req)
                    except Exception:
                        continue
                    pipe = (time.perf_counter() - t0) * 1000 + PAINT_MS
                    idx = [m.span[1] - 1 for m in res.entities if m.id in (req.subject, req.other) and m.span[1] > 0]
                    idx += [e.span[1] - 1 for e in res.events if req.key and e.type == req.key[0]]
                    c = toks[min(max(idx), len(toks) - 1)].start if idx and toks else None
                    trig = next((w for w, (a, b) in zip(ws, spans) if c is not None and a <= c < b), ws[-1])
                    lat["auto" if req.auto else "proposal"].append((tau - trig["t1"]) * 1000 + pipe)
    out = {"engine": cache.get("tag")}
    for k, xs in lat.items():
        out[f"{k}_n"], out[f"{k}_p50"], out[f"{k}_p95"] = len(xs), pct(xs, 0.5), pct(xs, 0.95)
    allx = lat["auto"] + lat["proposal"]
    out["all_p50"], out["all_p95"] = pct(allx, 0.5), pct(allx, 0.95)
    return out


def run(split: str = "dev", engine=None, **_) -> dict:
    if split != "dev":
        return {}  # las cachés de voz son de dev; la latencia no depende del contenido
    try:
        from eval.scripts import bench_asr
        best = bench_asr.run(split="dev").get("asr.engine")
    except Exception:
        best = None
    f = HYP / f"{best}.dev.json" if best else None
    if not f or not f.exists():
        return {}
    cache = json.loads(f.read_text())
    m = measure(cache)
    live = measure_live(cache)
    return {"latency.p95_ms": live["auto_p95"], "latency.p50_ms": live["auto_p50"], "latency.auto_cards": live["auto_n"],
            "latency.proposals_p50_ms": live["proposal_p50"], "latency.proposals_p95_ms": live["proposal_p95"],
            "latency.only_finals_p50_ms": m["final_p50"], "latency.only_finals_p95_ms": m["final_p95"], "latency.cards": m["n"],
            "latency.stable_p50_ms": m["stable_p50"], "latency.stable_p95_ms": m["stable_p95"],
            "latency.first_p50_ms": m["first_p50"], "latency.first_p95_ms": m["first_p95"],
            "latency.pipeline_p95_ms": round((m["nlu_p95"] or 0) + (m["select_p95"] or 0) + (m["build_p95"] or 0) + PAINT_MS, 1),
            "latency.engine": m["engine"]}


if __name__ == "__main__":
    for f in sorted(HYP.glob("*.dev.json")):
        c = json.loads(f.read_text())
        if c.get("complete") and not f.name.startswith("ref-"):
            print(json.dumps(measure(c), ensure_ascii=False))
            print("   vivo:", json.dumps(measure_live(c), ensure_ascii=False))
