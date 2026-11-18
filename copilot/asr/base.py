"""Interfaz común de los motores de voz (docs/ARCHITECTURE.md §6).

feed() es síncrono y puede tardar cientos de ms (inferencia): el servidor lo ejecuta SIEMPRE en un hilo propio
(un hilo por motor), nunca en el bucle de asyncio. Los Transcript llevan segment_id y stable_upto para que el
resto del sistema pueda actuar sobre el prefijo estable de un parcial.
"""
from __future__ import annotations

from typing import Protocol, runtime_checkable

from copilot.types import Transcript

SAMPLE_RATE = 16000  # PCM mono int16


@runtime_checkable
class AsrEngine(Protocol):
    name: str

    def start(self, *, prompt: str, vocabulary: list[str], language: str = "es") -> None:
        """Carga el modelo y fija el sesgo de vocabulario (nombres de las plantillas del partido)."""

    def feed(self, pcm16: bytes, t_audio: float) -> list[Transcript]:
        """Recibe audio (16 kHz mono int16) que empieza en t_audio; devuelve parciales/finales ya disponibles."""

    def flush(self) -> list[Transcript]:
        """Fuerza la emisión de lo pendiente (fin de la fuente)."""

    def close(self) -> None: ...
