"""Fail-closed HSSD scene assemblers.

The legacy living-room exports stay available lazily so the six-room worker can
bootstrap from a minimal sealed source bundle without importing unrelated
asset-provider modules.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "DEFAULT_BLENDER",
    "DEFAULT_SOURCE_RUN",
    "SceneAssemblyError",
    "build_assembly_plan",
    "execute_assembly",
]


def __getattr__(name: str) -> Any:
    if name not in __all__:
        raise AttributeError(name)
    from . import assembler

    return getattr(assembler, name)
