"""Banco de los motores de voz (docs/ARCHITECTURE.md §8, "ASR WER" y "ASR nombres (NER-ER)").

  python -m eval.scripts.bench_asr --engine mlx-whisper --cfg model=turbo,step_ms=1000 --tag whisper-turbo-1000 --split dev
  python -m eval.scripts.bench_asr --rescore            # recalcula métricas de todas las cachés sin ejecutar motores
  python -m eval.scripts.bench_asr --list

`run(split, engine)` (lo llama `make eval`) NO ejecuta motores: lee eval/asr/hyp/<tag>.<split>.json y devuelve
{"asr.name_error", "asr.wer", "asr.word_latency_p95_ms", "asr.engine", ...} del mejor motor, o {} si no hay caché.

Qué se mide (solo tramos `reviewed_windows` del split; filas del oro revisadas y sin `doubt`):
  * WER: jiwer, texto normalizado (minúsculas, sin tildes ni puntuación, números 0-30 a cifras) entre las palabras
    finales del motor cuyo punto medio cae en una fila del oro (±0,5 s) y `ref_text` de esas filas; un texto por tramo.
  * NER-ER = (S + D + I) / N_ref, POR FILA del oro (el oro lista cada entidad una vez por fila, así que la hipótesis
    también cuenta una vez por (fila, id); las menciones de la hipótesis se asignan a la fila cuyo intervalo
    [t0-1,5 s, t1+1,5 s] las contiene). Referencia: `entities` player/team/coach de las filas revisadas y sin duda.
    Hipótesis: palabras finales con diccionario EXACTO (name, known_as y aliases de jugadores y equipos de las dos
    plantillas + entrenadores; sin asr_aliases, sin aliases_extra, sin fonética). N-gramas de hasta 4 palabras, el más
    largo primero. Un alias que apunta a más de una entidad se descarta; un alias de una palabra de JUGADOR que es
    palabra corriente (gazetteer.is_common, que sale de comentarios reales: incluye "Gavi", "Lewandowski"...) solo cuenta
    si va con mayúscula inicial, salvo que el motor no escriba mayúsculas en absoluto (Vosk).
    Por fila: acierto = mismo id; con lo que sobra, S = parejas de ids distintos, D = referencia sin pareja,
    I = hipótesis sin pareja. Los tiempos por palabra solo se usan para asignar la mención a la fila (±1,5 s).
  * name_error_linked: igual pero la hipótesis se resuelve con copilot.nlu.engine.Engine (alias_extra, asr_aliases y
    fonética incluidos) frase final a frase final; el tiempo de cada mención se interpola por posición de palabra.
  * Latencia por palabra: palabras finales de longitud >= 4 emparejadas (difflib) con una palabra de ref.json;
    `instante de reloj de primera aparición` (en cualquier parcial, mismo texto normalizado y punto medio a ±0,6 s)
    menos `t1` de la palabra de referencia; igual para "estable" (dentro de stable_upto o en un final). El reloj es el
    del audio simulado: t_audio = inicio del tramo + (reloj - inicio) * speed, medido DESPUÉS de que feed() devuelva.
    Se ignoran las palabras de los últimos 3 s de cada tramo (efecto del flush de fin de fuente).
  * RTF = tiempo ocupado en feed()+flush() / audio; RAM = ru_maxrss del proceso (un proceso por ejecución).
"""
from __future__ import annotations

import argparse
import difflib
import json
import re
import resource
import sys
import time
from pathlib import Path
from typing import Any, Optional

ROOT = Path(__file__).resolve().parents[2]
ASR_DIR = ROOT / "eval" / "asr"
HYP_DIR = ASR_DIR / "hyp"
WAV = ASR_DIR / "barca-valladolid.16k.wav"
META = ASR_DIR / "barca-valladolid.meta.json"
REF = ASR_DIR / "barca-valladolid.ref.json"
GOLD_DIR = ROOT / "eval" / "gold"
MATCH_ID = "2024-25/J04/barcelona-valladolid"
TEAMS = ("barcelona", "valladolid")
MARGIN = 0.5  # s alrededor de cada fila del oro para asignar palabras del motor a la fila
TAIL_IGNORE = 3.0  # s finales de cada tramo excluidos de la latencia

