"""Las métricas tienen que poder fallar: estas pruebas fijan su comportamiento con casos a mano."""
from eval import metrics as M
from copilot.types import EVENT_TYPES, NluEvent

P, L, R = "barcelona/pedri", "barcelona/lamine-yamal", "barcelona/raphinha"


def ev(type, actor=None, modality="real", chain=None, order=0, **roles):
    r = dict(roles)
    if actor:
        r["actor"] = actor
    return {"type": type, "modality": modality, "roles": r, "chain": chain, "order": order}


def test_entities_f1_counts_misses_and_false_alarms():
    gold = [{"entities": [{"type": "player", "id": P}, {"type": "player", "id": L}], "events": []}]
    pred = [{"entities": [{"type": "player", "id": P}, {"type": "player", "id": R}], "events": []}]
    s = M.score(gold, pred)["entities"]
    assert (s["tp"], s["fp"], s["fn"]) == (1, 1, 1) and s["f1"] == 0.5


def test_empty_prediction_scores_zero_not_one():
    gold = [{"entities": [{"type": "player", "id": P}], "events": [ev("gol", P)]}]
    s = M.score(gold, [{"entities": [], "events": []}])
    assert s["entities"]["f1"] == 0 and s["events"]["f1"] == 0


def test_wrong_role_or_modality_is_an_error():
    gold = [{"entities": [], "events": [ev("pase", P, receiver=L)]}]
    assert M.score(gold, [{"entities": [], "events": [ev("pase", L, receiver=P)]}])["events"]["f1"] == 0
    assert M.score(gold, [{"entities": [], "events": [ev("pase", P)]}])["events"]["f1"] == 0
    gold = [{"entities": [], "events": [ev("penalti", modality="negated")]}]
    s = M.score(gold, [{"entities": [], "events": [ev("penalti")]}])["events"]
    assert (s["tp"], s["fp"], s["fn"]) == (0, 1, 1)


def test_target_role_priority_and_sub():
    assert M.event_key(ev("cambio", R, out=L)) == ("cambio", "real", R, L)
    assert M.event_key(ev("falta", P, victim=L)) == ("falta", "real", P, L)
    assert NluEvent(type="cambio", fine="cambio", roles={"actor": R, "out": L}).key() == ("cambio", "real", R, L)


def test_chain_needs_exact_sequence_one_to_one():
    g = [ev("pase", P, receiver=L, chain="c1", order=1), ev("regate", L, chain="c1", order=2),
         ev("centro", L, chain="c1", order=3)]
    gold = [{"entities": [], "events": g}]
    ok = M.score(gold, [{"entities": [], "events": g}])["chains"]
    assert (ok["ok"], ok["total"], ok["pct"], ok["precision"]) == (1, 1, 100.0, 1.0)
    renamed = [dict(e, chain="zz") for e in g]
    assert M.score(gold, [{"entities": [], "events": renamed}])["chains"]["ok"] == 1
    wrong_order = [dict(g[0], order=2), dict(g[1], order=1), g[2]]
    assert M.score(gold, [{"entities": [], "events": wrong_order}])["chains"]["ok"] == 0
    split = [g[0], dict(g[1], chain="c2"), dict(g[2], chain="c2")]
    assert M.score(gold, [{"entities": [], "events": split}])["chains"]["ok"] == 0
    assert M.score(gold, [{"entities": [], "events": g[:2]}])["chains"]["ok"] == 0
    unchained = [dict(e, chain=None) for e in g]
    assert M.score(gold, [{"entities": [], "events": unchained}])["chains"]["ok"] == 0
    same_order = [dict(e, order=0) for e in g]
    assert M.score(gold, [{"entities": [], "events": same_order}])["chains"]["ok"] == 0


def test_chain_cannot_be_inflated_by_one_big_chain():
    a = [ev("pase", P, receiver=L, chain="c1", order=1), ev("regate", L, chain="c1", order=2)]
    b = [ev("centro", L, receiver=R, chain="c2", order=1), ev("gol", R, chain="c2", order=2)]
    gold = [{"entities": [], "events": a + b}]
    merged = [dict(e, chain="x", order=i) for i, e in enumerate(a + b)]
    s = M.score(gold, [{"entities": [], "events": merged}])["chains"]
    assert (s["ok"], s["total"], s["precision"]) == (0, 2, 0.0)
    extra = a + b + [ev("falta", P, chain="c3", order=1), ev("amarilla", P, chain="c3", order=2)]
    s = M.score(gold, [{"entities": [], "events": extra}])["chains"]
    assert s["ok"] == 2 and round(s["precision"], 2) == 0.67


def test_duplicates_are_a_multiset_and_team_for_counts():
    gold = [{"entities": [], "events": [ev("falta", P), ev("falta", P)]}]
    s = M.score(gold, [{"entities": [], "events": [ev("falta", P)]}])["events"]
    assert (s["tp"], s["fp"], s["fn"]) == (1, 0, 1)
    gold = [{"entities": [], "events": [ev("penalti", team_for="barcelona")]}]
    assert M.score(gold, [{"entities": [], "events": [ev("penalti", team_for="valladolid")]}])["events"]["f1"] == 0
    assert M.score(gold, [{"entities": [], "events": [ev("penalti", team_for="barcelona")]}])["events"]["f1"] == 1


def test_event_types_are_unique():
    assert len(set(EVENT_TYPES)) == len(EVENT_TYPES) == 27
