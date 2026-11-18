"""Coherencia evento <-> agregado <-> marcador real."""
from collections import Counter

import pytest

from copilot.data.openfootball import OpenFootballProvider
from copilot.data.synthetic import SyntheticProvider


def test_goles_por_equipo_y_partido_igual_marcador_real(db):
    real = {m.id: (m.home_goals, m.away_goals) for m in OpenFootballProvider().matches("2024-25")}
    assert len(real) == 380
    goals = Counter()
    for match, team in db.execute("SELECT match, team FROM events WHERE type='shot' AND outcome='goal'"):
        goals[(match, team)] += 1
    teams = {r[0]: (r[1], r[2]) for r in db.execute("SELECT id, home, away FROM matches")}
    for mid, (hg, ag) in real.items():
        h, a = teams[mid]
        assert (goals[(mid, h)], goals[(mid, a)]) == (hg, ag), mid


def test_player_season_goles_y_asistencias_salen_de_eventos(db_path, db):
    p = SyntheticProvider(db_path)
    g = dict(db.execute("SELECT player, COUNT(*) FROM events WHERE type='shot' AND outcome='goal' GROUP BY player"))
    a = dict(db.execute("SELECT player, COUNT(*) FROM events WHERE type='pass' AND assist=1 GROUP BY player"))
    xg = dict(db.execute("SELECT player, SUM(xg) FROM events WHERE type='shot' GROUP BY player"))
    kp = dict(db.execute("SELECT player, COUNT(*) FROM events WHERE type='pass' AND key_pass=1 GROUP BY player"))
    for pid, in db.execute("SELECT id FROM players"):
        ps = p.player_season(pid, "2024-25")
        assert ps.stats["goals"].value == g.get(pid, 0), pid
        assert ps.stats["assists"].value == a.get(pid, 0), pid
        assert ps.stats["xg"].value == pytest.approx(xg.get(pid, 0.0), abs=0.01)
        assert ps.stats["key_passes"].value == kp.get(pid, 0)
    assert sum(g.values()) == 995 == sum(r[0] + r[1] for r in db.execute("SELECT home_goals, away_goals FROM matches"))


def test_xa_es_el_xg_del_disparo_enlazado(db_path, db):
    p = SyntheticProvider(db_path)
    xa = dict(db.execute("SELECT k.player, SUM(s.xg) FROM events s JOIN events k ON s.link = k.id "
                         "WHERE s.type='shot' AND k.key_pass=1 GROUP BY k.player"))
    for pid in list(xa)[:80]:
        assert p.player_season(pid, "2024-25").stats["xa"].value == pytest.approx(xa[pid], abs=0.01)


def test_cada_asistencia_es_el_pase_previo_a_un_gol_y_maximo_una_por_gol(db):
    # cada pase assist=1 es el 'link' de exactamente un disparo que es gol del receptor
    n_assist = db.execute("SELECT COUNT(*) FROM events WHERE assist=1").fetchone()[0]
    ok = db.execute("SELECT COUNT(*) FROM events s JOIN events k ON s.link=k.id WHERE s.type='shot' AND s.outcome='goal' "
                    "AND k.assist=1 AND k.receiver=s.player AND k.team=s.team AND k.match=s.match AND k.t<=s.t").fetchone()[0]
    assert n_assist == ok > 400
    dup = db.execute("SELECT COUNT(*) FROM (SELECT link FROM events WHERE link IS NOT NULL AND type='shot' "
                     "GROUP BY link HAVING COUNT(*)>1)").fetchone()[0]
    assert dup == 0
    # los pases clave que no son asistencia llevan a tiros que no son gol
    bad = db.execute("SELECT COUNT(*) FROM events s JOIN events k ON s.link=k.id WHERE s.type='shot' AND "
                     "k.assist=0 AND s.outcome='goal'").fetchone()[0]
    assert bad == 0
    # solo 'complete'
    assert db.execute("SELECT COUNT(*) FROM events WHERE (key_pass=1 OR assist=1) AND (type!='pass' OR outcome!='complete')").fetchone()[0] == 0


