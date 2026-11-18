import pytest
from pydantic import ValidationError

from copilot.graphics import payloads as P
from copilot.types import GraphicKind

TEAM = dict(id="barcelona", name="FC Barcelona", short="Barça", colors={"primary": "#A50044"}, crest="/api/img/crest/barcelona.svg")
SCOPE = dict(kind="season", label="LaLiga 2024-25 · hasta la J3", season="2024-25", until_round=3)


def test_every_graphic_kind_has_a_payload_model():
    assert set(P.PAYLOADS) == set(GraphicKind.__args__)


def test_graphic_payload_is_discriminated_by_kind():
    g = P.Graphic(id="g1", kind="standings", payload={"kind": "standings", "scope": SCOPE, "rows": []})
    assert isinstance(g.payload, P.Standings)
    with pytest.raises(ValidationError):
        P.Graphic(id="g2", kind="x", payload={"kind": "no_existe"})
    with pytest.raises(ValidationError):
        P.Graphic(id="g3", kind="h2h", payload={"kind": "h2h", "a": TEAM})


def test_schema_exports_both_directions():
    s = P.json_schema()
    assert {"ServerMsg", "OperatorAction", "PlayerCard", "HeatMap", "ConnectionG", "MatchState"} <= set(s["$defs"])
