"""Interfaz del motor de comprensión (docs/ARCHITECTURE.md §6-7)."""
from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from copilot.types import NluResult


@runtime_checkable
class NluEngine(Protocol):
    def reset(self, *, match_id: str | None = None) -> None:
        """Olvida el contexto (sujeto vigente, correferencia) y fija el partido en curso."""

    def analyze(self, text: str, *, t0: float = 0.0, t1: float = 0.0, final: bool = True,
                ctx: Any = None) -> NluResult:
        """Con final=False NO modifica el contexto de correferencia (los parciales se repiten y cambian)."""
