"""Pruebas del fichero de plantillas reales data/rosters/2024-25.json."""
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import pytest

from copilot.types import Player, Team

ROOT = Path(__file__).resolve().parent.parent
ROSTER = ROOT / "data" / "rosters" / "2024-25.json"
TRUTH = ROOT / "eval" / "gold" / "barca-valladolid.truth.json"

TEAM_IDS = {"alaves", "athletic", "atletico", "barcelona", "betis", "celta", "espanyol", "getafe", "girona",
            "las-palmas", "leganes", "mallorca", "osasuna", "rayo", "real-madrid", "real-sociedad", "sevilla",
            "valencia", "valladolid", "villarreal"}
LINE_OF = {"GK": "GK", "RB": "DEF", "CB": "DEF", "LB": "DEF", "DM": "MID", "CM": "MID", "AM": "MID",
           "RW": "FWD", "LW": "FWD", "ST": "FWD"}
ID_RE = re.compile(r"^[a-z-]+/[a-z0-9-]+$")

# ~300 palabras muy frecuentes del español (normalizadas): ninguna puede ser alias suelto de un jugador.
COMMON_ES = set("""
de la que el en y a los se del las un por con no una su para es al lo como mas pero sus le ya o este si porque esta entre
cuando muy sin sobre tambien me hasta hay donde quien desde todo nos durante todos uno les ni contra otros ese eso ante
ellos e esto mi antes algunos que unos yo otro otras otra el tanto esa estos mucho quienes nada muchos cual poco ella
estar estas algunas algo nosotros mi mis tu te ti tu tus ellas nosotras vosotros vosotras os mio mia mios mias tuyo
tuya suyo suya nuestro nuestra casa vida tiempo dia ano años cosa hombre mujer parte lugar vez forma caso mundo mano
ojo ojos cabeza pie pies lado fondo punto centro medio final inicio primero segundo tercero ultimo nuevo viejo grande
pequeno gran buen bueno malo mejor peor mayor menor alto bajo largo corto claro duro fuerte debil rapido lento facil
dificil libre lleno vacio blanco negro rojo verde azul amarillo rosa gris bravo cruz rey reina sol luna mar rio cielo
tierra fuego agua aire viento luz sombra paz guerra amor miedo suerte gracia ganas razon nombre numero hora minuto
semana mes noche tarde manana hoy ayer siempre nunca ahora luego despues antes aqui alli ahi asi bien mal mas menos
casi solo tan tanto cada ambos tres cuatro cinco seis siete ocho nueve diez cien mil torre campo balon pelota gol falta
penalti corner saque banda area tiro pase regate jugada partido equipo jugador campeon liga copa portero defensa
delantero lateral central extremo medio punta arbitro var tarjeta amarilla roja cambio lesion fuera dentro arriba
abajo derecha izquierda atras delante frente cerca lejos primera segunda parte mitad minuto prorroga empate victoria
derrota ataque contra remate cabezazo centro cabeza palo larguero red barrera muro mano pita pitar sacar tirar
pasar parar dejar poner hacer decir ver dar saber querer llegar pasar deber poder tener haber ser estar ir
torres garcia martin martinez pablo pedro juan jose luis carlos david daniel miguel angel antonio manuel marco
sanchez perez lopez gomez gonzalez rodriguez fernandez ruiz diaz alvarez moreno munoz alonso gutierrez navarro
dominguez vazquez ramos gil serrano molina morales suarez ortega delgado castro ortiz rubio marin sanz iglesias
nunez medina garrido cortes castillo santos lozano guerrero cano prieto mendez calvo gallego vidal leon marquez
herrera pena flores cabrera campos vega fuentes carrasco caballero reyes nieto aguilar pascual herrero montero
lorenzo hidalgo gimenez ibanez ferrer duran benitez mora vicente vargas arias crespo roman soto saez
velasco moya soler parra esteban gallardo rojas jimenez hernandez mateo marcos andres jorge sergio alex javi dani
hugo mario victor ivan oscar raul ruben diego nacho jon ander iker unai aitor lucas leo
""".split())