_NUMS = {w: str(i) for i, w in enumerate(
    "cero uno dos tres cuatro cinco seis siete ocho nueve diez once doce trece catorce quince dieciseis diecisiete "
    "dieciocho diecinueve veinte veintiuno veintidos veintitres veinticuatro veinticinco veintiseis veintisiete "
    "veintiocho veintinueve treinta".split())}


# ------------------------------------------------------------------ normalización
def norm_text(s: str) -> list[str]:
    from copilot.nlu.normalize import strip
    s = re.sub(r"[^a-z0-9 ]+", " ", strip(s))
    return [_NUMS.get(t, t) for t in s.split()]


def norm_tok(w: str) -> str:
    t = norm_text(w)
    return "".join(t)


# ------------------------------------------------------------------ datos
def meta() -> dict:
    return json.loads(META.read_text(encoding="utf-8"))


def windows(split: str) -> list[tuple[float, float]]:
    m = meta()
    fh = m["first_half_end"]
    ws = [(a, b) for a, b, _ in m["reviewed_windows"]]
    return [w for w in ws if (w[1] <= fh + 0.01 if split == "dev" else w[0] >= fh - 0.01)]


def gold_rows(split: str) -> list[dict]:
    """Filas revisadas y sin duda del split. Solo se abre el fichero del split pedido."""
    f = GOLD_DIR / f"barca-valladolid.{split}.jsonl"
    rows = []
    for line in f.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("//"):
            r = json.loads(line)
            if r.get("reviewed") and not r.get("doubt") and r.get("source") == "audio":
                rows.append(r)
    return rows


def rows_in_window(rows: list[dict], w: tuple[float, float]) -> list[dict]:
    return [r for r in rows if r["t0"] >= w[0] - 1.0 and r["t1"] <= w[1] + 1.0]


_REF: dict | None = None


def ref_words() -> tuple[dict[int, dict], list[dict]]:
    global _REF
    if _REF is None:
        _REF = json.loads(REF.read_text(encoding="utf-8"))
    segs = {s["id"]: s for s in _REF["segments"]}
    return segs, _REF["segments"]


# ------------------------------------------------------------------ diccionario exacto
def exact_dictionary() -> dict[tuple[str, ...], tuple[str, str, bool]]:
    """{tupla de tokens normalizados: (tipo, id, es_alias_corriente_de_una_palabra)} sin ambiguos."""
    from copilot.nlu.gazetteer import is_common, season, slug
    raw: dict[tuple[str, ...], set[tuple[str, str]]] = {}

    def add(alias: str, typ: str, ident: str) -> None:
        toks = tuple(norm_text(alias))
        if toks:
            raw.setdefault(toks, set()).add((typ, ident))

    for t in season()["teams"]:
        if t["id"] not in TEAMS:
            continue
        for a in {t["name"], t["short"], *t.get("aliases", [])}:
            add(a, "team", t["id"])
        if t.get("coach"):
            cid = "coach/" + slug(t["coach"])
            add(t["coach"], "coach", cid)
            add(t["coach"].split()[-1], "coach", cid)
        for p in t["players"]:
            for a in {p["name"], p["known_as"], *p.get("aliases", [])}:
                add(a, "player", p["id"])
    out = {}
    for toks, ids in raw.items():
        if len(ids) != 1:
            continue  # alias ambiguo entre entidades: no se puede resolver con diccionario exacto
        typ, ident = next(iter(ids))
        out[toks] = (typ, ident, typ == "player" and len(toks) == 1 and is_common(toks[0]))
    return out


