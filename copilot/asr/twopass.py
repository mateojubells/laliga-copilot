"""Motor compuesto en dos pasadas: primero el motor rápido (streaming), después el final corregido de Whisper.

  - Los parciales y finales del motor rápido salen YA (engine = motor rápido, ts["pass"] = 1).
  - El motor lento (Whisper) recibe el mismo audio en un hilo propio (la inferencia no frena al rápido). Solo se emiten
    sus FINALES, con el `segment_id` del segmento del motor rápido con el que más se solapan en el tiempo
    (engine = motor lento, ts["pass"] = 2, ts["covers_lo"/"covers_hi"] = rango de segment_id del rápido que cubre).
    Un consumidor se queda con el último final de cada segment_id: es la corrección.
"""
from __future__ import annotations

import queue
import threading
from typing import Optional

from copilot.asr.base import AsrEngine
from copilot.types import Transcript


class TwoPassEngine:
    def __init__(self, fast: AsrEngine | str = "parakeet", slow: AsrEngine | str = "mlx-whisper", *,
                 fast_cfg: Optional[dict] = None, slow_cfg: Optional[dict] = None, threaded: bool = True,
                 name: Optional[str] = None):
        from copilot.asr.factory import create
        self.fast = create(fast, **(fast_cfg or {})) if isinstance(fast, str) else fast
        self.slow = create(slow, **(slow_cfg or {})) if isinstance(slow, str) else slow
        self.name = name or f"twopass({self.fast.name}+{self.slow.name})"
        self.threaded = threaded
        self.segments: list[tuple[int, float, float]] = []  # (segment_id, t0, t1) del rápido, por orden
        self._open: dict[int, list[float]] = {}  # segmentos del rápido aún abiertos: id -> [t0, t1]
        self._out: "queue.Queue[Transcript | None]" = queue.Queue()
        self._in: "queue.Queue[tuple | None]" = queue.Queue()
        self._thread: Optional[threading.Thread] = None
        self.errors: list[str] = []

    # ------------------------------------------------------------ ciclo de vida
    def start(self, *, prompt: str, vocabulary: list[str], language: str = "es") -> None:
        self.fast.start(prompt=prompt, vocabulary=vocabulary, language=language)
        self.slow.start(prompt=prompt, vocabulary=vocabulary, language=language)
        if self.threaded and self._thread is None:
            self._thread = threading.Thread(target=self._worker, daemon=True, name="asr-slow")
            self._thread.start()

    def close(self) -> None:
        if self._thread is not None:
            self._in.put(None)
            self._thread.join(timeout=30)
            self._thread = None
        self.fast.close()
        self.slow.close()

    # ------------------------------------------------------------ hilo del motor lento
    def _worker(self) -> None:
        while True:
            item = self._in.get()
            if item is None:
                return
            kind, pcm, t = item
            try:
                res = self.slow.feed(pcm, t) if kind == "feed" else self.slow.flush()
            except Exception as e:  # el corrector falla: el rápido sigue solo
                self.errors.append(f"{type(e).__name__}: {e}")
                res = []
            for tr in res:
                self._out.put(tr)
            if kind == "flush":
                self._out.put(None)  # marca de fin de flush

    # ------------------------------------------------------------ streaming
    def _track(self, trs: list[Transcript]) -> list[Transcript]:
        out = []
        for tr in trs:
            tr = tr.model_copy(update={"ts": {**tr.ts, "pass": 1.0}})
            span = self._open.setdefault(tr.segment_id, [tr.t0, tr.t1])
            span[0], span[1] = min(span[0], tr.t0), max(span[1], tr.t1)
            if tr.final:
                self.segments.append((tr.segment_id, span[0], span[1]))
                self._open.pop(tr.segment_id, None)
            out.append(tr)
        return out

    def _correct(self, tr: Transcript) -> Transcript:
        cands = [(sid, a, b) for sid, a, b in self.segments] + [(sid, a, b) for sid, (a, b) in self._open.items()]
        over = [(max(0.0, min(b, tr.t1) - max(a, tr.t0)), sid) for sid, a, b in cands]
        over = [(o, sid) for o, sid in over if o > 0]
        if over:
            sid = max(over)[1]
            lo, hi = min(s for _, s in over), max(s for _, s in over)
        else:  # el rápido no oyó nada ahí: segmento nuevo, fuera del rango del rápido
            sid = 1_000_000 + tr.segment_id
            lo = hi = sid
        return tr.model_copy(update={"segment_id": sid, "final": True,
                                     "ts": {**tr.ts, "pass": 2.0, "covers_lo": float(lo), "covers_hi": float(hi)}})

    def _drain_slow(self) -> list[Transcript]:
        out = []
        while True:
            try:
                tr = self._out.get_nowait()
            except queue.Empty:
                return out
            if tr is not None:
                out.append(self._correct(tr))

    def feed(self, pcm16: bytes, t_audio: float) -> list[Transcript]:
        out = self._track(self.fast.feed(pcm16, t_audio))
        if self.threaded:
            self._in.put(("feed", pcm16, t_audio))
        else:
            for tr in self.slow.feed(pcm16, t_audio):
                self._out.put(tr)
        return out + self._drain_slow()

    def flush(self) -> list[Transcript]:
        out = self._track(self.fast.flush())
        if self.threaded:
            self._in.put(("flush", b"", 0.0))
            while True:  # espera a que el lento termine todo lo pendiente
                tr = self._out.get()
                if tr is None:
                    break
                out.append(self._correct(tr))
        else:
            for tr in self.slow.flush():
                out.append(self._correct(tr))
            out += self._drain_slow()
        self.segments.clear()
        self._open.clear()
        return out
