"""Simulación de un partido: genera TODOS los eventos con coordenadas a partir de un marcador real.

Un partido es una función pura de (semilla, jornada, equipos): np.random.default_rng([seed, ronda, idx_local,
idx_visitante]). Nada depende de hash() ni del orden de dict/set.
"""
from __future__ import annotations

import numpy as np

from . import lineups as L
from . import model as M

W_PEN = M._arr({"GK": 0, "RB": .02, "CB": .005, "LB": .02, "DM": .15, "CM": .8, "AM": 1.2, "RW": 1.0, "LW": 1.0, "ST": 1.2})
GKI = M.PI["GK"]

KIND_PEN, KIND_HEAD, KIND_FK, KIND_OPEN, KIND_SOLO, KIND_CROSS = 0, 1, 2, 3, 4, 5


# ---------------------------------------------------------------- buffer de eventos
class Buf:
    def __init__(self):
        self.chunks: list[dict] = []
        self.n = 0

    @staticmethod
    def _bc(v, n, kind):
        if kind == "f":
            if v is None:
                return np.full(n, np.nan)
            return np.broadcast_to(np.asarray(v, float), (n,)).copy()
        if kind == "i":
            return np.broadcast_to(np.asarray(v, np.int64), (n,)).copy()
        if v is None or isinstance(v, str):
            return np.full(n, v, dtype=object)
        return np.asarray(v, dtype=object)

    def add(self, t, team, player, typ, x, y, ex=None, ey=None, outcome=None, receiver=None, xg=None, key=0,
            assist=0, body=None, detail=None, link=-1):
        t = np.atleast_1d(np.asarray(t, np.int64))
        n = len(t)
        if n == 0:
            return np.zeros(0, np.int64)
        b = self._bc
        lid = np.arange(self.n, self.n + n, dtype=np.int64)
        self.chunks.append(dict(
            t=t, team=b(team, n, "o"), player=b(player, n, "o"), type=b(typ, n, "o"), x=b(x, n, "f"), y=b(y, n, "f"),
            ex=b(ex, n, "f"), ey=b(ey, n, "f"), outcome=b(outcome, n, "o"), receiver=b(receiver, n, "o"),
            xg=b(xg, n, "f"), key=b(key, n, "i"), assist=b(assist, n, "i"), body=b(body, n, "o"),
            detail=b(detail, n, "o"), lid=lid, link=b(link, n, "i")))
        self.n += n
        return lid

    def finish(self):
        cols = {k: np.concatenate([c[k] for c in self.chunks]) for k in self.chunks[0]}
        return cols