def hyp_mentions(words: list[dict], cased: Optional[bool] = None) -> list[dict]:
    """Menciones por n-gramas (<=4, el más largo primero, sin solapes) en una lista de palabras con t0/t1.
    `cased`: el motor escribe mayúsculas (si no se indica, se detecta: alguna palabra empieza en mayúscula). Solo
    entonces se exige la mayúscula a los alias corrientes de una palabra; un motor en minúsculas (Vosk) no la puede dar."""
    D = exact_dictionary()
    if cased is None:
        cased = any(w["w"][:1].isupper() for w in words)
    toks = [norm_tok(w["w"]) for w in words]
    out, i = [], 0
    while i < len(words):
        hit = None
        for n in (4, 3, 2, 1):
            if i + n > len(words):
                continue
            key = tuple(t for t in toks[i:i + n])
            if "" in key:
                continue
            if key in D:
                typ, ident, common1 = D[key]
                if common1 and cased and not words[i]["w"][:1].isupper():
                    continue
                hit = (n, typ, ident)
                break
        if hit:
            n, typ, ident = hit
            ws = words[i:i + n]
            out.append({"type": hit[1], "id": hit[2], "t": (ws[0]["t0"] + ws[-1]["t1"]) / 2})
            i += n
        else:
            i += 1
    return out


def ref_mentions(rows: list[dict]) -> list[dict]:
    segs, _ = ref_words()
    out = []
    for r in rows:
        seq = []
        for sid in r.get("segs", []):
            s = segs.get(sid)
            if s:
                seq += [(norm_tok(w["w"]), w["t0"], w["t1"]) for w in s["words"]]
        ptr = 0
        for e in r["entities"]:
            if e["type"] not in ("player", "team", "coach"):
                continue
            toks = norm_text(e.get("surface") or "")
            found = None
            for start in (ptr, 0) if toks else ():
                for i in range(start, len(seq) - len(toks) + 1):
                    if [x[0] for x in seq[i:i + len(toks)]] == toks:
                        found = i
                        break
                if found is not None:
                    break
            if found is not None:
                t = (seq[found][1] + seq[found + len(toks) - 1][2]) / 2
                ptr = found + len(toks)
            else:
                t = (r["t0"] + r["t1"]) / 2
            out.append({"type": e["type"], "id": e["id"], "t": t, "row": r["id"]})
    return out


def row_for(t: float, rows: list[dict], slack: float = 1.5) -> Optional[dict]:
    """Fila del oro cuyo intervalo [t0-slack, t1+slack] contiene t (la más cercana a su intervalo si hay varias)."""
    best, bd = None, 1e9
    for r in rows:
        d = max(r["t0"] - t, t - r["t1"], 0.0)
        if d <= slack and d < bd:
            best, bd = r, d
    return best


def match_mentions(rows: list[dict], hyp: list[dict]) -> dict[str, int]:
    """NER-ER por filas. El oro lista cada entidad UNA vez por fila, así que la hipótesis también se cuenta una vez por
    (fila, id): sus menciones se asignan a la fila cuyo intervalo [t0-1,5 s, t1+1,5 s] las contiene (la más cercana) y las
    que caen fuera de toda fila se ignoran. Por fila: acierto = id en ambos; con lo que sobra de cada lado, S = parejas
    (otra entidad en ese hueco), D = referencia sin pareja, I = hipótesis sin pareja."""
    ref = {r["id"]: {e["id"] for e in r["entities"] if e["type"] in ("player", "team", "coach")} for r in rows}
    hs: dict[str, set] = {r["id"]: set() for r in rows}
    for m in hyp:
        r = row_for(m["t"], rows)
        if r:
            hs[r["id"]].add(m["id"])
    S = D = I = N = ok = 0
    for rid, R in ref.items():
        H = hs[rid]
        hit = R & H
        r_rest, h_rest = len(R - hit), len(H - hit)
        s_ = min(r_rest, h_rest)
        S += s_
        D += r_rest - s_
        I += h_rest - s_
        N += len(R)
        ok += len(hit)
    return {"S": S, "D": D, "I": I, "N": N, "ok": ok}


