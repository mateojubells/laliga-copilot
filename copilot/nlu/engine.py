"""Motor de comprensión determinista (docs/ARCHITECTURE.md §7).

texto → tokens → entidades (exacto, alias, fonético, epítetos, correferencia) → situaciones del catálogo →
roles → modalidad → cadenas. Sin modelos: cada decisión es una regla legible y medible con `make eval`.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Any, Optional

from rapidfuzz.distance import Levenshtein

from copilot import seasons
from copilot.nlu.catalog import FRAME, MODAL_BY_FINE, Catalog, Hit
from copilot.nlu.gazetteer import Cand, Gazetteer, common_words, is_common, resolve_season
from copilot.nlu.normalize import Tok, phon, tokenize
from copilot.types import EntityMention, Intent, NluEvent, NluResult

_CATALOG: Catalog | None = None
_GAZ: dict[tuple[str, ...], Gazetteer] = {}


def _catalog() -> Catalog:
    global _CATALOG
    if _CATALOG is None:
        _CATALOG = Catalog()
    return _CATALOG


def _gazetteer(teams: tuple[str, ...], match_id: str | None = None, season: str | None = None) -> Gazetteer:
    """Diccionario cacheado por (temporada, equipos, partido). La temporada es la del partido o la activa."""
    season = resolve_season(season or (seasons.season_of(match_id) if match_id else None))
    key = (season,) + teams + ((match_id,) if match_id else ())
    if key not in _GAZ:
        _GAZ[key] = Gazetteer(teams, match_id, season)
    return _GAZ[key]


def clear_caches() -> None:
    """Olvida los diccionarios construidos (hay que llamarlo si cambia la alineación de un partido o una plantilla)."""
    _GAZ.clear()


@dataclass
class Mention:
    i: int
    n: int
    id: str
    type: str
    team: str
    via: str
    score: float = 1.0
    surface: Optional[str] = None

    @property
    def end(self) -> int:
        return self.i + self.n - 1


@dataclass
class Ev:
    hit: Hit
    type: str
    fine: str
    modality: str = "real"
    roles: dict[str, str] = field(default_factory=dict)
    inherited: bool = False
    chain: Optional[str] = None
    order: int = 0
    pos: float = 0.0  # posición lógica en la jugada (para ordenar "gol de X a pase de Y")


# ---------------------------------------------------------------- vocabulario de función
_FOR = re.compile(r"(?:^| )(?:a favor (?:de|del)|favor (?:de|del)|para(?: el| la| los| las)?(?: bueno de)?)$")
_AGAINST = re.compile(r"(?:^| )(?:en contra (?:de|del)|contra(?: el| la| los| las)?)$")
_VICTIM = re.compile(r"(?:^| )(?:sobre|ante|encima de|encima a)(?: el| la)?$")
_BY = re.compile(r"(?:^| )por$")
_WITH = re.compile(r"(?:^| )con$")
_TO = re.compile(r"(?:^| )(?:a|al|hacia)$")
_OF = re.compile(r"(?:^| )(?:de|del)(?: el| la| los| las)?(?: bueno de| mago| gran| joven| propio| mismisimo)?$")

_HYP_BEFORE = re.compile(
    r"(?:^| )(?:si|ojala|puede|pueden|podemos|puedo|puede ser|puede haber|no se si|pudo haber|podria haber|habra|podria ser|podria|podia|pudo ser|deberia|debio|tendria que|tenia que|tiene que|"
    r"va a|van a|iba a|a punto de|quiere|quieren|quiero|queremos|pide|piden|pedia|pedian|reclama|reclaman|"
    r"busca el|buscando el|seria|hubiera sido|habria sido|casi|a ver si|esperando|espero|necesita|necesitamos|"
    r"falta el|como marque|como meta|cuando marque|para que marque|que marque|que meta|parece|parecia|igual es|"
    r"quizas|quiza|a lo mejor|posible|posibles)(?: \w+){0,3}$")
_NEG_BEFORE = re.compile(
    r"(?:^| )(?:no|ni|sin|tampoco|nada de|nunca|jamas|ningun|ninguna)(?: (?:es|era|fue|hay|hubo|habia|ha|han|vale|"
    r"valio|sube|pita|senala|da|le|se|la|lo|me|parece|existe|ha sido|habido|ha habido|un|una|el|la|ni|esta|estaba|en|"
    r"puede ser|sera|seria|creo que sea|veo|vi|he visto))*$")
_NEG_AFTER = re.compile(r"^(?:no (?:vale|sube|cuenta)|anulado|anulada|invalidado|que no (?:sube|vale)|no era|no es|"
                        r"no existe|no hay|de nada|ni nada)")
_PAST = re.compile(
    r"\b(?:semana pasada|ano pasado|temporada pasada|jornada pasada|partido pasado|mes pasado|ayer|el otro dia|"
    r"de antes|del principio|de la primera parte|en la ida|la pasada|hace un rat\w+|antes|es[ea] era|hace (?:\w+ ){0,2}(?:anos|meses|semanas|dias|jornadas)|anterior|"
    r"aquel|aquella|recuerdan|recordais|recordamos|acordais|como (?:en )?el (?:primer|segundo|tercer|ultimo)|"
    r"lleva(?:ba)? \d+|contra el \w+ (?:marco|hizo)|en su carrera|historico|la temporada anterior)\b")
_QUERY = re.compile(r"\b(?:cuantos|cuantas|cuanto (?:lleva|llevan|ha|han|tiene|suma)|numeros de|estadisticas de|datos de|que numeros)\b")
_INTERROG = re.compile(r"^(?:no (?:es|era|fue|hay)|eso (?:no )?(?:es|era)|es|era|seguro que|como que no)\b")
_NUM_STOP = {"a", "minutos", "minuto", "goles", "partidos", "puntos", "veces", "tiros", "anos", "de", "y", "o",
             "cero", "uno", "dos", "tres", "segundos", "pases", "jornadas", "victorias", "por", "en"}
_CITY_AFTER = {"ciudad", "capital"}
_SWAP_OUT_FIRST = re.compile(r"^(?:sale|salen|se|abandona|sustituido|sustituye|sustituyen|deja|reemplaza|ocupa|en)$")
_SUBJECT_TTL = 8.0
#: un gol se canta y se repite durante este rato (sigue siendo el mismo gol, "real"); después y hasta
#: BURST_RECALL_S lo que se oye es la repetición o el comentario ("past")
BURST_LIVE_S = 120.0
BURST_RECALL_S = 300.0


class Engine:
    """Implementa NluEngine. Un motor por partido en curso (reset fija las plantillas en juego)."""

    def __init__(self) -> None:
        self.cat = _catalog()
        self.common = common_words()
        self.reset()

    # ------------------------------------------------------------ contexto
    def reset(self, *, match_id: str | None = None) -> None:
        teams: tuple[str, ...] = ()
        if match_id:
            pair = match_id.split("/")[-1]
            base = _gazetteer((), None, seasons.season_of(match_id))
            for a in base.teams:
                if pair.startswith(a + "-") and pair[len(a) + 1:] in base.teams:
                    teams = (a, pair[len(a) + 1:])
        self.gaz = _gazetteer(teams, match_id if teams else None, seasons.season_of(match_id) if match_id else None)
        self.match_teams = teams
        self.recent: list[tuple[str, float]] = []  # (id de jugador, t) más reciente al final
        self.recent_teams: list[str] = []
        self.clock = 0.0
        self._chain_n = 0
        self._bursts: list[dict] = []
        self.subject: Optional[str] = None  # sujeto de la última frase (para "él")
        self.last_players: list[str] = []

    def _remember(self, mentions: list[Mention], t: float) -> None:
        for m in mentions:
            if m.type == "player":
                self.recent = [(i, x) for i, x in self.recent if i != m.id][-30:] + [(m.id, t)]
            elif m.type == "team":
                self.recent_teams = [x for x in self.recent_teams if x != m.id][-5:] + [m.id]

    def _recency(self, pid: str) -> int:
        for k, (i, _) in enumerate(reversed(self.recent)):
            if i == pid:
                return k
        return 10**6

    # ------------------------------------------------------------ entidades
    def _pick(self, cands: list[Cand], sent_teams: set[str]) -> Optional[Cand]:
        """Desambigua un alias con varios candidatos: equipos del partido → equipo citado en la frase → recencia."""
        if len(cands) == 1:
            return cands[0]
        pool = [c for c in cands if c.primary] or cands
        if len(pool) > 1 and sent_teams:
            pool = [c for c in pool if c.team in sent_teams] or pool
        if len(pool) > 1 and self.gaz.squad_today:
            pool = [c for c in pool if c.id in self.gaz.squad_today] or pool
        if len(pool) > 1 and self.gaz.starters:
            on = [c for c in pool if c.id in self.gaz.starters]
            if len(on) == 1 and not any(self._recency(c.id) < 10**6 for c in pool if c is not on[0]):
                return on[0]
        if len(pool) > 1:
            seen = sorted(pool, key=lambda c: self._recency(c.id))
            if self._recency(seen[0].id) < 10**6 and self._recency(seen[1].id) != self._recency(seen[0].id):
                return seen[0]
            if self.recent_teams:
                last = [c for c in pool if c.team == self.recent_teams[-1]]
                if len(last) == 1:
                    return last[0]
        return pool[0] if len(pool) == 1 else None

    def _entities(self, toks: list[Tok]) -> list[Mention]:
        g, n_t = self.gaz, len(toks)
        norm = [t.n for t in toks]
        cased = any(t.cap for t in toks[1:]) and any(not t.cap for t in toks)
        taken = [False] * n_t
        raw: list[tuple[int, int, list[Cand]]] = []

        # 1) exacto / alias, el más largo primero
        i = 0
        while i < n_t:
            hit = None
            for n in range(min(g.maxlen, n_t - i), 0, -1):
                cands = g.exact.get(" ".join(norm[i:i + n]))
                if not cands:
                    continue
                if n == 1 and not self._single_ok(toks, i, cands, cased):
                    continue
                if n == 1 and norm[i] in g.cased_only and not (cased and toks[i].cap and i > 0 and not any(
                        ch in toks[i - 1].after for ch in ".!?")):
                    continue
                if n == 1 and all(c.via == "short" for c in cands) and i + 1 < n_t and toks[i + 1].cap \
                        and not is_common(norm[i + 1]) and norm[i + 1] not in g.exact:
                    continue  # nombre de pila + apellido desconocido: otra persona, o un apellido mal oído (fuzzy)
                if self.match_teams and not any(c.primary for c in cands) and n > 1 and any(
                        any(c.primary for c in g.exact.get(" ".join(norm[i + 1:i + 1 + k]), ())) for k in (3, 2)):
                    continue  # "de Marcos André": gana el jugador del partido que empieza una palabra después
                hit = (i, n, cands)
                break
            if hit:
                raw.append(hit)
                for k in range(i, i + hit[1]):
                    taken[k] = True
                i += hit[1]
            else:
                i += 1

        mentions: list[Mention] = []
        pending: list[tuple[int, int, list[Cand]]] = []
        for i, n, cands in raw:
            teams = [c for c in cands if c.type == "team"]
            if teams and len(cands) == len(teams):
                if n == 1 and norm[i] in ("barcelona", "madrid", "valencia", "sevilla", "valladolid", "girona",
                                          "mallorca", "getafe", "leganes", "villarreal") and self._is_city(norm, i, n):
                    continue
                mentions.append(Mention(i, n, teams[0].id, "team", teams[0].id, "alias"))
            else:
                pending.append((i, n, [c for c in cands if c.type != "team"] or cands))

        # "los de Flick", "el equipo de Pezzolano" → equipo
        coach_as_team: set[int] = set()
        for i, n, cands in pending:
            if cands[0].type == "coach" and i >= 2 and norm[i - 1] == "de" and norm[i - 2] in (
                    "los", "equipo", "hombres", "chicos", "pupilos", "conjunto", "cuadro"):
                start = i - 2 - (1 if i >= 3 and norm[i - 3] in ("el", "los") and norm[i - 2] != "los" else 0)
                mentions.append(Mention(start, i - start, g.coach_team[cands[0].id], "team", g.coach_team[cands[0].id], "epithet"))
                if norm[i - 2] == "los":
                    coach_as_team.add(i)  # "los de Flick": solo el equipo
        sent_teams = {m.id for m in mentions if m.type == "team"}
        for i, n, cands in pending:
            if i in coach_as_team:
                continue
            c = self._pick(cands, sent_teams)
            if c:
                mentions.append(Mention(i, n, c.id, c.type, c.team, c.via))

        # 2) epítetos, dorsales, porteros
        mentions += self._epithets(toks, norm, taken, sent_teams, mentions)
        # 3) aproximado por sonido, solo contra las plantillas del partido
        if self.match_teams:
            mentions += self._fuzzy(toks, norm, taken)
        mentions.sort(key=lambda m: m.i)
        for m in mentions:
            m.surface = " ".join(t.raw for t in toks[m.i:m.i + m.n])
        return mentions

    def _single_ok(self, toks: list[Tok], i: int, cands: list[Cand], cased: bool) -> bool:
        """Un alias de una sola palabra que además es palabra corriente necesita más pruebas."""
        w = toks[i].n
        rank = self.common.get(w)
        if all(c.type == "team" for c in cands):
            return True
        if rank is None:
            return True
        if self.match_teams and not any(c.primary for c in cands):
            return False  # jugador de otro partido con nombre de palabra corriente ("Milla", "Roca")
        if len(w) <= 3:
            return False
        if cased and not toks[i].cap and i > 0 and rank < 8000:
            return False  # texto con mayúsculas y el nombre va en minúscula: "un balde de agua"
        if i > 0 and toks[i - 1].n in ("un", "una", "unos", "unas", "mi", "tu", "su", "muy", "mas", "tan", "este", "esta") \
                and rank < 8000:
            return False
        return True

    @staticmethod
    def _is_city(norm: list[str], i: int, n: int) -> bool:
        nxt = norm[i + n:i + n + 4]
        prev = norm[max(0, i - 3):i]
        return bool(_CITY_AFTER & set(nxt)) or prev[-2:] == ["ciudad", "de"] or (prev[-1:] == ["en"] and not nxt[:1] == ["b"])

    def _epithets(self, toks, norm, taken, sent_teams: set[str], mentions: list[Mention]) -> list[Mention]:
        g, out, n_t = self.gaz, [], len(toks)
        teams_here = list(sent_teams)

        def team_after(j: int) -> Optional[tuple[str, int]]:
            """'del Barça' justo después de la posición j → (equipo, tokens consumidos)."""
            if j < n_t and norm[j] in ("del", "de"):
                for m in mentions:
                    if m.type == "team" and m.i in (j + 1, j + 2):
                        return m.id, m.end - j + 1
            return None

        for i in range(n_t):
            if taken[i]:
                continue
            # "el portero del Valladolid"
            if norm[i] in ("portero", "guardameta", "meta", "arquero", "cancerbero") and i > 0 and norm[i - 1] in ("el", "del", "al"):
                ta = team_after(i + 1)
                if ta and g.gks.get(ta[0]):
                    gks = g.gks[ta[0]]
                    pid = min(gks, key=lambda p: (p not in g.starters, self._recency(p), gks.index(p)))
                    out.append(Mention(i - 1, 2 + ta[1], pid, "player", ta[0], "epithet", 0.8))
                    continue
            # "el 9", "el nueve del Barça", "el dorsal 19"
            if toks[i].num is not None and i > 0 and (norm[i - 1] in ("el", "dorsal") or norm[i - 1] == "numero") \
                    and 1 <= toks[i].num <= 50:
                nxt = norm[i + 1] if i + 1 < n_t else ""
                if nxt in _NUM_STOP and not (nxt == "de" and team_after(i + 1)) or toks[i].after.startswith(("-", ":")):
                    continue
                if i >= 2 and norm[i - 2] in ("minuto", "en", "son", "van", "llevamos", "gana", "pierde", "empata"):
                    continue
                ta = team_after(i + 1)
                cand_teams = [ta[0]] if ta else (teams_here if len(teams_here) == 1 else list(self.match_teams))
                ids = [g.by_number[t][toks[i].num] for t in cand_teams if toks[i].num in g.by_number.get(t, {})]
                if len(ids) > 1:
                    ids = sorted(ids, key=self._recency)
                    ids = ids[:1] if self._recency(ids[0]) < self._recency(ids[1]) else []
                if len(ids) == 1:
                    start = i - 1
                    out.append(Mention(start, (i - start + 1) + (ta[1] if ta else 0), ids[0], "player",
                                       g.players[ids[0]]["team"], "number", 0.8))
                    continue
            # "el polaco", "el canterano"
            if norm[i] == "el" and i + 1 < n_t and not taken[i + 1]:
                cands = [c for c in g.epithet.get("el " + norm[i + 1], []) if c.primary or not self.match_teams]
                if cands:
                    ta = team_after(i + 2)
                    pool = [c for c in cands if c.team == ta[0]] if ta else cands
                    pool = sorted(pool, key=lambda c: self._recency(c.id))
                    pick = None
                    if len(pool) == 1:
                        pick = pool[0]
                    elif len(pool) > 1 and self._recency(pool[0].id) < self._recency(pool[1].id):
                        pick = pool[0]
                    if pick:
                        out.append(Mention(i, 2 + (ta[1] if ta else 0), pick.id, "player", pick.team, "epithet", 0.8))
        for m in out:
            for k in range(m.i, min(n_t, m.i + m.n)):
                taken[k] = True
        return out

    def _fuzzy(self, toks, norm, taken) -> list[Mention]:
        """Nombres deformados por el reconocedor: 'valde', 'la min jamal', 'le van doski'."""
        g, out, n_t = self.gaz, [], len(toks)
        cased = any(t.cap for t in toks[1:]) and any(not t.cap for t in toks)
        i = 0
        while i < n_t:
            best = None
            for n in (3, 2, 1):
                if i + n > n_t or any(taken[i:i + n]):
                    continue
                words = norm[i:i + n]
                joined = "".join(words)
                if len(joined) < 4 or any(w.isdigit() for w in words):
                    continue
                n_common = sum(is_common(w) for w in words)
                mid_cap = [toks[i + k].cap and (i + k) > 0 and not any(ch in toks[i + k - 1].after for ch in ".!?")
                           for k in range(n)]
                if n == 1 and n_common and not (cased and mid_cap[0] and len(joined) >= 5):
                    continue
                if n > 1 and n_common == n and not (cased and any(mid_cap)):
                    continue  # todo palabras corrientes y sin mayúsculas: no es un nombre
                if n > 1 and all(len(w) <= 3 for w in words):
                    continue
                pk = phon(joined)
                scored = []
                for fk, fj, c in g.fuzzy:
                    if abs(len(fk) - len(pk)) > 3:
                        continue
                    s = max(Levenshtein.normalized_similarity(pk, fk), Levenshtein.normalized_similarity(joined, fj))
                    if pk == fk:
                        s = 1.0
                    scored.append((s, c))
                if not scored:
                    continue
                scored.sort(key=lambda x: -x[0])
                top, c = scored[0]
                second = next((s for s, c2 in scored[1:] if c2.id != c.id), 0.0)
                thr = 0.84 if n == 1 else (0.80 if n_common < n else 0.86)
                if n == 1 and cased and mid_cap[0] and not n_common:
                    thr = 0.74  # palabra desconocida con mayúscula en mitad de frase: casi seguro un nombre propio
                if len(joined) <= 5 and not (cased and any(mid_cap)):
                    thr = max(thr, 0.99 if n_common else 0.8)
                # apócope: "rapha", "lewan", "frenk" → prefijo de un único jugador
                if n == 1 and not n_common and top < thr and len(joined) >= 4:
                    pref = {c2.id for fk, fj, c2 in g.fuzzy if fj.startswith(joined) or fk.startswith(pk)}
                    if len(pref) == 1:
                        c = next(c2 for fk, fj, c2 in g.fuzzy if c2.id in pref)
                        top, second = max(thr, 0.85), 0.0
                if top >= thr and top - second >= 0.06 and (best is None or top > best[0] + 0.02):
                    best = (top, n, c)
            if best:
                top, n, c = best
                out.append(Mention(i, n, c.id, "player", c.team, "phonetic" if top >= 0.99 else "fuzzy", round(top, 2)))
                for k in range(i, i + n):
                    taken[k] = True
                i += n
            else:
                i += 1
        return out

    # ------------------------------------------------------------ roles
    @staticmethod
    def _cue(norm: list[str], m: Mention) -> Optional[str]:
        s = " ".join(norm[max(0, m.i - 3):m.i])
        for name, rx in (("for", _FOR), ("against", _AGAINST), ("victim", _VICTIM), ("by", _BY), ("with", _WITH),
                         ("to", _TO), ("of", _OF)):
            if rx.search(s):
                return name
        return None

    def _link(self, norm: list[str], mentions: list[Mention], evs: list[Ev]) -> None:
        if not evs:
            return
        team_links: list[tuple[Ev, Mention, Optional[str]]] = []
        cues = {id(m): self._cue(norm, m) for m in mentions}
        clause = self._clauses

        def has_subject_before(e: Ev) -> bool:
            """¿Hay un nombre justo antes del verbo que pueda ser su sujeto (y no cuelgue de otra situación)?"""
            for m in mentions:
                if m.type != "player" or not (0 <= e.hit.i - m.end - 1 <= 2):
                    continue
                if cues[id(m)] and any(o is not e and o.hit.end < m.i for o in evs):
                    continue
                return True
            return False

        for m in mentions:
            if m.type == "coach":
                continue
            cue = cues[id(m)]
            best, bd = None, 1e9
            for e in evs:
                h = e.hit
                before = m.end < h.i
                inside = not before and m.i <= h.end
                if clause[min(m.i, len(clause) - 1)] != clause[h.i] and not (
                        h.need_e and not before and m.i - h.end - 1 <= 2):
                    continue  # otra oración
                gap = h.i - m.end - 1 if before else 0 if inside else m.i - h.end - 1
                if gap > (6 if before else 8 if cue else 6):
                    continue
                d = gap - (0.5 if before and not cue else 0) + (0.4 if cue in ("of", "by") and before else 0)
                # una preposición liga el nombre al evento que tiene delante ("falta DE Juric", "sobre Pedri")
                if cue and not before:
                    d -= 3.0 if gap <= 4 else 0.6
                if h.need_e and not before and gap <= 2:
                    d -= 2.0  # el patrón exigía un nombre justo después: es este
                if h.need_e and before and not cue and any(
                        o.type == "player" and 0 <= o.i - h.end - 1 <= 2 for o in mentions):
                    d += 1.0
                if not before and not inside and gap == 0 and not cue and m.type == "player" and not has_subject_before(e):
                    d -= 1.5  # verbo + sujeto: "roba Casadó", "la cuelga Raphinha"
                if d < bd:
                    best, bd = e, d
            if best is None:
                continue
            if m.type == "team":
                team_links.append((best, m, cue))
                continue
            if m.id in best.roles.values():
                continue
            if cue and best.hit.i <= m.i - 1 <= best.hit.end and norm[m.i - 1] == "para" and best.type == "parada":
                cue = None  # "se la PARA Hein": verbo, no preposición
            role = self._role(best, m, cue, m.end < best.hit.i, norm)
            if role and role not in best.roles:
                best.roles[role] = m.id
            elif role == "actor" and best.roles.get("actor") != m.id:
                alt = {"transfer": "receiver", "duel": "victim"}.get(FRAME[best.type])
                if alt and alt not in best.roles:
                    best.roles[alt] = m.id
        team_links.sort(key=lambda x: x[2] not in ("for", "against"))  # el equipo con preposición manda
        for e, m, cue in team_links:
            if any(r in e.roles for r in ("actor", "receiver", "victim", "out")) and FRAME[e.type] != "restart":
                continue
            if "actor" in e.roles:
                continue
            if FRAME[e.type] == "solo" and e.type != "gol" and not (m.i > e.hit.end and cue in ("of", "for")) \
                    and not (m.end < e.hit.i and e.hit.i - m.end - 1 <= 1):
                continue  # un equipo nombrado cerca no es el autor del tiro
            e.roles.setdefault("team_against" if cue == "against" or (cue == "to" and e.type == "gol") else "team_for", m.id)

    def _role(self, e: Ev, m: Mention, cue: Optional[str], before: bool, norm: list[str]) -> Optional[str]:
        frame, h = FRAME[e.type], e.hit
        first = norm[h.i]
        if frame == "none":
            return None
        if frame == "swap":
            if first.startswith("sustituid"):
                return "actor" if cue == "by" else "out"
            if cue == "by":
                return "out"
            if cue in ("of",) and first in ("lugar", "en", "cambio"):
                return "out"
            if _SWAP_OUT_FIRST.match(first) and first not in ("se",) or (first == "se" and h.n > 1 and norm[h.i + 1] in ("retira", "marcha", "va", "retiran", "marchan", "van")):
                return "out"
            if cue == "to" and first in ("sustituye", "reemplaza", "deja"):
                return "out"
            return "actor"
        if frame == "transfer":
            if cue in ("for", "to", "with", "victim"):
                return "receiver"
            if cue in ("of", "by"):
                return "actor"
            return "actor" if (before or "actor" not in e.roles) else "receiver"
        if frame == "duel":
            passive = bool(e.hit.sit.passive and e.hit.sit.passive.match(first))
            if cue in ("victim", "to", "against"):
                return "victim"
            if cue == "for":
                return "victim"
            if cue == "by":
                return "actor"
            if cue == "of":
                return "victim" if (e.hit.sit.after == "victim" and not before and m.i - 1 <= h.end) else "actor"
            if passive:
                return "victim" if before else "actor"
            if e.hit.sit.after == "victim" and not before and m.i - 1 <= h.end:
                return "victim"
            if e.type in ("penalti", "falta") and before and any(
                    re.match(r"^(recibe|recibio|sufre|sufrio|provoca|provoco|gana|gano|fuerza|forzo|saca|le)$", w)
                    for w in norm[m.end + 1:h.i + 1]):
                return "victim"
            return "actor" if (before or "actor" not in e.roles) else "victim"
        # solo / restart
        if cue in ("against",):
            return None
        if e.type == "fuera_juego" and before and h.i - m.end - 1 > 2:
            return None
        if frame == "restart" and not ((before and not cue and h.i - m.end - 1 <= 3) or
                                       (not before and (cue in ("of", "by") or m.i - h.end - 1 <= 1))):
            return None  # un nombre cerca de "córner" no es quien lo saca
        if cue == "to" and e.type in ("gol", "tiro", "ocasion") and not before:
            return None  # "le marca a Hein": no es el actor
        return "actor"

    # ------------------------------------------------------------ modalidad
    def _modality(self, toks: list[Tok], norm: list[str], e: Ev, text_n: str, is_question: bool) -> str:
        forced = MODAL_BY_FINE.get(e.fine)
        h = e.hit
        before = " ".join(norm[max(0, h.i - 7):h.i])
        after = " ".join(norm[h.end + 1:h.end + 5])
        # corta el contexto anterior en el último límite de oración
        cl = self._clauses
        cut = 0
        for k in range(h.i - 1, max(-1, h.i - 8), -1):
            if cl[k] != cl[h.i]:
                cut = k + 1
                break
        clause_n = " ".join(w for k, w in enumerate(norm) if cl[k] == cl[h.i])
        after = " ".join(w for k, w in enumerate(norm[h.end + 1:h.end + 5], h.end + 1) if cl[k] == cl[h.i])
        before = " ".join(norm[max(cut, h.i - 7):h.i])
        if forced == "negated":
            return "negated"
        first, last = norm[h.i], norm[h.end]
        if (first in ("va", "quiere", "quieren") or h.n <= 2 and first not in ("acaba", "vuelve", "ha", "volvio") and re.search(
                r"(?:[aei]r|[aei]rl[aeo]s?|[aei]rse)$", last) and last not in (
                "mujer", "ayer", "taller", "lugar", "primer", "tercer", "crear", "ser", "par", "mar", "bar", "corner", "jorner", "cornel",
                "korner", "carner", "saber", "poder", "mejor", "peor", "mayor", "menor", "superior", "anterior", "exterior")) and not re.search(
                r"(?:^| )(?:acaba de|vuelve a|ha vuelto a|volvio a|logra|consigue|sin)$", before) and FRAME[e.type] != "none":
            return "hypothetical"  # "va a poner", "quiere rematar": intención, no hecho
        neg = bool(_NEG_BEFORE.search(before)) or bool(_NEG_AFTER.match(after))
        if is_question and (neg or _INTERROG.search(text_n)):
            return "hypothetical"
        if neg:
            return "negated"
        if e.type in ("falta", "corner", "saque_banda", "saque_puerta", "fuera_juego", "amarilla", "roja") and re.search(
                r"(?:^| )(?:va a ser|va a haber|va a pitar|sera|va a senalar)(?: \w+)?$", before):
            return "real"
        if _HYP_BEFORE.search(before) and not re.search(r"(?:^| )si(?: \w+){0,3}$", before.replace("si senor", "")) \
                or self._conditional(toks, h.i, cut):
            return "hypothetical"
        if forced:
            return forced
        if _PAST.search(clause_n):
            return "past"
        if e.fine == "doblete":
            return "mention"  # "doblete", "hat-trick": resumen de goles ya cantados
        if e.type == "gol" and h.i > 0 and norm[h.i] in ("gol", "golazo") and re.match(
                r"^(su|el|del|al|ese|este|aquel|mi|tu|primer|segundo|tercer|cuarto|quinto|sexto|ultimo|otro|cada|con|de|"
                r"que|vaya|menudo|pedazo|tremendo)$",
                norm[h.i - 1]) and not (h.end + 2 < len(norm) and norm[h.end + 1] in ("de", "del")):
            return "mention"  # "su gol", "se le resiste el gol": se habla de un gol, no se canta
        if e.type == "penalti" and h.i > 0 and norm[h.i - 1] in ("ese", "este", "aquel", "posible", "supuesto"):
            return "hypothetical"  # "ese penalti sobre Kike": se discute, no se ha pitado
        return "real"

    @staticmethod
    def _conditional(toks: list[Tok], i: int, cut: int) -> bool:
        """'si marca Lewandowski…' (si sin tilde; 'sí' y 'sí señor' no cuentan)."""
        for k in range(max(cut, i - 6), i):
            if toks[k].raw.lower() == "si" and not (k + 1 < len(toks) and toks[k + 1].n in ("senor", "senora", "si", "que")):
                return True
        return False

    # ------------------------------------------------------------ análisis
    def analyze(self, text: str, *, t0: float = 0.0, t1: float = 0.0, final: bool = True, ctx: Any = None) -> NluResult:
        t_in = time.perf_counter()
        toks = tokenize(text)
        norm = [t.n for t in toks]
        text_n = " ".join(norm)
        now = t1 or t0 or self.clock
        mentions = self._entities(toks)
        self._clauses = self._clause_ids(toks, mentions)
        covered = {k for m in mentions if m.type != "team" or m.via == "epithet" for k in range(m.i, m.i + m.n)}
        covered -= {k for k, w in enumerate(norm) if w == "para"}
        starts = {m.i for m in mentions}
        pstarts = {m.i for m in mentions if m.type == "player"}
        hits = [h for h in self._find_skipping_fillers(norm, starts, covered, pstarts) if h.sit.coarse]
        hits = self._prune(norm, hits, mentions)
        evs = [Ev(h, h.sit.coarse, h.sit.id, pos=float(h.i)) for h in hits]
        mentions += self._corefs(toks, norm, mentions, now)
        mentions.sort(key=lambda m: m.i)
        self._swap_frames(norm, mentions, evs)
        is_query = bool(_QUERY.search(text_n)) or any(
            w in self._TOPICS and w.endswith("s") and i + 2 < len(norm) and norm[i + 1] in ("de", "del") and (i + 2) in
            {m.i for m in mentions if m.type == "player"} for i, w in enumerate(norm))
        if is_query:
            evs += self._query_topics(norm, evs)
        self._link(norm, mentions, evs)
        evs += self._sub_lists(norm, mentions, evs)
        evs.sort(key=lambda e: e.pos)
        is_q = "?" in text or "¿" in text
        for e in evs:
            cl = self._clauses
            in_query_clause = is_query and (len(set(cl)) == 1 or bool(_QUERY.search(
                " ".join(w for k, w in enumerate(norm) if cl[k] == cl[e.hit.i]))) or e.fine == "query_topic")
            e.modality = "query" if in_query_clause else self._modality(toks, norm, e, text_n, is_q)
        for e in evs:
            if e.modality == "mention":  # dentro de la celebración (90 s) sigue siendo el gol; fuera, es recuerdo
                live = any(now and 0 <= now - b["t0"] <= BURST_LIVE_S for b in self._bursts)
                e.modality = "real" if live else "past"
        evs = self._merge(evs)
        evs = [e for e in evs if not (FRAME[e.type] == "transfer" and not any(
            r in e.roles for r in ("actor", "receiver")) and any(r.startswith("team") for r in e.roles))]
        self._order_and_inherit(norm, evs, mentions, now)
        self._loose_actor(evs, mentions)
        if final:
            self._goal_bursts(evs, now)
        for e in evs:  # nadie se pasa el balón ni se hace una falta a sí mismo
            a = e.roles.get("actor")
            if a and any(e.roles.get(r) == a for r in ("receiver", "victim", "out")):
                del e.roles["actor"]
        self._chains(evs)

        res = NluResult(text=text, t0=t0, t1=t1, final=final)
        seen = set()
        for m in mentions:
            if (m.type, m.id) in seen:
                continue
            seen.add((m.type, m.id))
            res.entities.append(EntityMention(type=m.type, id=m.id, span=(m.i, m.i + m.n), surface=m.surface or "",
                                              score=m.score, via="alias" if m.via == "short" else m.via))  # type: ignore[arg-type]
        ent_ids = {m.id for m in mentions}
        for e in evs:
            for r, v in e.roles.items():
                if v not in ent_ids:  # rol resuelto por contexto: la entidad se añade como correferencia
                    ent_ids.add(v)
                    typ = "team" if v in self.gaz.teams else "player"
                    res.entities.append(EntityMention(type=typ, id=v, span=(0, 0), surface="", score=0.7, via="coref"))
            res.events.append(NluEvent(type=e.type, fine=e.fine, modality=e.modality, roles=e.roles,  # type: ignore[arg-type]
                                       span=(e.hit.i, e.hit.end + 1), chain=e.chain, order=e.order,
                                       confidence=0.6 if e.inherited else 0.9))
        if _QUERY.search(text_n):
            subj = next((m.id for m in mentions if m.type == "player"), None)
            res.intents.append(Intent(type="stat_query", topic=evs[0].type if evs else None, subject=subj))
        if final:
            pl = [m.id for m in mentions if m.type == "player"]
            if pl:
                self.subject = next((e.roles["actor"] for e in evs if e.roles.get("actor")), pl[0])
                self.last_players = pl
            self._remember(mentions, now)
            self.clock = now
        res.ts = {"nlu_ms": (time.perf_counter() - t_in) * 1000}
        return res

    _FILLER1 = {"ya", "ahora", "ahi", "finalmente", "bueno", "eh", "chicos", "tambien", "ojito", "ojo", "pues"}
    _FILLER2 = {("de", "nuevo"), ("otra", "vez"), ("madre", "mia"), ("por", "cierto"), ("una", "vez")}

    def _find_skipping_fillers(self, norm, starts, covered, pstarts) -> list[Hit]:
        """Las muletillas ("de nuevo", "ya", "ahora"…) no rompen un patrón: se buscan las situaciones sin ellas y
        se devuelven las posiciones en la frase original."""
        keep: list[int] = []
        i = 0
        while i < len(norm):
            if i not in covered and (norm[i], norm[i + 1] if i + 1 < len(norm) else "") in self._FILLER2 \
                    and (i + 1) not in covered:
                i += 2
                continue
            if i not in covered and norm[i] in self._FILLER1:
                i += 1
                continue
            keep.append(i)
            i += 1
        if len(keep) == len(norm):
            return self.cat.find(norm, starts, covered, pstarts)
        back = {k: orig for k, orig in enumerate(keep)}
        fwd = {orig: k for k, orig in back.items()}
        red = [norm[o] for o in keep]
        hits = self.cat.find(red, {fwd[x] for x in starts if x in fwd}, {fwd[x] for x in covered if x in fwd},
                             {fwd[x] for x in pstarts if x in fwd})
        out = []
        for h in hits:
            a, b = back[h.i], back[h.i + h.n - 1]
            out.append(Hit(h.sit, a, b - a + 1, h.need_e))
        return out

    def _prune(self, norm: list[str], hits: list[Hit], mentions: list[Mention]) -> list[Hit]:
        """Vetos que dependen de las entidades."""
        out = []
        gk = {m.i for m in mentions if m.type == "player" and self.gaz.players[m.id]["position"] == "GK"}
        for h in hits:
            if h.sit.id == "x_sale_debil" and not any(o is not h and o.sit.coarse == "cambio" for o in hits):
                continue
            if h.sit.id == "x_pase_para" and norm[h.i] in ("a", "con") and h.n == 1:
                prev_m = next((m for m in mentions if m.type == "player" and m.end == h.i - 1), None)
                if prev_m is None or any(o is not h and 0 <= prev_m.i - o.end - 1 <= 2 for o in hits):
                    continue  # "derriba Araújo a Machis": la "a" es del verbo anterior
            if h.sit.id == "x_pase_para":
                # "para" + jugador: pase si hay otro jugador antes cerca y no es parte de otra situación
                if any(o is not h and o.i <= h.i <= o.end for o in hits):
                    continue
                nxt = h.i + 1
                prev_player = any(m.type == "player" and 0 <= h.i - m.end - 1 <= 4 for m in mentions)
                if nxt in gk and not prev_player and (h.i == 0 or norm[h.i - 1] in ("que", "y", "la", "lo", "le")):
                    h = Hit(self.cat.sits["x_parada"], h.i, h.n, True)  # "Para Ter Stegen"
                elif h.i > 0 and norm[h.i - 1] in ("gracias", "saludo", "saludos", "abrazo", "vamos", "vaya", "voy",
                                                   "aplausos", "minutos", "tiempo", "meritos", "listo", "preparado"):
                    continue
                elif not any(m.type == "player" and 0 <= h.i - m.end - 1 <= 6 for m in mentions):
                    continue  # "para X" sin nadie antes que dé el pase
            out.append(h)
        return out

    _TOPICS = {"goles": "gol", "gol": "gol", "asistencias": "asistencia", "amarillas": "amarilla", "tarjetas": "amarilla",
               "rojas": "roja", "expulsiones": "roja", "penaltis": "penalti", "faltas": "falta", "regates": "regate",
               "tiros": "tiro", "disparos": "tiro", "remates": "tiro", "paradas": "parada", "pases": "pase",
               "corners": "corner", "centros": "centro", "robos": "robo", "recuperaciones": "robo",
               "perdidas": "perdida", "despejes": "despeje", "ocasiones": "ocasion", "cambios": "cambio"}

    def _query_topics(self, norm: list[str], evs: list[Ev]) -> list[Ev]:
        """'¿cuántos goles lleva X?': el sustantivo en plural es el tema de la petición."""
        have = {e.type for e in evs}
        out = []
        for i, w in enumerate(norm):
            t = self._TOPICS.get(w)
            if t and t not in have and not any(e.hit.i <= i <= e.hit.end for e in evs):
                have.add(t)
                out.append(Ev(Hit(self.cat.sits["gol"], i, 1), t, "query_topic", pos=float(i)))
        return out

    def _corefs(self, toks: list[Tok], norm: list[str], mentions: list[Mention], now: float) -> list[Mention]:
        """Pronombres resueltos con lo último que se nombró: 'él', 'su compañero'."""
        out: list[Mention] = []
        here = {m.id for m in mentions if m.type == "player"}
        fresh = [pid for pid, t in reversed(self.recent) if now - t <= _SUBJECT_TTL * 2]
        for i, t in enumerate(toks):
            if t.raw.lower() == "él" and fresh:
                pid = self.subject if self.subject and self.subject not in here else next((p for p in fresh if p not in here), None)
                if pid:
                    out.append(Mention(i, 1, pid, "player", self.gaz.players[pid]["team"], "coref", 0.7))
                    here.add(pid)
            elif norm[i] in ("companero", "socio") and i > 0 and norm[i - 1] == "su":
                actor = next((m for m in reversed(mentions) if m.type == "player" and m.i < i), None)
                team = actor.team if actor else None
                pool = [p for p in self.last_players if p != self.subject] + fresh
                pid = next((p for p in pool if p not in here and (team is None or self.gaz.players[p]["team"] == team)), None)
                if pid:
                    out.append(Mention(i - 1, 2, pid, "player", self.gaz.players[pid]["team"], "coref", 0.7))
                    here.add(pid)
        return out

    @staticmethod
    def _clause_ids(toks: list[Tok], mentions: list[Mention]) -> list[int]:
        """Oraciones dentro del enunciado: por puntuación fuerte o, en texto con mayúsculas, por palabra corriente
        en mayúscula que no es un nombre ("… juega Koundé Balón para Lamine")."""
        in_name = {k for m in mentions for k in range(m.i, m.i + m.n)}
        cased = any(t.cap for t in toks[1:]) and any(not t.cap for t in toks)
        ids, c = [], 0
        for i, t in enumerate(toks):
            if i > 0 and (any(ch in toks[i - 1].after for ch in ".!?;") or (
                    cased and t.cap and i not in in_name and (i - 1) not in in_name and is_common(t.n))):
                c += 1
            elif i > 0 and cased and t.cap and i not in in_name and is_common(t.n) and (i - 1) in in_name \
                    and t.n not in ("para", "a", "con", "de", "del", "por", "sobre"):
                c += 1
            ids.append(c)
        return ids or [0]

    def _sub_lists(self, norm: list[str], mentions: list[Mention], evs: list[Ev]) -> list[Ev]:
        """'entran Fermín, Eric García y Sergi Domínguez': un cambio por cada nombre de la lista."""
        extra: list[Ev] = []
        players = [m for m in mentions if m.type == "player"]
        for e in evs:
            if e.type != "cambio":
                continue
            for role in ("actor", "out"):
                pid = e.roles.get(role)
                last = next((m for m in players if m.id == pid and m.i > e.hit.end - 1), None)
                while last is not None:
                    nxt = next((m for m in players if m.i > last.end and all(w in ("y", "e", "tambien") for w in norm[last.end + 1:m.i])
                                and m.i - last.end - 1 <= 2 and m.id not in e.roles.values()
                                and not any(m.id in x.roles.values() for x in extra)), None)
                    if nxt is None:
                        break
                    extra.append(Ev(e.hit, "cambio", e.fine, roles={role: nxt.id}, pos=e.pos + 0.01 * (len(extra) + 1)))
                    last = nxt
        return extra

    def _swap_frames(self, norm: list[str], mentions: list[Mention], evs: list[Ev]) -> None:
        """'entra X por Y' es UN cambio; 'sale Y y entra X' también."""
        swaps = [e for e in evs if e.type == "cambio"]
        for a in swaps:
            for b in swaps:
                if a is not b and b in evs and a in evs and 0 < b.hit.i - a.hit.end <= 6:
                    fa, fb = norm[a.hit.i], norm[b.hit.i]
                    between = [e for e in evs if a.hit.end < e.hit.i < b.hit.i]
                    if not between and (bool(_SWAP_OUT_FIRST.match(fa)) != bool(_SWAP_OUT_FIRST.match(fb)) or fa == "cambio" or fb == "cambio"):
                        players_between = [m for m in mentions if m.type == "player" and a.hit.end < m.i < b.hit.i]
                        if len(players_between) <= 1:
                            b.pos = a.pos
                            b._merge_into = a  # type: ignore[attr-defined]

    def _merge(self, evs: list[Ev]) -> list[Ev]:
        out: list[Ev] = []
        for e in evs:
            tgt = getattr(e, "_merge_into", None)
            while tgt is not None and tgt not in out and getattr(tgt, "_merge_into", None) is not None:
                tgt = tgt._merge_into  # type: ignore[attr-defined]
            if tgt is not None and tgt in out:
                for r, v in e.roles.items():
                    tgt.roles.setdefault(r, v)
                continue
            dup = next((o for o in out if o.type == e.type and o.modality == e.modality and (
                o.roles == e.roles or not e.roles or not o.roles or
                (o.roles.get("actor") == e.roles.get("actor") and (set(o.roles) <= set(e.roles) or set(e.roles) <= set(o.roles))
                 and all(o.roles[r] == e.roles[r] for r in set(o.roles) & set(e.roles))))
                and e.hit.i - o.hit.end <= 7), None)
            if dup:
                for r, v in e.roles.items():
                    dup.roles.setdefault(r, v)
                continue
            out.append(e)
        return out

    def _order_and_inherit(self, norm: list[str], evs: list[Ev], mentions: list[Mention], now: float) -> None:
        # "gol de X a pase de Y", "paradón al remate de Z tras un centro de W": lo que va tras el conector pasó antes
        for k, e in enumerate(evs):
            pre = " ".join(norm[max(0, e.hit.i - 3):e.hit.i])
            first = norm[e.hit.i]
            if k > 0 and (re.search(r"(?:^| )(tras|despues de|despues del|gracias a|gracias al|aprovechando|al)( un| una| el| la)?$", pre)
                          or first in ("a", "tras") or e.fine == "x_asistencia" or (e.type == "asistencia" and first in ("asistencia", "pase"))):
                e.pos = min(x.pos for x in evs[:k]) - 1 + k * 0.01
        evs.sort(key=lambda e: e.pos)
        players_in_sentence = [m for m in mentions if m.type == "player"]
        # un pase ligado en la misma frase al gol de otro jugador es la asistencia ("se la deja X y marca Y")
        for k, e in enumerate(evs):
            if e.type in ("pase", "centro") and e.modality == "real" and e.roles.get("actor"):
                goal = next((x for x in evs[max(0, k - 1):k + 2] if x.type == "gol" and x.modality == "real"
                             and x.roles.get("actor") and x.roles["actor"] != e.roles["actor"]), None)
                if goal and e.roles.get("receiver") in (None, goal.roles["actor"]) and e.type == "pase":
                    e.type, e.roles["receiver"] = "asistencia", goal.roles["actor"]
                    e.pos = min(e.pos, goal.pos - 0.5)
        evs.sort(key=lambda e: e.pos)
        for k, e in enumerate(evs):
            frame = FRAME[e.type]
            if frame == "none":
                continue
            prev = evs[k - 1] if k else None
            if e.type == "asistencia" and "receiver" not in e.roles:
                goal = next((x for x in evs if x.type == "gol" and x.roles.get("actor")), None)
                if goal and goal.roles["actor"] != e.roles.get("actor"):
                    e.roles["receiver"] = goal.roles["actor"]
            if e.type == "parada" and "victim" not in e.roles and prev is not None and prev.type == "tiro" \
                    and prev.roles.get("actor") and prev.roles["actor"] != e.roles.get("actor"):
                e.roles["victim"] = prev.roles["actor"]
            if e.type == "lesion" and "actor" not in e.roles and prev is not None and prev.type == "falta" and prev.roles.get("victim"):
                e.roles["actor"] = prev.roles["victim"]
            if e.type == "cambio" and "out" not in e.roles and prev is not None and prev.type == "lesion" \
                    and prev.roles.get("actor") and prev.roles["actor"] != e.roles.get("actor"):
                e.roles["out"] = prev.roles["actor"]
            if "actor" in e.roles or "team_for" in e.roles or (frame == "swap" and "out" in e.roles):
                continue
            if e.type == "palo" or e.modality == "hypothetical" or frame in ("swap", "restart") or e.type in (
                    "falta", "penalti", "mano", "fuera_juego", "lesion"):
                continue
            if e.modality in ("query",):
                continue
            src = None
            if prev is not None and prev.modality == e.modality:
                if e.type in ("amarilla", "roja") and prev.type in ("falta", "penalti", "mano"):
                    src = prev.roles.get("actor")
                elif prev.type in ("perdida",) and e.type == "robo":
                    src = None
                elif e.type == "parada":
                    src = None
                    if prev.type == "tiro" and "victim" not in e.roles and prev.roles.get("actor"):
                        e.roles["victim"] = prev.roles["actor"]
                elif FRAME[prev.type] == "transfer":
                    src = prev.roles.get("receiver") or (prev.roles.get("actor") if e.type in ("centro", "tiro", "pase", "regate") and "receiver" not in prev.roles else None)
                elif prev.type in ("regate", "robo", "tiro", "gol", "despeje", "ocasion", "falta"):
                    src = prev.roles.get("actor") if not (prev.type == "falta") else None
            if src is None and prev is None and not players_in_sentence and e.modality == "real" and e.type in (
                    "gol", "tiro", "regate", "centro", "robo", "perdida", "despeje", "lesion", "palo", "ocasion", "parada"):
                # sujeto elidido: el último jugador nombrado hace muy poco
                if self.recent and now - self.recent[-1][1] <= _SUBJECT_TTL:
                    src = self.recent[-1][0]
            if src and src not in e.roles.values():
                e.roles["actor"] = src
                e.inherited = True
            if e.type == "parada" and "victim" not in e.roles and prev is not None and prev.type == "tiro" \
                    and prev.roles.get("actor") and prev.roles.get("actor") != e.roles.get("actor"):
                e.roles["victim"] = prev.roles["actor"]

    def _loose_actor(self, evs: list[Ev], mentions: list[Mention]) -> None:
        """Acción sin sujeto enlazado: el último jugador nombrado antes en el enunciado ("… Raúl Moro de nuevo, que
        se sigue marchando, se va de Olmo")."""
        for e in evs:
            if "actor" in e.roles or "team_for" in e.roles or e.modality == "query":
                continue
            if e.type not in ("regate", "tiro", "centro", "robo", "perdida", "despeje") and not (
                    e.type == "pase" and "receiver" in e.roles):
                continue
            used = set(e.roles.values())
            prev = [m for m in mentions if m.type == "player" and m.end < e.hit.i and e.hit.i - m.end <= 12 and m.id not in used]
            if prev:
                e.roles["actor"] = prev[-1].id
                e.inherited = True

    def _goal_bursts(self, evs: list[Ev], now: float) -> None:
        """Ver BURST_LIVE_S / BURST_RECALL_S. Solo con reloj real (audio en flujo)."""
        if not now:
            return
        for e in evs:
            if e.type != "gol" or e.modality != "real":
                continue
            who = e.roles.get("actor")
            burst = next((b for b in reversed(self._bursts) if now - b["t0"] <= BURST_RECALL_S and (
                who is None or b["who"] is None or b["who"] == who)), None)
            if burst is None:
                self._bursts.append({"t0": now, "who": who})
            elif now - burst["t0"] > BURST_LIVE_S:
                e.modality = "past"
            else:
                burst["who"] = burst["who"] or who
                if who is None and burst["who"] and "team_for" not in e.roles:
                    e.roles["actor"] = burst["who"]
                    e.inherited = True

    def _chains(self, evs: list[Ev]) -> None:
        run: list[Ev] = []

        def close() -> None:
            if len(run) >= 2:
                self._chain_n += 1
                for o, e in enumerate(run, 1):
                    e.chain, e.order = f"c{self._chain_n}", o
            run.clear()

        for e in evs:
            if e.modality != "real" or FRAME[e.type] == "none":
                close()
                continue
            if run and not self._related(run[-1], e):
                close()
            run.append(e)
        close()

    @staticmethod
    def _related(a: Ev, b: Ev) -> bool:
        pa = {v for r, v in a.roles.items() if not r.startswith("team")}
        pb = {v for r, v in b.roles.items() if not r.startswith("team")}
        if pa & pb or b.inherited:
            return True
        flow = {("perdida", "robo"), ("centro", "tiro"), ("centro", "gol"), ("tiro", "parada"), ("falta", "amarilla"),
                ("falta", "roja"), ("asistencia", "gol"), ("pase", "tiro"), ("pase", "gol"), ("corner", "tiro"),
                ("corner", "gol"), ("corner", "despeje"), ("centro", "despeje"), ("tiro", "palo"), ("robo", "pase"),
                ("tiro", "gol"), ("parada", "corner"), ("regate", "tiro"), ("regate", "centro"), ("centro", "parada"),
                ("tiro", "despeje"), ("pase", "centro"), ("pase", "regate"), ("penalti", "amarilla"), ("penalti", "roja"),
                ("falta", "tiro"), ("robo", "tiro"), ("pase", "pase"), ("mano", "penalti"), ("penalti", "gol")}
        return (a.type, b.type) in flow
