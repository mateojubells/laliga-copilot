"""Modelo futbolístico del generador: formaciones, zonas, matriz de pases, xG y atributos persistentes.

Campo 105x68, origen abajo-izquierda, cada equipo ataca hacia x creciente (su banda derecha es y baja).
"""
from __future__ import annotations

import hashlib
import math

import numpy as np

POS = ["GK", "RB", "CB", "LB", "DM", "CM", "AM", "RW", "LW", "ST"]
PI = {p: i for i, p in enumerate(POS)}
LINE_OF = {"GK": "GK", "RB": "DEF", "CB": "DEF", "LB": "DEF", "DM": "MID", "CM": "MID", "AM": "MID",
           "RW": "FWD", "LW": "FWD", "ST": "FWD"}

# (posición, lado, (x, y) medio con la pelota a 0,5 de posesión)
FORMATIONS: dict[str, list[tuple[str, str, tuple[float, float]]]] = {
    "4-3-3": [("GK", "C", (7, 34)), ("RB", "R", (41, 9)), ("CB", "R", (30, 24)), ("CB", "L", (30, 44)),
              ("LB", "L", (41, 59)), ("DM", "C", (47, 34)), ("CM", "R", (58, 25)), ("CM", "L", (58, 43)),
              ("RW", "R", (75, 10)), ("ST", "C", (83, 34)), ("LW", "L", (75, 58))],
    "4-1-4-1": [("GK", "C", (7, 34)), ("RB", "R", (41, 9)), ("CB", "R", (30, 24)), ("CB", "L", (30, 44)),
                ("LB", "L", (41, 59)), ("DM", "C", (46, 34)), ("CM", "R", (60, 26)), ("CM", "L", (60, 42)),
                ("RW", "R", (72, 9)), ("ST", "C", (83, 34)), ("LW", "L", (72, 59))],
    "4-2-3-1": [("GK", "C", (7, 34)), ("RB", "R", (41, 9)), ("CB", "R", (30, 24)), ("CB", "L", (30, 44)),
                ("LB", "L", (41, 59)), ("DM", "R", (46, 26)), ("CM", "L", (48, 42)), ("AM", "C", (65, 34)),
                ("RW", "R", (71, 11)), ("ST", "C", (82, 34)), ("LW", "L", (71, 57))],
    "4-4-2": [("GK", "C", (7, 34)), ("RB", "R", (41, 9)), ("CB", "R", (30, 24)), ("CB", "L", (30, 44)),
              ("LB", "L", (41, 59)), ("CM", "R", (53, 26)), ("CM", "L", (53, 42)), ("RW", "R", (67, 9)),
              ("ST", "R", (79, 27)), ("ST", "L", (79, 41)), ("LW", "L", (67, 59))],
}

#: formación habitual (ficticia salvo Barcelona/Valladolid, que fijan las verdades de campo)
TEAM_FORMATION = {
    "barcelona": "4-3-3", "real-madrid": "4-3-3", "atletico": "4-4-2", "athletic": "4-2-3-1", "villarreal": "4-4-2",
    "betis": "4-2-3-1", "celta": "4-3-3", "rayo": "4-2-3-1", "osasuna": "4-4-2", "mallorca": "4-4-2",
    "real-sociedad": "4-3-3", "valencia": "4-4-2", "getafe": "4-4-2", "espanyol": "4-4-2", "alaves": "4-4-2",
    "girona": "4-2-3-1", "sevilla": "4-2-3-1", "leganes": "4-4-2", "las-palmas": "4-3-3", "valladolid": "4-1-4-1",
}



def default_formation(team: str) -> str:
    """Formación de un equipo que no está en TEAM_FORMATION (temporadas importadas): estable por id, sin azar."""
    import zlib
    return ("4-3-3", "4-4-2", "4-2-3-1")[zlib.crc32(team.encode()) % 3]


