"""Preparación de partido y controles de directo (docs/LIVE_READINESS.md)."""
import asyncio
import json

import numpy as np
import pytest
from fastapi.testclient import TestClient

from copilot import seasons
from copilot.graphics import payloads as P
from copilot.server.app import app
from copilot.server.session import Session

M = "2024-25/J05/athletic-barcelona"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(seasons, "MATCHES", tmp_path / "matches")  # las alineaciones de prueba no tocan data/
    with TestClient(app) as c:
        yield c


def lineup_cfg(c, match=M, auto=False):
    lp = c.get(f"/api/lineup?match={match}").json()
    return {"season": "2024-25", "match": match, "lineups": lp["teams"], "voice": "none", "auto_program": auto}


def drain(ws, want, limit=40):
    for _ in range(limit):
        m = json.loads(ws.receive_text())
        if m["type"] == want:
            return m
    raise AssertionError(want)


def test_menu_lists_seasons_matches_and_lineups(client):
    ss = client.get("/api/seasons").json()
    assert any(s["season"] == "2024-25" and s["teams"] == 20 for s in ss)
    ms = client.get("/api/matches?season=2024-25").json()
    assert len(ms) == 380 and ms[0]["round"] == 1 and ms[0]["home"]["crest"].endswith(".svg")
    lp = client.get(f"/api/lineup?match={M}").json()
    assert lp["source"] == "proposed" and set(lp["teams"]) == {"athletic", "barcelona"}
    for team in lp["teams"].values():
        assert len(team["starting"]) == 11
    assert client.get("/api/matches?season=1999-00").status_code == 404


def test_start_match_without_restart_and_validation(client):
    assert client.get("/api/session").json()["config"] is None
    cfg = lineup_cfg(client)
    bad = json.loads(json.dumps(cfg))
    bad["lineups"]["athletic"]["starting"] = bad["lineups"]["athletic"]["starting"][:10]
    r = client.post("/api/session", json=bad)
    assert r.status_code == 400 and "11 titulares" in r.json()["detail"]
    info = client.post("/api/session", json=cfg).json()
    assert info["config"]["match"] == M and info["home"]["id"] == "athletic" and info["score"] == {"athletic": 0, "barcelona": 0}
    assert seasons.lineup_path(M).exists()  # la alineación confirmada queda guardada para la próxima vez
    assert client.get(f"/api/lineup?match={M}").json()["source"] == "saved"
    with client.websocket_connect("/ws") as op:
        assert drain(op, "hello")["state"]["home"]["id"] == "athletic"
        op.send_text(json.dumps({"type": "say", "text": "gol de Nico Williams"}))
        ev = drain(op, "event")["event"]
        assert ev["roles"]["actor"] == "athletic/nico-williams"
    assert client.delete("/api/session").json()["config"] is None


def test_clock_score_and_panic(client):
    client.post("/api/session", json=lineup_cfg(client, auto=True))
    with client.websocket_connect("/ws") as op:
        drain(op, "hello")
        op.send_text(json.dumps({"type": "clock", "value": "kickoff"}))
        st = drain(op, "state")["state"]
        assert st["period"] == 1 and st["clock_running"] and st["clock_base_s"] < 2
        op.send_text(json.dumps({"type": "clock", "value": "set_minute", "event": {"minute": 30, "second": 0}}))
        st = drain(op, "state")["state"]
        assert 1799 < st["clock_base_s"] < 1802 and st["minute"] == 31
        op.send_text(json.dumps({"type": "say", "text": "gol de Lewandowski"}))
        ev = drain(op, "event")["event"]
        assert ev["minute"] == 31 and ev["period"] == 1
        assert drain(op, "state")["state"]["away_goals"] == 1  # el gol actualiza el marcador
        op.send_text(json.dumps({"type": "clock", "value": "half_time"}))
        st = drain(op, "state")["state"]
        assert not st["clock_running"] and st["period"] == 1
        op.send_text(json.dumps({"type": "clock", "value": "second_half"}))
        st = drain(op, "state")["state"]
        assert st["period"] == 2 and st["clock_running"] and 2699 < st["clock_base_s"] < 2702
        op.send_text(json.dumps({"type": "set_score", "event": {"home": 2, "away": 0}}))
        st = drain(op, "state")["state"]
        assert (st["home_goals"], st["away_goals"]) == (2, 0)
        op.send_text(json.dumps({"type": "panic"}))
        assert drain(op, "program_clear")
        assert drain(op, "status")["data"]["auto_program"] is False


def test_session_survives_a_restart(tmp_path, monkeypatch):
    monkeypatch.setattr(seasons, "SESSIONS", tmp_path / "sessions")
    monkeypatch.setattr(seasons, "MATCHES", tmp_path / "matches")
    from copilot.server import setup as S
    lp = S.lineup("2024-25", M)
    s1 = Session(persist=True)
    s1.configure(P.SessionConfig(season="2024-25", match=M, lineups=lp.teams, voice="none"))

    async def play():
        await s1.clock("kickoff", {})
        await s1.clock("set_minute", {"minute": 12})
        await s1.set_score(1, 1)
    asyncio.run(play())
    s2 = Session(persist=True)
    assert s2.restore() and s2.resumed
    assert s2.ctx.score == {"athletic": 1, "barcelona": 1} and len(s2.ctx.events) == 2
    st = s2.state()
    assert st.clock_running and 719 < st.clock_base_s < 730 and st.home.id == "athletic"
    s2.end()
    assert s2.config is None and not (seasons.SESSIONS / "current.json").exists()
    assert len(list((seasons.SESSIONS / "archive").glob("*.json"))) == 1


def test_mic_level_and_queue_only_when_voice_is_on():
    s = Session()
    tone = (np.sin(np.arange(1600) / 16000 * 2 * np.pi * 440) * 8000).astype(np.int16).tobytes()
    s.mic_feed(tone)
    assert s.status["mic_level"] > 0.3 and s._mic_q.empty()
    s.status["voice"] = "on"
    s.mic_feed(tone)
    assert s._mic_q.qsize() == 1