def ner_er(rows: list[dict], hyp: list[dict]) -> float:
    m = match_mentions(rows, hyp)
    return (m["S"] + m["D"] + m["I"]) / max(1, m["N"])


# ------------------------------------------------------------------ puntuación de una caché
def _in_rows(t: float, rows: list[dict]) -> bool:
    return any(r["t0"] - MARGIN <= t <= r["t1"] + MARGIN for r in rows)


def resolve_finals(finals: list[dict]) -> list[dict]:
    """Motores en dos pasadas: un final de la 2ª pasada (corrección) sustituye a los de la 1ª que cubre en >= 50 %."""
    p2 = [f for f in finals if f.get("pass", 1) == 2]
    if not p2:
        return finals
    keep = []
    for f in finals:
        if f.get("pass", 1) == 1:
            dur = max(1e-6, f["t1"] - f["t0"])
            cov = sum(max(0.0, min(f["t1"], g["t1"]) - max(f["t0"], g["t0"])) for g in p2)
            if cov / dur >= 0.5:
                continue
        keep.append(f)
    return sorted(keep, key=lambda f: f["t0"])


def finals_by_window(cache: dict) -> list[tuple[tuple[float, float], list[dict]]]:
    return [((w["w"][0], w["w"][1]), resolve_finals(w["finals"])) for w in cache["windows"]]


def _pct(xs: list[float], q: float) -> Optional[float]:
    if not xs:
        return None
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(round(q * (len(xs) - 1))))]


def score(cache: dict, split: str) -> dict[str, Any]:
    import jiwer
    rows_all = gold_rows(split)
    refs, hyps = [], []
    all_rows, hyp_m, hyp_linked = [], [], []
    lat_first, lat_stable = [], []
    linked = _make_linker()
    _, all_segs = ref_words()
    for (a, b), finals in finals_by_window(cache):
        rows = rows_in_window(rows_all, (a, b))
        if not rows:
            continue
        refs.append(" ".join(" ".join(norm_text(r["ref_text"])) for r in rows))
        words = [w for f in finals for w in f["words"] if _in_rows((w["t0"] + w["t1"]) / 2, rows)]
        hyps.append(" ".join(t for w in words for t in norm_text(w["w"])))
        all_rows += rows
        hyp_m += [m for m in hyp_mentions(words)]
        if linked:
            hyp_linked += linked(finals, rows)
        # latencia
        rw = [(norm_tok(w["w"]), w["t1"]) for s in all_segs if a <= s["t0"] < b for w in s["words"]]
        hw = [w for f in finals for w in f["words"]]
        sm = difflib.SequenceMatcher(None, [x[0] for x in rw], [norm_tok(w["w"]) for w in hw], autojunk=False)
        for blk in sm.get_matching_blocks():
            for k in range(blk.size):
                w = hw[blk.b + k]
                if len(norm_tok(w["w"])) < 4 or "first" not in w or w["t1"] > b - TAIL_IGNORE:
                    continue
                t1ref = rw[blk.a + k][1]
                lat_first.append(w["first"] - t1ref)
                lat_stable.append(w["stable"] - t1ref)
    wer = jiwer.wer(refs, hyps) if refs else None
    out: dict[str, Any] = {"wer": wer, "name_error": ner_er(all_rows, hyp_m), "ner": match_mentions(all_rows, hyp_m)}
    out["n_ref_mentions"] = out["ner"]["N"]
    if linked:
        out["name_error_linked"] = ner_er(all_rows, hyp_linked)
        out["ner_linked"] = match_mentions(all_rows, hyp_linked)
    for k, v in (("first", lat_first), ("stable", lat_stable)):
        out[f"lat_{k}_p50_ms"] = None if not v else round(_pct(v, 0.5) * 1000)
        out[f"lat_{k}_p95_ms"] = None if not v else round(_pct(v, 0.95) * 1000)
    out["lat_n"] = len(lat_first)
    out["rtf"] = cache["stats"].get("rtf")
    out["ram_mb"] = cache["stats"].get("max_rss_mb")
    out["speed"] = cache.get("speed")
    out["audio_s"] = cache["stats"].get("audio_s")
    return out


