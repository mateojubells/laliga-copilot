"""Verosimilitud POR JUGADOR (las pruebas de test_plausibility.py solo miran medias de liga)."""
from collections import defaultdict

import numpy as np
import pytest

from copilot.data.synthetic import SyntheticProvider, sources_hash
from data.synth.generate import DEFAULT_SEED
from data.synth.testing import connect, seed_db

MIN_MINUTES = 900

SQL = """
SELECT p.id, p.team, p.position, p.line, p.known_as,
 COALESCE((SELECT SUM(minutes) FROM lineups l WHERE l.player=p.id), 0),
 COALESCE(SUM(e.type='shot'), 0), COALESCE(SUM(e.type='shot' AND e.outcome='goal'), 0),
 COALESCE(SUM(CASE WHEN e.type='shot' THEN e.xg ELSE 0 END), 0), COALESCE(SUM(e.type='pass'), 0),
 COALESCE(SUM(e.type='dribble'), 0), COALESCE(SUM(e.type='foul'), 0),
 COALESCE(SUM(e.type='card' AND e.detail='yellow'), 0)
FROM players p LEFT JOIN events e ON e.player=p.id GROUP BY p.id
"""
COLS = ["id", "team", "pos", "line", "name", "min", "shots", "goals", "xg", "passes", "drib", "fouls", "yellow"]


def table(db):
    return [dict(zip(COLS, r)) for r in db.execute(SQL)]


def p90(r, k):
    return r[k] / r["min"] * 90


@pytest.fixture(scope="module")
def rows(db):
    return table(db)


@pytest.fixture(scope="module")
def regulars(rows):
    return [r for r in rows if r["min"] >= MIN_MINUTES and r["pos"] != "GK"]


def fmt(rs, k):
    return [(r["name"], r["team"], r["pos"], round(p90(r, k), 2)) for r in rs]


def test_tiros_por_90_acotados(regulars):
    bad = [r for r in regulars if p90(r, "shots") > 5.5]
    assert not bad, fmt(bad, "shots")


def test_distribucion_de_tiros_por_90(regulars):
    v = np.array([p90(r, "shots") for r in regulars])
    p50, p90_, p99 = np.percentile(v, [50, 90, 99])
    assert 0.6 <= p50 <= 1.8, p50
    assert 1.8 <= p90_ <= 3.4, p90_
    assert p99 <= 4.8 and v.max() <= 5.5, (p99, v.max())
    # un delantero centro titular de cada equipo remata entre 1,5 y 5,5 por 90
    st = {}
    for r in regulars:
        if r["pos"] == "ST" and r["min"] > st.get(r["team"], {"min": 0})["min"]:
            st[r["team"]] = r
    assert len(st) == 20 and all(1.5 <= p90(r, "shots") <= 5.5 for r in st.values()), fmt(st.values(), "shots")


def test_ningun_jugador_acapara_los_tiros_del_equipo(rows):
    tot = defaultdict(int)
    for r in rows:
        tot[r["team"]] += r["shots"]
    bad = [(r["name"], r["team"], round(r["shots"] / tot[r["team"]], 3)) for r in rows
           if r["shots"] > 0.30 * tot[r["team"]]]
    assert not bad, bad
    # y el máximo de la liga no es absurdo: nadie por encima del 27 %
    assert max(r["shots"] / tot[r["team"]] for r in rows) <= 0.27


def test_porteros_sin_tiros_ni_goles(rows):
    gks = [r for r in rows if r["pos"] == "GK"]
    assert len(gks) >= 40
    assert all(r["shots"] == 0 and r["goals"] == 0 and r["drib"] == 0 for r in gks)


def test_goles_por_90_segun_posicion(regulars):
    mid = [r for r in regulars if r["pos"] in ("DM", "CM") and p90(r, "goals") > 0.45]
    assert not mid, fmt(mid, "goals")
    dfn = [r for r in regulars if r["pos"] in ("CB", "RB", "LB") and p90(r, "goals") > 0.15]
    assert len(dfn) <= 3, fmt(dfn, "goals")
    assert not [r for r in dfn if p90(r, "goals") > 0.30], fmt(dfn, "goals")
    # ningún defensa pasa de 6 goles y el reparto de goles por línea es el de una liga real
    assert max(r["goals"] for r in regulars if r["pos"] in ("CB", "RB", "LB")) <= 6


