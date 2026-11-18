"""NluEngine que envuelve el prototipo antiguo (legacy/) ejecutado con Node, para medir la línea base.

Traducción deliberadamente obvia: tablas explícitas abajo, sin ajustar a ningún conjunto de oro.
El prototipo no distingue hipótesis ni negación (salvo penalti_no / gol_anulado), no encadena jugadas.
"""
from __future__ import annotations

import json
import re
import shutil
import subprocess
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Any

from copilot.types import EVENT_TYPES, EntityMention, NluEvent, NluResult

ROOT = Path(__file__).resolve().parent.parent
HARNESS = ROOT / "eval" / "legacy" / "harness.mjs"
ROSTERS = ROOT / "data" / "rosters" / "2024-25.json"

#: id de situación del catálogo antiguo -> (tipo grueso, modality)
SIT_MAP: dict[str, tuple[str, str]] = {
    **{s: ("gol", "real") for s in ("gol", "gol_penalti", "doblete")},
    "gol_anulado": ("gol", "negated"),
    **{s: ("tiro", "real") for s in ("tiro", "tiro_puerta", "tiro_fuera", "remate_cabeza", "chilena", "volea",
                                      "tiro_lejano")},
    **{s: ("parada", "real") for s in ("parada", "penalti_parado")},
    "palo": ("palo", "real"),
    **{s: ("ocasion", "real") for s in ("ocasion", "mano_a_mano")},
    **{s: ("pase", "real") for s in ("pase", "pase_clave", "pase_largo", "pared")},
    "centro": ("centro", "real"),
    "asistencia": ("asistencia", "real"),
    **{s: ("regate", "real") for s in ("regate", "cano", "sombrero", "desborde", "finta")},
    **{s: ("falta", "real") for s in ("falta", "falta_tactica", "falta_peligrosa", "entrada")},
    **{s: ("penalti", "real") for s in ("penalti", "penalti_reclamado")},
    "penalti_no": ("penalti", "negated"),
    "mano": ("mano", "real"),
    **{s: ("corner", "real") for s in ("corner", "lanza_corner", "corner_corto")},
    **{s: ("saque_banda", "real") for s in ("saque_banda", "saque_largo")},
    "saque_puerta": ("saque_puerta", "real"),
    "fuera_juego": ("fuera_juego", "real"),
    **{s: ("amarilla", "real") for s in ("amarilla", "segunda_amarilla")},
    "roja": ("roja", "real"),
    "cambio": ("cambio", "real"),
    "lesion": ("lesion", "real"),
    **{s: ("robo", "real") for s in ("robo", "intercepcion")},
    "perdida": ("perdida", "real"),
    "despeje": ("despeje", "real"),
    "var": ("var", "real"),
    "inicio": ("inicio", "real"),
    "descanso": ("descanso", "real"),
    "final": ("final", "real"),
}
assert all(t in EVENT_TYPES for t, _ in SIT_MAP.values())


def _norm(s: str) -> str:
    s = unicodedata.normalize("NFD", s.lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]+", " ", s)).strip()


def _map_role(role: str, etype: str, is_team: bool) -> str | None:
    if role == "ref":
        return None
    if role == "benef":
        return "team_for"
    if role == "against":
        return "team_against"
    if role == "recv":
        role = "actor"
    if role == "victim":
        if etype in ("pase", "centro", "asistencia"):
            return "receiver"
        return "out" if etype == "cambio" else "victim"
    if role == "actor":
        return "team_for" if is_team else "actor"
    return None


class LegacyEngine:
    def __init__(self) -> None:
        self.unmapped: Counter[str] = Counter()
        self._proc: subprocess.Popen | None = None
        self._build_index()

    # ------------------------------------------------------------ nombres -> ids
    def _build_index(self) -> None:
        data = json.loads(ROSTERS.read_text())
        self._teams: dict[str, str | None] = {}
        self._players: dict[str, str | None] = {}

        def add(idx: dict, key: str, ident: str) -> None:
            k = _norm(key)
            if not k:
                return
            idx[k] = ident if idx.get(k, ident) == ident else None  # ambiguo -> None

        for t in data["teams"]:
            for k in (t["name"], t["short"], t["id"], *t.get("aliases", [])):
                add(self._teams, k, t["id"])
        # prioridad: nombre completo > known_as > alias > alias de ASR; cada nivel solo rellena huecos
        levels = [lambda p: [p["name"]], lambda p: [p["known_as"]], lambda p: p.get("aliases", []),
                  lambda p: p.get("asr_aliases", [])]
        for get in levels:
            idx: dict[str, str | None] = {}
            for t in data["teams"]:
                for p in t["players"]:
                    for k in get(p):
                        add(idx, k, p["id"])
            for k, v in idx.items():
                self._players.setdefault(k, v)

    def _player_id(self, name: str) -> str | None:
        return self._players.get(_norm(name))

    def _team_id(self, name: str) -> str | None:
        return self._teams.get(_norm(name))

    def _ident(self, kind: str, name: str) -> str | None:
        i = self._player_id(name) if kind == "player" else self._team_id(name)
        if i is None:
            self.unmapped[f"{kind}:{name}"] += 1
        return i

    # ------------------------------------------------------------ proceso node
    def _start(self) -> subprocess.Popen:
        node = shutil.which("node") or str(ROOT / ".tools" / "node" / "bin" / "node")
        if not Path(node).exists() and not shutil.which(node):
            raise RuntimeError("node no disponible")
        self._proc = subprocess.Popen([node, str(HARNESS)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                      stderr=subprocess.DEVNULL, text=True, encoding="utf-8", bufsize=1)
        return self._proc

    def _call(self, req: dict) -> dict:
        p = self._proc if self._proc and self._proc.poll() is None else self._start()
        p.stdin.write(json.dumps(req, ensure_ascii=False) + "\n")
        p.stdin.flush()
        line = p.stdout.readline()
        if not line:
            raise RuntimeError("el arnés de node terminó inesperadamente")
        out = json.loads(line)
        if "error" in out:
            raise RuntimeError(out["error"])
        return out

    def close(self) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.stdin.close()
            self._proc.wait(timeout=5)

    def __del__(self) -> None:
        try:
            self.close()
        except Exception:
            pass

    # ------------------------------------------------------------ NluEngine
    def reset(self, *, match_id: str | None = None) -> None:
        self._call({"cmd": "reset"})

    def analyze(self, text: str, *, t0: float = 0.0, t1: float = 0.0, final: bool = True,
                ctx: Any = None) -> NluResult:
        raw = self._call({"cmd": "analyze", "text": text})
        ents, seen = [], set()
        for e in raw["entities"]:
            i = self._ident(e["kind"], e["name"])
            if i and (e["kind"], i) not in seen:
                seen.add((e["kind"], i))
                ents.append(EntityMention(type=e["kind"], id=i, span=(0, 0), surface=e["name"]))
        events = []
        for n, ev in enumerate(raw["events"]):
            if ev["sit"] not in SIT_MAP:
                continue
            etype, modality = SIT_MAP[ev["sit"]]
            roles: dict[str, str] = {}
            for l in ev["links"]:
                i = self._ident(l["kind"], l["ent"])
                r = _map_role(l["role"], etype, l["kind"] == "team")
                if i and r and r not in roles:
                    roles[r] = i
            events.append(NluEvent(type=etype, fine=ev["sit"], modality=modality, roles=roles, order=n))
        return NluResult(text=text, t0=t0, t1=t1, final=final, entities=ents, events=events)
