"""Parakeet-TDT 0.6B v3 (multilingüe, incluye español) en MLX (`parakeet-mlx`).

Dos modos:
  - `ParakeetEngine` ("parakeet"): re-decodifica una ventana deslizante con el modelo offline (windowed.py). Rápido (RTF
    ~0,07) y con la calidad del modelo completo.
  - `ParakeetStreamEngine` ("parakeet-stream"): API nativa `transcribe_stream` de parakeet-mlx (atención local con
    contexto limitado). Es streaming de verdad, pero ver docs/EXPERIMENTS.md: en este audio degrada mucho el texto.

Descripción del modo nativo:

El modelo procesa el audio en trozos de `chunk_ms` con atención local; los tokens "finalizados" (ya fuera del contexto
derecho) no cambian y los "borrador" (draft) se re-decodifican en cada trozo. Estable = finalizado por el modelo o
acordado en dos borradores seguidos (LocalAgreement-2), lo que llegue antes. Segmentos: pausa del VAD >=
`silence_final_ms` o duración > `max_segment_s`.
Sesgo de vocabulario: búsqueda en haz con `boost.words` (potenciación de palabras de parakeet-mlx) con los nombres de la
lista `vocabulary`; `boost=0` usa decodificación voraz (más rápida).
"""
from __future__ import annotations

import time
from typing import Optional

import numpy as np

from copilot.asr.base import SAMPLE_RATE
from copilot.asr.streaming import EnergyVad, Emitter, LocalAgreement, pcm_to_float
from copilot.asr.windowed import WindowedEngine
from copilot.types import Transcript, Word

REPO = "mlx-community/parakeet-tdt-0.6b-v3"


def tokens_to_words(tokens, base: float) -> list[Word]:
    """Agrupa tokens SentencePiece en palabras: un token cuyo texto empieza por espacio abre palabra."""
    words: list[Word] = []
    cur: Optional[dict] = None
    for t in tokens:
        txt = t.text
        if cur is None or txt.startswith(" ") or txt.startswith("▁"):
            if cur is not None:
                words.append(_w(cur, base))
            cur = {"w": txt.lstrip(" ▁"), "t0": t.start, "t1": t.end, "p": [t.confidence]}
        else:
            cur["w"] += txt
            cur["t1"] = t.end
            cur["p"].append(t.confidence)
    if cur is not None:
        words.append(_w(cur, base))
    return [w for w in words if w.w]


def _w(c: dict, base: float) -> Word:
    return Word(w=c["w"], t0=round(c["t0"] + base, 3), t1=round(c["t1"] + base, 3),
                p=float(min(c["p"])) if c["p"] else 1.0)


