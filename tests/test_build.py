"""Cada tipo de grafismo se construye con datos reales del proveedor y cumple su contrato."""
import time

import pytest

from copilot.data.composite import CompositeProvider
from copilot.graphics import payloads as P
from copilot.graphics.build import Builder
from copilot.graphics.selector import GraphicRequest
from eval.scripts.replay import make_context

M = "2024-25/J04/barcelona-valladolid"
PED, LAM, LEW, HEIN = "barcelona/pedri", "barcelona/lamine-yamal", "barcelona/lewandowski", "valladolid/hein"


@pytest.fixture(scope="module")
def b():
    prov = CompositeProvider()
    if not prov.available():
        pytest.skip("faltan los datos sintéticos: make data")
    return Builder(prov, make_context(M))


@pytest.mark.parametrize("req", [
    GraphicRequest("player_card", LEW, event_type="gol"), GraphicRequest("player_card", HEIN), GraphicRequest("team_card", "valladolid"),
    GraphicRequest("pass_network", "barcelona"), GraphicRequest("pass_network", PED, LAM), GraphicRequest("connection", PED, LAM),
    GraphicRequest("shot_map", LEW), GraphicRequest("shot_map", "barcelona"), GraphicRequest("heat_map", LAM),
    GraphicRequest("comparison", "barcelona/ferran-torres", LEW, event_type="cambio"), GraphicRequest("comparison", "barcelona", "valladolid"),
    GraphicRequest("standings"), GraphicRequest("h2h"), GraphicRequest("situation", PED, event_type="falta", role="victim"),
    GraphicRequest("situation", "barcelona", event_type="corner"), GraphicRequest("timeline"), GraphicRequest("scorebug"),
], ids=lambda r: f"{r.kind}:{r.subject}")
def test_every_kind_builds_and_validates(b, req):
    t = time.perf_counter()
    g = b.graphic(req)
    ms = (time.perf_counter() - t) * 1000
    assert isinstance(g.payload, P.PAYLOADS[req.kind])
    P.Graphic.model_validate(g.model_dump())
    assert ms < 400, f"{req.kind} tarda {ms:.0f} ms"


def test_data_respects_the_cut_before_the_match(b):
    card = b.player_card("barcelona/raphinha", "gol")
    goals = next(s for s in card.stats if s.key == "goals")
    before = b.p.player_season("barcelona/raphinha", "2024-25", until=M).stats["goals"].value
    whole = b.p.player_season("barcelona/raphinha", "2024-25").stats["goals"].value
    assert goals.value == before and whole >= before + 3  # su triplete es de la J4: aún no cuenta
    assert card.scope.label.endswith("hasta la J3")
    assert all(r.played == 3 for r in b.standings().rows)


def test_network_has_eleven_and_a_highlighted_pair(b):
    net = b.pass_network("barcelona", (PED, LAM))
    assert len(net.nodes) == 11 and sum(n.highlight for n in net.nodes) <= 2
    assert all(e.count >= net.min_passes for e in net.edges) and len(net.edges) <= 30


def test_heat_grid_is_normalised(b):
    h = b.heat_map(LAM)
    assert len(h.grid) == h.cols * h.rows and max(h.grid) == 1.0 and min(h.grid) >= 0
    assert abs(sum(z.value for z in h.zones[:3]) - 100) < 1.5


def test_demo_badge_only_on_synthetic_data(b):
    assert b.graphic(GraphicRequest("player_card", PED)).demo_data is True
    assert b.graphic(GraphicRequest("standings")).demo_data is False
