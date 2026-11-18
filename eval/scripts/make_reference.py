"""Transcripción de referencia con Whisper (MLX) en tramos reanudables.

Uso:  .venv/bin/python -m eval.scripts.make_reference [--model REPO] [--start S] [--end S]
                                                     [--chunk 300] [--overlap 5] [--out-dir eval/asr]

Cada tramo se guarda en <out-dir>/ref_chunks/NNN.json y se salta si ya existe con los mismos parámetros.
Después se unen resolviendo el solape y se escribe barca-valladolid.ref.json y .ref.txt.
"""
from __future__ import annotations

import argparse
import json
import re
import resource
import sys
import time
import wave
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
AUDIO = "barca-valladolid.16k.wav"
STEM = "barca-valladolid"
SR = 16000
DEFAULT_MODEL = "mlx-community/whisper-large-v3-mlx"

PROMPT = (
    "Partido de LaLiga: FC Barcelona contra Real Valladolid. Barça: Ter Stegen, Koundé, Cubarsí, "
    "Íñigo Martínez, Balde, Marc Bernal, Casadó, Pedri, Dani Olmo, Lamine Yamal, Raphinha, Lewandowski, "
    "Ferran Torres, Fermín, Gavi, Eric García, Gerard Martín, Héctor Fort, Pau Víctor, Flick. "
    "Valladolid: Hein, Luis Pérez, Javi Sánchez, Boyomo, Lucas Rosa, Juric, Kike Pérez, Raúl Moro, "
    "Amallah, Iván Sánchez, Sylla, Marcos André, Latasa, Pezzolano."
)

# Frases típicas que Whisper inventa en silencios o música (comparación sobre texto normalizado).
HALLUCINATION_PHRASES = [
    "subtitulos realizados por la comunidad de amara",
    "subtitulos por la comunidad de amara",
    "amara org",
    "gracias por ver el video",
    "gracias por ver el episodio",
    "gracias por ver",
    "suscribete al canal",
    "suscribete",
    "no olvides suscribirte",
    "subtitulado por",
    "subtitulos de",
    "traduccion y subtitulos",
    "musica",
    "aplausos",
    "fin del video",
    "hasta la proxima",
    "www ",
]


def norm(s: str) -> str:
    s = s.lower()
    for a, b in zip("áéíóúüñ", "aeiouun"):
        s = s.replace(a, b)
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", s)).strip()


def load_wav(path: Path, t0: float, t1: float) -> np.ndarray:
    with wave.open(str(path), "rb") as w:
        assert w.getframerate() == SR and w.getnchannels() == 1 and w.getsampwidth() == 2
        w.setpos(int(t0 * SR))
        raw = w.readframes(int((t1 - t0) * SR))
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0


def wav_duration(path: Path) -> float:
    with wave.open(str(path), "rb") as w:
        return w.getnframes() / w.getframerate()


def maxrss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / (1024 * 1024)  # bytes en macOS


def simplify(res: dict, offset: float) -> list[dict]:
    """Segmentos de Whisper con tiempos absolutos."""
    segs = []
    for s in res["segments"]:
        words = []
        for w in s.get("words", []):
            words.append({
                "w": w["word"].strip(),
                "t0": round(w["start"] + offset, 3),
                "t1": round(w["end"] + offset, 3),
                "p": round(float(w.get("probability", 0.0)), 3),
            })
        segs.append({
            "t0": round(s["start"] + offset, 3),
            "t1": round(s["end"] + offset, 3),
            "text": s["text"].strip(),
            "avg_logprob": round(float(s.get("avg_logprob", 0.0)), 3),
            "no_speech_prob": round(float(s.get("no_speech_prob", 0.0)), 3),
            "compression_ratio": round(float(s.get("compression_ratio", 0.0)), 3),
            "words": words,
        })
    return segs


