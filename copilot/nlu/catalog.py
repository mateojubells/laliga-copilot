"""Catálogo de situaciones (docs/ARCHITECTURE.md §7.3).

Base: las ~90 situaciones del prototipo (catalog_legacy.json, exportadas de legacy/catalogo.js con sus vetos), más
vocabulario de narración añadido aquí (EXTRA). Cada situación fina declara su tipo grueso (COARSE): el que se evalúa.

Sintaxis de patrón (tokens normalizados): "(a|b)" alternativas, "pref*" prefijo, "tok?" opcional, " +E" al final
exige una entidad en los 3 tokens siguientes.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

# fino -> (tipo grueso, modalidad forzada o None). Lo que no está aquí no genera evento.
COARSE: dict[str, tuple[str, str | None]] = {
    "adelanta": ("gol", None), "gol": ("gol", None), "gol_penalti": ("gol", None), "autogol": ("gol", None), "doblete": ("gol", None),
    "gol_anulado": ("gol", "negated"),
    "tiro": ("tiro", None), "tiro_puerta": ("tiro", None), "tiro_fuera": ("tiro", None), "remate_cabeza": ("tiro", None),
    "chilena": ("tiro", None), "vaselina": ("tiro", None), "volea": ("tiro", None), "tiro_lejano": ("tiro", None),
    "lanza_penalti": ("tiro", None), "penalti_fallado": ("tiro", None),
    "parada": ("parada", None), "penalti_parado": ("parada", None),
    "palo": ("palo", None), "ocasion": ("ocasion", None), "mano_a_mano": ("ocasion", None),
    "pase": ("pase", None), "pase_clave": ("pase", None), "pase_largo": ("pase", None), "pared": ("pase", None),
    "cesion": ("pase", None), "centro": ("centro", None), "asistencia": ("asistencia", None),
    "regate": ("regate", None), "cano": ("regate", None), "sombrero": ("regate", None), "desborde": ("regate", None),
    "falta": ("falta", None), "falta_tactica": ("falta", None), "falta_peligrosa": ("falta", None),
    "penalti": ("penalti", None), "penalti_reclamado": ("penalti", "hypothetical"), "penalti_no": ("penalti", "negated"),
    "mano": ("mano", None), "corner": ("corner", None), "lanza_corner": ("corner", None), "corner_corto": ("corner", None),
    "saque_banda": ("saque_banda", None), "saque_largo": ("saque_banda", None), "saque_puerta": ("saque_puerta", None),
    "fuera_juego": ("fuera_juego", None), "amarilla": ("amarilla", None), "segunda_amarilla": ("amarilla", None),
    "tarjeta": ("amarilla", None), "roja": ("roja", None), "cambio": ("cambio", None), "lesion": ("lesion", None),
    "robo": ("robo", None), "intercepcion": ("robo", None), "perdida": ("perdida", None), "despeje": ("despeje", None),
    "var": ("var", None), "inicio": ("inicio", None), "descanso": ("descanso", None), "final": ("final", None),
}

# marco de roles por tipo grueso
FRAME = {
    "pase": "transfer", "centro": "transfer", "asistencia": "transfer",
    "regate": "duel", "falta": "duel", "robo": "duel", "penalti": "duel", "parada": "duel", "mano": "duel",
    "gol": "solo", "tiro": "solo", "palo": "solo", "ocasion": "solo", "perdida": "solo", "despeje": "solo",
    "lesion": "solo", "amarilla": "solo", "roja": "solo", "fuera_juego": "solo",
    "corner": "restart", "saque_banda": "restart", "saque_puerta": "restart",
    "cambio": "swap", "var": "none", "inicio": "none", "descanso": "none", "final": "none",
}

# vocabulario añadido: (id fino nuevo, tipo grueso, patrones, opciones)
#   after: rol de la entidad que va DESPUÉS del patrón sin preposición propia ("se va de X" → X es víctima)
EXTRA: list[tuple[str, str, list[str], dict]] = [
    ("x_gol", "gol", ["marca", "marcan", "marco", "la clava", "la manda a guardar", "la manda a la red", "la mete", "la enchufa", "golito",
                      "gol de +E", "hace el (primero|segundo|tercero|cuarto|quinto|sexto|septimo)",
                      "(pone|hace) el (1|2|3|4|5|6|7) (a|0|1|2)"], {}),
    ("x_tiro", "tiro", ["(la|le|lo|los|les) pega", "pega +E", "pegarle", "rematar", "cabecear", "disparar", "chutar", "prueba fortuna", "lo intenta desde", "remate de +E", "disparo de +E",
                        "tiro de +E", "cabezazo de +E", "(tira|tiran|tiro) a puerta"], {}),
    ("x_parada", "parada", ["se la para", "(la|lo) para", "le para", "para el (disparo|tiro|remate|cabezazo|balon)",
                            "detiene", "paradon de +E", "parada de +E", "mano salvadora", "(que|y) para +E",
                            "para (este|ese|el|un|otro) (disparo|tiro|remate|cabezazo|balon|penalti)", "las manos de +E"], {}),
    ("x_pase", "pase", ["abre (a|para|hacia)", "abre a la banda", "(se la|la) (da|deja|entrega|cede|sirve|toca|pasa|juega) (a|para|con) +E",
                        "se la (da|deja|entrega|cede|sirve|pasa)", "(juega|jugando|combina|conecta|toca|asocia) con +E",
                        "(balon|pelota) (es)? para +E", "busca a +E", "se apoya en +E", "se apoya (ahora)? en +E", "con un pase", "(que|vaya|menudo) pase", "(da|mete|pone) (el|un) (ultimo)? pase", "toca para", "tocar para", "(el|un) pase (es|ha sido|fue)", "retrasa (el balon)? (para|a|hacia)", "encuentra a +E", "se la devuelve", "la devuelve a +E",
                        "habilita a +E", "filtra (para|a) +E", "en largo (para|hacia|a) +E", "mete el pase",
                        "pase de +E", "(cambia|cambio) (el|de) juego", "(la|lo) (ve|encuentra) +E"], {}),
    ("x_pase_para", "pase", ["(para|a)", "para el bueno de", "para la posicion (que ocupa|de)", "en largo para",
                             "otra vez para", "de nuevo para"], {}),
    ("x_sale_debil", "cambio", ["se va +E"], {}),
    ("x_centro", "centro", ["la pone", "ponerla", "va a poner", "la va a poner", "la cuelga", "colgarla", "centrar", "pone el centro", "pone el balon", "centro de +E", "centro", "centro para +E",
                            "la mete al area", "cuelga el balon"], {}),
    ("x_asistencia", "asistencia", ["a pase de +E", "tras (un)? pase de +E", "tras asistencia de +E", "asistencia de +E",
                                    "asistido por +E", "regalo de +E", "servicio de +E"], {}),
    ("x_regate", "regate", ["se va de +E", "se marcha de +E", "se escapa de +E", "se deshace de +E", "se libra de +E",
                            "se quita (a|de) +E", "se quita de encima a +E", "supera a +E", "(marchar|marcharse|irse|ir) de +E", "se va de todos", "deja atras a +E",
                            "sienta a +E", "se lo quita", "rompe a +E", "baila a +E", "regate de +E", "cano de +E",
                            "cano a +E", "sombrero a +E"], {"after": "victim"}),
    ("x_robo", "robo", ["roba", "roban", "robo", "robar", "recuperar", "recupera", "recuperan", "recuperacion de +E", "(se|le) la quita",
                        "se lo quita a +E", "le arrebata", "robo de +E", "corta +E"], {}),
    ("x_perdida", "perdida", ["la pierde", "(la|lo) va a perder", "perderla", "(la|lo) regala", "perdida de +E", "pierde +E", "se la quitan"], {}),
    ("x_despeje", "despeje", ["la saca", "saca el balon", "aleja el peligro", "manda el balon fuera", "despeje de +E"], {}),
    ("x_falta", "falta", ["(es|era|fue|hay|pita|pitan|senala|otra|nueva) falta", "falta y (amarilla|tarjeta|roja)",
                          "falta (de|sobre|para|a|al) +E", "falta", "entrada (dura)? de +E", "le hace falta", "le hacen falta",
                          "(entra|entro) fuerte", "agarra a +E", "empuja a +E", "le da una patada"], {}),
    ("x_amarilla", "amarilla", ["ve la amarilla", "amarilla (para|a) +E", "tarjeta (para|a) +E", "amonestado +E",
                                "se lleva la amarilla"], {}),
    ("x_roja", "roja", ["roja (para|a) +E", "expulsado +E", "ve la roja", "se va a la calle"], {}),
    ("x_cambio", "cambio", ["(entra|entran|entrara|ingresa) +E", "(sale|se retira|se marcha) +E (y|por)", "sale +E",
                            "se retira +E", "se (marchan|van|retiran) +E", "salen +E", "se marcha +E", "cambio (de|en) +E", "cambio", "deja su sitio a +E", "al campo +E",
                            "ocupa el lugar de +E", "en lugar de +E", "sustituye a +E", "reemplaza a +E"], {}),
    ("x_fuera_juego", "fuera_juego", ["en fuera de juego", "estaba adelantado", "esta adelantado", "orsay"], {}),
    ("x_penalti", "penalti", ["penaltito", "penaltazo"], {}),
    ("x_corner", "corner", ["corner (para|de|del|a favor) +E", "jorner"], {}),
    ("x_saque_puerta", "saque_puerta", ["saque de porteria", "saca de porteria", "saca de puerta +E"], {}),
    ("x_lesion", "lesion", ["lesionado", "lesion de +E", "se ha hecho dano", "se rompe", "pide el cambio", "lesion", "esta (dolido|dolorido)", "se (esta|sigue) doliendo"], {}),
    ("x_descanso", "descanso", ["final de la primera (parte|mitad)", "nos vamos al descanso", "llega el descanso"], {}),
    ("x_tiro2", "tiro", ["la prueba", "lo prueba", "chuta", "chutan", "le quiere pegar", "tira"], {}),
    ("x_lesion2", "lesion", ["se lesion*"], {}),
    ("x_palo", "palo", ["al palo", "al larguero", "al poste", "en el palo", "en el larguero", "travesano"], {}),
    ("x_ocasion", "ocasion", ["la tuvo +E", "la tiene +E solo", "que ocasion", "ocasion de +E", "ocasion para +E"], {}),
    ("x_var", "var", ["el var"], {}),
]

# patrones del prototipo que en narración real disparan sin motivo o que la guía de anotación trata de otra forma
DROP_PATTERNS = {"var": {"pantalla", "revision", "revisa*", "revisando"}, "pase": {"(un|el) pase"},
                 "descanso": {"vestuarios"}, "gol": {"anoto"}}

MODAL_BY_FINE = {k: v[1] for k, v in COARSE.items() if v[1]}


@dataclass
class Sit:
    id: str
    coarse: str | None
    refines: list[str] = field(default_factory=list)
    passive: re.Pattern | None = None
    after: str | None = None
    kind: str = "play"


@dataclass
class Hit:
    sit: Sit
    i: int
    n: int
    need_e: bool = False

    @property
    def end(self) -> int:
        return self.i + self.n - 1


def _tok_re(part: str) -> re.Pattern:
    alts = part.strip("()").split("|")
    return re.compile("^(?:" + "|".join(re.escape(a[:-1]) + r"\w*" if a.endswith("*") else re.escape(a) for a in alts) + ")$")


def _expand(parts: list[str]) -> list[list[str]]:
    seqs: list[list[str]] = [[]]
    for p in parts:
        opt = p.endswith("?")
        p = p[:-1] if opt else p
        seqs = [s + [p] for s in seqs] + ([s[:] for s in seqs] if opt else [])
    return [s for s in seqs if s]


class Catalog:
    def __init__(self) -> None:
        self.sits: dict[str, Sit] = {}
        self.pats: list[tuple[Sit, list[re.Pattern], bool, set[str] | None]] = []
        legacy = json.loads((Path(__file__).parent / "catalog_legacy.json").read_text(encoding="utf-8"))
        for s in legacy:
            sit = Sit(s["id"], COARSE.get(s["id"], (None, None))[0], s.get("refines") or [],
                      re.compile(s["passive"]) if s.get("passive") else None, None, s["kind"])
            self.sits[sit.id] = sit
            for p in s["pats"]:
                if p not in DROP_PATTERNS.get(s["id"], ()):
                    self._compile(sit, p)
        for fid, coarse, pats, opts in EXTRA:
            sit = Sit(fid, coarse, [], None, opts.get("after"))
            self.sits[fid] = sit
            for p in pats:
                self._compile(sit, p)

    def _compile(self, sit: Sit, p: str) -> None:
        need_e = p.endswith(" +E")
        p = p[:-3] if need_e else p
        parts = p.split(" ")
        if "+E" in parts:  # entidad en medio: "sale +E (y|por)"
            k = parts.index("+E")
            for seq in _expand(parts[:k]):
                self.pats.append((sit, [_tok_re(x) for x in seq], True, None))
            return
        for seq in _expand(parts):
            firsts = None if "*" in seq[0] and seq[0].strip("()").split("|")[0][:1] == "" else {
                a[0] for a in seq[0].strip("()").split("|") if a}
            self.pats.append((sit, [_tok_re(x) for x in seq], need_e, firsts))

    def find(self, toks: list[str], ent_starts: set[int], covered: set[int],
             player_starts: set[int] | None = None) -> list[Hit]:
        """Situaciones mencionadas. `covered` = posiciones que son parte de un nombre (no disparan: "Rosa", "Moro")."""
        raw: list[Hit] = []
        n_t = len(toks)
        for i in range(n_t):
            if i in covered:
                continue
            c = toks[i][:1]
            for sit, res, need_e, firsts in self.pats:
                n = len(res)
                if (firsts is not None and c not in firsts) or i + n > n_t:
                    continue
                if not all(res[j].match(toks[i + j]) for j in range(n)):
                    continue
                if any((i + j) in covered for j in range(n)):
                    continue
                if need_e and not any(k in ent_starts for k in range(i + n, min(n_t, i + n + 3))):
                    continue
                if sit.id == "x_pase_para" and (player_starts is None or (i + n) not in player_starts):
                    continue
                if sit.id == "x_gol" and toks[i] in ("marca", "marco", "marcan") and i > 0 and toks[i - 1] in ("la", "una", "esa", "de", "que"):
                    continue
                if sit.coarse in ("descanso", "final") and n == 1 and i > 0 and re.match(
                        r"^(el|del|al|este|ese|de|un|gran|pedazo|que)$", toks[i - 1]) and not (
                        i > 2 and toks[i - 2] in ("vamos", "llega", "llego", "pita")):
                    continue
                base = sit.id
                if base in ("palo", "x_palo") and re.match(r"^(primer|segundo|primero|tercer)$", toks[i + n - 2] if n > 1 else toks[i - 1] if i else ""):
                    continue
                if base == "palo" and i > 0 and re.match(r"^(primer|segundo|primero|tercer)$", toks[i - 1]):
                    continue
                if sit.coarse == "falta" and toks[i] == "falta" and i > 0 and re.match(
                        r"^(hace|hacen|hacia|haria|hizo|hacer|hara|haran|hacia|que|sin|nos|me|le|les|os)$", toks[i - 1]) \
                        and not (n > 1):
                    continue
                if sit.coarse == "falta" and toks[i] == "falta" and n == 1 and i + 1 < n_t and re.match(
                        r"^(mucho|poco|un|una|el|la|los|las|mas|algo|por|todavia|aun|ritmo|gol|intensidad|que|\d+)$", toks[i + 1]):
                    continue
                raw.append(Hit(sit, i, n, need_e))
        # un patrón más específico que "refina" a otro lo sustituye si se solapan
        def ov(a: Hit, b: Hit) -> bool:
            return a.i <= b.end and b.i <= a.end
        hs = [b for b in raw if not any(a is not b and b.sit.id in a.sit.refines and ov(a, b) for a in raw)]
        # entre solapados gana el más largo; a igual longitud, el que tiene tipo grueso
        # se descarta lo contenido en un patrón más largo; a igual tipo grueso solapado, gana el más largo
        hs = [b for b in hs if not any(a is not b and a.i <= b.i and a.end >= b.end and a.n > b.n for a in hs)]
        hs.sort(key=lambda h: (-h.n, h.sit.coarse is None, h.i))
        out: list[Hit] = []
        for h in hs:
            if not any(ov(o, h) and (o.sit.coarse == h.sit.coarse or o.sit.coarse is None or h.sit.coarse is None
                                     or (o.i == h.i and o.n == h.n)) for o in out):
                out.append(h)
        return sorted(out, key=lambda h: h.i)
