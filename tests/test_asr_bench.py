"""Cálculo de NER-ER (S, D, I) y piezas del banco de voz con ejemplos a mano; sin motores ni modelos."""
import pytest

from eval.scripts import bench_asr as B


def m(i, t, typ="player"):
    return {"type": typ, "id": i, "t": t}


def row(rid, t0, t1, *ids):
    return {"id": rid, "t0": t0, "t1": t1, "entities": [{"type": "player", "id": i, "surface": i} for i in ids]}


def counts(rows, hyp):
    r = B.match_mentions(rows, hyp)
    return r["S"], r["D"], r["I"], r["N"]


def test_ner_perfect_match():
    rows = [row("r1", 10, 12, "barcelona/pedri"), row("r2", 20, 22, "barcelona/gavi")]
    hyp = [m("barcelona/pedri", 10.4), m("barcelona/gavi", 22.9)]  # 22.9 está a < 1,5 s del fin de r2
    assert counts(rows, hyp) == (0, 0, 0, 2) and B.ner_er(rows, hyp) == 0


def test_ner_substitution_deletion_insertion():
    rows = [row("r1", 10, 12, "a/pedri"), row("r2", 20, 22, "a/gavi"), row("r3", 30, 32, "a/balde"),
            row("r4", 40, 42)]
    hyp = [m("a/pedri", 11),      # acierto
           m("a/casado", 21),     # otro id en la fila de Gavi -> S
           m("v/hein", 41)]       # fila sin referencia -> I ; Balde sin pareja -> D
    assert counts(rows, hyp) == (1, 1, 1, 3)
    assert B.ner_er(rows, hyp) == pytest.approx(1.0)


def test_ner_counts_each_entity_once_per_row():
    # el oro lista a Pedri una vez aunque se le nombre tres veces: la hipótesis tampoco cuenta repeticiones
    rows = [row("r1", 10, 16, "a/pedri")]
    hyp = [m("a/pedri", 10.5), m("a/pedri", 12), m("a/pedri", 15)]
    assert counts(rows, hyp) == (0, 0, 0, 1)


def test_ner_extra_distinct_entity_in_row_is_insertion_and_outside_rows_ignored():
    rows = [row("r1", 10, 12, "a/pedri")]
    hyp = [m("a/pedri", 11), m("a/gavi", 11.5), m("a/balde", 50.0)]  # gavi: I ; balde fuera de toda fila: ignorado
    assert counts(rows, hyp) == (0, 0, 1, 1)


def test_row_assignment_slack_and_nearest():
    rows = [row("r1", 10, 12), row("r2", 13, 15)]
    assert B.row_for(11, rows)["id"] == "r1"
    assert B.row_for(12.7, rows)["id"] == "r2"   # más cerca de r2 (0,3) que de r1 (0,7)
    assert B.row_for(16.4, rows)["id"] == "r2" and B.row_for(16.6, rows) is None


def words(text, t=0.0, dt=0.3):
    return [{"w": w, "t0": t + i * dt, "t1": t + (i + 1) * dt} for i, w in enumerate(text.split())]


def test_hyp_mentions_exact_dictionary_longest_first():
    ms = B.hyp_mentions(words("gol de Lamine Yamal y pase de Pedri al Barça"))
    assert [x["id"] for x in ms] == ["barcelona/lamine-yamal", "barcelona/pedri", "barcelona"]


def test_hyp_mentions_does_not_use_asr_aliases_or_phonetics():
    ms = B.hyp_mentions(words("Alain Yamal con la pelota y Pedí por dentro"))
    ids = [x["id"] for x in ms]
    assert "barcelona/pedri" not in ids  # "Pedí" es un asr_alias: aquí NO cuenta
    assert ids == ["barcelona/lamine-yamal"]  # "Yamal" sí es alias exacto


def test_hyp_mentions_common_single_word_needs_capital():
    assert [x["id"] for x in B.hyp_mentions(words("el koke y Pedri"))] == ["barcelona/pedri"]  # "koke" es corriente
    assert [x["id"] for x in B.hyp_mentions(words("el Koke y Pedri"))] == ["valladolid/koke", "barcelona/pedri"]
    # motor que solo escribe minúsculas: no se exige mayúscula
    assert [x["id"] for x in B.hyp_mentions(words("el koke y pedri"))] == ["valladolid/koke", "barcelona/pedri"]


def test_norm_text_numbers_and_accents():
    assert B.norm_text("¡Gol! Tres-cero, Íñigo 2") == ["gol", "3", "0", "inigo", "2"]


def test_resolve_finals_prefers_second_pass():
    f1 = {"t0": 0.0, "t1": 2.0, "pass": 1, "words": []}
    f2 = {"t0": 0.1, "t1": 1.9, "pass": 2, "words": []}
    f3 = {"t0": 5.0, "t1": 6.0, "pass": 1, "words": []}  # sin corrección: se queda el rápido
    assert B.resolve_finals([f1, f2, f3]) == [f2, f3]
    assert B.resolve_finals([f1, f3]) == [f1, f3]


def test_run_returns_empty_without_cache(monkeypatch, tmp_path):
    monkeypatch.setattr(B, "HYP_DIR", tmp_path)
    assert B.run(split="dev", engine=object()) == {}


def test_run_picks_best_complete_cache(monkeypatch, tmp_path):
    import json
    monkeypatch.setattr(B, "HYP_DIR", tmp_path)
    def put(tag, ner, wer, complete=True):
        (tmp_path / f"{tag}.dev.json").write_text(json.dumps({
            "tag": tag, "complete": complete, "metrics": {"name_error": ner, "wer": wer, "name_error_linked": ner / 2,
                                                          "lat_first_p95_ms": 900, "lat_stable_p95_ms": 2000}}))
    put("a", 0.30, 0.2); put("b", 0.20, 0.25); put("c", 0.01, 0.01, complete=False)
    out = B.run(split="dev")
    assert out["asr.engine"] == "b" and out["asr.name_error"] == 0.20 and out["asr.word_latency_p95_ms"] == 900
