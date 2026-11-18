"""Utilidades de streaming de voz: LocalAgreement, lector por trozos, VAD, motor Whisper con decodificador falso."""
import numpy as np

from copilot.asr.base import SAMPLE_RATE, AsrEngine
from copilot.asr.mlx_whisper_engine import MlxWhisperEngine
from copilot.asr.streaming import EnergyVad, LocalAgreement, iter_blocks, norm_word
from copilot.types import Word


def W(*ws):
    return [Word(w=w, t0=i * 0.3, t1=i * 0.3 + 0.3) for i, w in enumerate(ws)]


def test_local_agreement_2_basic():
    la = LocalAgreement(2)
    assert la.update(W("gol", "de", "Raphi")) == 0  # una sola hipótesis: nada estable
    assert la.update(W("gol", "de", "Raphinha", "qué")) == 2  # coinciden "gol de"
    assert la.update(W("gol", "de", "Raphinha", "qué", "pase")) == 4
    assert la.stable == 4 and la.retractions == 0


def test_local_agreement_ignores_case_accents_punct():
    la = LocalAgreement(2)
    la.update(W("Cubarsí,", "juega"))
    assert la.update(W("cubarsi", "juega.", "bien")) == 2
    assert norm_word("Íñigo!") == "inigo"


def test_local_agreement_retraction_and_finish():
    la = LocalAgreement(2)
    la.update(W("a", "b", "c"))
    assert la.update(W("a", "b", "c", "d")) == 3
    # el motor se desdice de "c": el estable baja y se cuenta la retirada
    assert la.update(W("a", "b", "x")) == 2
    assert la.retractions == 1
    assert la.finish(W("a", "b", "x")) == 3


def test_local_agreement_n3_needs_three():
    la = LocalAgreement(3)
    la.update(W("a", "b"))
    assert la.update(W("a", "b", "c")) == 0
    assert la.update(W("a", "b", "c", "d")) == 2


def test_iter_blocks_pacing_and_times():
    audio = np.zeros(SAMPLE_RATE, dtype=np.int16)  # 1 s
    now = [0.0]
    slept = []

    def sleep(dt):
        slept.append(dt)
        now[0] += dt

    blocks = list(iter_blocks(audio, 10.0, block_ms=250, speed=2.0, clock=lambda: now[0], sleep=sleep))
    assert [round(t, 3) for _, t in blocks] == [10.0, 10.25, 10.5, 10.75]
    assert all(len(b) == 250 * SAMPLE_RATE // 1000 * 2 for b, _ in blocks)
    assert abs(sum(slept) - 0.5) < 1e-6  # 1 s de audio a velocidad 2 = 0,5 s de reloj


def test_iter_blocks_backlog_when_consumer_is_slow():
    audio = np.zeros(SAMPLE_RATE // 2, dtype=np.int16)
    now = [0.0]
    out = []
    for pcm, t in iter_blocks(audio, 0.0, block_ms=100, clock=lambda: now[0], sleep=lambda dt: now.__setitem__(0, now[0] + dt)):
        out.append(now[0])
        now[0] += 0.4  # el consumidor tarda 400 ms por bloque: los siguientes salen sin esperar
    assert out[0] == 0.1 and out[1] == 0.5 and out[2] == 0.9  # sin esperas extra tras el primero


def test_iter_blocks_no_realtime():
    audio = np.zeros(SAMPLE_RATE, dtype=np.int16)
    assert len(list(iter_blocks(audio, 0.0, block_ms=100, realtime=False, sleep=lambda dt: 1 / 0))) == 10


def test_vad_detects_pause():
    rng = np.random.default_rng(0)
    vad = EnergyVad()
    noise = (rng.standard_normal(SAMPLE_RATE) * 0.001).astype(np.float32)
    speech = (rng.standard_normal(SAMPLE_RATE) * 0.1).astype(np.float32)
    vad.feed(noise, 0.0)
    assert not vad.in_speech
    assert vad.feed(speech, 1.0)
    vad.feed(noise, 2.0)
    assert not vad.in_speech and vad.silence_s > 0.7


class FakeWhisper(MlxWhisperEngine):
    """Whisper sin modelo: «transcribe» los segundos de voz del buffer como palabras w0 w1 ... (una por 0,3 s)."""

    def _warmup(self):
        pass

    def _decode(self, audio):
        n = int(np.sum(np.abs(audio) > 0.02) / SAMPLE_RATE / 0.3)
        first = int(np.argmax(np.abs(audio) > 0.02)) / SAMPLE_RATE if n else 0
        return [Word(w=f"p{i}", t0=first + i * 0.3, t1=first + (i + 1) * 0.3) for i in range(n)]


def _pcm(sec, amp):
    x = np.full(int(sec * SAMPLE_RATE), amp, dtype=np.float32) * np.sign(np.sin(np.arange(int(sec * SAMPLE_RATE)) * 0.3))
    return (x * 32767).astype(np.int16).tobytes()


def test_whisper_engine_partials_then_final_on_pause():
    eng = FakeWhisper("turbo", step_ms=500, max_window_s=30)
    assert isinstance(eng, AsrEngine)
    eng.start(prompt="x", vocabulary=[])
    out, t = [], 0.0
    for _ in range(30):  # 3 s de voz en bloques de 100 ms
        out += eng.feed(_pcm(0.1, 0.1), t)
        t += 0.1
    parts = [o for o in out if not o.final]
    assert parts and parts[0].segment_id == parts[-1].segment_id
    assert parts[-1].stable_upto > 0 and parts[-1].stable_upto < len(parts[-1].words) + 1
    for _ in range(10):  # 1 s de silencio -> final por pausa
        out += eng.feed(b"\x00\x00" * 1600, t)
        t += 0.1
    finals = [o for o in out if o.final]
    assert len(finals) == 1 and finals[0].stable_upto == len(finals[0].words) > 5
    # lo siguiente es otro segmento
    out2 = []
    for _ in range(10):
        out2 += eng.feed(_pcm(0.1, 0.1), t)
        t += 0.1
    assert out2 and out2[0].segment_id > finals[0].segment_id


def test_whisper_engine_forced_cut_keeps_unstable_tail():
    eng = FakeWhisper("turbo", step_ms=500, max_window_s=4)
    eng.start(prompt="x", vocabulary=[])
    out, t = [], 0.0
    for _ in range(80):  # 8 s ininterrumpidos
        out += eng.feed(_pcm(0.1, 0.1), t)
        t += 0.1
    finals = [o for o in out if o.final]
    assert len(finals) >= 1
    assert finals[0].t1 < 4.5  # corta por longitud en el prefijo estable, no al final del buffer
    tail = eng.flush()
    assert tail and tail[-1].final
