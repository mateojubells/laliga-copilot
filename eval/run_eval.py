"""make eval: ejecuta todos los bancos disponibles, imprime la tabla y la guarda en eval/history/.

Los bancos que aún no tienen datos o motor salen como "n/d" (nunca como aprobados).
Objetivos: PROMPT_FABLE.md §6.
"""
from __future__ import annotations

import argparse
import datetime as dt
import importlib
import json
import subprocess
import sys
import time
from pathlib import Path

from eval import metrics

ROOT = Path(__file__).resolve().parent.parent
GOLD = ROOT / "eval" / "gold"
HISTORY = ROOT / "eval" / "history"
DEFAULT_ENGINE = "copilot.nlu.engine:Engine"
FALLBACK_ENGINE = "copilot.nlu.null:NullNlu"

TARGETS = {  # métrica -> (objetivo, mayor_es_mejor)
    "nlu.entities.f1": (0.95, True),
    "nlu.events.f1": (0.85, True),
    "nlu.chains.pct": (75.0, True),
    "match.goals": (1.0, True),
    "match.subs": (1.0, True),
    "match.fp_per_10min": (1.0, False),
    "asr.name_error": (0.05, False),
    "latency.p95_ms": (800.0, False),
    "nlu.latency_p95_ms": (50.0, False),
}


def load_engine(spec: str):
    mod, cls = spec.split(":")
    return getattr(importlib.import_module(mod), cls)()


#: La cifra de aceptación se calcula SOLO con estas fuentes. "catalog" sale del mismo catálogo que se porta al motor
#: (acertar ahí es circular): se informa aparte y no cuenta.
ACCEPTANCE_SOURCES = ("audio", "echoes", "hard")


def load_gold(split: str) -> list[dict]:
    """Filas del split que cuentan: revisadas y sin duda (ARCHITECTURE §8)."""
    from eval.gold_tools import iter_gold
    return [r for r in iter_gold() if r.get("split") == split and r.get("reviewed") and not r.get("doubt")]


def run_nlu(engine, rows: list[dict]) -> tuple[list[dict], list[float]]:
    """Las filas del audio real se pasan EN ORDEN y sin reiniciar el motor (como en directo: el contexto es lo que
    se dijo antes, con sus tiempos). El resto de filas son frases sueltas: motor reiniciado + su `prev`."""
    preds, lat = [], []
    stream = None
    for r in rows:
        if r.get("source") == "audio":
            if stream != r.get("match"):
                engine.reset(match_id=r.get("match"))
                stream = r.get("match")
        else:
            stream = None
            engine.reset(match_id=r.get("match"))
            for prev in r.get("prev") or []:
                engine.analyze(prev, final=True)
        t = time.perf_counter()
        res = engine.analyze(r["text"], t0=r.get("t0", 0.0), t1=r.get("t1", 0.0), final=True)
        lat.append((time.perf_counter() - t) * 1000)
        preds.append(res.model_dump())
    return preds, lat


def pctl(xs: list[float], q: float) -> float | None:
    if not xs:
        return None
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(q * (len(xs) - 1))))]


