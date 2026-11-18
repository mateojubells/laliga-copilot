"""Reproducibilidad, esquema y marcado como sintético."""
import hashlib
import sqlite3

from data.synth.generate import DEFAULT_SEED, generate


def events_hash(path) -> str:
    c = sqlite3.connect(str(path))
    h = hashlib.sha256()
    for row in c.execute("SELECT * FROM events ORDER BY id"):
        h.update(repr(row).encode())
    c.close()
    return h.hexdigest()


def test_reproducible_bit_a_bit(tmp_path):
    a = generate(DEFAULT_SEED, tmp_path / "a.sqlite", "4-5", verbose=False)
    b = generate(DEFAULT_SEED, tmp_path / "b.sqlite", "4-5", verbose=False)
    assert events_hash(a) == events_hash(b)
    c = generate(DEFAULT_SEED + 1, tmp_path / "c.sqlite", "4-5", verbose=False)
    assert events_hash(a) != events_hash(c)


def test_un_partido_no_depende_de_las_demas_jornadas(tmp_path):
    """Los eventos de un partido salen de default_rng([semilla, jornada, local, visitante])."""
    a = generate(DEFAULT_SEED, tmp_path / "a.sqlite", "4", verbose=False)
    b = generate(DEFAULT_SEED, tmp_path / "b.sqlite", "3-4", verbose=False)
    q = ("SELECT team, player, type, minute, added, second, x, y, outcome, xg FROM events "
         "WHERE match LIKE '2024-25/J04/%' ORDER BY t, team, player, type, x, y")
    qa = sqlite3.connect(str(a)).execute(q).fetchall()
    qb = sqlite3.connect(str(b)).execute(q).fetchall()
    assert len(qa) > 1000 and qa == qb


def test_meta_y_esquema(db):
    meta = dict(db.execute("SELECT key, value FROM meta"))
    assert meta["synthetic"] == "1" and meta["seed"] == str(DEFAULT_SEED)
    assert meta["version"] and meta["logical_date"] and "demostración" in meta["notice"]
    tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"meta", "matches", "lineups", "events", "players"} <= tables
    idx = " ".join(r[0] for r in db.execute("SELECT sql FROM sqlite_master WHERE type='index' AND sql IS NOT NULL"))
    for col in ("match", "player", "team", "type"):
        assert f"events({col}" in idx or f"events(match, type)" in idx or col in idx
    assert db.execute("SELECT COUNT(*) FROM matches").fetchone()[0] == 380


def test_volumen_y_tamano(db, db_path):
    n = db.execute("SELECT COUNT(*) FROM events").fetchone()[0]
    assert 400_000 <= n <= 550_000
    assert db_path.stat().st_size < 150e6


def test_tipos_de_evento(db):
    tipos = {r[0] for r in db.execute("SELECT DISTINCT type FROM events")}
    assert tipos == {"pass", "shot", "dribble", "recovery", "tackle", "interception", "clearance", "foul", "card",
                     "save", "sub"}
    assert db.execute("SELECT COUNT(*) FROM events WHERE x<0 OR x>105 OR y<0 OR y>68").fetchone()[0] == 0
