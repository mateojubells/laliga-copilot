"""Supervisor (conmutación al respaldo), motor en dos pasadas, adaptador Web Speech y fábrica; todo con motores falsos."""
import pytest

from copilot.asr import factory
from copilot.asr.base import AsrEngine
from copilot.asr.factory import AsrSupervisor
from copilot.asr.twopass import TwoPassEngine
from copilot.asr.webspeech import WebSpeechAdapter
from copilot.types import Transcript, Word


def tr(engine, sid, t0, t1, text, final=True, **ts):
    ws = [Word(w=w, t0=t0 + i * 0.2, t1=t0 + (i + 1) * 0.2) for i, w in enumerate(text.split())]
    return Transcript(trace_id=f"{engine}-{sid}", engine=engine, final=final, text=text, t0=t0, t1=t1, words=ws,
                      segment_id=sid, stable_upto=len(ws) if final else 0, ts=ts)


class Fake:
    def __init__(self, name, script=None, fail=False, delay=0.0, clock=None):
        self.name, self.script, self.fail, self.delay, self.clock = name, script or {}, fail, delay, clock
        self.started = self.closed = False
        self.calls = 0

    def start(self, *, prompt, vocabulary, language="es"):
        self.started = True
        self.prompt = prompt

    def feed(self, pcm16, t_audio):
        self.calls += 1
        if self.fail:
            raise RuntimeError("boom")
        if self.clock:
            self.clock[0] += self.delay
        return self.script.get(round(t_audio, 1), [])

    def flush(self):
        return self.script.get("flush", [])

    def close(self):
        self.closed = True


def test_fake_is_asr_engine_and_supervisor_too():
    assert isinstance(Fake("a"), AsrEngine)
    assert isinstance(AsrSupervisor(Fake("a"), Fake("b")), AsrEngine)


def test_supervisor_switches_after_consecutive_exceptions():
    p, b = Fake("main", fail=True), Fake("backup", script={0.3: [tr("backup", 0, 0, 0.3, "hola")]})
    sup = AsrSupervisor(p, b, max_strikes=3)
    sup.start(prompt="Barça", vocabulary=["Pedri"])
    assert sup.feed(b"", 0.0) == [] and sup.feed(b"", 0.1) == [] and not sup.switched
    sup.feed(b"", 0.2)  # tercer fallo seguido -> conmuta y el mismo trozo ya lo procesa el respaldo
    assert sup.switched and sup.name == "backup"
    assert b.started and b.prompt == "Barça"  # el respaldo arranca con el mismo sesgo
    assert sup.feed(b"", 0.3)[0].text == "hola"
    ev = sup.events[0]
    assert ev["from"] == "main" and ev["to"] == "backup" and "boom" in ev["reason"] and ev["t_audio"] == 0.2


def test_supervisor_resets_strikes_on_success():
    clock = [0.0]
    p = Fake("main", delay=0.0, clock=clock)
    sup = AsrSupervisor(p, Fake("b"), budget_ms=100, slow_factor=2.0, max_strikes=3, clock=lambda: clock[0])
    sup.start(prompt="", vocabulary=[])
    for delay in (0.5, 0.5, 0.01, 0.5, 0.5):  # lentos, lentos, bien (resetea), lentos, lentos -> sigue el principal
        p.delay = delay
        sup.feed(b"", 0.0)
    assert not sup.switched and sup.strikes == 2


def test_supervisor_switches_when_too_slow_n_times():
    clock = [0.0]
    p = Fake("main", delay=0.5, clock=clock)
    sup = AsrSupervisor(p, Fake("b"), budget_ms=100, slow_factor=2.0, max_strikes=3, clock=lambda: clock[0])
    sup.start(prompt="", vocabulary=[])
    for i in range(3):
        sup.feed(b"", i * 0.1)
    assert sup.switched and "tardó" in sup.events[0]["reason"]
    sup.switch_back()
    assert sup.active is p


def test_supervisor_primary_start_failure_goes_to_backup():
    class Bad(Fake):
        def start(self, **kw):
            raise OSError("modelo no encontrado")
    sup = AsrSupervisor(Bad("main"), Fake("backup"))
    sup.start(prompt="", vocabulary=[])
    assert sup.switched and "modelo no encontrado" in sup.events[0]["reason"]


def test_twopass_fast_first_then_corrected_final_same_segment():
    fast = Fake("fast", script={
        0.1: [tr("fast", 1, 0.0, 0.4, "gol de rafina", final=False)],
        0.2: [tr("fast", 1, 0.0, 0.6, "gol de rafina", final=True)],
        0.4: [tr("fast", 2, 1.0, 1.4, "pase de lamín", final=True)]})
    slow = Fake("slow", script={0.3: [tr("slow", 7, 0.0, 0.6, "gol de Raphinha", final=True)],
                                0.5: [tr("slow", 8, 1.0, 1.4, "pase de Lamine", final=True)]})
    two = TwoPassEngine(fast, slow, threaded=False)
    two.start(prompt="x", vocabulary=[])
    out = []
    for t in (0.1, 0.2, 0.3, 0.4, 0.5):
        out += two.feed(b"", t)
    assert [o.engine for o in out] == ["fast", "fast", "slow", "fast", "slow"]
    assert out[0].ts["pass"] == 1 and out[2].ts["pass"] == 2
    assert out[2].segment_id == 1 and out[2].text == "gol de Raphinha"  # corrige el segmento 1 del rápido
    assert out[4].segment_id == 2
    assert out[2].final and not out[0].final


def test_twopass_threaded_flush_waits_for_slow():
    fast = Fake("fast", script={"flush": [tr("fast", 1, 0.0, 0.5, "hola", final=True)]})
    slow = Fake("slow", script={"flush": [tr("slow", 1, 0.0, 0.5, "Hola", final=True)]})
    two = TwoPassEngine(fast, slow, threaded=True)
    two.start(prompt="", vocabulary=[])
    out = two.flush()
    two.close()
    assert [o.engine for o in out] == ["fast", "slow"] and out[1].segment_id == 1


def test_webspeech_adapter_partials_share_segment_and_final_closes():
    ws = WebSpeechAdapter()
    ws.start(prompt="", vocabulary=[])
    a = ws.push_text("gol de", False, 10.0)[0]
    b = ws.push_text("gol de Raphinha", False, 10.5)[0]
    c = ws.push_text("gol de Raphinha", True, 11.0)[0]
    d = ws.push_text("qué pase", False, 12.0)[0]
    assert a.segment_id == b.segment_id == c.segment_id != d.segment_id
    assert not a.final and c.final and c.stable_upto == 3 and b.stable_upto == 0
    assert c.words[-1].t1 == pytest.approx(11.0) and c.engine == "webspeech"
    assert len(ws.drain()) == 4 and ws.drain() == []


def test_factory_registry_and_unknown():
    assert isinstance(factory.create("webspeech"), WebSpeechAdapter)
    with pytest.raises(KeyError):
        factory.create("no-existe")
    w = factory.create("mlx-whisper-small", step_ms=700)  # no carga el modelo hasta start()
    assert w.name == "mlx-whisper-small" and w.step == 0.7
