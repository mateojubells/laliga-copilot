"""Base común de los motores no-streaming que se hacen "streaming" re-decodificando una ventana deslizante.

Cada `step_ms` de audio nuevo (y cuando ha terminado la decodificación anterior) se re-decodifica el buffer entero
(<= `max_window_s`) y se compara con la hipótesis previa con LocalAgreement-2 para saber qué palabras ya son estables.
Segmentos:
  - final por pausa: el VAD ve >= `silence_final_ms` de silencio tras voz -> se decodifica el buffer completo, se emite
    el final (todas las palabras estables) y el buffer se vacía;
  - final por longitud: si el buffer supera `max_window_s` sin pausa, se emite como final solo el prefijo estable y se
    recorta el audio justo tras su última palabra (lo no estable se redecodifica en el segmento siguiente).
Las subclases implementan `_load()` y `_decode(audio_float32) -> list[Word]` (tiempos relativos al buffer).
"""
from __future__ import annotations

import time
from typing import Optional

import numpy as np

from copilot.asr.base import SAMPLE_RATE
from copilot.asr.streaming import EnergyVad, Emitter, LocalAgreement, pcm_to_float
from copilot.types import Transcript, Word


class WindowedEngine:
    def __init__(self, name: str, *, step_ms: int = 1000, max_window_s: float = 12.0, silence_final_ms: int = 600,
                 min_window_s: float = 1.0, la_n: int = 2):
        self.name = name
        self.step, self.max_window, self.min_window = step_ms / 1000, max_window_s, min_window_s
        self.silence_final = silence_final_ms / 1000
        self.la = LocalAgreement(la_n)
        self.vad = EnergyVad()
        self.em = Emitter(self.name)
        self.prompt, self.vocabulary, self.language = "", [], "es"
        self._reset_buffer(0.0)
        self.last_final_text = ""
        self.decode_ms: list[float] = []

    # ------------------------------------------------------------ ciclo de vida
    def start(self, *, prompt: str, vocabulary: list[str], language: str = "es") -> None:
        self.prompt, self.vocabulary, self.language = prompt, vocabulary, language
        self._load()
        self._warmup()

    def _load(self) -> None:
        """Carga el modelo (los motores lo sobrescriben)."""

    def close(self) -> None:
        self._reset_buffer(0.0)

    def _warmup(self) -> None:
        self._decode(np.zeros(SAMPLE_RATE, dtype=np.float32))

    def _reset_buffer(self, t: float) -> None:
        self.buf = np.zeros(0, dtype=np.float32)
        self.buf_t0 = t
        self.speech_in_buf = False
        self.last_decode_end = t  # t_audio hasta el que se decodificó por última vez
        self.hyp: list[Word] = []
        self.la.reset()
        self.t_end = t

    # ------------------------------------------------------------ inferencia (la implementa cada motor)
    def _decode(self, audio: np.ndarray) -> list[Word]:
        """Decodifica float32 mono 16 kHz y devuelve palabras con t0/t1 relativos al inicio del buffer."""
        raise NotImplementedError

    def _hyp(self) -> list[Word]:
        """Decodifica el buffer actual y devuelve palabras con tiempos absolutos."""
        ws = self._decode(self.buf)
        return [Word(w=w.w, t0=round(w.t0 + self.buf_t0, 3), t1=round(w.t1 + self.buf_t0, 3), p=w.p) for w in ws]

    # ------------------------------------------------------------ streaming
    def feed(self, pcm16: bytes, t_audio: float) -> list[Transcript]:
        x = pcm_to_float(pcm16)
        if len(self.buf) == 0 and not self.speech_in_buf:
            self.buf_t0 = t_audio
            self.last_decode_end = t_audio
        speech = self.vad.feed(x, t_audio)
        self.buf = np.concatenate([self.buf, x])
        self.t_end = t_audio + len(x) / SAMPLE_RATE
        self.speech_in_buf = self.speech_in_buf or speech
        out: list[Transcript] = []

        if not self.speech_in_buf:  # solo silencio: conserva 0,5 s de pre-roll
            keep = int(0.5 * SAMPLE_RATE)
            if len(self.buf) > keep:
                self.buf_t0 += (len(self.buf) - keep) / SAMPLE_RATE
                self.buf = self.buf[-keep:]
            self.last_decode_end = self.buf_t0
            return out

        dur = len(self.buf) / SAMPLE_RATE
        if not speech and self.vad.silence_s >= self.silence_final and self.hyp_or_pending():
            return self._finalize_on_pause()
        if dur >= self.min_window and (self.t_end - self.last_decode_end) >= self.step and (speech or self.hyp):
            out += self._step()
        return out

    def hyp_or_pending(self) -> bool:
        return self.speech_in_buf and len(self.buf) / SAMPLE_RATE >= 0.3

    def _step(self) -> list[Transcript]:
        t0 = time.perf_counter()
        words = self._hyp()
        self.last_decode_end = self.t_end
        self.hyp = words
        stable = self.la.update(words)
        out = [self.em.make(words, final=False, stable_upto=stable, t_audio_end=self.t_end,
                            ts={"decode_ms": (time.perf_counter() - t0) * 1000})]
        dur = len(self.buf) / SAMPLE_RATE
        if dur >= self.max_window:
            cut = self._cut_stable()
            if not cut and dur >= 1.5 * self.max_window:
                cut = self._hard_cut()  # control de retraso: nunca dejar crecer el buffer (decodificar sería cada vez más lento)
            out += cut
        return out

    def _hard_cut(self) -> list[Transcript]:
        """Sin prefijo estable y buffer demasiado largo: emite lo que haya como final y conserva solo ~1 s de audio."""
        out: list[Transcript] = []
        keep_from = self.t_end - 1.0
        if self.hyp:
            tr = self.em.make(self.hyp, final=True, stable_upto=len(self.hyp), t_audio_end=self.t_end)
            self.last_final_text = tr.text
            out.append(tr)
            keep_from = min(keep_from, self.hyp[-1].t1)
            self.em.new_segment()
        i = max(0, min(len(self.buf), int((keep_from - self.buf_t0) * SAMPLE_RATE)))
        self.buf = self.buf[i:]
        self.buf_t0 += i / SAMPLE_RATE
        self.hyp = []
        self.la.reset()
        self.hard_cuts = getattr(self, "hard_cuts", 0) + 1
        self.last_decode_end = self.t_end
        return out

    def _cut_stable(self) -> list[Transcript]:
        """Final por longitud: solo el prefijo estable; el audio posterior se conserva."""
        n = self.la.stable
        if n < 2:  # nada fiable: forzar todo salvo las dos últimas palabras
            n = max(0, len(self.hyp) - 2)
        if n == 0:
            return []
        keep = self.hyp[:n]
        cut = keep[-1].t1
        tr = self.em.make(keep, final=True, stable_upto=n, t_audio_end=self.t_end)
        self.last_final_text = tr.text
        i = max(0, min(len(self.buf), int((cut - self.buf_t0) * SAMPLE_RATE)))
        self.buf = self.buf[i:]
        self.buf_t0 = cut
        self.hyp = []
        self.la.reset()
        self.em.new_segment()
        self.last_decode_end = self.t_end
        return [tr]

    def _finalize_on_pause(self) -> list[Transcript]:
        if self.t_end - self.last_decode_end > 0.3 or not self.hyp:
            words = self._hyp()
        else:
            words = self.hyp
        out: list[Transcript] = []
        if words:
            tr = self.em.make(words, final=True, stable_upto=len(words), t_audio_end=self.t_end)
            self.last_final_text = tr.text
            out.append(tr)
        self.em.new_segment()
        self._reset_buffer(self.t_end)
        self.speech_in_buf = False
        return out

    def flush(self) -> list[Transcript]:
        out: list[Transcript] = []
        if self.speech_in_buf and len(self.buf) > 0.3 * SAMPLE_RATE:
            out = self._finalize_on_pause()
        self._reset_buffer(self.t_end)
        return out
