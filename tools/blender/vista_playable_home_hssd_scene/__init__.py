"""Fail-closed HSSD living-room research scene assembler."""

from .assembler import (
    DEFAULT_BLENDER,
    DEFAULT_SOURCE_RUN,
    SceneAssemblyError,
    build_assembly_plan,
    execute_assembly,
)

__all__ = [
    "DEFAULT_BLENDER",
    "DEFAULT_SOURCE_RUN",
    "SceneAssemblyError",
    "build_assembly_plan",
    "execute_assembly",
]
