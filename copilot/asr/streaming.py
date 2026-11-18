"""Utilidades comunes de los motores de voz en streaming.

- `read_wav` / `iter_blocks`: lector de WAV por trozos que simula un micro (a velocidad real o acelerada).
- `EnergyVad`: detector de voz por energía (sin dependencias; suficiente para decidir cortes y no decodificar silencio).
- `LocalAgreement`: política de acuerdo local (LocalAgreement-n de Macháček et al., 2023): una palabra es estable
  cuando las n últimas hipótesis coinciden en ella (y en todo lo anterior).
- `Emitter`: construye los `Transcript` (segment_id, stable_upto, ts) con una numeración coherente.
"""
from __future__ import annotations

import re
import time
import unicodedata
import wave
from typing import Callable, Iterator, Optional

import numpy as np

from copilot.asr.base import SAMPLE_RATE
from copilot.types import Transcript, Word


# ------------------------------------------------------------------ audio
def read_wav(path, t0: float = 0.0, t1: Optional[float] = None) -> np.ndarray:
    """Lee [t0, t1) de un WAV 16 kHz mono int16 y lo devuelve como int16."""
    with wave.open(str(path), "rb") as w:
        if not (w.getframerate() == SAMPLE_RATE and w.getnchannels() == 1 and w.getsampwidth() == 2):
            raise ValueError("se espera WAV 16 kHz mono int16")
        total = w.getnframes() / SAMPLE_RATE
        t1 = total if t1 is None else min(t1, total)
        w.setpos(int(t0 * SAMPLE_RATE))
        raw = w.readframes(max(0, int((t1 - t0) * SAMPLE_RATE)))
    return np.frombuffer(raw, dtype=np.int16)


def iter_blocks(audio: np.ndarray, t_start: float = 0.0, *, block_ms: int = 100, speed: float = 1.0,
                realtime: bool = True, clock: Callable[[], float] = time.monotonic,
                sleep: Callable[[float], None] = time.sleep) -> Iterator[tuple[bytes, float]]:
    """Entrega el audio en bloques de `block_ms` como un micro: (pcm16, t_audio del primer sample).

    Un bloque solo está disponible cuando ya se ha "grabado" entero, es decir, en t_wall = (fin del bloque - t_start) /
    speed. Si el consumidor tarda más que eso (inferencia lenta), los bloques siguientes salen de inmediato (cola
    acumulada), igual que en el servidor real. Con realtime=False no hay esperas (para tests)."""
    n = max(1, int(SAMPLE_RATE * block_ms / 1000))
    wall0 = clock()
    for i in range(0, len(audio), n):
        chunk = audio[i:i + n]
        t_audio = t_start + i / SAMPLE_RATE
        if realtime:
            due = wall0 + (i + len(chunk)) / SAMPLE_RATE / speed
            wait = due - clock()
            if wait > 0:
                sleep(wait)
        yield chunk.tobytes(), t_audio


def pcm_to_float(pcm16: bytes) -> np.ndarray:
    return np.frombuffer(pcm16, dtype=np.int16).astype(np.float32) / 32768.0


# ------------------------------------------------------------------ VAD
class EnergyVad:
    """VAD por energía con umbral adaptativo: suelo de ruido (percentil bajo móvil) + margen en dB.

    No distingue voz de público; sirve para no decodificar silencios digitales/pausas y para detectar pausas reales
    del narrador. `feed(float32, t_audio)` actualiza el estado; `silence_s` es el silencio acumulado al final."""

    def __init__(self, frame_ms: int = 30, margin_db: float = 9.0, min_db: float = -50.0, hang_ms: int = 150,
                 max_floor_db: float = -38.0):
        self.frame = int(SAMPLE_RATE * frame_ms / 1000)
        self.margin_db, self.min_db, self.hang = margin_db, min_db, hang_ms / 1000
        self.max_floor_db = max_floor_db  # un fondo de público muy alto no debe tapar la voz
        self.floor_db = -60.0
        self._levels: list[float] = []
        self.last_speech_t = -1e9  # fin (audio) de la última trama con voz
        self.t_now = 0.0
        self.in_speech = False

    def frames_db(self, x: np.ndarray) -> np.ndarray:
        n = len(x) // self.frame
        if n == 0:
            return np.zeros(0, dtype=np.float32)
        fr = x[: n * self.frame].reshape(n, self.frame)
        return 10 * np.log10(np.mean(fr * fr, axis=1) + 1e-10)

    def feed(self, x: np.ndarray, t_audio: float) -> bool:
        db = self.frames_db(x)
        t = t_audio
        step = self.frame / SAMPLE_RATE
        for d in db:
            self._levels.append(float(d))
            if len(self._levels) > 400:
                self._levels = self._levels[-400:]
            self.floor_db = min(self.max_floor_db, float(np.percentile(self._levels, 20)))
            thr = max(self.min_db, self.floor_db + self.margin_db)
            t += step
            if d > thr:
                self.last_speech_t = t
        self.t_now = t_audio + len(x) / SAMPLE_RATE
        self.in_speech = (self.t_now - self.last_speech_t) <= self.hang
        return self.in_speech

    @property
    def silence_s(self) -> float:
        return max(0.0, self.t_now - self.last_speech_t)

    def has_speech(self, x: np.ndarray) -> bool:
        """Sin estado: ¿hay alguna trama por encima del umbral actual en x?"""
        db = self.frames_db(x)
        if len(db) == 0:
            return False
        return bool(np.max(db) > max(self.min_db, self.floor_db + self.margin_db))


