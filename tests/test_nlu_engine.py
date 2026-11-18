"""Comportamientos del motor que no deben romperse (frases escritas para el test, no sacadas del oro)."""
import pytest

from copilot.nlu.engine import Engine

M = "2024-25/J04/barcelona-valladolid"
B, V = "barcelona/", "valladolid/"


@pytest.fixture()
def eng():
    e = Engine()
    e.reset(match_id=M)
    return e


def keys(res):
    return sorted((e.type, e.modality, e.roles.get("actor") or e.roles.get("team_for"), e.target()) for e in res.events)


def ents(res):
    return {e.id for e in res.entities}


def test_roles_by_preposition(eng):
    assert keys(eng.analyze("falta de Araujo sobre Raúl Moro")) == [("falta", "real", B + "araujo", V + "raul-moro")]
    assert keys(eng.analyze("penalti para el Barça")) == [("penalti", "real", "barcelona", None)]
    assert keys(eng.analyze("amarilla para Juric")) == [("amarilla", "real", V + "juric", None)]


def test_substitution_is_one_event(eng):
    assert keys(eng.analyze("entra Fermín por Pedri")) == [("cambio", "real", B + "fermin-lopez", B + "pedri")]
    assert keys(eng.analyze("sale Amallah y entra Chuki")) == [("cambio", "real", V + "chuki", V + "amallah")]


def test_chain_with_relative_clause(eng):
    r = eng.analyze("Casadó abre para Koundé que se va de Lucas Rosa y la pone")
    assert keys(r) == [("centro", "real", B + "kounde", None), ("pase", "real", B + "casado", B + "kounde"),
                       ("regate", "real", B + "kounde", V + "lucas-rosa")]
    assert len({e.chain for e in r.events}) == 1 and [e.order for e in r.events] == [1, 2, 3]


def test_modality(eng):
    assert keys(eng.analyze("no es penalti sobre Raphinha"))[0][1] == "negated"
    assert keys(eng.analyze("si marca Ferran se acaba esto"))[0][1] == "hypothetical"
    assert keys(eng.analyze("¿cuántos goles lleva Lewandowski?")) == [("gol", "query", B + "lewandowski", None)]
    assert keys(eng.analyze("el año pasado Gavi vio la roja"))[0][1] == "past"


def test_misheard_names(eng):
    assert ents(eng.analyze("la tiene valde por la izquierda")) == {B + "balde"}
    assert ents(eng.analyze("gol de Levandoski")) == {B + "lewandowski"}
    assert B + "lamine-yamal" in ents(eng.analyze("qué bueno es la min jamal"))


def test_known_false_positives(eng):
    for t in ("hace falta más ritmo", "faltan cinco minutos", "al segundo palo no llega nadie", "muchas gracias a todos por venir"):
        r = eng.analyze(t)
        assert not r.events and not r.entities, t


def test_partials_do_not_change_context(eng):
    eng.analyze("la tiene Pedri", final=False)
    assert eng.recent == []
    eng.analyze("la tiene Pedri", t1=10.0)
    assert keys(eng.analyze("y dispara", t1=12.0)) == [("tiro", "real", B + "pedri", None)]


def test_without_match_only_exact_names():
    e = Engine()
    e.reset()
    assert ents(e.analyze("Mbappé recibe de Bellingham")) == {"real-madrid/mbappe", "real-madrid/bellingham"}


def test_fast(eng):
    r = eng.analyze("Pedri abre a la banda para Lamine que se va de su par y la pone al segundo palo donde remata Lewandowski")
    assert r.ts["nlu_ms"] < 50


def test_nobody_passes_to_themselves(eng):
    r = eng.analyze("Balón para Pau Cubarsí, que juega en banda derecha para Lamine Yamal")
    for e in r.events:
        a = e.roles.get("actor")
        assert a is None or a not in (e.roles.get("receiver"), e.roles.get("victim"), e.roles.get("out"))
