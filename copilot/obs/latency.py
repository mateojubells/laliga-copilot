"""Latencias por etapa (docs/ARCHITECTURE.md §8 y §10): se guardan las últimas N muestras y se dan p50/p95."""
from __future__ import annotations

import time
from collections import defaultdict, deque


def now_ms() -> float:
    return time.monotonic() * 1000.0


class LatencyBook:
    STAGES = ("asr", "nlu", "select", "net", "paint", "total")

    def __init__(self, keep: int = 2000) -> None:
        self._s: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=keep))

    def add(self, stage: str, ms: float) -> None:
        self._s[stage].append(ms)

    def add_trace(self, ts: dict[str, float]) -> None:
        """ts: marcas de GraphicCommand.ts más t_paint. Etapas que falten se ignoran."""
        pairs = {"asr": ("audio_end", "asr_emit"), "nlu": ("asr_emit", "nlu_out"), "select": ("nlu_out", "select_out"),
                 "net": ("select_out", "ws_send"), "paint": ("ws_send", "t_paint"), "total": ("audio_end", "t_paint")}
        for stage, (a, b) in pairs.items():
            if a in ts and b in ts:
                self.add(stage, ts[b] - ts[a])

    @staticmethod
    def _pct(xs: list[float], q: float) -> float:
        xs = sorted(xs)
        return xs[min(len(xs) - 1, int(round(q * (len(xs) - 1))))]

    def summary(self) -> dict[str, dict[str, float]]:
        return {st: {"n": len(v), "p50": round(self._pct(list(v), 0.5), 1), "p95": round(self._pct(list(v), 0.95), 1)}
                for st, v in self._s.items() if v}