# ---------------------------------------------------------------- línea temporal de un equipo
class TL:
    def __init__(self, lu: L.TeamLineup, T_end: int, formation_arrays):
        ms = lu.members
        self.lu = lu
        self.P = len(ms)
        far = T_end + 10
        self.pid = np.array([m.p["id"] for m in ms], dtype=object)
        self.t_on = np.array([m.t_on if m.t_on >= 0 else far for m in ms], np.int64)
        self.t_off = np.array([m.t_off if m.t_on >= 0 else far for m in ms], np.int64)
        self.slot = np.array([max(m.slot, 0) for m in ms])
        self.pos = np.array([M.PI[m.pos] if m.slot >= 0 else 0 for m in ms])
        self.foot = np.array([{"R": 0, "L": 1, "B": 2}.get(m.p.get("foot", "R"), 0) for m in ms])
        a = [m.attr for m in ms]
        self.f_pass = np.array([x.f_pass for x in a]); self.f_shoot = np.array([x.f_shoot for x in a])
        self.f_create = np.array([x.f_create for x in a]); self.f_drib = np.array([x.f_drib for x in a])
        self.f_def = np.array([x.f_def for x in a]); self.f_foul = np.array([x.f_foul for x in a])
        self.f_pen = np.array([x.f_pen for x in a])
        # tope de acaparamiento de tiros: ningún jugador pasa de SHOT_SHARE_CAP del peso de los once iniciales
        w_open = M.W_SHOT[self.pos] * self.f_shoot
        started = np.array([bool(m.started) for m in ms])
        thr = M.SHOT_SHARE_CAP * float(w_open[started].sum())
        self.f_shoot = self.f_shoot * np.minimum(1.0, thr / np.maximum(w_open, 1e-9))
        _, _, self.anchors, self.Wslot = formation_arrays
        b = sorted({0, T_end} | {int(t) for t in self.t_on if 0 < t < T_end} | {int(t) for t in self.t_off if 0 < t < T_end})
        self.bounds = np.array(b, np.int64)
        self.present = (self.t_on[None, :] <= self.bounds[:-1, None]) & (self.bounds[:-1, None] < self.t_off[None, :])
        self.ax = self.ay = None
        self.T_end = T_end

    def set_shift(self, dx: float):
        ax = self.anchors[self.slot, 0] + np.where(self.pos == GKI, dx * 0.15, dx)
        self.ax = np.clip(ax, 3, 100)
        self.ay = self.anchors[self.slot, 1]

    def seg_of(self, t):
        return np.clip(np.searchsorted(self.bounds, t, side="right") - 1, 0, len(self.bounds) - 2)

    def pick(self, rng, t, base, exclude=None):
        t = np.atleast_1d(t)
        n = len(t)
        seg = self.seg_of(t)
        pres = self.present[seg].astype(float)
        w = pres * base
        if exclude is not None:
            ok = exclude >= 0
            w[np.arange(n)[ok], exclude[ok]] = 0.0
            pres[np.arange(n)[ok], exclude[ok]] = 0.0
        cum = np.cumsum(w, axis=1)
        tot = cum[:, -1]
        bad = tot <= 0
        if bad.any():
            w[bad] = pres[bad]
            cum = np.cumsum(w, axis=1)
            tot = cum[:, -1]
        r = (1.0 - rng.random(n)) * tot
        return np.minimum((cum < r[:, None]).sum(1), self.P - 1)

    def pick_near(self, rng, t, mx, my, base, sigma=13.0):
        """Jugador presente cercano a (mx, my) (en el sistema de este equipo)."""
        d2 = (self.ax[None, :] - np.asarray(mx)[:, None]) ** 2 + (self.ay[None, :] - np.asarray(my)[:, None]) ** 2
        return self.pick(rng, t, base[None, :] * np.exp(-d2 / (2 * sigma ** 2)))


# ---------------------------------------------------------------- contexto
class Ctx:
    def __init__(self, seed, rosters, attrs, strength, tidx, truth, cal, b_ng):
        self.seed, self.rosters, self.attrs, self.strength = seed, rosters, attrs, strength
        self.tidx, self.truth, self.cal, self.b_ng = tidx, truth, cal, b_ng


class Sim:
    """Estado mutable de un partido."""
    def __init__(self, rng, a1, a2, buf):
        self.rng, self.a1, self.a2, self.buf = rng, a1, a2, buf
        self.T1 = 2700 + 60 * a1
        self.T_end = 5400 + 60 * (a1 + a2)
        self.yellow = {}  # equipo -> set de índices amonestados
        self.ht = {}      # equipo -> goles en la primera parte


def _clipxy(x, y):
    return np.round(np.clip(x, 0.5, 104.5), 1), np.round(np.clip(y, 0.5, 67.5), 1)


