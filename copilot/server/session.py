"""Sesión de partido: une NLU, estado, selector y constructores, y reparte por WebSocket (docs/ARCHITECTURE.md §1, §9)."""
from __future__ import annotations

import asyncio
import datetime as dt
import itertools
import json
import queue
import threading
import time
from pathlib import Path
from typing import Any, Optional

from copilot import seasons
from copilot.config import ROOT, settings
from copilot.graphics import payloads as P
from copilot.graphics.build import Builder
from copilot.graphics.selector import GraphicRequest, Selector
from copilot.obs.latency import LatencyBook, now_ms
from copilot.types import Transcript


#: hechos que en modo automático se confirman solos (son los mismos que salen a antena sin operador)
SELF_CONFIRMED = {"gol", "cambio", "amarilla", "roja", "penalti"}


class Session:
    def __init__(self, cfg: Optional[dict] = None, provider: Any = None, engine: Any = None, persist: bool = False):
        from copilot.data.composite import CompositeProvider
        from copilot.nlu.engine import Engine
        from eval.scripts.replay import make_context  # misma construcción de contexto que el banco

        self.cfg = cfg or settings()
        self.match_id: str = self.cfg["match"]
        self.season: str = seasons.season_of(self.match_id)
        self.provider = provider or CompositeProvider()
        self.engine = engine or Engine()
        self.engine.reset(match_id=self.match_id)
        self.ctx = make_context(self.match_id)
        self.selector = Selector(self.ctx)
        self.builder = Builder(self.provider, self.ctx, self.season)
        # partido preparado en el menú principal (None = aún no se ha preparado ninguno; el servidor arranca igualmente
        # con el partido de la configuración para que la demo y los tests funcionen)
        self.config: Optional[P.SessionConfig] = None
        self.started_epoch = time.time()  # base de tiempo de la sesión en directo (sobrevive a reinicios)
        self.resumed = False
        self.persist = persist
        self._mic_q: "queue.Queue[Optional[bytes]]" = queue.Queue(maxsize=600)
        self._mic_t = 0.0
        self.latency = LatencyBook()
        self.auto_program: bool = bool(self.cfg.get("graphics", {}).get("auto_program", False))
        self.clients: dict[Any, str] = {}  # websocket -> rol
        self.graphics: dict[str, P.Graphic] = {}
        self.program: Optional[P.Graphic] = None
        self.status: dict[str, Any] = {"asr": "inactivo", "data": "ok" if self.provider.available() else "sin datos sintéticos",
                                       "replay": None, "errors": 0, "voice": "off", "mic_level": 0.0,
                                       "program_clients": 0, "session": False}
        self._trace = itertools.count(1)
        self.now_audio = 0.0
        self.replay_task: Optional[asyncio.Task] = None
        import threading
        self._voice_stop = threading.Event()
        self._ttl_task: Optional[asyncio.Task] = None
        self._spec: dict[int, set[str]] = {}  # segmento de voz -> eventos adelantados con parciales
        self.transcripts: list[dict] = []  # últimos finales, para recargar el operador

    # ------------------------------------------------------------------ difusión
    async def send(self, ws: Any, type_: str, **fields) -> None:
        msg = P.ServerMsg(type=type_, server_now=now_ms(), **fields)  # type: ignore[arg-type]
        try:
            await ws.send_text(msg.model_dump_json(exclude_none=True))
        except Exception:
            self.clients.pop(ws, None)

    async def broadcast(self, type_: str, roles: tuple[str, ...] = ("operator", "program"), **fields) -> None:
        await asyncio.gather(*(self.send(ws, type_, **fields) for ws, role in list(self.clients.items()) if role in roles))

    def tnow(self) -> float:
        """Tiempo de la sesión: el del audio en una repetición; si no, segundos desde que empezó el partido."""
        if self.status.get("replay"):
            return self.now_audio
        return time.time() - self.started_epoch

    def state(self) -> P.MatchState:
        t = self.tnow()
        c = self.ctx.clock
        base = self.builder.match_state(t)
        on = {k: sorted(v) for k, v in self.ctx.on_pitch.items()}
        return base.model_copy(update={"clock_running": c.running(t), "clock_base_s": round(c.seconds(t), 2),
                                       "clock_at_ms": now_ms(), "added": c.added, "on_pitch": on,
                                       "period": c.period(t), "minute": c.minute(t)})

    async def push_state(self) -> None:
        await self.broadcast("state", state=self.state())
        self.save()

    # ------------------------------------------------------------------ tubería
    async def on_transcript(self, tr: Transcript) -> list[P.Graphic]:
        """ASR → NLU → partido → selector → grafismos. Nunca lanza: un fallo se cuenta y se sigue."""
        self.now_audio = max(self.now_audio, tr.t1)
        await self.broadcast("transcript", roles=("operator",), transcript=tr.model_dump())
        if not tr.text.strip():
            return []
        if not tr.final:
            return await self._on_partial(tr)
        self.transcripts = self.transcripts[-199:] + [{"t0": tr.t0, "t1": tr.t1, "text": tr.text, "engine": tr.engine}]
        out: list[P.Graphic] = []
        try:
            ts = dict(tr.ts)
            ts.setdefault("asr_emit", now_ms())
            res = self.engine.analyze(tr.text, t0=tr.t0, t1=tr.t1, final=True)
            res.trace_id = tr.trace_id
            ts["nlu_out"] = now_ms()
            changes = self.ctx.ingest(res, tr.t1)
            reqs = self.selector.on_result(res, changes, tr.t1)
            await self._settle_partials(tr, res)
            for action, me in changes:
                # sin operador (modo automático) el sistema da por confirmados los hechos que saca solo a antena;
                # con operador, los confirma él. La timeline de programa solo enseña lo confirmado.
                if self.auto_program and action != "retract" and me.status == "auto" and me.type in SELF_CONFIRMED \
                        and me.roles.get("actor"):
                    me.status = "approved"
                await self.broadcast("event", roles=("operator",), event={**me.model_dump(), "action": action})
            if any(me.type == "gol" for _, me in changes):
                await self.push_state()
            elif changes:
                self.save()
            for req in sorted(reqs, key=lambda r: r.priority):  # la más importante llega la última: queda arriba y seleccionada
                g = self.builder.graphic(req, ts={**ts, "select_out": now_ms()})
                out.append(g)
                await self.publish(g, auto=req.auto)
        except Exception as e:  # un grafismo roto no puede parar la emisión
            self.status["errors"] += 1
            self.status["last_error"] = f"{type(e).__name__}: {e}"
            await self.broadcast("status", roles=("operator",), data=self.status)
        return out

    # ------------------------------------------------------------------ ruta rápida (parciales)
    async def _on_partial(self, tr: Transcript) -> list[P.Graphic]:
        """La frase aún no ha terminado, pero un gol o una petición de dato no esperan: se actúa ya y, si el final
        no lo confirma, se retira (y cuenta como tarjeta errónea)."""
        out: list[P.Graphic] = []
        try:
            ts = dict(tr.ts)
            ts.setdefault("asr_emit", now_ms())
            res = self.engine.analyze(tr.text, t0=tr.t0, t1=tr.t1, final=False)  # no toca el contexto del motor
            res.trace_id = tr.trace_id
            # con un parcial solo se adelantan goles: un cambio adelantado movería la alineación y no se puede deshacer
            res.events = [e for e in res.events if e.type == "gol" and e.modality == "real"]
            ts["nlu_out"] = now_ms()
            changes = self.ctx.ingest(res, tr.t1)
            spec = self._spec.setdefault(tr.segment_id, set())
            spec |= {me.id for action, me in changes if action == "new"}
            for action, me in changes:
                await self.broadcast("event", roles=("operator",), event={**me.model_dump(), "action": action})
            if any(me.type == "gol" for _, me in changes):
                await self.push_state()
            for req in self.selector.on_result(res, changes, tr.t1, partial=True):
                g = self.builder.graphic(req, ts={**ts, "select_out": now_ms(), "partial": 1.0})
                out.append(g)
                await self.publish(g, auto=req.auto)
        except Exception as e:
            self.status["errors"] += 1
            self.status["last_error"] = f"{type(e).__name__}: {e}"
        return out

    async def _settle_partials(self, tr: Transcript, res: Any) -> None:
        """Al cerrar la frase: lo que se adelantó con un parcial y el final no sostiene, se retira."""
        spec = self._spec.pop(tr.segment_id, set())
        # segmentos que el motor nunca cerró (cambió de numeración): se liquidan contra este final si son recientes
        for seg in [k for k in self._spec if k < tr.segment_id]:
            spec |= self._spec.pop(seg)
        if not spec:
            return
        kept = {(e.type, e.roles.get("actor")) for e in res.events if e.modality == "real"}
        kept_types = {t for t, _ in kept}

        def sustained(ev) -> bool:  # mismo tipo y, si el final nombra autor, el mismo autor
            a = ev.roles.get("actor")
            return (ev.type, a) in kept or (ev.type in kept_types and (a is None or (ev.type, None) in kept))

        for ev in list(self.ctx.events):
            if ev.id in spec and ev.status == "auto" and not sustained(ev):
                self.selector.forget(ev)
                self.ctx.edit(ev.id, status="discarded")
                self.status["retracted"] = self.status.get("retracted", 0) + 1
                await self.broadcast("event", roles=("operator",), event={**ev.model_dump(), "action": "retract"})
                for gid, g in list(self.graphics.items()):
                    if g.reason.get("event_id") == ev.id:
                        g.state = "retracted"
                        self.graphics.pop(gid, None)
                        await self.broadcast("graphic_hide", roles=("operator",), graphic_id=gid)
                        if self.program is not None and self.program.id == gid:
                            await self.clear_program()
                await self.push_state()

    async def publish(self, g: P.Graphic, auto: bool = False) -> None:
        self.graphics[g.id] = g
        if len(self.graphics) > 200:
            self.graphics.pop(next(iter(self.graphics)))
        g.ts["ws_send"] = now_ms()
        await self.broadcast("graphic", roles=("operator",), graphic=g)
        if auto and self.auto_program:
            await self.take(g.id, manual=False)

    async def take(self, gid: str, manual: bool = True) -> None:
        """A programa. Si lo decide el operador, su tiempo de decisión no es latencia del sistema: se marca `manual`
        y la latencia de extremo a extremo solo se mide en las salidas automáticas."""
        g = self.graphics.get(gid)
        if not g:
            return
        g.state = "on_air"
        g.ts["take"] = now_ms()
        if manual:
            g.ts["manual"] = 1.0
        else:
            g.ts["ws_send"] = g.ts["take"]
        g.ts.pop("t_paint", None)
        self.program = g
        await self.broadcast("program", graphic=g)
        if self._ttl_task and not self._ttl_task.done():
            self._ttl_task.cancel()
        self._ttl_task = asyncio.create_task(self._expire(g.id, g.ttl_ms / 1000))

    async def _expire(self, gid: str, seconds: float) -> None:
        """El servidor retira lo vencido (una recarga de OBS no debe resucitar un grafismo)."""
        await asyncio.sleep(seconds)
        while self.program is not None and self.program.id == gid and self.program.pinned:
            await asyncio.sleep(1.0)
        if self.program is not None and self.program.id == gid:
            await self.clear_program()

    async def clear_program(self) -> None:
        self.program = None
        await self.broadcast("program_clear")

    # ------------------------------------------------------------------ operador
    async def on_action(self, ws: Any, a: P.OperatorAction) -> None:
        t = a.type
        if t == "ping":
            await self.send(ws, "hello", data={"client_now": a.client_now})
        elif t == "painted" and a.graphic_id in self.graphics and a.t_paint:
            g = self.graphics[a.graphic_id]
            if "t_paint" not in g.ts:
                g.ts["t_paint"] = a.t_paint
                if g.ts.get("manual"):
                    self.latency.add("paint", a.t_paint - g.ts.get("take", a.t_paint))
                else:
                    self.latency.add_trace(g.ts)
        elif t in ("approve", "take") and a.graphic_id:
            await self.take(a.graphic_id)
        elif t == "clear_program":
            await self.clear_program()
        elif t == "discard" and a.graphic_id:
            if self.program and self.program.id == a.graphic_id:
                await self.clear_program()
            self.graphics.pop(a.graphic_id, None)
            await self.broadcast("graphic_hide", roles=("operator",), graphic_id=a.graphic_id)
        elif t in ("pin", "unpin") and a.graphic_id in self.graphics:
            self.graphics[a.graphic_id].pinned = t == "pin"
            await self.broadcast("graphic", roles=("operator",), graphic=self.graphics[a.graphic_id])
            if self.program is not None and self.program.id == a.graphic_id:
                await self.broadcast("program", graphic=self.program)
        elif t == "request" and a.request:
            r = a.request
            req = GraphicRequest(r["kind"], r.get("subject"), r.get("other"), event_type=r.get("event_type"), priority=90,
                                 ttl_ms=int(r.get("ttl_ms", 15000)), trigger="operator", t=self.now_audio)
            await self.publish(self.builder.graphic(req, ts={"select_out": now_ms()}))
        elif t == "say" and a.text:
            n = next(self._trace)
            t1 = self.tnow()
            await self.on_transcript(Transcript(trace_id=f"say-{n}", engine="simulado", final=True, text=a.text, t0=t1 - 0.5,
                                                t1=t1, ts={"audio_end": now_ms(), "asr_emit": now_ms()}))
        elif t == "set_auto":
            self.auto_program = bool(a.value)
            await self.broadcast("status", roles=("operator",), data={**self.status, "auto_program": self.auto_program})
        elif t == "discard_event" and a.event_id:
            self.ctx.edit(a.event_id, status="discarded")
            await self._events_changed()
        elif t == "edit_event" and a.event_id and a.event:
            self.ctx.edit(a.event_id, **{k: v for k, v in a.event.items() if k in ("type", "roles", "minute", "team", "status")})
            await self._events_changed()
        elif t == "add_event" and a.event:
            tn = self.tnow()
            self.ctx.add(t_audio=tn, minute=self.ctx.clock.minute(tn), period=self.ctx.clock.period(tn),
                         **{k: v for k, v in a.event.items() if k in ("type", "roles", "team", "text")})
            await self._events_changed()
        elif t == "replay_control":
            await self.replay_control(str(a.value or "stop"), a.event or {})
        elif t == "clock":
            await self.clock(str(a.value or ""), a.event or {})
        elif t == "panic":
            self.auto_program = False
            await self.clear_program()
            await self.broadcast("status", roles=("operator",), data={**self.status, "auto_program": False, "panic": now_ms()})
        elif t == "set_score" and a.event:
            await self.set_score(int(a.event.get("home", 0)), int(a.event.get("away", 0)))
        elif t == "voice":
            await (self.voice_start() if a.value == "start" else self.voice_stop())

    # ------------------------------------------------------------------ reloj y marcador
    async def clock(self, cmd: str, ev: dict) -> None:
        """Pitido inicial, descanso, segunda parte, final, ajuste de minuto y descuento (docs/LIVE_READINESS.md §2.3)."""
        c, t = self.ctx.clock, self.tnow()
        if cmd == "kickoff":
            c.kickoff, c.first_half_end, c.second_half, c.full_time, c.added = t, None, None, None, None
        elif cmd == "half_time" and c.period(t) == 1:
            c.first_half_end, c.added = t, None
        elif cmd == "second_half" and c.kickoff is not None:
            if c.first_half_end is None:
                c.first_half_end = t
            c.second_half, c.added = t, None
        elif cmd == "full_time" and c.kickoff is not None:
            c.full_time, c.added = t, None
        elif cmd == "set_minute":
            target = 60 * float(ev.get("minute", 0)) + float(ev.get("second", 0))
            if c.period(t) == 2 or (c.second_half is not None and target >= 2700):
                c.second_half = t - max(0.0, target - 2700)
            else:
                c.kickoff = t - target
                if c.first_half_end is not None and not c.halftime(t):
                    c.first_half_end = None
        elif cmd == "set_added":
            c.added = int(ev.get("minutes", 0)) or None
        else:
            return
        await self.push_state()

    async def set_score(self, home: int, away: int) -> None:
        """Cuadra el marcador a mano: añade goles de operador o descarta los últimos goles del equipo."""
        tn = self.tnow()
        for team, want in ((self.ctx.home, max(0, home)), (self.ctx.away, max(0, away))):
            have = self.ctx.score.get(team, 0)
            while have < want:
                self.ctx.add(t_audio=tn, minute=self.ctx.clock.minute(tn), period=self.ctx.clock.period(tn), type="gol",
                             roles={"team_for": team}, team=team, text="Marcador corregido por el operador")
                have += 1
            goals = [e for e in self.ctx.events if e.type == "gol" and e.team == team and e.status != "discarded"]
            while have > want and goals:
                self.ctx.edit(goals.pop().id, status="discarded")
                have -= 1
        await self._events_changed()

    async def _events_changed(self) -> None:
        await self.broadcast("event", roles=("operator",), event={"action": "reload", "events": [e.model_dump() for e in self.ctx.events]})
        await self.push_state()

    # ------------------------------------------------------------------ repetición
    async def replay_control(self, cmd: str, opts: dict) -> None:
        if self.replay_task and not self.replay_task.done():
            self.replay_task.cancel()
        self.status["replay"] = None
        self._voice_stop.set()
        if cmd == "start":
            start, speed, until = float(opts.get("from", 0.0)), float(opts.get("speed", 1.0)), opts.get("until")
            if opts.get("mode") == "voz":
                self.replay_task = asyncio.create_task(self._replay_voice(start, until))
            else:
                self.replay_task = asyncio.create_task(self._replay(start, speed, until))
        await self.broadcast("status", roles=("operator",), data=self.status)

    def _replay_source(self) -> tuple[list[dict], dict]:
        from eval.scripts import replay as R
        ref, meta = R.load_reference()
        return R.utterances(ref, meta["first_half_end"]), meta

    async def _replay(self, start: float, speed: float, until: Optional[float]) -> None:
        """Repetición desde la transcripción cacheada: cada enunciado se emite cuando termina de decirse."""
        from copilot.match.context import Clock
        utts, meta = self._replay_source()
        self.ctx.clock = Clock(meta["kickoff"], meta["second_half_start"], meta["first_half_end"], meta["full_time"])
        self.status["replay"] = {"mode": "transcripción", "speed": speed, "from": start}
        loop = asyncio.get_event_loop()
        t_wall0 = loop.time()
        await self.broadcast("status", data={**self.status, "replay_started": {"audio_t": start, "speed": speed}})
        await self.push_state()
        for n, u in enumerate(utts):
            if u["t1"] < start:
                continue
            if until is not None and u["t0"] > until:
                break
            delay = (u["t1"] - start) / speed - (loop.time() - t_wall0)
            if delay > 0:
                await asyncio.sleep(delay)
            # sin motor de voz en este modo: audio_end = instante en que la frase termina en la repetición
            await self.on_transcript(Transcript(trace_id=f"rp-{n}", engine="referencia", final=True, text=u["text"], t0=u["t0"],
                                                t1=u["t1"], ts={"audio_end": now_ms(), "asr_emit": now_ms()}))
            if n % 20 == 0:
                await self.push_state()
        self.status["replay"] = None
        await self.broadcast("status", roles=("operator",), data=self.status)

    async def _replay_voice(self, start: float, until: Optional[float]) -> None:
        """Repetición con el motor de voz EN VIVO: el WAV se entrega a velocidad real como si fuera el micro.
        El motor corre en su propio hilo (su feed bloquea). Si no carga, se cae a la transcripción guardada."""
        import threading

        from copilot.match.context import Clock
        _, meta = self._replay_source()
        self.ctx.clock = Clock(meta["kickoff"], meta["second_half_start"], meta["first_half_end"], meta["full_time"])
        loop = asyncio.get_event_loop()
        stop = self._voice_stop = threading.Event()
        cfg = self.cfg.get("asr", {})
        ready: asyncio.Future = loop.create_future()

        def emit(tr: Transcript) -> None:
            tr.ts.setdefault("asr_emit", now_ms())
            asyncio.run_coroutine_threadsafe(self.on_transcript(tr), loop)

        def work() -> None:
            try:
                from copilot.asr import factory, streaming, vocab
                primary = factory.create(cfg.get("engine", "mlx-whisper-small"), **(cfg.get("options") or {}))
                try:
                    engine = factory.AsrSupervisor(primary, factory.create(cfg["fallback"])) if cfg.get("fallback") else primary
                except Exception:
                    engine = primary  # sin respaldo disponible en esta máquina
                prompt, vocabulary = vocab.build(self.match_id)
                engine.start(prompt=prompt, vocabulary=vocabulary, language=cfg.get("language", "es"))
                self.status["asr"] = engine.name
                audio = streaming.read_wav(ROOT / "eval" / "asr" / meta.get("wav", "barca-valladolid.16k.wav"), start, until)
                loop.call_soon_threadsafe(ready.set_result, True)
                for pcm, t_audio in streaming.iter_blocks(audio, start, block_ms=100, speed=1.0):
                    if stop.is_set():
                        break
                    for tr in engine.feed(pcm, t_audio):
                        emit(tr)
                    if getattr(engine, "switched", False) and self.status.get("asr") != engine.name:
                        self.status["asr"] = f"{engine.name} (respaldo)"
                if not stop.is_set():
                    for tr in engine.flush():
                        emit(tr)
                engine.close()
            except Exception as e:
                self.status["errors"] += 1
                self.status["last_error"] = f"voz: {type(e).__name__}: {e}"
                if not ready.done():
                    loop.call_soon_threadsafe(ready.set_result, False)
            finally:
                self.status["asr"] = "inactivo" if not str(self.status.get("asr", "")).startswith("error") else self.status["asr"]

        threading.Thread(target=work, name="asr", daemon=True).start()
        ok = await ready
        if not ok:
            self.status["asr"] = "error: se usa la transcripción guardada"
            await self.broadcast("status", roles=("operator",), data=self.status)
            return await self._replay(start, 1.0, until)
        self.status["replay"] = {"mode": "voz en vivo", "speed": 1.0, "from": start}
        await self.broadcast("status", data={**self.status, "replay_started": {"audio_t": start, "speed": 1.0}})
        await self.push_state()
        while not stop.is_set() and self.status.get("asr") not in ("inactivo", None):
            await asyncio.sleep(1.0)
        self.status["replay"] = None
        await self.broadcast("status", roles=("operator",), data=self.status)

    # ------------------------------------------------------------------ micrófono en directo
    def mic_feed(self, pcm16: bytes) -> None:
        """Llega un bloque del micro (PCM16 16 kHz mono) desde el WebSocket /ws/audio."""
        import numpy as np
        x = np.frombuffer(pcm16, dtype=np.int16)
        if len(x):
            rms = float(np.sqrt(np.mean((x.astype(np.float32) / 32768.0) ** 2)))
            self.status["mic_level"] = round(min(1.0, rms * 4), 3)
        if self.status.get("voice") in ("on", "starting"):
            try:
                self._mic_q.put_nowait(pcm16)
            except queue.Full:  # el motor va retrasado: se descarta lo más antiguo para no acumular retraso
                try:
                    self._mic_q.get_nowait()
                    self._mic_q.put_nowait(pcm16)
                except queue.Empty:
                    pass

    async def voice_start(self) -> None:
        if self.status.get("voice") in ("on", "starting"):
            return
        if self.replay_task and not self.replay_task.done():
            await self.replay_control("stop", {})
        self.status["voice"] = "starting"
        self.status["asr"] = "cargando el motor de voz…"
        await self.broadcast("status", roles=("operator",), data=self.status)
        while not self._mic_q.empty():
            self._mic_q.get_nowait()
        self._mic_t = self.tnow()
        loop = asyncio.get_event_loop()
        stop = self._voice_stop = threading.Event()
        cfg = self.cfg.get("asr", {})

        def emit(tr: Transcript) -> None:
            tr.ts.setdefault("asr_emit", now_ms())
            asyncio.run_coroutine_threadsafe(self.on_transcript(tr), loop)

        def status() -> None:
            asyncio.run_coroutine_threadsafe(self.broadcast("status", roles=("operator",), data=self.status), loop)

        def work() -> None:
            from copilot.asr import factory, vocab
            from copilot.asr.base import SAMPLE_RATE
            try:
                primary = factory.create(cfg.get("engine", "mlx-whisper-small"), **(cfg.get("options") or {}))
                try:
                    engine = factory.AsrSupervisor(primary, factory.create(cfg["fallback"])) if cfg.get("fallback") else primary
                except Exception:
                    engine = primary
                prompt, vocabulary = vocab.build(self.match_id)
                engine.start(prompt=prompt, vocabulary=vocabulary, language=cfg.get("language", "es"))
                self.status["voice"], self.status["asr"] = "on", engine.name
                status()
                t_audio = self._mic_t
                while not stop.is_set():
                    try:
                        pcm = self._mic_q.get(timeout=0.5)
                    except queue.Empty:
                        continue
                    if pcm is None:
                        break
                    for tr in engine.feed(pcm, t_audio):
                        emit(tr)
                    t_audio += len(pcm) / 2 / SAMPLE_RATE
                    if getattr(engine, "switched", False) and "respaldo" not in str(self.status.get("asr")):
                        self.status["asr"] = f"{engine.name} (respaldo)"
                        status()
                for tr in engine.flush():
                    emit(tr)
                engine.close()
                self.status["voice"], self.status["asr"] = "off", "inactivo"
            except Exception as e:
                self.status["errors"] += 1
                self.status["voice"] = "error"
                self.status["asr"] = f"error del motor de voz: {type(e).__name__}"
                self.status["last_error"] = f"voz: {type(e).__name__}: {e}"
            status()

        threading.Thread(target=work, name="asr-mic", daemon=True).start()

    async def voice_stop(self) -> None:
        self._voice_stop.set()
        try:
            self._mic_q.put_nowait(None)
        except queue.Full:
            pass
        if self.status.get("voice") in ("on", "starting"):
            self.status["voice"] = "off"
        await self.broadcast("status", roles=("operator",), data=self.status)

    # ------------------------------------------------------------------ menú principal y persistencia
    def configure(self, cfg: P.SessionConfig, *, started_epoch: Optional[float] = None) -> None:
        """Prepara un partido sin reiniciar el servidor: motor de comprensión, estado, selector y datos nuevos."""
        from copilot.data.composite import CompositeProvider
        from copilot.nlu import engine as nlu_engine
        from copilot.nlu.engine import Engine
        from copilot.server import setup as S
        from eval.scripts.replay import make_context
        S.validate(cfg)
        S.save_lineup(cfg)
        nlu_engine._GAZ.clear()  # la alineación del partido ha cambiado: el diccionario de nombres se reconstruye
        if hasattr(nlu_engine, "clear_caches"):
            nlu_engine.clear_caches()
        self._voice_stop.set()
        if self.replay_task and not self.replay_task.done():
            self.replay_task.cancel()
        self.config = cfg
        self.match_id, self.season = cfg.match, cfg.season
        try:
            self.provider = CompositeProvider(season=cfg.season)  # type: ignore[call-arg]
        except TypeError:
            self.provider = CompositeProvider()
        self.engine = Engine()
        self.engine.reset(match_id=self.match_id)
        self.ctx = make_context(self.match_id)
        self.selector = Selector(self.ctx)
        self.builder = Builder(self.provider, self.ctx, self.season)
        self.auto_program = cfg.auto_program
        self.graphics, self.program, self.transcripts, self._spec = {}, None, [], {}
        self.now_audio = 0.0
        self.started_epoch = started_epoch or time.time()
        self.resumed = False
        self.status.update({"session": True, "replay": None, "voice": "off", "asr": "inactivo",
                            "data": "ok" if self.provider.available() else "sin estadísticas de demostración"})
        self.save()

    def info(self) -> P.SessionInfo:
        if self.config is None:
            return P.SessionInfo()
        return P.SessionInfo(config=self.config, resumed=self.resumed,
                             started_at=dt.datetime.fromtimestamp(self.started_epoch).isoformat(timespec="seconds"),
                             home=self.builder.team(self.ctx.home), away=self.builder.team(self.ctx.away),
                             events=len(self.ctx.events), score=dict(self.ctx.score))

    def _dump(self) -> dict:
        c = self.ctx.clock
        return {"version": 1, "config": self.config.model_dump() if self.config else None, "started_epoch": self.started_epoch,
                "saved_at": time.time(), "auto_program": self.auto_program,
                "clock": {"kickoff": c.kickoff, "first_half_end": c.first_half_end, "second_half": c.second_half,
                          "full_time": c.full_time, "added": c.added},
                "events": [e.model_dump() for e in self.ctx.events], "n": self.ctx._n,
                "on_pitch": {k: sorted(v) for k, v in self.ctx.on_pitch.items()},
                "bench": {k: sorted(v) for k, v in self.ctx.bench.items()}, "transcripts": self.transcripts[-200:]}

    def save(self) -> None:
        """Todo cambio del partido se guarda en disco: si el servidor se reinicia, el partido sigue (§2.2)."""
        if not self.persist or self.config is None:
            return
        try:
            seasons.SESSIONS.mkdir(parents=True, exist_ok=True)
            tmp = seasons.SESSIONS / "current.json.tmp"
            tmp.write_text(json.dumps(self._dump(), ensure_ascii=False), encoding="utf-8")
            tmp.replace(seasons.SESSIONS / "current.json")
        except OSError as e:
            self.status["last_error"] = f"no se pudo guardar la sesión: {e}"

    def restore(self) -> bool:
        f = seasons.SESSIONS / "current.json"
        if not self.persist or not f.exists():
            return False
        from copilot.match.context import Clock
        from copilot.types import MatchEvent
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            self.configure(P.SessionConfig.model_validate(d["config"]), started_epoch=d["started_epoch"])
        except Exception as e:
            self.status["last_error"] = f"no se pudo restaurar la sesión guardada: {e}"
            return False
        self.auto_program = d.get("auto_program", False)
        self.ctx.clock = Clock(**d["clock"])
        self.ctx.events = [MatchEvent.model_validate(e) for e in d["events"]]
        self.ctx._n = d.get("n", len(self.ctx.events))
        self.ctx._recount()
        self.ctx.on_pitch = {k: set(v) for k, v in d.get("on_pitch", {}).items()}
        self.ctx.bench = {k: set(v) for k, v in d.get("bench", {}).items()}
        self.transcripts = d.get("transcripts", [])
        self.resumed = True
        return True

    def end(self) -> None:
        """Termina el partido: archiva el registro y vuelve al estado sin partido preparado."""
        self._voice_stop.set()
        f = seasons.SESSIONS / "current.json"
        if self.config is not None and self.persist:
            self.save()
            arch = seasons.SESSIONS / "archive"
            arch.mkdir(parents=True, exist_ok=True)
            stamp = dt.datetime.now().strftime("%Y%m%d-%H%M%S")
            if f.exists():
                f.replace(arch / f"{self.match_id.replace('/', '-')}-{stamp}.json")
        self.config = None
        self.status["session"] = False

    def snapshot(self) -> dict:
        return {"match": self.match_id, "score": self.ctx.score, "events": len(self.ctx.events), "graphics": len(self.graphics),
                "program": self.program.id if self.program else None, "auto_program": self.auto_program, "status": self.status,
                "latency": self.latency.summary(), "clients": sorted(self.clients.values())}
