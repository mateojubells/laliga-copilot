"""Servidor de LaLiga Copilot: API + WebSocket + frontend compilado. `make dev` lo arranca."""
from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from copilot.config import ROOT, settings
from copilot.data.images import GeneratedImages
from copilot.graphics import payloads as P
from copilot.server.session import Session

DIST = ROOT / "web" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    persist = bool(settings().get("sessions", {}).get("persist", True))
    app.state.session = Session(persist=persist)
    app.state.session.restore()  # si el servidor se reinició a mitad de partido, el partido sigue
    app.state.images = GeneratedImages()
    yield
    s = app.state.session
    if s.replay_task:
        s.replay_task.cancel()


app = FastAPI(title="LaLiga Copilot", lifespan=lifespan)


@app.get("/api/health")
def health():
    s: Session = app.state.session
    return {"ok": True, "data": s.status["data"], "asr": s.status["asr"], "errors": s.status["errors"]}


# ---------------------------------------------------------------------- menú principal
@app.get("/api/seasons")
def api_seasons():
    from copilot.server import setup as S
    s: Session = app.state.session
    return [x.model_dump() for x in S.season_list(s.season)]


@app.get("/api/matches")
def api_matches(season: str):
    from copilot import seasons
    from copilot.data.composite import CompositeProvider
    from copilot.server import setup as S
    if season not in seasons.installed():
        raise HTTPException(404, f"La temporada {season} no está instalada")
    try:
        prov = CompositeProvider(season=season)  # type: ignore[call-arg]
    except TypeError:
        prov = CompositeProvider()
    return [m.model_dump() for m in S.match_list(season, prov)]


@app.get("/api/lineup")
def api_lineup(match: str):
    from copilot import seasons
    from copilot.server import setup as S
    season = seasons.season_of(match)
    if season not in seasons.installed():
        raise HTTPException(404, f"La temporada {season} no está instalada")
    try:
        return S.lineup(season, match).model_dump()
    except S.LineupError as e:
        raise HTTPException(400, str(e))


@app.get("/api/session")
def api_session_get():
    return app.state.session.info().model_dump()


@app.post("/api/session")
async def api_session_post(cfg: P.SessionConfig = Body(...)):
    from copilot.server import setup as S
    s: Session = app.state.session
    try:
        s.configure(cfg)
    except S.LineupError as e:
        raise HTTPException(400, str(e))
    await s.broadcast("hello", data={"role": "operator", "auto_program": s.auto_program, "status": s.status, "reload": True},
                      state=s.state())
    await s.clear_program()
    await s.broadcast("status", data=s.status)
    return s.info().model_dump()


@app.delete("/api/session")
async def api_session_delete():
    s: Session = app.state.session
    s.end()
    await s.clear_program()
    await s.broadcast("status", data=s.status)
    return s.info().model_dump()


@app.get("/api/metrics")
def metrics():
    return app.state.session.snapshot()


@app.get("/api/state")
def state():
    s: Session = app.state.session
    return {"state": s.state().model_dump(), "events": [e.model_dump() for e in s.ctx.events],
            "graphics": [g.model_dump() for g in list(s.graphics.values())[-30:]],
            "program": s.program.model_dump() if s.program else None, "transcripts": s.transcripts[-100:],
            "replay": s.status.get("replay"), "now_audio": s.now_audio}


@app.get("/api/roster")
def roster():
    s: Session = app.state.session
    b = s.builder
    return {"teams": [b.team(t).model_dump() for t in (s.ctx.home, s.ctx.away)],
            "players": [b.player(p).model_dump() for p, t in s.ctx.team_of.items()]}


@app.get("/api/graphic/{kind}")
def graphic(kind: str, subject: str | None = None, other: str | None = None, event_type: str | None = None):
    """Grafismo a la carta (lo usa la galería con datos reales del proveedor)."""
    from copilot.graphics.selector import GraphicRequest
    if kind not in P.PAYLOADS:
        raise HTTPException(404, "grafismo desconocido")
    try:
        return app.state.session.builder.graphic(GraphicRequest(kind, subject, other, event_type=event_type)).model_dump()
    except (KeyError, TypeError) as e:
        raise HTTPException(400, f"faltan datos para {kind}: {e}")


@app.get("/api/img/crest/{team_id}.svg")
def crest(team_id: str):
    return Response(app.state.images.team_crest(team_id), media_type="image/svg+xml", headers={"Cache-Control": "max-age=86400"})


@app.get("/api/img/player/{team_id}/{slug}.svg")
def avatar(team_id: str, slug: str):
    return Response(app.state.images.player_avatar(f"{team_id}/{slug}"), media_type="image/svg+xml",
                    headers={"Cache-Control": "max-age=86400"})


@app.get("/api/replay/audio")
def replay_audio():
    f = ROOT / settings().get("replay", {}).get("audio", "")
    if not f.is_file():
        raise HTTPException(404, "no hay audio de repetición en esta máquina")
    return FileResponse(f, media_type="audio/mpeg")


@app.websocket("/ws")
async def ws(sock: WebSocket, role: str = "operator"):
    s: Session = app.state.session
    await sock.accept()
    s.clients[sock] = "program" if role == "program" else "operator"
    s.status["program_clients"] = sum(r == "program" for r in s.clients.values())
    await s.send(sock, "hello", data={"role": s.clients[sock], "auto_program": s.auto_program, "status": s.status},
                 state=s.state())
    await s.broadcast("status", roles=("operator",), data=s.status)
    if s.program:
        await s.send(sock, "program", graphic=s.program)
    try:
        while True:
            raw = await sock.receive_text()
            try:
                await s.on_action(sock, P.OperatorAction.model_validate_json(raw))
            except Exception as e:
                s.status["errors"] += 1
                s.status["last_error"] = f"{type(e).__name__}: {e}"
                await s.send(sock, "status", data=s.status)
    except (WebSocketDisconnect, RuntimeError):  # el cliente cerró (también a mitad de un envío)
        pass
    finally:
        s.clients.pop(sock, None)
        s.status["program_clients"] = sum(r == "program" for r in s.clients.values())
        await s.broadcast("status", roles=("operator",), data=s.status)


@app.websocket("/ws/audio")
async def ws_audio(sock: WebSocket):
    """Audio del micro del operador: PCM16 little-endian, 16 kHz, mono, en bloques de ~100 ms."""
    s: Session = app.state.session
    await sock.accept()
    last = 0.0
    try:
        while True:
            msg = await sock.receive()
            if msg.get("type") == "websocket.disconnect":
                break
            data = msg.get("bytes")
            if data:
                s.mic_feed(data)
                import time as _t
                if _t.monotonic() - last > 0.25:  # el medidor del operador se refresca 4 veces por segundo
                    last = _t.monotonic()
                    await s.broadcast("status", roles=("operator",), data=s.status)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        s.status["mic_level"] = 0.0


if DIST.is_dir():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}")
    def spa(path: str):
        f = DIST / path
        return FileResponse(f if path and f.is_file() else DIST / "index.html")