# ---------------------------------------------------------------- faltas y tarjetas
def emit_fouls(S, tlF, tlV, tf, tv, t, fouler=None, detail=None, region=None):
    """Faltas cometidas por tlF (equipo tf) sobre tlV. Devuelve (lid, fouler_idx, x, y)."""
    rng, buf = S.rng, S.buf
    t = np.asarray(t, np.int64)
    n = len(t)
    if n == 0:
        z = np.zeros(0)
        return z.astype(np.int64), z.astype(int), z, z
    if fouler is None:
        fouler = tlF.pick(rng, t, M.W_FOUL[tlF.pos] * tlF.f_foul)
    if region == "box":  # falta dentro de su propia área (penalti)
        x = np.clip(rng.normal(8, 3, n), 2, 15.5)
        y = 34 + rng.uniform(-12, 12, n)
    else:
        x = tlF.ax[fouler] * 0.85 + rng.normal(0, 8, n)
        y = tlF.ay[fouler] + rng.normal(0, 7, n)
    x, y = _clipxy(x, y)
    fouled = tlV.pick_near(rng, t, 105 - x, 68 - y, M.W_FOULED[tlV.pos] * tlV.f_drib, 14.0)
    lid = buf.add(t, tf, tlF.pid[fouler], "foul", x, y, receiver=tlV.pid[fouled], detail=detail)
    return lid, fouler, x, y


def emit_card(S, tlF, tf, t, lid, fouler, x, y, kind):
    """Una tarjeta por fila; link = falta que la origina."""
    if len(t) == 0:
        return
    S.buf.add(t, tf, tlF.pid[fouler], "card", x, y, detail=kind, link=lid)


def regular_fouls(S, tlF, tlV, tf, tv, lam, cards=True):
    rng = S.rng
    n = int(rng.poisson(lam))
    t = np.sort(rng.integers(0, S.T_end, n))
    lid, fo, x, y = emit_fouls(S, tlF, tlV, tf, tv, t)
    if not cards or n == 0:
        return
    p = 0.205 * M.P_YELLOW[tlF.pos[fo]]
    yes = rng.random(n) < p
    seen = S.yellow.setdefault(tf, set())
    keep = []
    for i in np.nonzero(yes)[0]:
        if int(fo[i]) in seen:
            continue
        seen.add(int(fo[i]))
        keep.append(i)
    k = np.array(keep, int)
    emit_card(S, tlF, tf, t[k], lid[k], fo[k], x[k], y[k], "yellow")