def _make_linker():
    """Resuelve la hipótesis con el motor NLU completo (entidades de tipo player/team/coach con span)."""
    try:
        from copilot.nlu.engine import Engine
        from copilot.nlu.normalize import tokenize
    except Exception:  # pragma: no cover
        return None
    eng = Engine()

    def link(finals: list[dict], rows: list[dict]) -> list[dict]:
        eng.reset(match_id=MATCH_ID)
        out = []
        for f in finals:
            ws = f["words"]
            if not ws or not any(_in_rows((w["t0"] + w["t1"]) / 2, rows) for w in ws):
                continue
            res = eng.analyze(f["text"], t0=f["t0"], t1=f["t1"], final=True)
            ntok = len(tokenize(f["text"]))
            for e in res.entities:
                if e.type not in ("player", "team", "coach") or e.span == (0, 0):
                    continue
                i0, i1 = e.span
                # posición de palabra interpolada (los tokens del NLU parten palabras con guion, etc.)
                a = ws[min(len(ws) - 1, int(i0 * len(ws) / max(1, ntok)))]
                b = ws[min(len(ws) - 1, max(0, int(max(i0, i1 - 1) * len(ws) / max(1, ntok))))]
                t = (a["t0"] + b["t1"]) / 2
                if _in_rows(t, rows):
                    out.append({"type": e.type, "id": e.id, "t": t})
        return out
    return link


# ------------------------------------------------------------------ caché
def cache_path(tag: str, split: str) -> Path:
    return HYP_DIR / f"{tag}.{split}.json"


def load_caches(split: str) -> list[dict]:
    out = []
    for f in sorted(HYP_DIR.glob(f"*.{split}.json")):
        try:
            out.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            continue
    return out


def _headline(c: dict) -> dict:
    m = c["metrics"]
    return {"asr.name_error": m["name_error"], "asr.wer": m["wer"],
            "asr.name_error_linked": m.get("name_error_linked"),
            "asr.word_latency_p95_ms": m.get("lat_first_p95_ms"),
            "asr.word_latency_stable_p95_ms": m.get("lat_stable_p95_ms"),
            "asr.engine": c["tag"]}


def run(split: str = "dev", engine: Any = None, **kw) -> dict:
    """Lo llama `make eval`: lee cachés (no ejecuta motores). `engine` (si es str) fuerza una caché concreta; el motor NLU
    que pasa run_eval se ignora."""
    caches = [c for c in load_caches(split) if c.get("complete") and c.get("metrics") and not c.get("ceiling")]
    if isinstance(engine, str):
        caches = [c for c in caches if c["tag"] == engine]
    if not caches:
        return {}
    # una medida con WER > 1 no es fiable (finales duplicados): no puede ser la cabecera
    caches = [c for c in caches if c["metrics"]["wer"] <= 1.0] or caches
    # el motor recomendado es el que menos nombres falla tras el enlazador (lo que ve el producto)
    best = min(caches, key=lambda c: (c["metrics"].get("name_error_linked", c["metrics"]["name_error"]), c["metrics"]["wer"]))
    return {k: v for k, v in _headline(best).items() if v is not None}


# ------------------------------------------------------------------ ejecución de un motor
def _parse_cfg(s: str) -> dict:
    cfg = {}
    for kv in filter(None, s.split(",")):
        k, v = kv.split("=", 1)
        for cast in (int, float):
            try:
                v = cast(v)
                break
            except ValueError:
                pass
        if v in ("true", "false"):
            v = v == "true"
        if "." in k:  # slow_cfg.model=small -> {"slow_cfg": {"model": "small"}}
            a, b = k.split(".", 1)
            cfg.setdefault(a, {})[b] = v
        else:
            cfg[k] = v
    return cfg


