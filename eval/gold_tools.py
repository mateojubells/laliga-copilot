"""Carga, validación y congelación del conjunto de oro (docs/ANNOTATION.md, docs/ARCHITECTURE.md §8).

    python -m eval.gold_tools validate     # comprueba formato, ids, splits y coherencia con plantillas y descanso
    python -m eval.gold_tools freeze       # escribe eval/gold/TEST_MANIFEST.sha256 (congela test)
"""
from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Iterator

from copilot.types import EVENT_TYPES

ROOT = Path(__file__).resolve().parent.parent
GOLD = ROOT / "eval" / "gold"
MANIFEST = GOLD / "TEST_MANIFEST.sha256"
SOURCES = {"audio", "echoes", "catalog", "hard"}
MODALITIES = {"real", "negated", "hypothetical", "query", "past"}
ROLES = {"actor", "receiver", "victim", "out", "team_for", "team_against"}
TEST_BUCKETS = 40  # % de grupos que van a test


def iter_gold() -> Iterator[dict]:
    for f in sorted(GOLD.glob("*.jsonl")):
        for n, line in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            line = line.strip()
            if line and not line.startswith("//"):
                r = json.loads(line)
                r["_file"], r["_line"] = f.name, n
                yield r


def split_for_group(group: str) -> str:
    """Reparto estable por GRUPO (plantilla, partido de Echoes, familia de casos), no por frase."""
    h = int(hashlib.sha256(group.encode("utf-8")).hexdigest(), 16) % 100
    return "test" if h < TEST_BUCKETS else "dev"


def _canon(r: dict) -> str:
    return json.dumps({k: v for k, v in r.items() if not k.startswith("_")}, ensure_ascii=False, sort_keys=True)


def test_digest() -> tuple[str, int]:
    rows = sorted(_canon(r) for r in iter_gold() if r.get("split") == "test")
    return hashlib.sha256("\n".join(rows).encode("utf-8")).hexdigest(), len(rows)


def check_manifest() -> list[str]:
    if not MANIFEST.exists():
        return []  # aún no congelado
    want = MANIFEST.read_text().split()
    got, n = test_digest()
    return [] if want and want[0] == got else [f"esperado {want[0][:12]}… ({want[1] if len(want) > 1 else '?'} filas), "
                                               f"actual {got[:12]}… ({n} filas). Test está congelado: no se edita."]


def _known_ids() -> tuple[set, set]:
    f = ROOT / "data" / "rosters" / "2024-25.json"
    if not f.exists():
        return set(), set()
    d = json.loads(f.read_text(encoding="utf-8"))
    return {t["id"] for t in d["teams"]}, {p["id"] for t in d["teams"] for p in t["players"]}


def validate() -> list[str]:
    errs: list[str] = []
    teams, players = _known_ids()
    meta_f = ROOT / "eval" / "asr" / "barca-valladolid.meta.json"
    halftime = json.loads(meta_f.read_text())["first_half_end"] if meta_f.exists() else None
    ids: Counter = Counter()
    group_split: dict[str, str] = {}

    def known(v: str) -> bool:
        return (not players) or v in players or v in teams

    for r in iter_gold():
        w = f"{r['_file']}:{r['_line']}"
        for k in ("id", "split", "source", "text", "entities", "events", "reviewed"):
            if k not in r:
                errs.append(f"{w} falta '{k}'")
        ids[r.get("id")] += 1
        if r.get("source") not in SOURCES:
            errs.append(f"{w} source inválido {r.get('source')}")
        if r.get("split") not in ("dev", "test"):
            errs.append(f"{w} split inválido")
        if r.get("source") == "audio":
            if halftime is not None and "t0" in r and (r["t0"] < halftime) != (r["split"] == "dev"):
                errs.append(f"{w} audio: split no coincide con el descanso (1.ª parte dev, 2.ª test)")
        else:
            g = r.get("group")
            if not g:
                errs.append(f"{w} falta 'group' (obligatorio fuera del audio)")
            else:
                if r.get("split") != split_for_group(g):
                    errs.append(f"{w} split {r.get('split')} ≠ {split_for_group(g)} para group={g}")
                if group_split.setdefault(g, r.get("split")) != r.get("split"):
                    errs.append(f"{w} el grupo {g} está en dev y en test")
        if r.get("preannotated_by") and "copilot.nlu" in str(r["preannotated_by"]):
            errs.append(f"{w} pre-anotado con el motor que se evalúa")
        for e in r.get("entities", []):
            if e.get("type") not in ("player", "team", "coach", "referee") or not e.get("id"):
                errs.append(f"{w} entidad mal formada {e}")
            elif e["type"] in ("player", "team") and not known(e["id"]):
                errs.append(f"{w} id desconocido {e['id']}")
        ent_ids = {e.get("id") for e in r.get("entities", [])}
        chains: dict[str, list[int]] = {}
        for ev in r.get("events", []):
            if ev.get("type") not in EVENT_TYPES:
                errs.append(f"{w} tipo de evento inválido {ev.get('type')}")
            if ev.get("modality", "real") not in MODALITIES:
                errs.append(f"{w} modalidad inválida {ev.get('modality')}")
            for role, v in (ev.get("roles") or {}).items():
                if role not in ROLES:
                    errs.append(f"{w} rol inválido {role}")
                elif not known(v):
                    errs.append(f"{w} id desconocido en rol {role}: {v}")
                elif v not in ent_ids:
                    errs.append(f"{w} {v} está en un rol pero no en 'entities'")
            if ev.get("chain"):
                chains.setdefault(ev["chain"], []).append(ev.get("order", 0))
        for c, orders in chains.items():
            if len(orders) < 2 or len(set(orders)) != len(orders):
                errs.append(f"{w} cadena {c}: necesita ≥2 eventos con 'order' distintos")
    errs += [f"id repetido: {i}" for i, n in ids.items() if n > 1]
    errs += check_manifest()
    return errs


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "validate"
    if cmd == "freeze":
        d, n = test_digest()
        MANIFEST.write_text(f"{d} {n}\n")
        print(f"test congelado: {n} filas, {d[:12]}…")
    else:
        errs = validate()
        rows = list(iter_gold())
        c = Counter((r.get("source"), r.get("split")) for r in rows)
        print(f"{len(rows)} filas:", dict(sorted(c.items(), key=str)))
        print("\n".join(errs[:60]) or "oro válido")
        sys.exit(1 if errs else 0)