def test_reparto_de_goles_por_linea(rows):
    g = defaultdict(int)
    for r in rows:
        g[r["line"]] += r["goals"]
    tot = sum(g.values())
    assert 0.05 <= g["DEF"] / tot <= 0.16, dict(g)
    assert 0.50 <= g["FWD"] / tot <= 0.72, dict(g)
    assert 0.15 <= g["MID"] / tot <= 0.32, dict(g)


def test_goles_coherentes_con_xg_por_jugador(rows):
    bad = [(r["name"], r["goals"], round(r["xg"], 1)) for r in rows
           if r["goals"] >= 10 and not (0.4 * r["goals"] <= r["xg"] <= 1.6 * r["goals"])]
    assert not bad, bad


def test_pases_centrales_y_pivotes_mas_que_delanteros(rows):
    mins = defaultdict(dict)
    for r in rows:
        mins[r["team"]].setdefault(r["pos"], []).append(r)
    ok = n = 0
    for t, d in mins.items():
        st = max(d["ST"], key=lambda r: r["min"])
        back = [max(d[k], key=lambda r: r["min"]) for k in ("CB", "DM") if k in d]
        n += 1
        ok += max(p90(r, "passes") for r in back) > p90(st, "passes")
    assert n == 20 and ok / n >= 0.8, (ok, n)


def test_acciones_individuales_acotadas(regulars):
    assert max(p90(r, "passes") for r in regulars) <= 95
    assert max(p90(r, "drib") for r in regulars) <= 7.0, fmt(sorted(regulars, key=lambda r: -p90(r, "drib"))[:3], "drib")
    assert max(p90(r, "fouls") for r in regulars) <= 4.0, fmt(sorted(regulars, key=lambda r: -p90(r, "fouls"))[:3], "fouls")
    assert max(r["yellow"] for r in regulars) <= 16
    # extremos regatean más que centrales y delanteros
    m = {k: np.mean([p90(r, "drib") for r in regulars if r["pos"] in k]) for k in (("RW", "LW"), ("CB",))}
    assert m[("RW", "LW")] > 3 * m[("CB",)]
    # los pases por 90 de un titular no bajan de 8 salvo delanteros
    assert min(p90(r, "passes") for r in regulars if r["pos"] in ("CB", "DM", "CM")) >= 15


@pytest.mark.parametrize("seed", [DEFAULT_SEED, 7, 123])
def test_maximo_goleador_para_varias_semillas(seed, tmp_path_factory):
    db = connect(seed_db(seed, tmp_path_factory.getbasetemp()))
    top = db.execute("SELECT COUNT(*) c FROM events WHERE type='shot' AND outcome='goal' GROUP BY player "
                     "ORDER BY c DESC LIMIT 1").fetchone()[0]
    assert 18 <= top <= 36, (seed, top)
    # las reglas por jugador se cumplen también con otras semillas
    rs = [r for r in table(db) if r["min"] >= MIN_MINUTES and r["pos"] != "GK"]
    assert max(p90(r, "shots") for r in rs) <= 5.5, (seed, fmt(sorted(rs, key=lambda r: -p90(r, "shots"))[:2], "shots"))
    assert not [r for r in rs if r["pos"] in ("DM", "CM") and p90(r, "goals") > 0.45]
    dfn = [r for r in rs if r["pos"] in ("CB", "RB", "LB") and p90(r, "goals") > 0.15]
    # con 900-1500 minutos, 2 goles ya superan 0,15/90: ruido de muestra pequeña; se exige el límite estricto
    # (<=3 excepciones) a partir de 1500 minutos y uno holgado (0,30) por debajo
    assert len([r for r in dfn if r["min"] >= 1500]) <= 3 and not [r for r in dfn if p90(r, "goals") > 0.30], \
        (seed, fmt(dfn, "goals"))
    db.close()


def test_hash_de_fuentes_en_meta(db):
    meta = dict(db.execute("SELECT key, value FROM meta"))
    assert meta.get("sources_hash") == sources_hash()


def test_el_proveedor_avisa_de_una_base_generada_con_otro_codigo(db_path, tmp_path):
    import shutil
    import sqlite3
    ok = SyntheticProvider(db_path)
    assert not ok.stale and ok.stale_reason is None
    viejo = tmp_path / "viejo.sqlite"
    shutil.copy(db_path, viejo)
    c = sqlite3.connect(viejo)
    c.execute("UPDATE meta SET value='0000000000000000' WHERE key='sources_hash'")
    c.commit(); c.close()
    sp = SyntheticProvider(viejo)
    with pytest.warns(RuntimeWarning, match="obsoletos"):
        assert sp.stale and sp.available()
        sp.conn  # no rompe el arranque
    assert sp.standings("2024-25")  # sigue funcionando