#: si no hay jugador natural de la posición, cadena de sustitutos
FALLBACK = {
    "GK": ["GK"], "RB": ["RB", "CB", "DM", "CM", "RW"], "LB": ["LB", "CB", "DM", "CM", "LW"],
    "CB": ["CB", "DM", "RB", "LB"], "DM": ["DM", "CM", "CB"], "CM": ["CM", "DM", "AM", "RW", "LW"],
    "AM": ["AM", "CM", "RW", "LW", "ST"], "RW": ["RW", "LW", "AM", "ST", "CM"],
    "LW": ["LW", "RW", "AM", "ST", "CM"], "ST": ["ST", "AM", "RW", "LW"],
}
FILL_ORDER = ["GK", "CB", "RB", "LB", "DM", "ST", "RW", "LW", "AM", "CM"]


def _arr(d: dict[str, float]) -> np.ndarray:
    return np.array([d[p] for p in POS], float)


#: volumen de pases (relativo) por posición
PASS_VOL = _arr({"GK": 22, "RB": 44, "CB": 52, "LB": 44, "DM": 68, "CM": 56, "AM": 36, "RW": 30, "LW": 30, "ST": 20})
#: atractivo como destinatario
PASS_ATTR = _arr({"GK": .35, "RB": .95, "CB": 1.15, "LB": .95, "DM": 1.45, "CM": 1.3, "AM": 1.0, "RW": .8, "LW": .8,
                  "ST": .55})
#: ajuste de precisión de pase por posición del pasador
PASS_ACC = _arr({"GK": -.12, "RB": -.01, "CB": .035, "LB": -.01, "DM": .02, "CM": .01, "AM": -.04, "RW": -.06,
                 "LW": -.06, "ST": -.08})
#: pesos por posición de cada acción (relativos)
W_SHOT = _arr({"GK": 0, "RB": .35, "CB": .25, "LB": .35, "DM": .45, "CM": .95, "AM": 1.6, "RW": 1.9, "LW": 1.9, "ST": 3.0})
#: un jugador no puede acaparar más de esta fracción del peso de tiro de los once iniciales de su equipo
SHOT_SHARE_CAP = 0.18
W_HEAD = _arr({"GK": 0, "RB": .3, "CB": 1.1, "LB": .3, "DM": .5, "CM": .6, "AM": .5, "RW": .3, "LW": .3, "ST": 3.0})
W_FK = _arr({"GK": 0, "RB": .7, "CB": .3, "LB": .7, "DM": .5, "CM": 1.5, "AM": 2.0, "RW": 1.5, "LW": 1.5, "ST": .5})
W_CREATE = _arr({"GK": .05, "RB": 1.4, "CB": .25, "LB": 1.4, "DM": .7, "CM": 1.5, "AM": 2.2, "RW": 2.0, "LW": 2.0,
                 "ST": .9})
W_DRIB = _arr({"GK": 0, "RB": 1.3, "CB": .12, "LB": 1.3, "DM": .45, "CM": 1.1, "AM": 2.4, "RW": 3.4, "LW": 3.4,
               "ST": 1.5})
W_REC = _arr({"GK": 1.2, "RB": 5, "CB": 5, "LB": 5, "DM": 7, "CM": 6, "AM": 3.5, "RW": 3, "LW": 3, "ST": 2})
W_TACK = _arr({"GK": 0, "RB": 2, "CB": 1.2, "LB": 2, "DM": 2.5, "CM": 1.8, "AM": 1.0, "RW": 1.0, "LW": 1.0, "ST": .5})
W_INT = _arr({"GK": 0, "RB": 1.2, "CB": 1.6, "LB": 1.2, "DM": 1.8, "CM": 1.0, "AM": .5, "RW": .4, "LW": .4, "ST": .2})
W_CLR = _arr({"GK": .2, "RB": 2, "CB": 4, "LB": 2, "DM": 1.2, "CM": .7, "AM": .3, "RW": .3, "LW": .3, "ST": .3})
W_FOUL = _arr({"GK": 0, "RB": 1.0, "CB": 1.2, "LB": 1.0, "DM": 1.7, "CM": 1.3, "AM": .7, "RW": .6, "LW": .6, "ST": .8})
W_FOULED = _arr({"GK": 0, "RB": .8, "CB": .5, "LB": .8, "DM": .8, "CM": 1.0, "AM": 1.2, "RW": 1.6, "LW": 1.6,
                 "ST": 1.2})