# ---------------------------------------------------------------- disparos
def make_shots(S, tl, opp, tm, tmo, t, kind, goal, forced_shooter=None, forced_key=None, cal=None):
    rng, buf = S.rng, S.buf
    n = len(t)
    if n == 0:
        return
    t = np.asarray(t, np.int64)
    kind = np.asarray(kind)
    goal = np.asarray(goal, bool)
    # --- penaltis: falta previa del rival
    pen = kind == KIND_PEN
    if pen.any():
        tp = t[pen]
        tf = np.maximum(tp - rng.integers(40, 121, len(tp)), 0)
        lidf, fo, fx, fy = emit_fouls(S, opp, tl, tmo, tm, tf, region="box")
        yel = rng.random(len(tp)) < 0.3
        seen = S.yellow.setdefault(tmo, set())
        sel = []
        for i in np.nonzero(yel)[0]:
            if int(fo[i]) not in seen:
                seen.add(int(fo[i])); sel.append(i)
        k = np.array(sel, int)
        emit_card(S, opp, tmo, tf[k], lidf[k], fo[k], fx[k], fy[k], "yellow")
    # --- tirador
    sh = np.full(n, -1)
    groups = [((kind == KIND_PEN), W_PEN[tl.pos] * tl.f_pen ** 8),
              (((kind == KIND_HEAD) | (kind == KIND_CROSS)), M.W_HEAD[tl.pos] * tl.f_shoot),
              ((kind == KIND_FK), M.W_FK[tl.pos] * tl.f_shoot),
              (((kind == KIND_OPEN) | (kind == KIND_SOLO)), M.W_SHOT[tl.pos] * tl.f_shoot)]
    for gi, (mask, base) in enumerate(groups):
        if mask.any():
            if gi in (1, 3):  # goles de jugada/cabeza: se reparten según la calidad media de tiro de cada posición
                gm = mask & goal
                nm = mask & ~goal
                if nm.any():
                    sh[nm] = tl.pick(rng, t[nm], base)
                if gm.any():
                    q = M.HEAD_Q[tl.pos] if gi == 1 else M.POS_XG[tl.pos]
                    sh[gm] = tl.pick(rng, t[gm], base * q)
            else:
                sh[mask] = tl.pick(rng, t[mask], base)
    if forced_shooter is not None:
        fs = np.asarray(forced_shooter)
        sh = np.where(fs >= 0, fs, sh)
    spos = tl.pos[sh]
    # --- ubicación (3 candidatos; para goles se elige ∝ xG)
    cx = np.zeros((n, 3)); cy = np.zeros((n, 3)); cg = np.zeros((n, 3))
    through = rng.random(n) < 0.18
    for j in range(3):
        x = np.full(n, 94.0); y = np.full(n, 34.0); g = np.full(n, M.PENALTY_XG)
        m = (kind == KIND_HEAD) | (kind == KIND_CROSS)
        if m.any():
            hx, hy = M.sample_header_shots(rng, int(m.sum())); x[m], y[m] = hx, hy
            g[m] = M.xg_open(hx, hy, header=True)
        m = kind == KIND_FK
        if m.any():
            fx, fy = M.sample_fk_shots(rng, int(m.sum())); x[m], y[m] = fx, fy; g[m] = M.xg_fk(fx, fy)
        m = (kind == KIND_OPEN) | (kind == KIND_SOLO)
        if m.any():
            ox, oy = M.sample_open_shots(rng, spos[m]); x[m], y[m] = ox, oy
            g[m] = M.xg_open(ox, oy, through=through[m] & (kind[m] == KIND_OPEN), solo=(kind[m] == KIND_SOLO))
        cx[:, j], cy[:, j], cg[:, j] = x, y, g
    u = rng.random(n)
    cum = np.cumsum(cg, axis=1)
    cj = np.minimum((cum < (u * cum[:, -1])[:, None]).sum(1), 2)
    cj = np.where(goal & (kind != KIND_PEN), cj, 0)
    ar = np.arange(n)
    x, y, xg = cx[ar, cj], cy[ar, cj], np.round(cg[ar, cj], 3)
    # --- parte del cuerpo
    pr = np.array([.78, .22, .5])[tl.foot[sh]]
    right = rng.random(n) < pr
    body = np.where(right, "right_foot", "left_foot").astype(object)
    body[(kind == KIND_HEAD) | (kind == KIND_CROSS)] = "head"
    detail = np.full(n, "open_play", dtype=object)
    detail[kind == KIND_PEN] = "penalty"; detail[kind == KIND_HEAD] = "set_piece"; detail[kind == KIND_FK] = "free_kick"
    # --- resultado
    r = rng.random(n)
    out = np.empty(n, dtype=object)
    c = np.cumsum(np.array([.24, .28, .35, .025]) / .895)
    ngo = np.select([r < c[0], r < c[1], r < c[2]], ["saved", "blocked", "off"], "post").astype(object)
    pc = np.select([r < .6, r < .85], ["saved", "off"], "post").astype(object)
    out[:] = np.where(kind == KIND_PEN, pc, ngo)
    out[goal] = "goal"
    # --- pase clave / asistencia
    has_key = (kind == KIND_OPEN) | (kind == KIND_CROSS) | ((kind == KIND_HEAD) & (rng.random(n) < np.where(goal, .45, .6)))
    fk_ = np.full(n, -1) if forced_key is None else np.asarray(forced_key)
    has_key = np.where(fk_ == -2, False, np.where(fk_ >= 0, True, has_key))
    # los goles de saque de falta/penalti/jugada individual nunca llevan pase clave salvo orden expresa
    link = np.full(n, -1, dtype=np.int64)
    ki = np.nonzero(has_key)[0]
    if len(ki):
        tk = np.maximum(t[ki] - rng.integers(1, 6, len(ki)), tl.t_on[sh[ki]])
        tk = np.minimum(tk, t[ki])
        cre = np.full(len(ki), -1)
        corner = kind[ki] == KIND_HEAD
        for mask, base in ((corner, M.W_FK[tl.pos] * tl.f_create), (~corner, M.W_CREATE[tl.pos] * tl.f_create)):
            if mask.any():
                cre[mask] = tl.pick(rng, tk[mask], base, exclude=sh[ki][mask])
        forced = fk_[ki] >= 0
        cre = np.where(forced, fk_[ki], cre)
        m_ = len(ki)
        side_r = np.where(tl.anchors[tl.slot[cre], 1] < 28, 1, np.where(tl.anchors[tl.slot[cre], 1] > 40, 0, rng.random(m_) < .5))
        ox = np.zeros(m_); oy = np.zeros(m_)
        det = np.full(m_, None, dtype=object)
        cr = kind[ki] == KIND_CROSS
        ox[cr] = rng.uniform(80, 102, cr.sum()); oy[cr] = np.where(side_r[cr] == 1, rng.uniform(2, 13, cr.sum()), rng.uniform(55, 66, cr.sum()))
        det[cr] = "cross"
        cn = corner
        ox[cn] = 104.5; oy[cn] = np.where(side_r[cn] == 1, 0.5, 67.5); det[cn] = "corner"
        op = ~(cr | cn)
        ox[op] = x[ki][op] - rng.uniform(6, 28, op.sum()); oy[op] = y[ki][op] + rng.normal(0, 10, op.sum())
        det[op] = np.where(through[ki][op], "through_ball", None)
        ox, oy = _clipxy(ox, oy)
        ex = np.round(np.clip(x[ki] + rng.normal(0, .5, m_), 0.5, 104.5), 1)
        ey = np.round(np.clip(y[ki] + rng.normal(0, .5, m_), 0.5, 67.5), 1)
        lk = buf.add(tk, tm, tl.pid[cre], "pass", ox, oy, ex=ex, ey=ey, outcome="complete", receiver=tl.pid[sh[ki]],
                     key=1, assist=goal[ki].astype(int), detail=det)
        link[ki] = lk
    # --- coordenadas finales del disparo
    ex = np.full(n, 105.0); ey = 34.0 + np.zeros(n)
    s = rng.choice([-1.0, 1.0], n)
    ey = np.where(out == "goal", 34 + rng.uniform(-3.1, 3.1, n), ey)
    ey = np.where(out == "saved", 34 + rng.uniform(-3.0, 3.0, n), ey)
    ey = np.where(out == "post", 34 + s * 3.66, ey)
    ey = np.where(out == "off", 34 + s * rng.uniform(4.0, 9.0, n), ey)
    bl = out == "blocked"
    ex = np.where(bl, np.minimum(x + rng.uniform(1.5, 6.0, n), 104.5), ex)
    ey = np.where(bl, y + rng.normal(0, 1.5, n), ey)
    slid = buf.add(t, tm, tl.pid[sh], "shot", x, y, ex=np.round(ex, 1), ey=np.round(ey, 1), outcome=out, xg=xg,
                   body=body, detail=detail, link=link)
    sv = out == "saved"
    if sv.any():
        gb = np.where(opp.pos == GKI, 1.0, 0.0)
        gk = opp.pick(rng, t[sv], gb)
        k = int(sv.sum())
        gx = np.round(np.clip(rng.normal(3.5, 1.3, k), 0.8, 9), 1)
        gy = np.round(np.clip(rng.normal(34, 3.5, k), 24, 44), 1)
        buf.add(t[sv], tmo, opp.pid[gk], "save", gx, gy, outcome="saved", link=slid[sv])


