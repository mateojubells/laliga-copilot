"""Proveedores de datos: openfootball (real), sintético, compuesto y hueco de pago."""
import json
import time
from pathlib import Path

import pytest

from copilot.data.composite import CompositeProvider
from copilot.data.licensed import LicensedProvider
from copilot.data.openfootball import TEAM_IDS, OpenFootballProvider
from copilot.data.provider import DataProvider
from copilot.data.synthetic import SyntheticDataMissing, SyntheticProvider
from data.synth.testing import connect, full_db

ROOT = Path(__file__).resolve().parent.parent
ROSTER_IDS = {t["id"] for t in json.loads((ROOT / "data" / "rosters" / "2024-25.json").read_text())["teams"]}
J4 = "2024-25/J04/barcelona-valladolid"


@pytest.fixture(scope="module")
def of():
    return OpenFootballProvider()


@pytest.fixture(scope="module")
def sp():
    return SyntheticProvider(full_db())


# ------------------------------------------------------------------ openfootball
def test_mapeo_de_los_20_equipos(of):
    names_2425 = {m for m in TEAM_IDS if TEAM_IDS[m] in ROSTER_IDS}
    assert len(names_2425) == 20 and {TEAM_IDS[n] for n in names_2425} == ROSTER_IDS
    import json as _j
    raw = _j.loads((ROOT / "data" / "real" / "es.1.2024-25.json").read_text())["matches"]
    assert {m["team1"] for m in raw} == names_2425
    assert {t.id for t in of.teams("2024-25")} == ROSTER_IDS


def test_resultados_reales(of):
    for s in ("2022-23", "2023-24", "2024-25"):
        ms = of.matches(s)
        assert len(ms) == 380 and all(m.home_goals is not None for m in ms) and not any(m.synthetic for m in ms)
    m = {x.id: x for x in of.matches("2024-25")}[J4]
    assert (m.home_goals, m.away_goals, m.date, m.round) == (7, 0, "2024-08-31", 4)
    assert len(of.matches("2024-25", "barcelona")) == 38


def test_clasificacion_final_real(of):
    t = of.standings("2024-25")
    assert [r.team for r in t[:5]] == ["barcelona", "real-madrid", "atletico", "athletic", "villarreal"]
    r = {x.team: x for x in t}
    assert (r["barcelona"].points, r["barcelona"].gf, r["barcelona"].ga) == (88, 102, 39)
    assert (r["real-madrid"].points, r["valladolid"].points) == (84, 16)
    assert all(x.played == 38 for x in t) and sum(x.gf for x in t) == sum(x.ga for x in t) == 995


def test_clasificacion_tras_3_jornadas(of):
    t = of.standings("2024-25", until_round=3)
    assert all(x.played == 3 for x in t)
    manual = {}
    for m in of.matches("2024-25"):
        if m.round <= 3:
            for a, b, c in ((m.home, m.home_goals, m.away_goals), (m.away, m.away_goals, m.home_goals)):
                manual[a] = manual.get(a, 0) + (3 if b > c else 1 if b == c else 0)
    assert {x.team: x.points for x in t} == manual
    assert [x.points for x in t] == sorted((x.points for x in t), reverse=True)
    assert all(len(x.form) == 3 for x in t)


def test_h2h_real(of):
    h = of.h2h("barcelona", "valladolid")
    assert h.played == 4 and h.a_wins == 3 and h.b_wins == 1 and (h.a_goals, h.b_goals) == (14, 4)
    assert h.last[0].id == "2024-25/J34/valladolid-barcelona"
    h4 = of.h2h("barcelona", "valladolid", until=4)   # antes de la J4: solo 2022-23
    assert h4.played == 2 and h4.last[0].season == "2022-23"
    assert of.h2h("valladolid", "barcelona").a_wins == 1


def test_openfootball_resto_no_implementado(of):
    for call in (lambda: of.squad("barcelona", "2024-25"), lambda: of.player_season("x", "2024-25"),
                 lambda: of.team_season("x", "2024-25"), lambda: of.events(), lambda: of.pass_network("x"),
                 lambda: of.connection("a", "b", season="2024-25")):
        with pytest.raises(NotImplementedError):
            call()
    assert of.synthetic is False