class ParakeetStreamEngine:
    def __init__(self, repo: str = REPO, *, chunk_ms: int = 320, left_ctx: int = 128, right_ctx: int = 16, depth: int = 1,
                 boost: float = 0.0, beam: int = 4, silence_final_ms: int = 600, max_segment_s: float = 10.0,
                 name: Optional[str] = None):
        self.repo = repo
        self.name = name or ("parakeet-stream" + (f"-boost{boost:g}" if boost else ""))
        self.chunk = int(SAMPLE_RATE * chunk_ms / 1000)
        self.ctx, self.depth = (left_ctx, right_ctx), depth
        self.boost, self.beam = boost, beam
        self.silence_final = silence_final_ms / 1000
        self.max_segment = max_segment_s
        self.vad = EnergyVad()
        self.la = LocalAgreement(2)
        self.em = Emitter(self.name)
        self.model = None
        self.config = None
        self._stream = None
        self._reset_state()

    # ------------------------------------------------------------ ciclo de vida
    def start(self, *, prompt: str = "", vocabulary: Optional[list[str]] = None, language: str = "es") -> None:
        from parakeet_mlx import from_pretrained
        self.model = from_pretrained(self.repo)
        self.config = _config(self.model, vocabulary or [], self.boost, self.beam)
        self._warmup()

    def _warmup(self) -> None:
        self._open(0.0)
        self._stream_add(np.zeros(self.chunk, dtype=np.float32))
        self._close_stream()
        self._reset_state()

    def _open(self, t_base: float) -> None:
        import parakeet_mlx
        kw = {"decoding_config": self.config} if self.config is not None else {}
        self._stream = self.model.transcribe_stream(context_size=self.ctx, depth=self.depth, **kw)
        self._stream.__enter__()
        self.t_base = t_base

    def _close_stream(self) -> None:
        if self._stream is not None:
            self._stream.__exit__(None, None, None)
            self._stream = None

    def _stream_add(self, x: np.ndarray) -> None:
        import mlx.core as mx
        self._stream.add_audio(mx.array(x))

    def _reset_state(self) -> None:
        self.pending = np.zeros(0, dtype=np.float32)
        self.seg_start_t = None  # t_audio de inicio del segmento actual
        self.cut_t = -1.0  # las palabras que empiezan antes de cut_t ya se emitieron en finales
        self.speech_in_seg = False
        self.la.reset()
        self.t_end = 0.0

    def close(self) -> None:
        self._close_stream()

    # ------------------------------------------------------------ streaming
    def _words(self) -> tuple[list[Word], int]:
        """(palabras del segmento actual, nº de ellas finalizadas por el modelo)."""
        st = self._stream
        fin = tokens_to_words([t for t in st.finalized_tokens if t.start + self.t_base >= self.cut_t - 1e-3], self.t_base)
        dra = tokens_to_words([t for t in st.draft_tokens if t.start + self.t_base >= self.cut_t - 1e-3], self.t_base)
        # la última palabra finalizada puede continuar en el borrador (token sin espacio): se acepta la partición del modelo
        return fin + dra, len(fin)

    def feed(self, pcm16: bytes, t_audio: float) -> list[Transcript]:
        x = pcm_to_float(pcm16)
        speech = self.vad.feed(x, t_audio)
        if self._stream is None:
            self._open(t_audio)
        self.pending = np.concatenate([self.pending, x])
        self.t_end = t_audio + len(x) / SAMPLE_RATE
        if speech and self.seg_start_t is None:
            self.seg_start_t = t_audio
        self.speech_in_seg = self.speech_in_seg or speech
        out: list[Transcript] = []
        if len(self.pending) < self.chunk:
            return out
        self._stream_add(self.pending)
        self.pending = np.zeros(0, dtype=np.float32)
        words, nfin = self._words()
        if not words:
            return out
        stable = max(nfin, self.la.update(words))
        pause = not speech and self.vad.silence_s >= self.silence_final
        too_long = (self.t_end - (self.seg_start_t or self.t_end)) >= self.max_segment
        if pause or too_long:
            keep = words if pause else words[:max(1, stable)]
            out.append(self.em.make(keep, final=True, stable_upto=len(keep), t_audio_end=self.t_end))
            self.cut_t = keep[-1].t1 - 0.02
            self.em.new_segment()
            self.la.reset()
            self.seg_start_t = None if pause else keep[-1].t1
            self.speech_in_seg = False
            return out
        out.append(self.em.make(words, final=False, stable_upto=stable, t_audio_end=self.t_end))
        return out

    def flush(self) -> list[Transcript]:
        out: list[Transcript] = []
        if self._stream is not None:
            if len(self.pending):
                self._stream_add(self.pending)
                self.pending = np.zeros(0, dtype=np.float32)
            words, _ = self._words()
            if words:
                out.append(self.em.make(words, final=True, stable_upto=len(words), t_audio_end=self.t_end))
                self.em.new_segment()
            self._close_stream()
        self._reset_state()
        return out


def _config(model, vocabulary: list[str], boost: float, beam: int):
    """Decodificación en haz con potenciación de nombres (parakeet-mlx `boost.words`), o None (voraz)."""
    if boost <= 0 or not vocabulary:
        return None
    from parakeet_mlx import Beam, DecodingConfig
    from parakeet_mlx.boost import lift, words
    weights: dict[str, float] = {}
    for v in vocabulary:
        for form in {v, v.lower(), v.capitalize()}:
            weights[form] = boost
        for part in v.split():  # apellidos sueltos ("Yamal", "Stegen")
            if len(part) >= 4:
                weights.setdefault(part, boost)
                weights.setdefault(part.lower(), boost)
    return DecodingConfig(decoding=Beam(beam_size=beam, booster=lift(words(weights), model.vocabulary)))


class ParakeetEngine(WindowedEngine):
    """Parakeet-TDT v3 offline sobre ventana deslizante + LocalAgreement-2."""

    def __init__(self, repo: str = REPO, *, step_ms: int = 500, max_window_s: float = 10.0, silence_final_ms: int = 600,
                 boost: float = 0.0, beam: int = 4, name: Optional[str] = None):
        super().__init__(name or ("parakeet-win" + (f"-boost{boost:g}" if boost else "")), step_ms=step_ms,
                         max_window_s=max_window_s, silence_final_ms=silence_final_ms)
        self.repo, self.boost, self.beam = repo, boost, beam
        self.model = None
        self.config = None

    def _load(self) -> None:
        from parakeet_mlx import from_pretrained
        self.model = from_pretrained(self.repo)
        self.config = _config(self.model, self.vocabulary, self.boost, self.beam)

    def _decode(self, audio: np.ndarray) -> list[Word]:
        import mlx.core as mx
        from parakeet_mlx.audio import get_logmel
        t = time.perf_counter()
        if len(audio) < self.model.preprocessor_config.hop_length * 4:
            return []
        mel = get_logmel(mx.array(audio), self.model.preprocessor_config)
        kw = {"decoding_config": self.config} if self.config is not None else {}
        res = self.model.generate(mel, **kw)[0]
        self.decode_ms.append((time.perf_counter() - t) * 1000)
        return tokens_to_words(res.tokens, 0.0)
