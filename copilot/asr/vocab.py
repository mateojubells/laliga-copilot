"""Sesgo de vocabulario: nombres de las plantillas del partido (titulares + banquillo) y entrenadores.

Solo usa lo que el operador carga antes del partido (data/matches/*.json) y data/rosters: nada de lo que ocurre durante
el partido.
"""
from __future__ import annotations

import json
from pathlib import Path

from copilot import seasons
from copilot.nlu.gazetteer import season


def _match(match_id: str | None) -> str:
    """El partido pedido o, si no se indica, el de la configuración (`match`)."""
    if match_id:
        return match_id
    from copilot.config import settings
    m = settings().get("match")
    if not m:
        raise ValueError("indica el id del partido (o `match` en la configuración)")
    return m


def match_names(match_id: str | None = None) -> dict[str, list[str]]:
    """{equipo_id: [nombres]} con known_as de titulares y banquillo; entrenador al final."""
    match_id = _match(match_id)
    f = seasons.lineup_path(match_id)
    lineups = json.loads(f.read_text(encoding="utf-8"))["lineups"]
    teams = {t["id"]: t for t in season(seasons.season_of(match_id))["teams"]}
    out: dict[str, list[str]] = {}
    for tid, lu in lineups.items():
        players = {p["id"]: p for p in teams[tid]["players"]}
        names: list[str] = []
        for pid in lu["starting"] + lu["bench"]:
            p = players.get(pid)
            if p and p["known_as"] not in names:
                names.append(p["known_as"])
        coach = teams[tid].get("coach")
        if coach:
            names.append(coach.split()[-1])
        out[tid] = names
    return out


def build(match_id: str | None = None) -> tuple[str, list[str]]:
    """(prompt, vocabulary) para `AsrEngine.start`."""
    match_id = _match(match_id)
    per_team = match_names(match_id)
    teams = {t["id"]: t for t in season(seasons.season_of(match_id))["teams"]}
    ids = list(per_team)
    short = {i: teams[i]["short"] for i in ids}
    prompt = (f"Partido de LaLiga: {teams[ids[0]]['name']} contra {teams[ids[1]]['name']}. "
              + " ".join(f"{short[i]}: {', '.join(per_team[i])}." for i in ids))
    vocab: list[str] = []
    for i in ids:
        for n in [teams[i]["name"], short[i], *per_team[i]]:
            if n not in vocab:
                vocab.append(n)
    return prompt, vocab