P_YELLOW = _arr({"GK": .3, "RB": 1.0, "CB": 1.1, "LB": 1.0, "DM": 1.5, "CM": 1.1, "AM": .8, "RW": .7, "LW": .7, "ST": .8})
W_SUBOUT = _arr({"GK": 0, "RB": .8, "CB": .6, "LB": .8, "DM": 1.0, "CM": 1.2, "AM": 1.3, "RW": 1.5, "LW": 1.5, "ST": 1.4})
POS_EXTRA = {"p": 0}  # reservado

# ---------------------------------------------------------------- xG
_XG_C = (-2.4866, -0.0598, 2.2540)  # ajuste logístico: 1, distancia, ángulo de portería
GOAL_Y = 34.0
POST = 3.66


def xg_open(x, y, header=False, through=False, solo=False):
    """xG de un disparo abierto desde (x, y) atacando hacia x=105. Vectorizado."""
    dx = 105.0 - np.asarray(x, float)
    dy = np.abs(np.asarray(y, float) - GOAL_Y)
    d = np.hypot(dx, dy)
    a = np.arctan2(2 * POST * dx, dx * dx + dy * dy - POST * POST)
    a = np.where(a < 0, a + math.pi, a)
    z = _XG_C[0] + _XG_C[1] * d + _XG_C[2] * a + 0.15
    z = z - 0.62 * header + 0.35 * through - 0.10 * solo
    p = 1.0 / (1.0 + np.exp(-z))
    return np.clip(p, 0.01, 0.92)


def xg_fk(x, y):
    d = np.hypot(105.0 - np.asarray(x, float), np.asarray(y, float) - GOAL_Y)
    return np.clip(0.045 + 0.003 * (25 - d), 0.02, 0.09)


PENALTY_XG = 0.76

# ---------------------------------------------------------------- zonas de tiro (open play)
ZONES = ["six", "box", "angle", "edge", "long", "wide"]
_ZONE_BOX = {  # (x0, x1, y0, y1) para la banda central; angle/wide se espejan por banda
    "six": (99.5, 104.5, 27.5, 40.5), "box": (88.5, 99.5, 22.5, 45.5), "angle": (94.0, 104.0, 10.0, 22.0),
    "edge": (77.0, 88.5, 19.0, 49.0), "long": (62.0, 77.0, 14.0, 54.0), "wide": (84.0, 95.0, 4.0, 12.0),
}
_ZW = {
    "ST": [.10, .42, .16, .22, .05, .05], "W": [.03, .20, .27, .33, .08, .09], "AM": [.03, .20, .08, .42, .20, .02],
    "CM": [.02, .13, .06, .42, .35, .02], "DM": [.01, .08, .03, .35, .50, .03], "FB": [.02, .10, .15, .30, .30, .13],
    "CB": [.04, .30, .05, .25, .34, .02],
}
_ZW_OF = {"GK": "CB", "RB": "FB", "LB": "FB", "CB": "CB", "DM": "DM", "CM": "CM", "AM": "AM", "RW": "W", "LW": "W",
          "ST": "ST"}
ZONE_P = np.array([np.array(_ZW[_ZW_OF[p]]) / sum(_ZW[_ZW_OF[p]]) for p in POS])  # (10, 6)
POS_SIDE = np.array([0, -1, 0, 1, 0, 0, 0, -1, 1, 0])  # -1 = derecha (y bajo), +1 = izquierda