def run_chunks(args, out_dir: Path, audio_path: Path, total: float) -> list[dict]:
    import mlx_whisper

    chunks_dir = out_dir / "ref_chunks"
    chunks_dir.mkdir(parents=True, exist_ok=True)
    start = args.start
    end = min(args.end if args.end else total, total)
    n_first = int(start // args.chunk)
    metas = []
    s = start
    i = n_first
    while s < end - 1e-6:
        core_end = min(s + args.chunk, end)
        a_end = min(core_end + args.overlap, total)
        params = {"model": args.model, "start": s, "core_end": core_end, "audio_end": a_end,
                  "chunk": args.chunk, "overlap": args.overlap, "prompt": PROMPT}
        f = chunks_dir / f"{i:03d}.json"
        if f.exists():
            d = json.loads(f.read_text())
            if d.get("params") == params:
                print(f"[{i:03d}] ya existe, salto", flush=True)
                metas.append(d)
                s, i = core_end, i + 1
                continue
        t = time.time()
        audio = load_wav(audio_path, s, a_end)
        res = mlx_whisper.transcribe(
            audio, path_or_hf_repo=args.model, language="es", word_timestamps=True,
            condition_on_previous_text=False, temperature=0, initial_prompt=PROMPT, verbose=None,
        )
        el = time.time() - t
        d = {"params": params, "elapsed": round(el, 2), "maxrss_mb": round(maxrss_mb()),
             "segments": simplify(res, s)}
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(d, ensure_ascii=False))
        tmp.replace(f)
        dur = a_end - s
        print(f"[{i:03d}] {s:7.1f}-{a_end:7.1f}s  {el:6.1f}s  RTF={el/dur:.3f}  "
              f"segs={len(d['segments'])}  rss={maxrss_mb():.0f}MB", flush=True)
        metas.append(d)
        s, i = core_end, i + 1
    return metas


def merge(metas: list[dict]) -> list[dict]:
    """Une tramos: la palabra se queda con el tramo en el que cae más lejos del borde
    (corte en el punto medio de la zona de solape)."""
    out = []
    for k, d in enumerate(metas):
        p = d["params"]
        lo = -1.0 if k == 0 else p["start"] + (metas[k - 1]["params"]["audio_end"] - p["start"]) / 2
        hi = 1e12 if k == len(metas) - 1 else (
            metas[k + 1]["params"]["start"] + (p["audio_end"] - metas[k + 1]["params"]["start"]) / 2)
        for sg in d["segments"]:
            ws = [w for w in sg["words"] if lo <= (w["t0"] + w["t1"]) / 2 < hi]
            if not ws and not sg["words"]:
                if lo <= sg["t0"] < hi:
                    out.append({**sg, "words": [], "_chunk": k})
                continue
            if not ws:
                continue
            text = sg["text"] if len(ws) == len(sg["words"]) else " ".join(w["w"] for w in ws)
            out.append({**sg, "t0": ws[0]["t0"] if len(ws) != len(sg["words"]) else sg["t0"],
                        "t1": ws[-1]["t1"] if len(ws) != len(sg["words"]) else sg["t1"],
                        "text": text, "words": ws, "_chunk": k})
    out.sort(key=lambda x: (x["t0"], x["t1"]))
    # une fragmentos cortados en la frontera entre tramos si la frase no había terminado
    merged = []
    for sg in out:
        if (merged and sg["_chunk"] != merged[-1]["_chunk"] and not re.search(r"[.!?…]$", merged[-1]["text"])
                and sg["t0"] - merged[-1]["t1"] < 1.5):
            m = merged[-1]
            m["text"] = (m["text"] + " " + sg["text"]).strip()
            m["t1"] = sg["t1"]
            m["words"] += sg["words"]
            m["no_speech_prob"] = max(m["no_speech_prob"], sg["no_speech_prob"])
            m["compression_ratio"] = max(m["compression_ratio"], sg["compression_ratio"])
            m["avg_logprob"] = min(m["avg_logprob"], sg["avg_logprob"])
            m["_chunk"] = sg["_chunk"]
        else:
            merged.append(sg)
    return merged