@pytest.fixture(scope="module")
def data():
    return json.loads(ROSTER.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def players(data):
    return [p for t in data["teams"] for p in t["players"]]


def test_loads_with_pydantic(data):
    assert data["season"] == "2024-25"
    for t in data["teams"]:
        extra = {"verified", "source", "players"}
        team = Team(**{k: v for k, v in t.items() if k not in extra})
        assert team.id == t["id"] and team.colors.get("primary", "").startswith("#")
        assert isinstance(t["verified"], bool) and t["source"]
        for p in t["players"]:
            pl = Player(**p)
            assert pl.team == team.id
            assert pl.id.startswith(team.id + "/")


def test_twenty_teams(data):
    assert {t["id"] for t in data["teams"]} == TEAM_IDS
    assert len(data["teams"]) == 20


def test_team_metadata(data):
    for t in data["teams"]:
        assert t["aliases"], t["id"]
        assert all(a == a.lower() and a.isascii() for a in t["aliases"]), t["id"]
        assert set(t["colors"]) >= {"primary", "secondary", "text"}
        assert all(re.fullmatch(r"#[0-9A-Fa-f]{6}", c) for c in t["colors"].values()), t["id"]


def test_min_players_and_goalkeepers(data):
    for t in data["teams"]:
        assert len(t["players"]) >= 20, (t["id"], len(t["players"]))
        assert sum(p["position"] == "GK" for p in t["players"]) >= 2, t["id"]


def test_ids_unique_and_well_formed(players):
    ids = [p["id"] for p in players]
    dup = [i for i, c in Counter(ids).items() if c > 1]
    assert not dup, dup
    bad = [i for i in ids if not ID_RE.match(i)]
    assert not bad, bad


def test_line_matches_position(players):
    for p in players:
        assert LINE_OF[p["position"]] == p["line"], p["id"]
        assert p["foot"] in {"L", "R", "B"}


def test_numbers_unique_within_team(data):
    for t in data["teams"]:
        nums = [p["number"] for p in t["players"] if p["number"] is not None]
        dup = [n for n, c in Counter(nums).items() if c > 1]
        assert not dup, (t["id"], dup)


def test_aliases_normalized_not_common_and_unique_in_team(data):
    for t in data["teams"]:
        owner: dict[str, str] = {}
        for p in t["players"]:
            assert p["aliases"], p["id"]
            for a in p["aliases"]:
                assert a == a.strip() and a == a.lower() and a.isascii(), (p["id"], a)
                assert a not in COMMON_ES, f"alias demasiado frecuente: {a!r} ({p['id']})"
                assert len(a) >= 3, (p["id"], a)
                assert owner.setdefault(a, p["id"]) == p["id"], f"alias {a!r} repetido: {owner[a]} y {p['id']}"


def test_asr_aliases_ported_from_legacy(data):
    by_id = {p["id"]: p for t in data["teams"] for p in t["players"]}
    assert {"alain", "la mine"} <= set(by_id["barcelona/lamine-yamal"]["asr_aliases"])
    assert "covarsi" in by_id["barcelona/cubarsi"]["asr_aliases"]
    assert "binicius" in by_id["real-madrid/vinicius"]["asr_aliases"]


def test_reference_match_ids_exist(players):
    ids = {p["id"] for p in players}
    nums = {p["id"]: p["number"] for p in players}
    truth = json.loads(TRUTH.read_text(encoding="utf-8"))
    must = set()
    for lu in truth["lineups"].values():
        for grp in ("starting", "bench"):
            for p in lu[grp]:
                must.add(p["id"])
                assert nums.get(p["id"]) == p["number"], (p["id"], nums.get(p["id"]), p["number"])
    for g in truth["goals"]:
        must.add(g["scorer"])
        if g.get("assist"):
            must.add(g["assist"])
    for s in truth["substitutions"]:
        must |= {s["in"], s["out"]}
    for c in truth["cards"]:
        must.add(c["player"])
    missing = sorted(must - ids)
    assert not missing, missing
    for must_id in ("valladolid/juanmi-latasa", "barcelona/sergi-dominguez", "barcelona/pablo-torre",
                    "valladolid/chuki", "valladolid/ozkacar"):
        assert must_id in ids