# ------------------------------------------------------------------ acuerdo local
def norm_word(w: str) -> str:
    s = unicodedata.normalize("NFD", w.lower())
    s = "".join(c for c in s if unicodedata.category(c) != "Mn")
    return re.sub(r"[^a-z0-9ñ]+", "", s)


class LocalAgreement:
    """LocalAgreement-n sobre hipótesis sucesivas de un MISMO segmento (todas empiezan en el mismo instante).

    update(words) devuelve el nº de palabras iniciales estables: el prefijo común (normalizado) de las n últimas
    hipótesis. El prefijo estable nunca decrece mientras las nuevas hipótesis lo respeten; si una hipótesis lo
    contradice (el motor "se desdice"), el estable baja al prefijo común con lo confirmado y se cuenta una retirada."""

    def __init__(self, n: int = 2):
        if n < 1:
            raise ValueError("n >= 1")
        self.n = n
        self.reset()

    def reset(self) -> None:
        self.history: list[list[str]] = []
        self.stable = 0
        self.committed: list[str] = []
        self.retractions = 0

    def update(self, words: list[Word] | list[str]) -> int:
        toks = [norm_word(w.w if isinstance(w, Word) else w) for w in words]
        self.history = (self.history + [toks])[-self.n:]
        # contradice lo confirmado -> retirada
        k = _lcp(self.committed, toks)
        if k < len(self.committed):
            self.retractions += 1
            self.committed = self.committed[:k]
            self.stable = k
        if len(self.history) >= self.n:
            common = toks
            for h in self.history[:-1]:
                common = common[:_lcp(common, h)]
            if len(common) > self.stable:
                self.stable = len(common)
                self.committed = list(common)
        return min(self.stable, len(toks))

    def finish(self, words: list[Word] | list[str]) -> int:
        """Fin de segmento: todo pasa a estable."""
        self.stable = len(words)
        self.committed = [norm_word(w.w if isinstance(w, Word) else w) for w in words]
        return self.stable


def _lcp(a: list[str], b: list[str]) -> int:
    k = 0
    for x, y in zip(a, b):
        if x != y:
            break
        k += 1
    return k


# ------------------------------------------------------------------ emisión
class Emitter:
    """Fabrica Transcript con segment_id creciente y marcas de reloj (ms, monotónico)."""

    def __init__(self, engine: str, clock: Callable[[], float] = time.monotonic):
        self.engine = engine
        self.clock = clock
        self.segment_id = 0
        self._n = 0

    def new_segment(self) -> int:
        self.segment_id += 1
        return self.segment_id

    def make(self, words: list[Word], *, final: bool, stable_upto: int, t_audio_end: float,
             segment_id: Optional[int] = None, engine: Optional[str] = None,
             ts: Optional[dict[str, float]] = None, text: Optional[str] = None) -> Transcript:
        self._n += 1
        sid = self.segment_id if segment_id is None else segment_id
        eng = engine or self.engine
        stamp = {"audio_end": t_audio_end * 1000.0, "asr_emit": self.clock() * 1000.0}
        if ts:
            stamp.update(ts)
        return Transcript(
            trace_id=f"{eng}-{sid}-{self._n}", engine=eng, final=final,
            text=text if text is not None else " ".join(w.w for w in words),
            t0=words[0].t0 if words else t_audio_end, t1=words[-1].t1 if words else t_audio_end,
            words=words, segment_id=sid, stable_upto=len(words) if final else min(stable_upto, len(words)),
            ts=stamp)
