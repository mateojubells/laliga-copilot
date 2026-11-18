"""El Barcelona-Valladolid de la J4 respeta eval/gold/barca-valladolid.truth.json."""
import json
from pathlib import Path

import pytest

from data.synth import lineups as L

TRUTH = json.loads((Path(__file__).resolve().parents[2] / "eval" / "gold" / "barca-valladolid.truth.json").read_text())
MID = TRUTH["match"]


def test_id_y_marcador(db):
    row = db.execute("SELECT home, away, home_goals, away_goals, ht_home, ht_away, added1 FROM matches WHERE id=?",
                     (MID,)).fetchone()
    assert MID == "2024-25/J04/barcelona-valladolid"
    assert row[:6] == ("barcelona", "valladolid", 7, 0, 3, 0)


def test_goles_minutos_goleadores_y_asistentes(db):
    rows = db.execute("SELECT id, team, player, minute, added, link FROM events WHERE match=? AND type='shot' "
                      "AND outcome='goal' ORDER BY t", (MID,)).fetchall()
    assert len(rows) == len(TRUTH["goals"]) == 7
    for r, g in zip(rows, TRUTH["goals"]):
        assert (r[1], r[2], r[3], r[4]) == (g["team"], g["scorer"], g["minute"], g["added"])
        if g["assist"]:
            a = db.execute("SELECT player, receiver, assist, key_pass, outcome FROM events WHERE id=?",
                           (r[5],)).fetchone()
            assert a == (g["assist"], g["scorer"], 1, 1, "complete")
        else:
            assert r[5] is None, "gol sin asistente en truth.json"
    assert db.execute("SELECT COUNT(*) FROM events WHERE match=? AND type='shot' AND outcome='goal' AND team='valladolid'",
                      (MID,)).fetchone()[0] == 0
    # ninguna asistencia extra en el partido
    assert db.execute("SELECT COUNT(*) FROM events WHERE match=? AND assist=1", (MID,)).fetchone()[0] == 6


def test_alineaciones(db):
    for team, lu in TRUTH["lineups"].items():
        starters = {r[0]: r[1] for r in db.execute("SELECT player, slot FROM lineups WHERE match=? AND team=? AND started=1",
                                                   (MID, team))}
        assert starters == {s["id"]: s["position"] for s in lu["starting"]} or \
            set(starters) == {s["id"] for s in lu["starting"]}
        for s in lu["starting"]:
            assert starters[s["id"]] == s["position"]
        bench = {r[0] for r in db.execute("SELECT player FROM lineups WHERE match=? AND team=? AND started=0", (MID, team))}
        assert {b["id"] for b in lu["bench"]} <= bench
        f = db.execute("SELECT formation_home FROM matches WHERE id=?" if team == "barcelona" else
                       "SELECT formation_away FROM matches WHERE id=?", (MID,)).fetchone()[0]
        assert f == lu["formation"]


def test_cambios(db):
    got = db.execute("SELECT team, minute, added, player, detail FROM events WHERE match=? AND type='sub' ORDER BY t, player",
                     (MID,)).fetchall()
    exp = sorted(((s["team"], s["minute"], 0, s["in"], s["out"]) for s in TRUTH["substitutions"]),
                 key=lambda r: (r[1], r[3]))
    assert len(got) == len(exp) == 10
    assert sorted(got, key=lambda r: (r[1], r[3])) == exp
    # minutos jugados coherentes con los cambios
    mins = dict(db.execute("SELECT player, minutes FROM lineups WHERE match=?", (MID,)))
    for s in TRUTH["substitutions"]:
        assert mins[s["out"]] == s["minute"]
        assert mins[s["in"]] == 90 - s["minute"]


def test_amarillas(db):
    got = db.execute("SELECT team, player, minute FROM events WHERE match=? AND type='card' ORDER BY t", (MID,)).fetchall()
    assert got == [(c["team"], c["player"], c["minute"]) for c in TRUTH["cards"]]
    assert {r[0] for r in db.execute("SELECT detail FROM events WHERE match=? AND type='card'", (MID,))} == {"yellow"}


def test_dominio_del_barcelona(db):
    passes = dict(db.execute("SELECT team, COUNT(*) FROM events WHERE match=? AND type='pass' GROUP BY team", (MID,)))
    shots = dict(db.execute("SELECT team, COUNT(*) FROM events WHERE match=? AND type='shot' GROUP BY team", (MID,)))
    assert passes["barcelona"] > 1.8 * passes["valladolid"]
    assert shots["barcelona"] >= 20 and shots["valladolid"] <= 6
