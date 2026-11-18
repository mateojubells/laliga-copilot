"""Estado del partido: deduplicación de goles y lógica de cambios (frases escritas para el test)."""
from copilot.nlu.engine import Engine
from eval.scripts.replay import make_context

M = "2024-25/J04/barcelona-valladolid"
B, V = "barcelona/", "valladolid/"


def play(lines):
    eng = Engine()
    eng.reset(match_id=M)
    ctx = make_context(M)
    t = 100.0
    for text in lines:
        t += 6
        ctx.ingest(eng.analyze(text, t0=t - 4, t1=t), t)
    return ctx


def subs(ctx):
    return sorted((e.roles["actor"], e.roles["out"]) for e in ctx.events if e.type == "cambio")


def test_goal_is_sung_many_times_but_counts_once():
    ctx = play(["gol gol gol", "gol de Lewandowski", "qué golazo de Lewandowski", "el Barça se adelanta"])
    goals = [e for e in ctx.events if e.type == "gol"]
    assert len(goals) == 1 and goals[0].roles["actor"] == B + "lewandowski" and ctx.score == {"barcelona": 1, "valladolid": 0}


def test_disallowed_goal_is_retracted():
    ctx = play(["gol de Raphinha", "gol anulado a Raphinha por fuera de juego"])
    assert ctx.score["barcelona"] == 0 and ctx.events[0].status == "discarded"


def test_simple_and_split_substitution():
    assert subs(play(["entra Ferran Torres por Lewandowski"])) == [(B + "ferran-torres", B + "lewandowski")]
    assert subs(play(["se retira Amallah", "y entra Chuki en su lugar"])) == [(V + "chuki", V + "amallah")]


def test_triple_change_is_paired_by_position():
    ctx = play(["triple cambio en el Barça entran Fermín, Eric García y Sergi Domínguez",
                "se marchan Pedri, Casadó y Cubarsí"])
    assert subs(ctx) == [(B + "eric-garcia", B + "casado"), (B + "fermin-lopez", B + "pedri"), (B + "sergi-dominguez", B + "cubarsi")]


def test_lineup_guards_against_false_substitutions():
    # Lamine ya está en el campo: "entra" es entrar al área; Ferran está en el banquillo: no puede "salir"
    assert subs(play(["entra Lamine Yamal en el área", "sale Ferran Torres"])) == []
    ctx = play(["entra Ferran Torres por Lewandowski", "entra Ferran Torres por Lewandowski otra vez"])
    assert len(subs(ctx)) == 1 and B + "ferran-torres" in ctx.on_pitch["barcelona"] and B + "lewandowski" not in ctx.on_pitch["barcelona"]


def test_recalling_a_goal_is_not_a_new_goal_but_a_sung_one_is():
    eng = Engine()
    eng.reset(match_id=M)
    ctx = make_context(M)

    def say(text, t):
        ctx.ingest(eng.analyze(text, t0=t - 3, t1=t), t)

    say("gol de Koundé", 100)
    say("el Barça marca gracias a Koundé que está de dulce", 400)   # recuerdo 5 min después: no cuenta
    assert ctx.score["barcelona"] == 1
    say("¡Gol, gol, gol de Koundé otra vez!", 520)                   # cantado: sí cuenta
    assert ctx.score["barcelona"] == 2
    say("gol de Lewandowski", 560)                                    # otro goleador: cuenta siempre
    assert ctx.score["barcelona"] == 3


def test_own_goal_counts_for_the_opponent():
    ctx = play(["gol en propia puerta de Javi Sánchez"])
    assert ctx.score == {"barcelona": 1, "valladolid": 0}