def sample_open_shots(rng, pos_idx: np.ndarray):
    """(x, y) de disparos abiertos para jugadores con posición pos_idx (array de índices de POS)."""
    n = len(pos_idx)
    u = rng.random(n)
    cum = np.cumsum(ZONE_P[pos_idx], axis=1)
    z = np.minimum((u[:, None] > cum).sum(1), 5)
    box = np.array([_ZONE_BOX[k] for k in ZONES])[z]
    x = box[:, 0] + (box[:, 1] - box[:, 0]) * rng.random(n)
    yl = box[:, 2] + (box[:, 3] - box[:, 2]) * rng.random(n)
    # y: las zonas angle/wide están definidas en la banda derecha (y bajo); se espeja según el lado
    wide_z = (z == 2) | (z == 5)
    side = POS_SIDE[pos_idx].astype(float)
    flip = rng.random(n) < np.where(side == 0, .5, np.where(side < 0, .35, .65))  # 1 = banda izquierda
    y = np.where(wide_z, np.where(flip, 68.0 - yl, yl), yl)
    return np.round(x, 1), np.round(np.clip(y, 1, 67), 1)


def sample_header_shots(rng, n):
    x = np.clip(rng.normal(94.3, 3.6, n), 87, 104.5)
    y = np.clip(rng.normal(34, 6.5, n), 20, 48)
    return np.round(x, 1), np.round(y, 1)


def sample_fk_shots(rng, n):
    x = rng.uniform(74, 90, n)
    y = np.clip(rng.normal(34, 6, n), 20, 48)
    return np.round(x, 1), np.round(y, 1)


# ---------------------------------------------------------------- matriz de pases por plantilla
def build_pass_matrix(tmpl) -> np.ndarray:
    """W[i, j]: peso de pase del hueco i al hueco j de una formación."""
    n = len(tmpl)
    W = np.zeros((n, n))
    for i, (pi_, si, ai) in enumerate(tmpl):
        for j, (pj, sj, aj) in enumerate(tmpl):
            if i == j:
                continue
            d = math.hypot(aj[0] - ai[0], aj[1] - ai[1])
            w = math.exp(-0.5 * ((d - 17.0) / 11.0) ** 2) + 0.02
            w *= 1.15 if aj[0] > ai[0] else 0.9
            w *= PASS_ATTR[PI[pj]]
            same_side = si == sj and si != "C"
            fb_i, fb_j = pi_ in ("RB", "LB"), pj in ("RB", "LB")
            wing_j, wing_i = pj in ("RW", "LW"), pi_ in ("RW", "LW")
            if fb_i and wing_j and same_side: w *= 3.0
            if fb_i and pj in ("CM", "DM", "AM") and (same_side or si == "C"): w *= 1.5
            if fb_i and pj == "CB" and same_side: w *= 1.5
            if fb_i and pj == "DM": w *= 1.1
            if wing_i and fb_j and same_side: w *= 2.0
            if pi_ == "CB" and pj == "CB": w *= 1.9
            if pi_ == "CB" and pj == "DM": w *= 1.5
            if pi_ == "CB" and fb_j and same_side: w *= 1.4
            if pi_ == "GK" and pj == "CB": w *= 2.2
            if pi_ == "GK" and fb_j: w *= 1.4
            if pi_ in ("DM", "CM") and pj in ("DM", "CM"): w *= 1.3
            if wing_i and pj in ("ST", "AM"): w *= 1.4
            if pi_ == "AM" and pj == "ST": w *= 1.4
            W[i, j] = w
    return W


_CACHE: dict[str, tuple] = {}


def formation_arrays(name: str):
    """(pos_idx[11], side[11], anchors[11,2], W[11,11])"""
    if name not in _CACHE:
        t = FORMATIONS[name]
        pos_idx = np.array([PI[p] for p, _, _ in t])
        anchors = np.array([a for _, _, a in t], float)
        _CACHE[name] = (pos_idx, [s for _, s, _ in t], anchors, build_pass_matrix(t))
    return _CACHE[name]


# ---------------------------------------------------------------- atributos persistentes
def stable_u64(*parts) -> int:
    h = hashlib.blake2b("|".join(str(p) for p in parts).encode(), digest_size=8).digest()
    return int.from_bytes(h, "big")