def optional_bench(module: str, **kw) -> dict:
    """Bancos que viven en eval/scripts/ y pueden no existir todavía: devuelven {métrica: valor}."""
    try:
        return importlib.import_module(module).run(**kw) or {}
    except ModuleNotFoundError as e:
        if e.name != module:  # el banco existe pero le falta una dependencia: eso es un error, no un "n/d"
            raise
        return {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--split", default="dev", choices=["dev", "test"])
    ap.add_argument("--engine", default=None)
    ap.add_argument("--no-save", action="store_true")
    ap.add_argument("--errors", type=int, default=0, help="muestra N errores (solo permitido en dev)")
    a = ap.parse_args()
    if a.errors and a.split == "test":
        print("No se inspeccionan errores de test (ARCHITECTURE §8).", file=sys.stderr)
        return 2

    spec = a.engine or DEFAULT_ENGINE
    from eval.gold_tools import check_manifest
    problems = check_manifest()
    if problems:
        print("[eval] el conjunto de test no coincide con TEST_MANIFEST.sha256:\n  " + "\n  ".join(problems), file=sys.stderr)
        return 3

    try:
        engine = load_engine(spec)
    except ModuleNotFoundError as e:
        if a.engine or e.name != DEFAULT_ENGINE.split(":")[0]:
            raise
        print(f"[eval] motor {spec} no existe todavía; uso {FALLBACK_ENGINE} (línea base nula)")
        spec = FALLBACK_ENGINE
        engine = load_engine(spec)

    out: dict = {"date": dt.datetime.now().isoformat(timespec="minutes"), "split": a.split, "engine": spec,
                 "commit": subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=ROOT, capture_output=True,
                                          text=True).stdout.strip(), "metrics": {}, "detail": {}}
    m = out["metrics"]

    rows = load_gold(a.split)
    if rows:
        preds, lat = run_nlu(engine, rows)
        acc = [i for i, r in enumerate(rows) if r.get("source") in ACCEPTANCE_SOURCES]
        s = metrics.score([rows[i] for i in acc], [preds[i] for i in acc])
        out["detail"]["nlu"] = s
        m["nlu.n"] = s["n"]
        m["nlu.chains.precision"] = s["chains"]["precision"]
        m["nlu.entities.f1"] = s["entities"]["f1"]
        m["nlu.events.f1"] = s["events"]["f1"]
        m["nlu.chains.pct"] = s["chains"]["pct"]
        m["nlu.latency_p95_ms"] = round(pctl(lat, 0.95), 2)
        by_src: dict[str, list[int]] = {}
        for i, r in enumerate(rows):
            by_src.setdefault(r.get("source", "?"), []).append(i)
        out["detail"]["nlu_by_source"] = {
            src: {k: v for k, v in metrics.score([rows[i] for i in ix], [preds[i] for i in ix]).items()
                  if k in ("n", "entities", "events", "chains")} for src, ix in by_src.items()}
        if a.errors:
            shown = 0
            for r, p in zip(rows, preds):
                g, q = metrics.event_set(r["events"]), metrics.event_set(p["events"])
                ge, qe = metrics.entity_set(r["entities"]), metrics.entity_set(p["entities"])
                if g != q or ge != qe:
                    print(f"\n[{r['id']}] {r['text']}\n   oro : {sorted(map(str, ge))} {sorted(map(str, g))}"
                          f"\n   pred: {sorted(map(str, qe))} {sorted(map(str, q))}")
                    shown += 1
                    if shown >= a.errors:
                        break

    # bancos opcionales (se añaden en H1.6-H1.8); cada uno devuelve claves de TARGETS u otras informativas
    for mod in ("eval.scripts.bench_match", "eval.scripts.bench_asr", "eval.scripts.bench_latency",
                "eval.scripts.bench_data"):
        m.update(optional_bench(mod, split=a.split, engine=engine))

    prev = None
    hist = sorted(HISTORY.glob(f"*_{a.split}.json"))
    if hist:
        prev = json.loads(hist[-1].read_text())["metrics"]

    lines = [f"# make eval · {out['date']} · split={a.split} · motor={spec} · commit={out['commit']}", "",
             "| Métrica | Valor | Objetivo | Estado | Anterior |", "|---|---|---|---|---|"]
    keys = list(TARGETS) + [k for k in m if k not in TARGETS]
    for k in keys:
        v = m.get(k)
        tgt = TARGETS.get(k)
        if v is None:
            state, vs = "n/d", "n/d"
        else:
            vs = f"{v:.4g}" if isinstance(v, float) else str(v)
            state = "" if not tgt else ("OK" if (v >= tgt[0] if tgt[1] else v <= tgt[0]) else "NO")
        ts = "" if not tgt else (("≥ " if tgt[1] else "≤ ") + f"{tgt[0]:g}")
        pv = "" if not prev or prev.get(k) is None else (f"{prev[k]:.4g}" if isinstance(prev[k], float) else str(prev[k]))
        lines.append(f"| {k} | {vs} | {ts} | {state} | {pv} |")
    table = "\n".join(lines)
    print(table)

    if a.split == "test":
        out["detail"] = {}  # de test solo se guardan las cifras de cabecera: los desgloses serían una vía de ajuste
    if not a.no_save:
        HISTORY.mkdir(parents=True, exist_ok=True)
        stamp = dt.datetime.now().strftime("%Y-%m-%d_%H%M%S")
        (HISTORY / f"{stamp}_{a.split}.json").write_text(json.dumps(out, ensure_ascii=False, indent=1))
        (HISTORY / f"{stamp}_{a.split}.md").write_text(table + "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
