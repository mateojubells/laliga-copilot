"""Diccionario de entidades del partido en curso y del resto de la liga (docs/ARCHITECTURE.md §7.2)."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from copilot import seasons
from copilot.nlu.normalize import phon, strip

ROOT = Path(__file__).resolve().parents[2]


@lru_cache(maxsize=1)
def common_words() -> dict[str, int]:
    """palabra -> rango de frecuencia (0 = la más común) en comentarios reales."""
    words = (Path(__file__).parent / "common_words.txt").read_text(encoding="utf-8").split()
    return {w: i for i, w in enumerate(words)}


def is_common(w: str) -> bool:
    """La lista no trae palabras de ≤3 letras (artículos, preposiciones…): se consideran corrientes."""
    return len(w) <= 3 or w in common_words()


@lru_cache(maxsize=16)
def _load_roster(path: str, mtime_ns: int) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def resolve_season(name: str | None = None) -> str:
    """Temporada pedida si está instalada; si no (o None), la temporada activa (seasons.current())."""
    return name if name and name in seasons.installed() else seasons.current()


def season(name: str | None = None) -> dict:
    """Plantillas de una temporada (None = seasons.current()). Se cachea por fichero y fecha de modificación,
    así que reinstalar una temporada se nota sin reiniciar."""
    f = seasons.roster_path(resolve_season(name))
    return _load_roster(str(f), f.stat().st_mtime_ns)


def clear_caches() -> None:
    """Vacía la caché de plantillas (p. ej. tras instalar una temporada)."""
    _load_roster.cache_clear()


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", strip(s)).strip("-")


@dataclass(frozen=True)
class Cand:
    id: str
    type: str  # player | team | coach
    team: str
    via: str
    primary: bool  # pertenece a uno de los dos equipos del partido


class Gazetteer:
    def __init__(self, match_teams: tuple[str, ...] = (), match_id: str | None = None, season_name: str | None = None):
        self.season = resolve_season(season_name or (seasons.season_of(match_id) if match_id else None))
        data = season(self.season)
        self.starters: set[str] = set()
        self.squad_today: set[str] = set()
        if match_id:
            f = seasons.lineup_path(match_id)
            if f.exists():
                for lu in json.loads(f.read_text(encoding="utf-8"))["lineups"].values():
                    self.starters |= set(lu["starting"])
                    self.squad_today |= set(lu["starting"]) | set(lu["bench"])
        self.match_teams = tuple(match_teams)
        self.exact: dict[str, list[Cand]] = {}
        self.epithet: dict[str, list[Cand]] = {}
        self.players: dict[str, dict] = {}
        self.teams: dict[str, dict] = {}
        self.coach_team: dict[str, str] = {}
        self.by_number: dict[str, dict[int, str]] = {}
        self.gks: dict[str, list[str]] = {}
        self.fuzzy: list[tuple[str, str, Cand]] = []  # (clave fonética, forma unida, candidato)
        common = common_words()
        for t in data["teams"]:
            tid, prim = t["id"], (not match_teams) or t["id"] in match_teams
            self.teams[tid] = t
            tc = Cand(tid, "team", tid, "alias", prim)
            for a in {t["name"], t["short"], *t.get("aliases", [])}:
                self._add(strip(a), tc)
            if t.get("coach"):
                cid = "coach/" + slug(t["coach"])
                self.coach_team[cid] = tid
                cc = Cand(cid, "coach", tid, "alias", prim)
                parts = strip(t["coach"]).split()
                self._add(" ".join(parts), cc)
                if len(parts[-1]) >= 4 and (prim and match_teams or parts[-1] not in common):
                    self._add(parts[-1], cc)
            self.by_number[tid] = {}
            self.gks[tid] = [p["id"] for p in sorted(t["players"], key=lambda p: p.get("number") or 99)
                             if p["position"] == "GK"]
            for p in t["players"]:
                self.players[p["id"]] = p
                if p.get("number") is not None:
                    self.by_number[tid][p["number"]] = p["id"]
                forms = {strip(p["name"]): "exact", strip(p["known_as"]): "exact"}
                for a in p.get("aliases", []):
                    forms.setdefault(strip(a), "alias")
                for a in p.get("asr_aliases", []):
                    forms.setdefault(strip(a), "asr_alias")
                for key, via in forms.items():
                    key = " ".join(re.findall(r"[a-z0-9]+", key))
                    if not key:
                        continue
                    self._add(key, Cand(p["id"], "player", tid, via, prim))
                    if prim and match_teams and via != "asr_alias" and len(key.replace(" ", "")) >= 4:
                        self.fuzzy.append((phon(key), key.replace(" ", ""), Cand(p["id"], "player", tid, "phonetic", True)))
                for e in p.get("epithets", []):
                    k = strip(e)
                    if not re.fullmatch(r"el \d+", k):
                        self.epithet.setdefault(k, []).append(Cand(p["id"], "player", tid, "epithet", prim))
        extra_all = json.loads((Path(__file__).parent / "aliases_extra.json").read_text(encoding="utf-8"))
        for tid, d in extra_all.get("teams", {}).items():
            if tid not in self.teams:  # equipo de otra temporada
                continue
            for a in d.get("aliases", []):
                self._add(strip(a), Cand(tid, "team", tid, "alias", (not match_teams) or tid in match_teams))
        extra = extra_all["players"]
        self.cased_only: set[str] = set()
        for pid, d in extra.items():
            if d.get("cased_only"):
                self.cased_only |= {strip(a) for a in d.get("asr_aliases", [])}
            p = self.players.get(pid)
            if p is None:  # jugador de otra temporada
                continue
            prim = (not match_teams) or p["team"] in match_teams
            for via, key in (("alias", "aliases"), ("asr_alias", "asr_aliases")):
                for a in d.get(key, []):
                    self._add(strip(a), Cand(pid, "player", p["team"], via, prim))
        if match_teams:
            self._derive_short_aliases(common)
        self.maxlen = max(len(k.split()) for k in self.exact)

    def _add(self, key: str, c: Cand) -> None:
        lst = self.exact.setdefault(key, [])
        if not any(x.id == c.id for x in lst):
            lst.append(c)

    def _derive_short_aliases(self, common: dict[str, int]) -> None:
        """Nombre de pila o apellido suelto, solo para los dos equipos del partido y solo si es único entre ellos
        ("Kike", "Robert", "Íñigo"). Los apellidos que son palabra muy corriente no se derivan ("Rosa", "Torres")."""
        firsts: dict[str, list[dict]] = {}
        lasts: dict[str, list[dict]] = {}
        squad = [p for p in self.players.values() if p["team"] in self.match_teams]
        for p in squad:
            for src in {strip(p["name"]), strip(p["known_as"])}:
                parts = re.findall(r"[a-z]+", src)
                if len(parts) >= 2:
                    firsts.setdefault(parts[0], []).append(p)
                    lasts.setdefault(parts[-1], []).append(p)
        for table, is_first in ((firsts, True), (lasts, False)):
            for tok, ps in table.items():
                ids = {p["id"] for p in ps}
                if is_first and self.squad_today and len(tok) >= 3 and tok not in self.exact:
                    # con la convocatoria cargada, un nombre de pila compartido se resuelve después (titular, recencia)
                    today = [p for p in ps if p["id"] in self.squad_today]
                    if today and tok not in ("real", "club", "juan", "jose", "de", "del", "van", "ter"):
                        for p in {p["id"]: p for p in today}.values():
                            self._add(tok, Cand(p["id"], "player", p["team"], "short", True))
                        continue
                if len(ids) != 1 or len(tok) < 4 or tok in self.exact:
                    continue
                if not is_first and common.get(tok, 10**9) < 3000:
                    continue
                if is_first and tok in ("real", "club", "juan", "jose", "de", "del", "van", "ter"):
                    continue
                p = ps[0]
                self._add(tok, Cand(p["id"], "player", p["team"], "short", True))
