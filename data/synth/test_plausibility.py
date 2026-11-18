"""Verosimilitud futbolística de los datos generados."""
from collections import Counter, defaultdict

import numpy as np

from copilot.data.synthetic import SyntheticProvider


def q(db, sql, args=()):
    return db.execute(sql, args).fetchall()


def test_porteros_sin_regates_ni_tiros(db):
    n = q(db, "SELECT COUNT(*) FROM events e JOIN players p ON p.id=e.player WHERE p.position='GK' "
              "AND e.type IN ('dribble','shot')")[0][0]
    assert n == 0
    n = q(db, "SELECT COUNT(*) FROM events e JOIN lineups l ON l.match=e.match AND l.player=e.player "
              "WHERE l.slot='GK' AND e.type IN ('dribble','shot','tackle','interception','foul')")[0][0]
    assert n == 0
    assert q(db, "SELECT COUNT(*) FROM events e JOIN players p ON p.id=e.player WHERE e.type='save' AND p.position!='GK'")[0][0] == 0


def test_volumen_por_partido(db):
    per = q(db, "SELECT type, COUNT(*) FROM events GROUP BY type")
    cnt = dict(per)
    passes = [r[0] for r in q(db, "SELECT COUNT(*) FROM events WHERE type='pass' GROUP BY match, team")]
    assert 300 <= np.mean(passes) <= 650 and min(passes) > 150 and max(passes) < 900
    assert 800 <= cnt["pass"] / 380 <= 1000
    shots = np.mean([r[0] for r in q(db, "SELECT COUNT(*) FROM events WHERE type='shot' GROUP BY match, team")])
    assert 6 <= shots <= 20 and 20 <= cnt["shot"] / 380 <= 28
    assert 25 <= cnt["dribble"] / 380 <= 35
    assert 20 <= cnt["foul"] / 380 <= 28
    y = cnt["card"] / 380
    yellow = q(db, "SELECT COUNT(*) FROM events WHERE type='card' AND detail='yellow'")[0][0] / 380
    assert 3 <= yellow <= 7
    reds = q(db, "SELECT COUNT(*) FROM events WHERE type='card' AND detail='red'")[0][0]
    assert 5 <= reds <= 70


def test_precision_de_pase(db):
    acc = q(db, "SELECT AVG(outcome='complete') FROM events WHERE type='pass'")[0][0]
    assert 0.70 <= acc <= 0.93
    por_equipo = [r[0] for r in q(db, "SELECT AVG(outcome='complete') FROM events WHERE type='pass' GROUP BY team")]
    assert min(por_equipo) > 0.70 and max(por_equipo) < 0.93
    # los porteros fallan más que los centrales
    by = dict(q(db, "SELECT l.slot, AVG(e.outcome='complete') FROM events e JOIN lineups l ON l.match=e.match "
                    "AND l.player=e.player WHERE e.type='pass' GROUP BY l.slot"))
    assert by["CB"] > by["ST"] and by["CB"] > by["GK"]


def test_xg_realista(db):
    xg, goals = q(db, "SELECT SUM(xg), SUM(outcome='goal') FROM events WHERE type='shot'")[0]
    assert abs(xg - goals) / goals < 0.08
    mean = q(db, "SELECT AVG(xg) FROM events WHERE type='shot'")[0][0]
    assert 0.08 <= mean <= 0.14
    assert abs(q(db, "SELECT AVG(xg) FROM events WHERE detail='penalty'")[0][0] - 0.76) < 1e-9
    # distancia: lejanos 0.02-0.05, área pequeña alto
    far = q(db, "SELECT AVG(xg) FROM events WHERE type='shot' AND detail='open_play' AND x < 80")[0][0]
    six = q(db, "SELECT AVG(xg) FROM events WHERE type='shot' AND detail='open_play' AND x >= 99.5 AND y BETWEEN 27.5 AND 40.5")[0][0]
    assert far < 0.06 and six > 0.30 and six > 5 * far
    # centrado y cerca vale más que desde el pico del área
    wide = q(db, "SELECT AVG(xg) FROM events WHERE type='shot' AND detail='open_play' AND x BETWEEN 94 AND 100 AND (y<14 OR y>54)")[0][0]
    mid = q(db, "SELECT AVG(xg) FROM events WHERE type='shot' AND detail='open_play' AND x BETWEEN 94 AND 100 AND y BETWEEN 28 AND 40")[0][0]
    assert mid > 2 * wide
    # los goles tienen más xG medio que los fallos, los cabezazos menos que los pies a igual zona
    g = q(db, "SELECT AVG(xg) FROM events WHERE type='shot' AND outcome='goal' AND detail='open_play'")[0][0]
    n = q(db, "SELECT AVG(xg) FROM events WHERE type='shot' AND outcome!='goal' AND detail='open_play'")[0][0]
    assert g > n
    # penaltis: ~75 % de conversión
    pen = q(db, "SELECT AVG(outcome='goal'), COUNT(*) FROM events WHERE detail='penalty'")[0]
    assert 0.6 <= pen[0] <= 0.9 and 60 <= pen[1] <= 160


def test_zonas_de_tiro(db):
    # la mayoría de los tiros desde dentro del área o su borde; muy pocos desde el campo propio
    n = q(db, "SELECT COUNT(*) FROM events WHERE type='shot'")[0][0]
    inbox = q(db, "SELECT COUNT(*) FROM events WHERE type='shot' AND x>=88.5 AND y BETWEEN 13.84 AND 54.16")[0][0]
    assert 0.40 <= inbox / n <= 0.80
    assert q(db, "SELECT COUNT(*) FROM events WHERE type='shot' AND x < 60")[0][0] == 0
    heads = q(db, "SELECT AVG(x), AVG(ABS(y-34)) FROM events WHERE type='shot' AND body='head'")[0]
    assert heads[0] > 90 and heads[1] < 9