#: Jugadores de primer nivel: titulares habituales en el modelo (el tiempo de juego sigue siendo ficticio).
STARS = frozenset("""barcelona/lewandowski barcelona/raphinha barcelona/lamine-yamal barcelona/pedri
barcelona/ter-stegen barcelona/kounde barcelona/balde barcelona/cubarsi barcelona/inigo-martinez
barcelona/dani-olmo barcelona/casado barcelona/de-jong real-madrid/mbappe real-madrid/vinicius
real-madrid/bellingham real-madrid/courtois real-madrid/valverde real-madrid/rodrygo real-madrid/tchouameni
real-madrid/carvajal real-madrid/rudiger atletico/oblak atletico/griezmann atletico/julian-alvarez atletico/koke
athletic/nico-williams athletic/inaki-williams villarreal/pepe real-sociedad/oyarzabal""".split())


class Attr:
    __slots__ = ("q", "f_pass", "f_shoot", "f_create", "f_drib", "f_def", "f_foul", "f_pen")

    def __init__(self, seed: int, pid: str, number, line: str = "MID"):
        r = np.random.default_rng([seed, stable_u64("attr", pid) % (2 ** 32)])
        n = number or 40
        star = pid in STARS
        self.q = float(r.normal(0, 1) - (1.3 if n >= 30 else 0.0) - 0.02 * max(0, n - 22) + (3.0 if star else 0.0))
        ln = lambda s: float(np.exp(r.normal(0, s)))
        # dispersión moderada y acotada: los rematadores muy por encima de la media no existen en la realidad
        self.f_pass = ln(.12)
        self.f_shoot = float(np.clip(ln(.28) * np.exp(.10 * self.q * (line != "DEF")), .6, 1.6))
        self.f_create = ln(.40) * float(np.exp(.15 * self.q))
        self.f_drib = float(np.clip(ln(.30), .55, 1.8))
        self.f_def = ln(.25)
        self.f_foul = float(np.clip(ln(.25), .6, 1.6))
        self.f_pen = float(r.random())


def calibrate(seed: int = 0) -> dict:
    """Constantes de xG medias del modelo (Monte Carlo fijo, determinista)."""
    r = np.random.default_rng([seed, 99])
    # mezcla de posiciones de un equipo medio, ponderada por peso de disparo
    pos = np.array([PI[p] for p in ["CB", "CB", "RB", "LB", "DM", "CM", "CM", "RW", "LW", "ST", "ST", "AM"]])
    w = W_SHOT[pos]
    n = 20000
    idx = r.choice(len(pos), size=n, p=w / w.sum())
    x, y = sample_open_shots(r, pos[idx])
    xo = xg_open(x, y)
    xs = np.where(r.random(n) < 0.5, xg_open(x, y, through=True), xo)
    hx, hy = sample_header_shots(r, n)
    xh = xg_open(hx, hy, header=True)
    fx, fy = sample_fk_shots(r, n)
    xf = xg_fk(fx, fy)
    return {"open": float(xs.mean()), "header": float(xh.mean()), "fk": float(xf.mean())}


def _pos_xg_mean() -> np.ndarray:
    """xG medio de un disparo abierto por posición (Monte Carlo fijo): sirve para repartir los goles según la calidad
    media de los tiros de cada posición, de modo que goles y xG por jugador sean coherentes."""
    r = np.random.default_rng([0, 7])
    out = np.zeros(len(POS))
    for i in range(len(POS)):
        x, y = sample_open_shots(r, np.full(4000, i))
        out[i] = float(xg_open(x, y).mean())
    return out


POS_XG = _pos_xg_mean() * _arr({"GK": 0, "RB": .3, "CB": .25, "LB": .3, "DM": .7, "CM": .8, "AM": .95, "RW": 1,
                                "LW": 1, "ST": 1})  # los defensas marcan menos de lo que su xG sugiere (sin ocasiones claras)
#: calidad relativa del remate de cabeza por posición (los defensas rematan en peores condiciones: marcados, en carrera)
HEAD_Q = _arr({"GK": 0, "RB": .15, "CB": .16, "LB": .15, "DM": .8, "CM": .9, "AM": 1.0, "RW": 1.0, "LW": 1.0, "ST": 1.25})