# ---------------------------------------------------------------- pases
def gen_passes(S, tl, tm, N, acc_adj):
    rng, buf = S.rng, S.buf
    if N <= 0:
        return
    t = rng.integers(0, S.T_end, N)
    pas = tl.pick(rng, t, M.PASS_VOL[tl.pos] * tl.f_pass)
    seg = tl.seg_of(t)
    Wp = tl.Wslot[np.ix_(tl.slot, tl.slot)]          # (P, P) por hueco
    w = tl.present[seg].astype(float) * Wp[pas]
    w[np.arange(N), pas] = 0.0
    cum = np.cumsum(w, axis=1)
    tot = cum[:, -1]
    r = (1.0 - rng.random(N)) * np.where(tot > 0, tot, 1.0)
    rec = np.minimum((cum < r[:, None]).sum(1), tl.P - 1)
    ox = tl.ax[pas] + rng.normal(0, 7.5, N)
    oy = tl.ay[pas] + rng.normal(0, 6.5, N)
    dx = tl.ax[rec] - tl.ax[pas] + rng.normal(0, 5.0, N)
    dy = tl.ay[rec] - tl.ay[pas] + rng.normal(0, 4.2, N)
    ox, oy = _clipxy(ox, oy)
    ex, ey = _clipxy(ox + dx, oy + dy)
    ln = np.hypot(ex - ox, ey - oy)
    p = np.clip(0.93 - 0.0075 * np.maximum(ln - 12, 0) + M.PASS_ACC[tl.pos[pas]] + acc_adj, 0.35, 0.97)
    ok = rng.random(N) < p
    buf.add(t, tm, tl.pid[pas], "pass", ox, oy, ex=ex, ey=ey, outcome=np.where(ok, "complete", "incomplete").astype(object),
            receiver=np.where(ok, tl.pid[rec], None).astype(object))


