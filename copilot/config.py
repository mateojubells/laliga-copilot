"""Configuración: config/default.yaml ← config/local.yaml ← variables COPILOT_SECCION__CLAVE."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parent.parent


def _merge(a: dict, b: dict) -> dict:
    out = dict(a)
    for k, v in b.items():
        out[k] = _merge(out[k], v) if isinstance(v, dict) and isinstance(out.get(k), dict) else v
    return out


def load(env: dict[str, str] | None = None, root: Path = ROOT) -> dict[str, Any]:
    cfg: dict[str, Any] = {}
    for name in ("default.yaml", "local.yaml"):
        f = root / "config" / name
        if f.exists():
            cfg = _merge(cfg, yaml.safe_load(f.read_text(encoding="utf-8")) or {})
    for k, v in (os.environ if env is None else env).items():
        if not k.startswith("COPILOT_"):
            continue
        node, path = cfg, k[len("COPILOT_"):].lower().split("__")
        for part in path[:-1]:
            node = node.setdefault(part, {})
        node[path[-1]] = yaml.safe_load(v)
    return cfg


@lru_cache(maxsize=1)
def settings() -> dict[str, Any]:
    return load()
