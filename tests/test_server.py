"""El servidor de extremo a extremo con frases simuladas (sin motor de voz)."""
import json

import pytest
from fastapi.testclient import TestClient

from copilot.server.app import app


@pytest.fixture()
def client():
    with TestClient(app) as c:
        if c.get("/api/health").json()["data"] != "ok":
            pytest.skip("faltan los datos sintéticos: make data")
        yield c


def drain(ws, want: str, limit: int = 30) -> dict:
    for _ in range(limit):
        m = json.loads(ws.receive_text())
        if m["type"] == want:
            return m
    raise AssertionError(f"no llegó {want}")


def test_goal_phrase_becomes_event_score_and_card(client):
    with client.websocket_connect("/ws?role=operator") as op, client.websocket_connect("/ws?role=program") as prog:
        assert drain(op, "hello")["state"]["home"]["id"] == "barcelona"
        drain(prog, "hello")
        op.send_text(json.dumps({"type": "say", "text": "gol de Lewandowski"}))
        ev = drain(op, "event")["event"]
        assert ev["type"] == "gol" and ev["roles"]["actor"] == "barcelona/lewandowski"
        assert drain(op, "state")["state"]["home_goals"] == 1
        g = drain(op, "graphic")["graphic"]
        assert g["kind"] == "player_card" and g["payload"]["player"]["id"] == "barcelona/lewandowski" and g["demo_data"]
        op.send_text(json.dumps({"type": "take", "graphic_id": g["id"]}))
        on_air = drain(prog, "program")["graphic"]
        assert on_air["id"] == g["id"] and on_air["state"] == "on_air"
        op.send_text(json.dumps({"type": "painted", "graphic_id": g["id"], "t_paint": on_air["ts"]["ws_send"] + 12}))
        op.send_text(json.dumps({"type": "clear_program"}))
        drain(prog, "program_clear")
    m = client.get("/api/metrics").json()
    assert m["score"]["barcelona"] == 1 and "paint" in m["latency"]


def test_operator_can_request_edit_and_discard(client):
    with client.websocket_connect("/ws") as op:
        drain(op, "hello")
        op.send_text(json.dumps({"type": "request", "request": {"kind": "connection", "subject": "barcelona/pedri", "other": "barcelona/lamine-yamal"}}))
        assert drain(op, "graphic")["graphic"]["kind"] == "connection"
        op.send_text(json.dumps({"type": "say", "text": "amarilla para Juric"}))
        ev = drain(op, "event")["event"]
        op.send_text(json.dumps({"type": "discard_event", "event_id": ev["id"]}))
        again = drain(op, "event")["event"]
        assert again["action"] == "reload" and again["events"][-1]["status"] == "discarded"
        op.send_text("esto no es json")
        assert drain(op, "status")["data"]["errors"] >= 1  # un mensaje roto no tira la conexión


def test_api_and_images(client):
    assert client.get("/api/graphic/standings").json()["kind"] == "standings"
    assert client.get("/api/graphic/no_existe").status_code == 404
    assert client.get("/api/img/crest/barcelona.svg").text.startswith("<svg")
    assert "19" in client.get("/api/img/player/barcelona/lamine-yamal.svg").text
    assert len(client.get("/api/roster").json()["players"]) > 40


def test_fast_path_on_partials_and_retraction(client):
    """Un parcial con un gol saca ya la tarjeta; si el final no lo confirma, se retira."""
    import asyncio

    from copilot.types import Transcript
    s = client.app.state.session
    s.auto_program = True

    def tr(text, final, seg):
        return Transcript(trace_id=f"t{seg}", engine="falso", final=final, text=text, t0=500.0, t1=503.0, segment_id=seg)

    async def run():
        early = await s.on_transcript(tr("gol de Ferran", False, 1))
        assert [g.kind for g in early] == ["player_card"] and s.ctx.score["barcelona"] == 1
        again = await s.on_transcript(tr("gol de Ferran Torres qué", False, 1))
        late = await s.on_transcript(tr("gol de Ferran Torres qué barbaridad", True, 1))
        assert again == [] and late == [] and s.ctx.score["barcelona"] == 1  # misma tarjeta, no se repite
        await s.on_transcript(tr("gol de Koundé", False, 2))
        assert s.ctx.score["barcelona"] == 2
        await s.on_transcript(tr("con el de Koundé se calienta el partido", True, 2))  # el final ya no dice "gol"
        assert s.ctx.score["barcelona"] == 1 and s.status.get("retracted") == 1
    asyncio.run(run())
