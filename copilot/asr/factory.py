"""Fábrica de motores y supervisor con conmutación al respaldo.

    eng = create("mlx-whisper", model="turbo", step_ms=1000)
    sup = AsrSupervisor(create("parakeet"), create("mlx-whisper", model="small"), budget_ms=1500)
"""
from __future__ import annotations

import importlib
import time
from typing import Any, Callable, Optional

from copilot.asr.base import AsrEngine
from copilot.types import Transcript

#: nombre -> (módulo, clase, configuración fija). Las importaciones son perezosas: no se cargan modelos hasta create().
REGISTRY: dict[str, tuple[str, str, dict]] = {
    "mlx-whisper": ("copilot.asr.mlx_whisper_engine", "MlxWhisperEngine", {}),
    "mlx-whisper-turbo": ("copilot.asr.mlx_whisper_engine", "MlxWhisperEngine", {"model": "turbo"}),
    "mlx-whisper-small": ("copilot.asr.mlx_whisper_engine", "MlxWhisperEngine", {"model": "small"}),
    "mlx-whisper-large": ("copilot.asr.mlx_whisper_engine", "MlxWhisperEngine", {"model": "large"}),
    "parakeet": ("copilot.asr.parakeet_engine", "ParakeetEngine", {}),
    "parakeet-stream": ("copilot.asr.parakeet_engine", "ParakeetStreamEngine", {}),
    "vosk": ("copilot.asr.vosk_engine", "VoskEngine", {}),
    "twopass": ("copilot.asr.twopass", "TwoPassEngine", {}),
    "webspeech": ("copilot.asr.webspeech", "WebSpeechAdapter", {}),
}


def create(name: str, **cfg: Any) -> AsrEngine:
    if name not in REGISTRY:
        raise KeyError(f"motor de voz desconocido: {name!r} (disponibles: {', '.join(sorted(REGISTRY))})")
    mod, cls, fixed = REGISTRY[name]
    return getattr(importlib.import_module(mod), cls)(**{**fixed, **cfg})


class AsrSupervisor:
    """Envuelve un motor principal y uno de respaldo (también es un AsrEngine).

    Un `feed` cuenta como fallo si lanza excepción o tarda más de `slow_factor` × `budget_ms`. Tras `max_strikes`
    fallos SEGUIDOS conmuta al respaldo (lo arranca con el mismo prompt/vocabulario) y lo anota en `events`.
    No vuelve al principal por sí solo (evita oscilar); `switch_back()` lo permite al operador."""

    def __init__(self, primary: AsrEngine, backup: AsrEngine, *, budget_ms: float = 1500.0, slow_factor: float = 2.0,
                 max_strikes: int = 3, clock: Callable[[], float] = time.monotonic):
        self.primary, self.backup = primary, backup
        self.budget_ms, self.slow_factor, self.max_strikes = budget_ms, slow_factor, max_strikes
        self.clock = clock
        self.active = primary
        self.strikes = 0
        self.events: list[dict] = []
        self._start_args: Optional[dict] = None
        self._backup_started = False

    @property
    def name(self) -> str:
        return self.active.name

    @property
    def switched(self) -> bool:
        return self.active is self.backup

    def start(self, *, prompt: str, vocabulary: list[str], language: str = "es") -> None:
        self._start_args = dict(prompt=prompt, vocabulary=vocabulary, language=language)
        try:
            self.primary.start(**self._start_args)
        except Exception as e:  # el principal ni siquiera arranca: directamente al respaldo
            self.events.append({"t_audio": 0.0, "from": self.primary.name, "to": self.backup.name,
                                "reason": f"start: {type(e).__name__}: {e}"})
            self._activate_backup()

    def _activate_backup(self) -> None:
        if not self._backup_started:
            self.backup.start(**(self._start_args or dict(prompt="", vocabulary=[])))
            self._backup_started = True
        self.active = self.backup

    def _strike(self, t_audio: float, reason: str) -> bool:
        self.strikes += 1
        if self.strikes >= self.max_strikes and self.active is self.primary:
            self.events.append({"t_audio": t_audio, "from": self.primary.name, "to": self.backup.name,
                                "reason": f"{self.strikes} fallos seguidos; último: {reason}"})
            try:
                self.primary.flush()
            except Exception:
                pass
            self._activate_backup()
            self.strikes = 0
            return True
        return False

    def feed(self, pcm16: bytes, t_audio: float) -> list[Transcript]:
        eng = self.active
        t = self.clock()
        try:
            out = eng.feed(pcm16, t_audio)
        except Exception as e:
            if eng is self.primary:
                self._strike(t_audio, f"{type(e).__name__}: {e}")
                return self.active.feed(pcm16, t_audio) if self.active is self.backup else []
            raise
        ms = (self.clock() - t) * 1000
        if eng is self.primary:
            if ms > self.slow_factor * self.budget_ms:
                self._strike(t_audio, f"feed tardó {ms:.0f} ms (> {self.slow_factor}×{self.budget_ms:.0f})")
            else:
                self.strikes = 0
        return out

    def flush(self) -> list[Transcript]:
        try:
            return self.active.flush()
        except Exception:
            if self.active is self.primary:
                self._activate_backup()
                self.events.append({"t_audio": -1.0, "from": self.primary.name, "to": self.backup.name,
                                    "reason": "excepción en flush"})
                return []
            raise

    def switch_back(self) -> None:
        self.active, self.strikes = self.primary, 0

    def close(self) -> None:
        for e in (self.primary, self.backup):
            try:
                e.close()
            except Exception:
                pass
