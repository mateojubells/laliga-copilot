"""Normalización y tokenización (docs/ARCHITECTURE.md §7.1): minúsculas, sin tildes, ñ→n, con offsets."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

_TOKEN = re.compile(r"[0-9]+|[^\W\d_]+", re.UNICODE)
_NUM = {w: i for i, w in enumerate(
    "cero uno dos tres cuatro cinco seis siete ocho nueve diez once doce trece catorce quince dieciseis diecisiete "
    "dieciocho diecinueve veinte veintiuno veintidos veintitres veinticuatro veinticinco veintiseis veintisiete "
    "veintiocho veintinueve treinta".split())}
_NUM.update({"cuarenta": 40, "cincuenta": 50})


def strip(s: str) -> str:
    s = s.lower().replace("ñ", "n").replace("ß", "ss").replace("ø", "o").replace("ł", "l").replace("đ", "d")
    return "".join(c for c in unicodedata.normalize("NFD", s) if unicodedata.category(c) != "Mn")


@dataclass
class Tok:
    n: str  # normalizado
    raw: str
    start: int
    end: int
    num: int | None = None  # valor si es un número (cifra o palabra)
    after: str = ""  # puntuación entre este token y el siguiente

    @property
    def cap(self) -> bool:
        return self.raw[:1].isupper()


def tokenize(text: str) -> list[Tok]:
    toks: list[Tok] = []
    for m in _TOKEN.finditer(text):
        n = strip(m.group())
        num = int(n) if n.isdigit() else _NUM.get(n) if n != "uno" else None
        toks.append(Tok(n, m.group(), m.start(), m.end(), num))
    for i, t in enumerate(toks):
        nxt = toks[i + 1].start if i + 1 < len(toks) else len(text)
        t.after = text[t.end:nxt].strip()
    return toks


def phon(s: str) -> str:
    """Clave fonética aproximada del español + cómo deforma un reconocedor los nombres extranjeros.
    Entrada ya normalizada con strip(); se ignoran los espacios."""
    s = s.replace(" ", "")
    for a, b in (("sch", "x"), ("szcz", "x"), ("sh", "x"), ("ch", "x"), ("tx", "x"), ("tz", "x"), ("ph", "f"),
                 ("qu", "k"), ("ck", "k"), ("ou", "u"), ("ee", "i"), ("oo", "u"), ("th", "t"), ("ll", "y"),
                 ("gue", "ge"), ("gui", "gi"), ("ge", "je"), ("gi", "ji"), ("ce", "se"), ("ci", "si"), ("nh", "n"),
                 ("w", "b"), ("v", "b"), ("z", "s"), ("c", "k"), ("q", "k"), ("j", "y"), ("y", "i"), ("h", "")):
        s = s.replace(a, b)
    return re.sub(r"(.)\1+", r"\1", s)
