"""Repetición determinista del partido desde una transcripción con tiempos (sin audio ni motor de voz).

Es la misma tubería que en directo a partir del ASR: enunciados → NLU → MatchContext → Selector.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from copilot.graphics.selector import GraphicRequest, Selector
from copilot.match.context import Clock, MatchContext
from copilot import seasons
from copilot.nlu.gazetteer import season
from copilot.types import MatchEvent

ROOT = Path(__file__).resolve().parents[2]
ASR = ROOT / "eval" / "asr"


def utterances(ref: dict, first_half_end: float) -> list[dict]:
    """Une segmentos en enunciados (pausa < 0,8 s, máx. 12 s, corta en fin de frase). Misma regla que el oro."""
    segs = [s for s in ref["segments"] if not s.get("hallucination") and s["text"].strip()]
    utts: list[dict] = []
    cur = None
    for s in segs:
        if cur and (s["t0"] - cur["t1"] < 0.8) and (s["t1"] - cur["t0"] <= 12) and not re.search(r"[.!?]$", cur["text"]) \
                and (cur["t0"] < first_half_end) == (s["t0"] < first_half_end):
            cur["text"] += " " + s["text"].strip()
            cur["t1"] = s["t1"]
        else:
            cur = {"t0": s["t0"], "t1": s["t1"], "text": s["text"].strip()}
            utts.append(cur)
    return utts


@dataclass
class ReplayResult:
    events: list[MatchEvent] = field(default_factory=list)
    cards: list[GraphicRequest] = field(default_factory=list)
    retracted: list[MatchEvent] = field(default_factory=list)
    ctx: MatchContext | None = None


def make_context(match_id: str, meta: dict | None = None) -> MatchContext:
    pair = match_id.split("/")[-1]
    teams = {t["id"]: t for t in season(seasons.season_of(match_id))["teams"]}
    home = next(a for a in teams if pair.startswith(a + "-") and pair[len(a) + 1:] in teams)
    away = pair[len(home) + 1:]
    team_of = {p["id"]: t for t in (home, away) for p in teams[t]["players"]}
    clock = Clock()
    if meta:  # en directo lo marca el operador (o la frase "comienza el partido")
        clock = Clock(meta.get("kickoff"), meta.get("second_half_start"), meta.get("first_half_end"), meta.get("full_time"))
    ctx = MatchContext(match_id, home, away, team_of=team_of, clock=clock)
    ctx.position = {p["id"]: (p["position"], p["line"]) for t in (home, away) for p in teams[t]["players"]}
    lineup = seasons.lineup_path(match_id)
    if lineup.exists():  # alineación oficial previa al partido: quién empieza y quién está en el banquillo
        for team, lu in json.loads(lineup.read_text(encoding="utf-8"))["lineups"].items():
            ctx.on_pitch[team] = set(lu["starting"])
            ctx.bench[team] = set(lu["bench"])
    return ctx


def run(engine, match_id: str, utts: list[dict], meta: dict | None = None) -> ReplayResult:
    engine.reset(match_id=match_id)
    ctx = make_context(match_id, meta)
    sel = Selector(ctx)
    out = ReplayResult(ctx=ctx)
    for u in utts:
        res = engine.analyze(u["text"], t0=u["t0"], t1=u["t1"], final=True)
        changes = ctx.ingest(res, u["t1"])
        out.retracted += [me for a, me in changes if a == "retract"]
        out.cards += sel.on_result(res, changes, u["t1"])
    out.events = ctx.events
    return out


def load_reference() -> tuple[dict, dict]:
    return (json.loads((ASR / "barca-valladolid.ref.json").read_text()),
            json.loads((ASR / "barca-valladolid.meta.json").read_text()))