def test_nadie_actua_sin_estar_en_el_campo(db):
    # eventos propios del jugador (menos 'sub', que se trata aparte)
    bad = db.execute("""SELECT COUNT(*) FROM events e LEFT JOIN lineups l ON l.match=e.match AND l.player=e.player
        WHERE e.type!='sub' AND (l.player IS NULL OR l.t_on IS NULL OR e.t < l.t_on OR e.t > l.t_off OR l.team != e.team)""").fetchone()[0]
    assert bad == 0
    bad = db.execute("""SELECT COUNT(*) FROM events e JOIN lineups l ON l.match=e.match AND l.player=e.player
        WHERE e.type='sub' AND (e.t != l.t_on OR l.started=1)""").fetchone()[0]
    assert bad == 0
    # el que sale (detail) estaba en el campo y sale en ese instante
    bad = db.execute("""SELECT COUNT(*) FROM events e LEFT JOIN lineups l ON l.match=e.match AND l.player=e.detail
        WHERE e.type='sub' AND (l.player IS NULL OR l.t_off != e.t OR l.team != e.team)""").fetchone()[0]
    assert bad == 0


def test_receptores_son_companeros_en_el_campo(db):
    bad = db.execute("""SELECT COUNT(*) FROM events e LEFT JOIN lineups l ON l.match=e.match AND l.player=e.receiver
        WHERE e.type='pass' AND e.outcome='complete' AND
        (e.receiver IS NULL OR e.receiver=e.player OR l.player IS NULL OR l.team != e.team OR e.t < l.t_on OR e.t > l.t_off)""").fetchone()[0]
    assert bad == 0
    assert db.execute("SELECT COUNT(*) FROM events WHERE type='pass' AND outcome='incomplete' AND receiver IS NOT NULL").fetchone()[0] == 0
    # el que sufre la falta es del otro equipo y está en el campo
    bad = db.execute("""SELECT COUNT(*) FROM events e LEFT JOIN lineups l ON l.match=e.match AND l.player=e.receiver
        WHERE e.type='foul' AND (l.player IS NULL OR l.team = e.team OR e.t < l.t_on OR e.t > l.t_off)""").fetchone()[0]
    assert bad == 0


def test_porteros_parada_y_tiros_enlazados(db):
    # cada parada es de un portero y apunta a un tiro 'saved' del rival
    bad = db.execute("""SELECT COUNT(*) FROM events v JOIN events s ON v.link=s.id JOIN players p ON p.id=v.player
        WHERE v.type='save' AND (p.position!='GK' OR s.outcome!='saved' OR s.team=v.team OR s.match!=v.match)""").fetchone()[0]
    assert bad == 0
    n_saved = db.execute("SELECT COUNT(*) FROM events WHERE type='shot' AND outcome='saved'").fetchone()[0]
    assert n_saved == db.execute("SELECT COUNT(*) FROM events WHERE type='save'").fetchone()[0]


def test_cambios_y_minutos(db):
    rows = db.execute("""SELECT m.id, l.team, COUNT(*), SUM(l.minutes) FROM matches m JOIN lineups l ON l.match=m.id
        WHERE l.minutes>0 GROUP BY m.id, l.team""").fetchall()
    subs = {(r[0], r[1]): r[2] for r in db.execute("SELECT match, team, COUNT(*) FROM events WHERE type='sub' GROUP BY 1,2")}
    reds = {(r[0], r[1]) for r in db.execute("SELECT match, team FROM events WHERE type='card' AND detail='red'")}
    for mid, team, n, total in rows:
        k = subs.get((mid, team), 0)
        if (mid, team) not in reds:
            assert 3 <= k <= 5, (mid, team, k)
            assert total == 990, (mid, team, total)
            assert 11 <= n <= 11 + k
        else:
            assert total <= 990 and k <= 5
    assert db.execute("SELECT COUNT(*) FROM lineups WHERE started=1 AND slot='GK'").fetchone()[0] == 760


def test_un_portero_titular_y_formacion_coherente(db):
    for (m, t, n_gk, n) in db.execute("SELECT match, team, SUM(slot='GK'), COUNT(*) FROM lineups WHERE started=1 "
                                      "GROUP BY match, team"):
        assert n == 11 and n_gk == 1
    # el portero sale al campo con el dorsal de la plantilla real
    bad = db.execute("""SELECT COUNT(*) FROM lineups l JOIN players p ON p.id=l.player WHERE l.number IS NOT p.number""").fetchone()[0]
    assert bad == 0
    # defensa/medio/ataque por formación: 4 DEF (RB,CB,CB,LB), 1 GK
    for (m, t, d) in db.execute("SELECT match, team, SUM(slot IN ('RB','CB','LB')) FROM lineups WHERE started=1 GROUP BY 1,2"):
        assert d == 4