def run_engine(engine_name: str, cfg: dict, split: str, speed: float, tag: str, only: Optional[list[int]] = None,
               max_seconds: Optional[float] = None) -> dict:
    import numpy as np  # noqa: F401
    from copilot.asr import factory, vocab
    from copilot.asr.streaming import iter_blocks, norm_word, read_wav

    eng = factory.create(engine_name, **cfg)
    prompt, vocabulary = vocab.build(MATCH_ID)
    t_load = time.monotonic()
    eng.start(prompt=prompt, vocabulary=vocabulary, language="es")
    load_s = time.monotonic() - t_load
    out_windows, busy, audio_total = [], 0.0, 0.0
    for wi, (a, b) in enumerate(windows(split)):
        if only is not None and wi not in only:
            continue
        if max_seconds:
            b = min(b, a + max_seconds)
        audio = read_wav(WAV, a, b)
        audio_total += len(audio) / 16000
        emissions: list[tuple[float, Any]] = []
        wall0 = time.monotonic()
        clock = lambda: a + (time.monotonic() - wall0) * speed  # noqa: E731
        for pcm, t in iter_blocks(audio, a, speed=speed, realtime=True):
            t_in = time.monotonic()
            res = eng.feed(pcm, t)
            busy += time.monotonic() - t_in
            now = clock()
            emissions += [(now, tr) for tr in res]
        t_in = time.monotonic()
        res = eng.flush()
        busy += time.monotonic() - t_in
        now = clock()
        emissions += [(now, tr) for tr in res]
        out_windows.append({"w": [a, b], "finals": _annotate(emissions, norm_word),
                            "n_partials": sum(1 for _, t in emissions if not t.final)})
        print(f"[{tag}] tramo {wi} {a:.0f}-{b:.0f} s: {len(out_windows[-1]['finals'])} finales, "
              f"{out_windows[-1]['n_partials']} parciales, ocupado {busy:.0f} s", flush=True)
    stats = {"audio_s": round(audio_total, 1), "busy_s": round(busy, 1), "rtf": round(busy / max(1e-9, audio_total), 3),
             "load_s": round(load_s, 1), "max_rss_mb": round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 2**20)}
    eng.close()
    complete = only is None and not max_seconds
    return {"tag": tag, "engine": engine_name, "engine_name": getattr(eng, "name", engine_name), "config": cfg,
            "split": split, "speed": speed, "complete": complete, "stats": stats,
            "word_time_tol": 1.5, "windows": out_windows, "date": time.strftime("%Y-%m-%d %H:%M:%S")}


def _annotate(emissions: list[tuple[float, Any]], norm_word) -> list[dict]:
    """Finales del tramo con, por palabra, el reloj (audio simulado) de primera aparición y de estabilidad."""
    idx: dict[str, list[tuple[float, float, bool]]] = {}
    for now, tr in emissions:
        for i, w in enumerate(tr.words):
            k = norm_word(w.w)
            if k:
                idx.setdefault(k, []).append((now, (w.t0 + w.t1) / 2, tr.final or i < tr.stable_upto))
    finals = []
    for now, tr in emissions:
        if not tr.final:
            continue
        ws = []
        for w in tr.words:
            k, mid = norm_word(w.w), (w.t0 + w.t1) / 2
            c = [(t, st) for t, m, st in idx.get(k, []) if abs(m - mid) <= 0.6]
            d = {"w": w.w, "t0": round(w.t0, 3), "t1": round(w.t1, 3), "p": round(w.p, 3)}
            if c:
                d["first"] = round(min(t for t, _ in c), 3)
                d["stable"] = round(min([t for t, st in c if st] or [now]), 3)
            ws.append(d)
        finals.append({"segment_id": tr.segment_id, "engine": tr.engine, "pass": int(tr.ts.get("pass", 1)),
                       "t0": round(tr.t0, 3), "t1": round(tr.t1, 3), "text": tr.text, "emit": round(now, 3), "words": ws})
    return finals