# ------------------------------------------------------------------ interfaz
def test_cumplen_el_protocolo(sp, of):
    for p in (sp, of, CompositeProvider(of, sp), LicensedProvider()):
        assert isinstance(p, DataProvider)
    assert sp.synthetic is True and CompositeProvider(of, sp).synthetic is True and LicensedProvider().synthetic is False
    with pytest.raises(NotImplementedError):
        LicensedProvider().h2h("a", "b")


# ------------------------------------------------------------------ sintético
def test_clasificacion_sintetica_igual_a_openfootball(sp, of):
    for r in (None, 3, 20):
        assert sp.standings("2024-25", r) == of.standings("2024-25", r)
    assert sp.matches("2024-25") == of.matches("2024-25")


def test_squad_y_teams(sp):
    sq = sp.squad("barcelona", "2024-25")
    assert any(p.id == "barcelona/pedri" and p.number == 8 for p in sq)
    assert len(sp.teams("2024-25")) == 20


def test_until_jornada_y_partido_equivalentes(sp):
    for pid in ("barcelona/lewandowski", "barcelona/raphinha", "barcelona/pedri"):
        a = sp.player_season(pid, "2024-25", until=4)
        b = sp.player_season(pid, "2024-25", until=J4)
        assert a == b
        assert a.matches <= 3 and a.minutes <= 270


def test_until_no_cuenta_la_j4_en_adelante(sp):
    db = connect()
    for pid in ("barcelona/lewandowski", "barcelona/raphinha", "barcelona/lamine-yamal"):
        ps = sp.player_season(pid, "2024-25", until=4)
        g = db.execute("SELECT COUNT(*) FROM events WHERE player=? AND type='shot' AND outcome='goal' AND round<4", (pid,)).fetchone()[0]
        mi = db.execute("SELECT COALESCE(SUM(minutes),0) FROM lineups WHERE player=? AND round<4", (pid,)).fetchone()[0]
        assert ps.stats["goals"].value == g and ps.minutes == mi
        full = sp.player_season(pid, "2024-25")
        assert full.stats["goals"].value >= g and full.minutes > ps.minutes
    ev = sp.events(player_id="barcelona/raphinha", until=4)
    assert ev and all(e.match.split("/")[1] < "J04" for e in ev)
    assert sp.events(J4, until=4) == []
    assert sp.events(J4, until=5) != []
    ts = sp.team_season("barcelona", "2024-25", until=4)
    assert ts.stats["points"].value == 9 or ts.stats["points"].value <= 9   # tres partidos
    assert sum(ts.stats[k].value for k in ("wins", "draws", "losses")) == 3
    net = sp.pass_network("barcelona", season="2024-25", until=4)
    net_all = sp.pass_network("barcelona", season="2024-25")
    assert sum(e.count for e in net.edges) < sum(e.count for e in net_all.edges) / 5
    assert sp.pass_network("barcelona", match_id=J4, until=4).nodes == []
    c4 = sp.connection("barcelona/pedri", "barcelona/lamine-yamal", season="2024-25", until=4)
    c = sp.connection("barcelona/pedri", "barcelona/lamine-yamal", season="2024-25")
    assert c4.a_to_b < c.a_to_b


def test_player_season_forma_y_percentiles(sp):
    ps = sp.player_season("barcelona/lewandowski", "2024-25")
    assert ps.synthetic and ps.minutes > 1500 and ps.matches >= 20
    for k in ("goals", "assists", "xg", "xa", "shots", "shots_on_target", "passes", "pass_pct", "key_passes",
              "dribbles", "dribbles_won", "recoveries", "tackles", "interceptions", "clearances", "fouls", "fouled",
              "yellow", "red", "saves", "touches"):
        assert k in ps.stats
    assert ps.stats["goals"].per90 == pytest.approx(ps.stats["goals"].value * 90 / ps.minutes, abs=1e-2)
    assert 0 <= ps.stats["shots"].percentile <= 100 and ps.stats["shots"].percentile >= 60  # un 9 tira mucho
    assert ps.stats["pass_pct"].per90 is None and 50 < ps.stats["pass_pct"].value < 100
    gk = sp.player_season("barcelona/ter-stegen", "2024-25")
    assert gk.stats["dribbles"].value == 0 and gk.stats["shots"].value == 0 and gk.stats["saves"].percentile is not None
    assert sp.player_season("barcelona/pedri", "2024-25").stats["saves"].percentile is None