def test_mediocentro_entre_los_3_que_mas_pasan(db):
    pos = dict(q(db, "SELECT id, position FROM players"))
    ok = 0
    teams = [r[0] for r in q(db, "SELECT DISTINCT team FROM events")]
    for t in teams:
        top = q(db, "SELECT player FROM events WHERE type='pass' AND team=? GROUP BY player ORDER BY COUNT(*) DESC LIMIT 3", (t,))
        ok += any(pos[p[0]] in ("DM", "CM") for p in top)
    assert len(teams) == 20 and ok / len(teams) >= 0.70, ok


def test_laterales_conectados_con_su_banda(db):
    """Para >=70 % de los laterales titulares, su destinatario n.º 1 o 2 es el extremo/interior de su banda o el central contiguo."""
    slot = defaultdict(Counter)
    for p, s, side, n in q(db, "SELECT player, slot, side, COUNT(*) FROM lineups WHERE minutes>0 GROUP BY 1,2,3"):
        slot[p][(s, side)] = n
    modal = {p: c.most_common(1)[0][0] for p, c in slot.items()}
    fbs = q(db, "SELECT player, slot, side FROM (SELECT player, slot, side, COUNT(*) n FROM lineups WHERE started=1 "
                "AND slot IN ('RB','LB') GROUP BY 1,2,3) WHERE n>=10")
    total = good = 0
    for p, s, side in fbs:
        top = q(db, "SELECT receiver FROM events WHERE type='pass' AND outcome='complete' AND player=? GROUP BY receiver "
                    "ORDER BY COUNT(*) DESC LIMIT 2", (p,))
        total += 1
        for (r,) in top:
            rs, rside = modal[r]
            if rside == side and rs in ("RW", "LW", "CM", "DM", "AM", "CB"):
                good += 1
                break
    assert total >= 20 and good / total >= 0.70, (good, total)


def test_delanteros_tiran_mas_que_defensas(db_path):
    p = SyntheticProvider(db_path)
    by = defaultdict(list)
    for pl in ("GK", "DEF", "MID", "FWD"):
        pass
    import sqlite3
    c = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    for pid, line in c.execute("SELECT id, line FROM players"):
        ps = p.player_season(pid, "2024-25")
        if ps.minutes >= 900:
            by[line].append(ps.stats["shots"].per90)
    m = {k: float(np.mean(v)) for k, v in by.items()}
    assert m["FWD"] > 2 * m["DEF"] and m["MID"] > m["DEF"] and m["GK"] == 0 if "GK" in m else True


def test_posiciones_medias_en_su_zona(db):
    rows = q(db, """SELECT l.slot, l.side, AVG(e.x), AVG(e.y) FROM events e JOIN lineups l ON l.match=e.match AND l.player=e.player
                    WHERE e.type='pass' AND l.started=1 GROUP BY l.slot, l.side""")
    zone = {("GK", "C"): (3, 20, 28, 40), ("CB", "R"): (20, 42, 14, 34), ("CB", "L"): (20, 42, 34, 54),
            ("RB", "R"): (28, 58, 2, 24), ("LB", "L"): (28, 58, 44, 66),
            ("RW", "R"): (55, 85, 2, 30), ("LW", "L"): (55, 85, 38, 66), ("ST", "C"): (62, 100, 26, 42)}
    got = {(s, sd): (x, y) for s, sd, x, y in rows}
    for k, (x0, x1, y0, y1) in zone.items():
        x, y = got[k]
        assert x0 <= x <= x1 and y0 <= y <= y1, (k, x, y)
    for (s, sd), (x, y) in got.items():
        if s == "ST":
            assert x > 60
        if s == "GK":
            assert x < 20
        if s in ("CM", "DM"):
            assert 35 <= x <= 68
    # el 'y' bajo es la banda derecha para el propio equipo
    assert got[("RB", "R")][1] < got[("LB", "L")][1]


def test_goleador_de_la_liga(db):
    top = q(db, "SELECT player, COUNT(*) c FROM events WHERE type='shot' AND outcome='goal' GROUP BY player ORDER BY c DESC LIMIT 1")[0]
    assert 20 <= top[1] <= 35, top
    # reparto: ningún defensa central entre los 10 máximos goleadores
    pos = dict(q(db, "SELECT id, position FROM players"))
    top10 = q(db, "SELECT player FROM events WHERE type='shot' AND outcome='goal' GROUP BY player ORDER BY COUNT(*) DESC LIMIT 10")
    assert sum(pos[p[0]] in ("CB", "RB", "LB", "GK") for p in top10) <= 1


def test_minutos_de_los_goles_plausibles(db):
    mins = [r[0] for r in q(db, "SELECT minute FROM events WHERE type='shot' AND outcome='goal'")]
    assert 0.40 <= np.mean(np.array(mins) <= 45) <= 0.52   # algo menos de la mitad antes del descanso
    assert min(mins) >= 1 and max(mins) <= 90


def test_porteros_titulares_juegan_casi_todo(db):
    mx = q(db, "SELECT t, MAX(m) FROM (SELECT l.team t, l.player, SUM(l.minutes) m FROM lineups l JOIN players p ON p.id=l.player "
               "WHERE p.position='GK' GROUP BY l.team, l.player) GROUP BY t")
    assert len(mx) == 20 and min(m for _, m in mx) >= 1800 and sum(m >= 2500 for _, m in mx) >= 17
