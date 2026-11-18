"""Vosk (Kaldi) con el modelo pequeño de español: streaming nativo de muy baja latencia, CPU, ~50 MB.

El modelo se descarga una vez (gratis) de https://alphacephei.com/vosk/models a ~/.cache/laliga-copilot/vosk/
(`LALIGA_VOSK_MODEL` lo cambia). Salida en minúsculas y sin puntuación. Endpoint nativo de Vosk = final de segmento.
`grammar=True` restringe el reconocedor a los nombres de `vocabulary` + las `grammar_common` palabras más comunes
del corpus de comentarios + [unk] (el modelo pequeño admite gramática dinámica); sesga hacia los nombres a costa del
modelo de lenguaje general.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Optional

from copilot.asr.base import SAMPLE_RATE
from copilot.asr.streaming import Emitter, LocalAgreement
from copilot.types import Transcript, Word

DEFAULT_MODEL = Path(os.environ.get("LALIGA_VOSK_MODEL",
                                    Path.home() / ".cache" / "laliga-copilot" / "vosk" / "vosk-model-small-es-0.42"))


class VoskEngine:
    def __init__(self, model_path: Optional[str] = None, *, grammar: bool = False, grammar_common: int = 3000,
                 name: Optional[str] = None):
        self.model_path = Path(model_path) if model_path else DEFAULT_MODEL
        self.grammar, self.grammar_common = grammar, grammar_common
        self.name = name or ("vosk-small-es" + ("-grammar" if grammar else ""))
        self.em = Emitter(self.name)
        self.la = LocalAgreement(2)
        self.rec = None
        self.model = None
        self._gram: Optional[str] = None
        self.t_base: Optional[float] = None
        self.t_end = 0.0
        self._last_partial: list[Word] = []

    def start(self, *, prompt: str = "", vocabulary: Optional[list[str]] = None, language: str = "es") -> None:
        from vosk import Model, SetLogLevel
        SetLogLevel(-1)
        if not self.model_path.exists():
            raise FileNotFoundError(f"modelo Vosk no encontrado en {self.model_path}")
        self.model = Model(str(self.model_path))
        if self.grammar:
            from copilot.nlu.gazetteer import common_words
            from copilot.nlu.normalize import strip
            words = set()
            for v in vocabulary or []:
                words.update(strip(v).split())
            words.update(sorted(common_words(), key=common_words().get)[: self.grammar_common])
            self._gram = json.dumps(sorted(words) + ["[unk]"], ensure_ascii=False)
        self._new_rec()

    def _new_rec(self) -> None:
        from vosk import KaldiRecognizer
        self.rec = KaldiRecognizer(self.model, SAMPLE_RATE, self._gram) if self._gram \
            else KaldiRecognizer(self.model, SAMPLE_RATE)
        self.rec.SetWords(True)
        self.rec.SetPartialWords(True)
        self.t_base = None
        self.la.reset()
        self._last_partial = []

    def _words(self, items: list[dict]) -> list[Word]:
        base = self.t_base or 0.0
        return [Word(w=i["word"], t0=round(base + i["start"], 3), t1=round(base + i["end"], 3), p=float(i.get("conf", 1.0)))
                for i in items if i.get("word") and i["word"] != "[unk]"]

    def feed(self, pcm16: bytes, t_audio: float) -> list[Transcript]:
        if self.t_base is None:
            self.t_base = t_audio
        self.t_end = t_audio + len(pcm16) / 2 / SAMPLE_RATE
        out: list[Transcript] = []
        if self.rec.AcceptWaveform(pcm16):
            words = self._words(json.loads(self.rec.Result()).get("result", []))
            if words:
                out.append(self.em.make(words, final=True, stable_upto=len(words), t_audio_end=self.t_end))
                self.em.new_segment()
            self.la.reset()
            self._last_partial = []
        else:
            words = self._words(json.loads(self.rec.PartialResult()).get("partial_result", []))
            if words and [w.w for w in words] != [w.w for w in self._last_partial]:
                stable = self.la.update(words)
                out.append(self.em.make(words, final=False, stable_upto=stable, t_audio_end=self.t_end))
                self._last_partial = words
        return out

    def flush(self) -> list[Transcript]:
        out: list[Transcript] = []
        if self.rec is not None:
            words = self._words(json.loads(self.rec.FinalResult()).get("result", []))
            if words:
                out.append(self.em.make(words, final=True, stable_upto=len(words), t_audio_end=self.t_end))
                self.em.new_segment()
            self._new_rec()
        return out

    def close(self) -> None:
        self.rec = None