def test_team_season(sp):
    ts = sp.team_season("barcelona", "2024-25")
    assert ts.stats["points"].value == 88 and ts.stats["goals_for"].value == 102 and ts.stats["goals_against"].value == 39
    assert ts.stats["possession"].value > 50
    assert abs(ts.stats["xg_for"].value - 102) / 102 < 0.35


def test_events_y_filtros(sp):
    ev = sp.events(J4, types=["shot"])
    assert len(ev) >= 24 and all(e.type == "shot" and e.xg is not None for e in ev)
    assert sum(e.outcome == "goal" for e in ev) == 7
    ids = [e.id for e in sp.events(J4)]
    assert ids == sorted(ids)
    assert all(0 <= e.x <= 105 and 0 <= e.y <= 68 for e in sp.events(J4))
    sv = sp.events(team_id="valladolid", match_id=J4, types=["save"])
    assert sv and {e.player for e in sv} <= {"valladolid/hein", "valladolid/andre-ferreira"}


def test_pass_network_partido(sp):
    net = sp.pass_network("barcelona", match_id=J4)
    assert net.scope == J4 and len(net.nodes) == 11 and net.synthetic
    by = {n.player: n for n in net.nodes}
    assert by["barcelona/ter-stegen"].x < 20 and by["barcelona/lewandowski"].x > 60
    assert by["barcelona/lamine-yamal"].y < by["barcelona/raphinha"].y   # extremo derecho = y bajo
    assert all(e.a in by and e.b in by and e.count > 0 for e in net.edges)
    assert sum(e.count for e in net.edges) > 300


def test_connection(sp):
    c = sp.connection("barcelona/kounde", "barcelona/lamine-yamal", season="2024-25")
    assert c.a_to_b > 50 and c.b_to_a > 10 and 1 <= c.rank_for_a <= 5 and 0 < len(c.sample) <= 40
    assert all({e.player, e.receiver} == {c.a, c.b} for e in c.sample)
    p = sp.connection("barcelona/pedri", "barcelona/lamine-yamal", season="2024-25")
    assert p.key_passes >= 1


def test_rendimiento_con_la_base_caliente(sp):
    sp.player_season("barcelona/pedri", "2024-25", until=10)
    sp.team_season("barcelona", "2024-25", until=10)
    sp.pass_network("barcelona", season="2024-25", until=10)
    sp.connection("barcelona/pedri", "barcelona/lamine-yamal", season="2024-25", until=10)
    for f in (lambda: sp.player_season("barcelona/pedri", "2024-25", until=10),
              lambda: sp.team_season("real-madrid", "2024-25", until=10),
              lambda: sp.pass_network("barcelona", match_id=J4),
              lambda: sp.pass_network("barcelona", season="2024-25", until=10),
              lambda: sp.connection("barcelona/pedri", "barcelona/lamine-yamal", season="2024-25", until=10),
              lambda: sp.standings("2024-25", 10)):
        t = time.perf_counter()
        f()
        assert (time.perf_counter() - t) < 0.05


# ------------------------------------------------------------------ compuesto
def test_compuesto_con_y_sin_sqlite(tmp_path, of, sp):
    c = CompositeProvider(of, sp)
    assert c.available() and c.standings("2024-25") == of.standings("2024-25")
    assert c.h2h("barcelona", "valladolid") == of.h2h("barcelona", "valladolid")
    assert c.player_season("barcelona/pedri", "2024-25").synthetic
    vacio = CompositeProvider(db_path=tmp_path / "no.sqlite")
    assert not vacio.available() and vacio.synthetic
    assert len(vacio.matches("2024-25")) == 380 and vacio.standings("2024-25")[0].team == "barcelona"
    assert vacio.h2h("barcelona", "valladolid").played == 4 and len(vacio.teams("2024-25")) == 20
    assert any(p.id == "barcelona/pedri" for p in vacio.squad("barcelona", "2024-25"))
    with pytest.raises(SyntheticDataMissing):
        vacio.player_season("barcelona/pedri", "2024-25")
    with pytest.raises(SyntheticDataMissing):
        vacio.events(J4)