# ---------------------------------------------------------------- acciones individuales
def gen_dribbles(S, tl, opp, tm, lam):
    rng, buf = S.rng, S.buf
    n = int(rng.poisson(lam))
    if n == 0:
        return
    t = rng.integers(0, S.T_end, n)
    a = tl.pick(rng, t, M.W_DRIB[tl.pos] * tl.f_drib)
    x, y = _clipxy(tl.ax[a] + rng.normal(4, 7, n), tl.ay[a] + rng.normal(0, 6, n))
    won = rng.random(n) < (0.52 + 0.04 * (tl.f_drib[a] - 1))
    d = opp.pick_near(rng, t, 105 - x, 68 - y, np.where(opp.pos == GKI, 0.0, 1.0) * opp.f_def, 12.0)
    buf.add(t, tm, tl.pid[a], "dribble", x, y, outcome=np.where(won, "won", "lost").astype(object), detail=opp.pid[d])


def gen_defensive(S, tl, tm, kind, lam):
    rng, buf = S.rng, S.buf
    n = int(rng.poisson(lam))
    if n == 0:
        return
    base = {"recovery": M.W_REC, "tackle": M.W_TACK, "interception": M.W_INT, "clearance": M.W_CLR}[kind][tl.pos] * tl.f_def
    t = rng.integers(0, S.T_end, n)
    a = tl.pick(rng, t, base)
    if kind == "clearance":
        x = np.abs(rng.normal(13, 7, n)); y = 34 + rng.normal(0, 13, n)
    else:
        x = tl.ax[a] * 0.85 + rng.normal(0, 6, n); y = tl.ay[a] + rng.normal(0, 6.5, n)
    x, y = _clipxy(x, y)
    out = None
    if kind == "tackle":
        out = np.where(rng.random(n) < .62, "won", "lost").astype(object)
    buf.add(t, tm, tl.pid[a], kind, x, y, outcome=out)


# ---------------------------------------------------------------- partido completo
def _goal_times(rng, n1, n2, T1, T_end):
    t1 = np.sort((T1 * rng.random(n1) ** 0.9).astype(np.int64))
    t2 = np.sort((T1 + (T_end - T1) * rng.random(n2) ** 0.85).astype(np.int64))
    return np.concatenate([t1, np.minimum(t2, T_end - 1)])


