"""Motor nulo: no detecta nada. Línea base inferior para comprobar que make eval puntúa de verdad."""
from __future__ import annotations

from typing import Any

from copilot.types import NluResult


class NullNlu:
    def reset(self, *, match_id: str | None = None) -> None:
        pass

    def analyze(self, text: str, *, t0: float = 0.0, t1: float = 0.0, final: bool = True, ctx: Any = None) -> NluResult:
        return NluResult(text=text, t0=t0, t1=t1, final=final)
