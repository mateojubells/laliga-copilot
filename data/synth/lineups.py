"""Alineaciones, banquillo, cambios y reloj del partido.

Reloj interno: T = segundos de juego desde el pitido inicial, incluida la prolongación. La primera parte dura
2700 + 60*a1 s; la segunda empieza en T = 2700 + 60*a1. Minuto mostrado: floor(reloj/60)+1; la prolongación se
codifica como minute=45 (o 90) y added=N (convención de eval/gold/barca-valladolid.truth.json: "45+2" -> 45, added 2).
"""
from __future__ import annotations

import numpy as np

from . import model as M

BENCH_SIZE = 9


# ---------------------------------------------------------------- reloj
def t_from_display(minute: int, added: int, sec: int, a1: int) -> int:
    if added > 0 and minute == 45:
        return 2700 + 60 * (added - 1) + sec
    if added > 0 and minute >= 90:
        return 5400 + 60 * a1 + 60 * (added - 1) + sec
    if minute <= 45:
        return (minute - 1) * 60 + sec
    return (minute - 1) * 60 + sec + 60 * a1


def display_from_t(T, a1: int):
    """T (array) -> period, minute, added, second."""
    T = np.asarray(T, dtype=np.int64)
    p2 = T >= 2700 + 60 * a1
    u = np.where(p2, T - 60 * a1, T)
    minute = np.where(~p2, np.where(T < 2700, T // 60 + 1, 45), np.where(u < 5400, u // 60 + 1, 90))
    added = np.where(~p2, np.where(T < 2700, 0, (T - 2700) // 60 + 1), np.where(u < 5400, 0, (u - 5400) // 60 + 1))
    return np.where(p2, 2, 1), minute, added, T % 60


def display_minute(T, a1):
    """Minuto mostrado (<=90) para contar minutos jugados."""
    return int(min(display_from_t(np.array([T]), a1)[1][0], 90))


# ---------------------------------------------------------------- estructuras
class Member:
    """Un jugador de la convocatoria en un partido."""
    __slots__ = ("p", "attr", "slot", "pos", "started", "t_on", "t_off", "min_in", "min_out")

    def __init__(self, p, attr):
        self.p = p              # dict de la plantilla (id, number, position, line, foot...)
        self.attr = attr
        self.slot = -1          # hueco de la formación (0..10) que ocupa
        self.pos = p["position"]
        self.started = False
        self.t_on = -1          # -1: no juega
        self.t_off = -1
        self.min_in = None
        self.min_out = None


class TeamLineup:
    def __init__(self, team: str, formation: str, members: list[Member]):
        self.team = team
        self.formation = formation
        self.members = members
        self.subs: list[tuple[int, int, int]] = []   # (T, idx_in, idx_out)
        self.reds: list[tuple[int, int]] = []        # (T, idx)

    def finalize(self, T_end: int, a1: int):
        for m in self.members:
            if m.t_on < 0:
                continue
            m.min_in = 0 if m.started else display_minute(m.t_on, a1)
            m.min_out = 90 if m.t_off >= T_end else display_minute(m.t_off, a1)
            m.min_out = max(m.min_out, m.min_in)


def _pairs_by_foot(slots_by_pos, assign, members):
    """Pierna zurda en el lado izquierdo (y alto) cuando hay dos huecos de la misma posición."""
    for pos, idxs in slots_by_pos.items():
        if len(idxs) != 2:
            continue
        a, b = idxs  # a: lado derecho (y bajo) o primero
        ma, mb = members[assign[a]], members[assign[b]]
        fa, fb = ma.p.get("foot", "R"), mb.p.get("foot", "R")
        if fa == "L" and fb != "L":
            assign[a], assign[b] = assign[b], assign[a]


# ---------------------------------------------------------------- selección aleatoria
def pick_lineup(rng, team: str, roster: list[dict], attrs: dict, formation: str, avail_p=0.93) -> TeamLineup:
    pos_idx, sides, anchors, W = M.formation_arrays(formation)
    members = [Member(p, attrs[p["id"]]) for p in roster]
    n = len(members)
    avail = rng.random(n) < avail_p
    need = 11 + BENCH_SIZE
    if avail.sum() < need:  # jugadores justos: se completa con algunos "tocados" que juegan igualmente
        for i in rng.permutation(n):
            avail[i] = True
            if avail.sum() >= need:
                break
    gum = rng.gumbel(size=n)
    gk_all = [i for i, m in enumerate(members) if m.p["position"] == "GK"]
    if gk_all and not any(avail[i] for i in gk_all):
        avail[gk_all[0]] = True
    score = np.array([2.5 * m.attr.q for m in members]) + gum
    # el portero titular casi siempre juega
    gks = [i for i, m in enumerate(members) if m.pos == "GK"]
    if gks:
        order = sorted(gks, key=lambda i: (members[i].p.get("number") or 99, i))
        bonus = [5.0, 0.0] + [-3.0] * len(order)
        for r, i in enumerate(order):
            score[i] += bonus[r]
    used = np.zeros(n, bool)
    assign: dict[int, int] = {}
    slot_pos = [M.POS[i] for i in pos_idx]
    fill = sorted(range(11), key=lambda s: (M.FILL_ORDER.index(slot_pos[s]), s))
    for s in fill:
        chosen = None
        for level in M.FALLBACK[slot_pos[s]]:
            cand = [i for i in range(n) if avail[i] and not used[i] and members[i].pos == level]
            if cand:
                chosen = max(cand, key=lambda i: score[i])
                break
        if chosen is None:  # último recurso: cualquiera no portero
            cand = [i for i in range(n) if not used[i] and members[i].pos != "GK"]
            chosen = max(cand, key=lambda i: score[i])
        used[chosen] = True
        assign[s] = chosen
    by_pos: dict[str, list[int]] = {}
    for s in range(11):
        by_pos.setdefault(slot_pos[s], []).append(s)
    _pairs_by_foot(by_pos, assign, members)
    for s, i in assign.items():
        m = members[i]
        m.slot, m.started, m.t_on = s, True, 0
        m.pos = slot_pos[s]
    # banquillo: portero suplente + cuotas por línea
    bench: list[int] = []
    rest = [i for i in np.argsort(-score) if not used[i] and avail[i]]
    gk = [i for i in rest if members[i].p["position"] == "GK"]
    if gk:
        bench.append(gk[0])
    quota = {"DEF": 3, "MID": 3, "FWD": 2}
    for i in rest:
        if len(bench) >= BENCH_SIZE:
            break
        ln = members[i].p["line"]
        if members[i].p["position"] != "GK" and quota.get(ln, 0) > 0:
            bench.append(i)
            quota[ln] -= 1
    for i in rest:
        if len(bench) >= BENCH_SIZE:
            break
        if i not in bench and members[i].p["position"] != "GK":
            bench.append(i)
    tl = TeamLineup(team, formation, members)
    tl.bench = bench  # type: ignore[attr-defined]
    return tl


def plan_subs(rng, tl: TeamLineup, a1: int, T_end: int, allow=True):
    """3-5 cambios; quien entra ocupa el hueco de quien sale."""
    members = tl.members
    on = [i for i, m in enumerate(members) if m.started]
    bench = [i for i in tl.bench if members[i].p["position"] != "GK"]   # type: ignore[attr-defined]
    k = int(rng.choice([3, 4, 5], p=[.15, .35, .5]))
    k = min(k, len(bench))
    nwin = int(rng.choice([1, 2, 3], p=[.08, .42, .50]))
    nwin = min(nwin, k)
    ranges = {1: [(54, 72)], 2: [(46, 68), (66, 84)], 3: [(46, 62), (62, 76), (76, 88)]}[nwin]
    mins = [int(rng.integers(a, b + 1)) for a, b in ranges]
    secs = [int(rng.integers(0, 60)) for _ in mins]
    wins = [t_from_display(mn, 0, sc, a1) for mn, sc in zip(mins, secs)]
    # reparto de los k cambios entre ventanas (>=1 por ventana)
    sizes = [1] * nwin
    for _ in range(k - nwin):
        sizes[int(rng.integers(0, nwin))] += 1
    times = []
    for w, s in zip(wins, sizes):
        times += [w] * s
    if rng.random() < 0.04 and k >= 1:  # cambio por lesión temprano
        times[0] = t_from_display(int(rng.integers(10, 41)), 0, int(rng.integers(0, 60)), a1)
        times.sort()
    times.sort()
    cur = list(on)
    avail_b = list(bench)
    for T in times:
        outc = [i for i in cur if members[i].started and members[i].pos != "GK" and members[i].t_off < 0]
        w = np.array([M.W_SUBOUT[M.PI[members[i].pos]] for i in outc])
        o = outc[int(rng.choice(len(outc), p=w / w.sum()))]
        ow = np.array([(3.0 if members[b].p["line"] == members[o].p["line"] else 1.0)
                       * (2.0 if members[b].p["position"] == members[o].pos else 1.0)
                       * float(np.exp(0.3 * members[b].attr.q)) for b in avail_b])
        b = avail_b[int(rng.choice(len(avail_b), p=ow / ow.sum()))]
        avail_b.remove(b)
        cur.remove(o)
        cur.append(b)
        members[o].t_off = T
        mb = members[b]
        mb.slot, mb.pos, mb.t_on = members[o].slot, members[o].pos, T
        tl.subs.append((T, b, o))


def apply_red(rng, tl: TeamLineup, T_red: int, T_end: int):
    """Expulsa a un jugador en el campo en T_red; sus cambios posteriores se cancelan."""
    present = [i for i, m in enumerate(tl.members) if m.t_on >= 0 and m.t_on <= T_red < (m.t_off if m.t_off >= 0 else 10 ** 9)
               and m.pos != "GK"]
    if not present:
        return None
    w = np.array([1.0 + 0.4 * (tl.members[i].p["line"] == "DEF") for i in present])
    i = present[int(rng.choice(len(present), p=w / w.sum()))]
    m = tl.members[i]
    # si iba a ser sustituido después, se cancela ese cambio (el suplente se queda en el banquillo)
    for sub in list(tl.subs):
        if sub[2] == i and sub[0] > T_red:
            tl.subs.remove(sub)
            b = tl.members[sub[1]]
            b.t_on = -1; b.slot = -1; b.pos = b.p["position"]
            m.t_off = -1
    m.t_off = T_red
    tl.reds.append((T_red, i))
    return i


def finish_presence(tl: TeamLineup, T_end: int):
    for m in tl.members:
        if m.t_on >= 0 and m.t_off < 0:
            m.t_off = T_end


# ---------------------------------------------------------------- partido real (verdad de campo)
def truth_lineup(truth: dict, team: str, roster: list[dict], attrs: dict, formation: str, a1: int,
                 rng) -> TeamLineup:
    pos_idx, sides, anchors, W = M.formation_arrays(formation)
    members = [Member(p, attrs[p["id"]]) for p in roster]
    byid = {m.p["id"]: i for i, m in enumerate(members)}
    lu = truth["lineups"][team]
    slot_pos = [M.POS[i] for i in pos_idx]
    free = list(range(11))
    assign: dict[int, int] = {}
    starters = lu["starting"]
    for s in starters:
        i = byid[s["id"]]
        pos = s["position"]
        for sl in free:
            if slot_pos[sl] == pos:
                assign[sl] = i
                free.remove(sl)
                break
        else:
            raise ValueError(f"sin hueco {pos} en {formation} para {s['id']}")
    by_pos: dict[str, list[int]] = {}
    for sl in range(11):
        by_pos.setdefault(slot_pos[sl], []).append(sl)
    _pairs_by_foot(by_pos, assign, members)
    for sl, i in assign.items():
        m = members[i]
        m.slot, m.started, m.t_on, m.pos = sl, True, 0, slot_pos[sl]
    tl = TeamLineup(team, formation, members)
    tl.bench = [byid[b["id"]] for b in lu["bench"]]  # type: ignore[attr-defined]
    by_min: dict[int, int] = {}
    for s in truth["substitutions"]:
        if s["team"] != team:
            continue
        mn = s["minute"]
        if mn not in by_min:
            by_min[mn] = t_from_display(mn, 0, int(rng.integers(0, 60)), a1)
        T = by_min[mn]
        o, b = members[byid[s["out"]]], members[byid[s["in"]]]
        o.t_off = T
        b.slot, b.pos, b.t_on = o.slot, o.pos, T
        tl.subs.append((T, byid[s["in"]], byid[s["out"]]))
    return tl
