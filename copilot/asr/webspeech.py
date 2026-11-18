"""Adaptador del modo demo: el navegador (Web Speech API de Chrome) ya transcribe; aquí solo se convierte en Transcript.

No hay audio que procesar: feed() ignora el PCM. El servidor llama a push_text() cuando llega un resultado del navegador
y recoge los Transcript con drain() (o los recibe directamente de push_text).
"""
from __future__ import annotations

from copilot.asr.streaming import Emitter
from copilot.types import Transcript, Word


class WebSpeechAdapter:
    name = "webspeech"

    def __init__(self, avg_word_s: float = 0.35):
        self.avg_word_s = avg_word_s
        self.em = Emitter(self.name)
        self._pending: list[Transcript] = []
        self._open = False  # hay un parcial sin cerrar -> el siguiente comparte segment_id
        self._t_last = 0.0

    def start(self, *, prompt: str = "", vocabulary: list[str] | None = None, language: str = "es") -> None:
        self.language = language

    def push_text(self, text: str, final: bool, t_audio: float) -> list[Transcript]:
        """Texto del navegador que termina en t_audio. Chrome no da tiempos por palabra: se reparten hacia atrás."""
        toks = text.split()
        if not toks:
            return []
        t0 = max(0.0, t_audio - self.avg_word_s * len(toks))
        words = [Word(w=w, t0=t0 + i * self.avg_word_s, t1=t0 + (i + 1) * self.avg_word_s, p=1.0)
                 for i, w in enumerate(toks)]
        # Chrome reescribe el parcial entero cada vez: ninguna palabra es estable hasta el final
        tr = self.em.make(words, final=final, stable_upto=0, t_audio_end=t_audio, text=text)
        self._open = not final
        if final:
            self.em.new_segment()
        self._pending.append(tr)
        self._t_last = t_audio
        return [tr]

    def drain(self) -> list[Transcript]:
        out, self._pending = self._pending, []
        return out

    def feed(self, pcm16: bytes, t_audio: float) -> list[Transcript]:
        return self.drain()

    def flush(self) -> list[Transcript]:
        return self.drain()

    def close(self) -> None:
        self._pending.clear()