def rescore(tag: Optional[str] = None) -> None:
    for f in sorted(HYP_DIR.glob("*.json")):
        c = json.loads(f.read_text(encoding="utf-8"))
        if tag and c["tag"] != tag:
            continue
        c["metrics"] = score(c, c["split"])
        f.write_text(json.dumps(c, ensure_ascii=False), encoding="utf-8")
        m = c["metrics"]
        print(f"{c['tag']:<34} {c['split']} WER {m['wer']:.3f} NER {m['name_error']:.3f} "
              f"linked {m.get('name_error_linked', float('nan')):.3f} "
              f"lat1 {m['lat_first_p50_ms']}/{m['lat_first_p95_ms']} lats {m['lat_stable_p50_ms']}/{m['lat_stable_p95_ms']} "
              f"RTF {m['rtf']} RAM {m['ram_mb']} MB")


def ref_ceiling(split: str = "dev") -> dict:
    """Techo: la propia transcripción de referencia (Whisper large-v3 offline con prompt) por el mismo cálculo."""
    _, segs = ref_words()
    wins = []
    for a, b in windows(split):
        finals = [{"segment_id": s["id"], "engine": "ref-whisper-large-v3", "pass": 1, "t0": s["t0"], "t1": s["t1"],
                   "text": s["text"], "emit": s["t1"], "words": [dict(w) for w in s["words"]]}
                  for s in segs if a <= s["t0"] < b]
        wins.append({"w": [a, b], "finals": finals})
    c = {"tag": "ref-whisper-large-v3", "engine": "reference", "config": {}, "split": split, "speed": None, "complete": True,
         "ceiling": True, "stats": {"rtf": None, "max_rss_mb": None, "audio_s": None}, "windows": wins}
    c["metrics"] = score(c, split)
    return c


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine")
    ap.add_argument("--cfg", default="")
    ap.add_argument("--tag")
    ap.add_argument("--split", default="dev", choices=["dev", "test"])
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--windows", help="índices separados por comas (caché parcial, no cuenta para make eval)")
    ap.add_argument("--max-seconds", type=float)
    ap.add_argument("--rescore", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--ref-ceiling", action="store_true", help="puntúa la propia referencia (techo) y guarda su caché")
    a = ap.parse_args()
    HYP_DIR.mkdir(parents=True, exist_ok=True)
    if a.list:
        for c in load_caches(a.split):
            print(c["tag"], c.get("complete"), c.get("speed"), c.get("config"))
        return 0
    if a.ref_ceiling:
        c = ref_ceiling(a.split)
        cache_path(c["tag"], a.split).write_text(json.dumps(c, ensure_ascii=False), encoding="utf-8")
        print(json.dumps(c["metrics"], ensure_ascii=False, indent=1))
        return 0
    if a.rescore:
        rescore(a.tag)
        return 0
    if not a.engine:
        ap.error("--engine es obligatorio")
    cfg = _parse_cfg(a.cfg)
    tag = a.tag or a.engine
    only = [int(x) for x in a.windows.split(",")] if a.windows else None
    c = run_engine(a.engine, cfg, a.split, a.speed, tag, only, a.max_seconds)
    p = cache_path(tag + ("" if c["complete"] else ".partial"), a.split)
    p.write_text(json.dumps(c, ensure_ascii=False), encoding="utf-8")  # primero la caché: no se pierde la ejecución
    c["metrics"] = score(c, a.split)
    p.write_text(json.dumps(c, ensure_ascii=False), encoding="utf-8")
    m = c["metrics"]
    print(json.dumps({k: v for k, v in m.items()}, ensure_ascii=False, indent=1))
    print("caché:", p)
    return 0


if __name__ == "__main__":
    sys.exit(main())