def simulate_match(ctx: Ctx, m: dict):
    home, away, rnd = m["home"], m["away"], m["round"]
    rng = np.random.default_rng([ctx.seed, rnd, ctx.tidx[home], ctx.tidx[away]])
    truth = ctx.truth if (ctx.truth and ctx.truth["match"] == m["id"]) else None
    a1 = int(rng.choice([1, 2, 3, 4], p=[.15, .35, .30, .20]))
    a2 = int(rng.choice([3, 4, 5, 6, 7], p=[.12, .25, .30, .20, .13]))
    if truth:
        a1, a2 = 3, 5
    buf = Buf()
    S = Sim(rng, a1, a2, buf)
    teams = (home, away)
    lus = {}
    for tm in teams:
        base = M.TEAM_FORMATION.get(tm) or M.default_formation(tm)
        if truth:
            form = truth["lineups"][tm]["formation"]
            lus[tm] = L.truth_lineup(truth, tm, ctx.rosters[tm], ctx.attrs, form, a1, rng)
        else:
            form = base if rng.random() < .85 else str(rng.choice(sorted(M.FORMATIONS)))
            lu = L.pick_lineup(rng, tm, ctx.rosters[tm], ctx.attrs, form)
            L.plan_subs(rng, lu, a1, S.T_end)
            if rng.random() < 0.035:
                L.apply_red(rng, lu, int(rng.integers(900, S.T_end - 240)), S.T_end)
            lus[tm] = lu
        L.finish_presence(lus[tm], S.T_end)
        lus[tm].finalize(S.T_end, a1)
    tls = {tm: TL(lus[tm], S.T_end, M.formation_arrays(lus[tm].formation)) for tm in teams}
    st = ctx.strength
    zh, za = st[home]["z"], st[away]["z"]
    pi_h = float(np.clip(0.5 + 0.055 * (zh - za) + 0.02 + rng.normal(0, .035), .3, .72))
    if truth:
        pi_h = 0.74
    pis = {home: pi_h, away: 1 - pi_h}
    for tm in teams:
        tls[tm].set_shift((pis[tm] - 0.5) * 30.0)
    goals = {home: m["home_goals"], away: m["away_goals"]}
    ht = {home: m.get("ht_home"), away: m.get("ht_away")}
    hn = {home: 1.06, away: 0.94}
    for tm in teams:
        o = away if tm == home else home
        tl, opp = tls[tm], tls[o]
        G = int(goals[tm])
        pi = pis[tm]
        z = st[tm]["z"]
        # ---------------- goles
        gs = dict(t=np.zeros(0, np.int64), kind=np.zeros(0, int), sh=np.zeros(0, int), key=np.zeros(0, int))
        S.ht[tm] = 0
        if truth:
            byid = {mm.p["id"]: i for i, mm in enumerate(lus[tm].members)}
            ts, ks, shs, kys = [], [], [], []
            for g in truth["goals"]:
                if g["team"] != tm:
                    continue
                ts.append(L.t_from_display(g["minute"], g["added"], int(rng.integers(0, 60)), a1))
                shs.append(byid[g["scorer"]])
                kys.append(byid[g["assist"]] if g["assist"] else -2)
                ks.append(KIND_OPEN if g["assist"] else KIND_HEAD)
            gs = dict(t=np.array(ts, np.int64), kind=np.array(ks, int), sh=np.array(shs, int), key=np.array(kys, int))
            S.ht[tm] = truth["halftime"]["home" if tm == home else "away"]
        elif G > 0:
            n1 = ht[tm] if ht[tm] is not None else int(rng.binomial(G, .44))
            S.ht[tm] = n1
            gt = _goal_times(rng, n1, G - n1, S.T1, S.T_end)
            r = rng.random(G)
            kind = np.select([r < .085, r < .235, r < .835], [KIND_PEN, KIND_HEAD, KIND_OPEN], KIND_SOLO)
            kind = np.where((kind == KIND_HEAD) & (rng.random(G) < .15), KIND_FK, kind)
            kind = np.where((kind == KIND_OPEN) & (rng.random(G) < .22), KIND_CROSS, kind)
            gs = dict(t=gt, kind=kind, sh=np.full(G, -1), key=np.full(G, -1))
        # ---------------- tiros que no son gol
        if truth:
            lam_ng = 17.0 if tm == home else 4.0
            n_ng = int(lam_ng)
        else:
            eg = 1.32 * st[tm]["att"] * st[o]["dfn"] * hn[tm]
            lam = (ctx.b_ng * st[tm]["att"] ** .45 * st[o]["dfn"] ** .35 * (2 * pi) ** .55 * hn[tm] ** .5
                   + 2.0 * (G - eg))
            lam = max(lam, 1.5) * rng.gamma(10.0, .1)
            n_ng = int(rng.poisson(lam))
        r = rng.random(n_ng)
        k_ng = np.select([r < .46, r < .72, r < .88], [KIND_OPEN, KIND_SOLO, KIND_HEAD], KIND_FK)
        k_ng = np.where((k_ng == KIND_OPEN) & (rng.random(n_ng) < .22), KIND_CROSS, k_ng)
        t_ng = rng.integers(0, S.T_end, n_ng)
        npen = 0 if truth else int(rng.poisson(0.03))
        t_pen = rng.integers(300, S.T_end - 60, npen)
        t_all = np.concatenate([gs["t"], t_ng, t_pen]).astype(np.int64)
        kind_all = np.concatenate([gs["kind"], k_ng, np.full(npen, KIND_PEN)]).astype(int)
        goal_all = np.concatenate([np.ones(len(gs["t"]), bool), np.zeros(n_ng + npen, bool)])
        fs_all = np.concatenate([gs["sh"], np.full(n_ng + npen, -1)]).astype(int)
        fk_all = np.concatenate([gs["key"], np.full(n_ng + npen, -1)]).astype(int)
        make_shots(S, tl, opp, tm, o, t_all, kind_all, goal_all, fs_all, fk_all)
        # ---------------- pases
        N = int(round(940 * pis[tm] * np.exp(rng.normal(0, .06)) * (0.97 + .06 * (z > 0))))
        gen_passes(S, tl, tm, N, 0.025 * z)
        # ---------------- regates y acciones defensivas
        gen_dribbles(S, tl, opp, tm, 14.0 * (pi / .5) ** .5 * np.exp(.08 * z))
        fd = float(np.clip((1 - pi) / .5, .5, 1.6))
        gen_defensive(S, tl, tm, "recovery", 50.0 * fd ** .5)
        gen_defensive(S, tl, tm, "tackle", 17.5 * fd)
        gen_defensive(S, tl, tm, "interception", 11.0 * fd)
        gen_defensive(S, tl, tm, "clearance", 20.0 * fd ** 1.2)
        # ---------------- faltas y tarjetas
        if truth:
            lam_f = 14.0 if tm == away else 8.0
            regular_fouls(S, tl, opp, tm, o, lam_f, cards=False)
            byid = {mm.p["id"]: i for i, mm in enumerate(lus[tm].members)}
            for c in truth["cards"]:
                if c["team"] != tm:
                    continue
                T = L.t_from_display(c["minute"], 0, int(rng.integers(0, 60)), a1)
                fi = np.array([byid[c["player"]]])
                lid, fo, x, y = emit_fouls(S, tl, opp, tm, o, np.array([T]), fouler=fi,
                                           detail="handball" if c["player"].endswith("javi-sanchez") else None)
                emit_card(S, tl, tm, np.array([T]), lid, fo, x, y, c["card"])
        else:
            regular_fouls(S, tl, opp, tm, o, 11.7 * (1 + .3 * (.5 - pi)) * (1 - .04 * z))
            for (T, i) in lus[tm].reds:
                lid, fo, x, y = emit_fouls(S, tl, opp, tm, o, np.array([T - 1]), fouler=np.array([i]))
                emit_card(S, tl, tm, np.array([T - 1]), lid, fo, x, y, "red")
        # ---------------- cambios
        for (T, i_in, i_out) in lus[tm].subs:
            buf.add([T], tm, tl.pid[i_in], "sub", 52.5, 0.0, detail=tl.pid[i_out])
    return lus, buf.finish(), a1, a2, S