def flag_hallucinations(segs: list[dict]) -> int:
    for sg in segs:
        n = norm(sg["text"])
        why = None
        if not n:
            why = "vacío"
        elif any(n == ph.strip() or n.startswith(ph) or (len(n) < 60 and ph.strip() in n) for ph in HALLUCINATION_PHRASES):
            why = "frase conocida"
        elif sg["compression_ratio"] > 2.4:
            why = f"compression_ratio {sg['compression_ratio']}"
        elif sg["no_speech_prob"] > 0.6 and sg["avg_logprob"] < -1.0:
            why = f"no_speech {sg['no_speech_prob']} / logprob {sg['avg_logprob']}"
        elif sg["no_speech_prob"] > 0.85:
            why = f"no_speech {sg['no_speech_prob']}"
        if why:
            sg["hallucination"] = True
            sg["why"] = why
    # repeticiones idénticas en bucle (>=3 seguidas): se marcan todas menos la primera
    i = 0
    while i < len(segs):
        j = i
        while j + 1 < len(segs) and norm(segs[j + 1]["text"]) == norm(segs[i]["text"]) and norm(segs[i]["text"]):
            j += 1
        if j - i + 1 >= 3 and len(norm(segs[i]["text"]).split()) >= 2:
            for k in range(i + 1, j + 1):
                segs[k]["hallucination"] = True
                segs[k].setdefault("why", f"repetición x{j - i + 1}")
        i = j + 1
    return sum(1 for s in segs if s.get("hallucination"))


def hms(t: float) -> str:
    t = int(t)
    return f"{t // 3600:02d}:{t % 3600 // 60:02d}:{t % 60:02d}"


def write_outputs(segs: list[dict], metas: list[dict], args, out_dir: Path, total: float) -> dict:
    n_hall = flag_hallucinations(segs)
    final = []
    for i, sg in enumerate(segs):
        o = {"id": i, "t0": round(sg["t0"], 2), "t1": round(sg["t1"], 2), "text": sg["text"], "reviewed": False,
             "no_speech_prob": sg["no_speech_prob"], "avg_logprob": sg["avg_logprob"],
             "compression_ratio": sg["compression_ratio"]}
        if sg.get("hallucination"):
            o["hallucination"] = True
            o["why"] = sg["why"]
        o["words"] = sg["words"]
        final.append(o)
    n_words = sum(len(s["words"]) for s in final)
    elapsed = sum(d["elapsed"] for d in metas)
    audio_s = sum(d["params"]["core_end"] - d["params"]["start"] for d in metas)
    stats = {"processing_s": round(elapsed, 1), "audio_s": round(audio_s, 1),
             "rtf": round(elapsed / audio_s, 3) if audio_s else None,
             "max_rss_mb": max(d["maxrss_mb"] for d in metas),
             "segments": len(final), "words": n_words, "hallucinations": n_hall}
    ref = {"audio": AUDIO, "engine": "mlx-whisper " + args.model.split("/")[-1].replace("whisper-", "").replace("-mlx", ""),
           "model_repo": args.model, "duration": round(total, 1), "prompt": PROMPT,
           "stats": stats, "segments": final}
    (out_dir / f"{STEM}.ref.json").write_text(json.dumps(ref, ensure_ascii=False, indent=1))
    lines = []
    for s in final:
        mark = " [ALUCINACION]" if s.get("hallucination") else ""
        lines.append(f"[{hms(s['t0'])}] {s['text']}{mark}")
    (out_dir / f"{STEM}.ref.txt").write_text("\n".join(lines) + "\n")
    return stats


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--start", type=float, default=0.0)
    ap.add_argument("--end", type=float, default=0.0, help="0 = hasta el final")
    ap.add_argument("--chunk", type=float, default=300.0)
    ap.add_argument("--overlap", type=float, default=5.0)
    ap.add_argument("--out-dir", default=str(ROOT / "eval" / "asr"))
    args = ap.parse_args(argv)
    out_dir = Path(args.out_dir)
    audio_path = ROOT / "eval" / "asr" / AUDIO
    total = wav_duration(audio_path)
    t = time.time()
    metas = run_chunks(args, out_dir, audio_path, total)
    segs = merge(metas)
    stats = write_outputs(segs, metas, args, out_dir, total)
    stats["wall_this_run_s"] = round(time.time() - t, 1)
    stats["max_rss_this_run_mb"] = round(maxrss_mb())
    print("STATS " + json.dumps(stats), flush=True)


if __name__ == "__main__":
    sys.exit(main())
