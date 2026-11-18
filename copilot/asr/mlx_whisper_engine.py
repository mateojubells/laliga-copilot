"""Whisper en MLX con ventana deslizante (streaming simulado por re-decodificación; ver windowed.py).

`initial_prompt` lleva los nombres de las plantillas (sesgo de vocabulario). `model`: turbo | large | small | base o un
repo de Hugging Face. `context_words` > 0 añade al prompt las últimas palabras del final anterior.
"""
from __future__ import annotations

import time
from typing import Optional

import numpy as np

from copilot.asr.streaming import norm_word
from copilot.asr.windowed import WindowedEngine
from copilot.types import Word

#: frases que Whisper inventa en silencios o música (texto normalizado)
HALLUCINATIONS = (
    "subtitulos realizados por la comunidad de amara", "subtitulos por la comunidad de amara", "amara org",
    "gracias por ver el video", "gracias por ver el episodio", "gracias por ver", "suscribete al canal",
    "no olvides suscribirte", "subtitulado por", "traduccion y subtitulos", "fin del video",
)

MODELS = {
    "turbo": "mlx-community/whisper-large-v3-turbo",
    "large": "mlx-community/whisper-large-v3-mlx",
    "small": "mlx-community/whisper-small-mlx",
    "base": "mlx-community/whisper-base-mlx",
}


class MlxWhisperEngine(WindowedEngine):
    def __init__(self, model: str = "turbo", *, step_ms: int = 1000, max_window_s: float = 12.0,
                 silence_final_ms: int = 600, min_window_s: float = 1.0, la_n: int = 2, word_timestamps: bool = True,
                 context_words: int = 0, max_tokens: Optional[int] = None, name: Optional[str] = None):
        tag = model if model in MODELS else model.split("/")[-1]
        super().__init__(name or f"mlx-whisper-{tag}", step_ms=step_ms, max_window_s=max_window_s,
                         silence_final_ms=silence_final_ms, min_window_s=min_window_s, la_n=la_n)
        self.repo = MODELS.get(model, model)
        self.word_timestamps = word_timestamps
        self.context_words = context_words
        # tope de tokens por decodificación: ~7 tokens/s de ventana; evita bucles de repetición con ruido/gritos
        self.max_tokens = max_tokens or int(max_window_s * 7 + 20)

    def start(self, *, prompt: str, vocabulary: list[str], language: str = "es") -> None:
        if not prompt and vocabulary:
            prompt = "Nombres: " + ", ".join(vocabulary) + "."
        super().start(prompt=prompt, vocabulary=vocabulary, language=language)

    def _decode(self, audio: np.ndarray) -> list[Word]:
        import mlx_whisper
        prompt = self.prompt
        if self.context_words and self.last_final_text:
            prompt = (prompt + " " + " ".join(self.last_final_text.split()[-self.context_words:])).strip()
        t = time.perf_counter()
        res = mlx_whisper.transcribe(
            audio, path_or_hf_repo=self.repo, language=self.language, word_timestamps=self.word_timestamps,
            condition_on_previous_text=False, temperature=0.0, initial_prompt=prompt or None, verbose=None,
            sample_len=self.max_tokens)
        self.decode_ms.append((time.perf_counter() - t) * 1000)
        words: list[Word] = []
        for s in res["segments"]:
            if s.get("no_speech_prob", 0) > 0.6 and s.get("avg_logprob", 0) < -1.0:
                continue
            if s.get("compression_ratio", 0) > 2.4:
                continue
            ntxt = " ".join(norm_word(x) for x in s["text"].split())
            if len(ntxt.split()) < 12 and any(h in ntxt for h in HALLUCINATIONS):
                continue
            ws = s.get("words") or []
            if ws:
                for w in ws:
                    words.append(Word(w=w["word"].strip(), t0=float(w["start"]), t1=float(w["end"]),
                                      p=float(w.get("probability", 1.0))))
            else:  # sin marcas por palabra: se reparten uniformemente en el segmento
                toks = s["text"].split()
                a, b = float(s["start"]), float(s["end"])
                for i, tok in enumerate(toks):
                    words.append(Word(w=tok, t0=a + (b - a) * i / len(toks), t1=a + (b - a) * (i + 1) / len(toks)))
        return [w for w in words if w.w]
