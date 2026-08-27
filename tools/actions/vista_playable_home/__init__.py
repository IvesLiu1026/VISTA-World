"""Fail-closed VISTA indoor action catalog support."""

from .catalog import (
    ActionCatalogContractError,
    CANONICAL_ACTION_IDS,
    LEGACY_ALIASES,
    load_catalog,
    require_verified_variant,
    resolve_action_id,
    seal_document,
    validate_catalog,
)

__all__ = [
    "ActionCatalogContractError",
    "CANONICAL_ACTION_IDS",
    "LEGACY_ALIASES",
    "load_catalog",
    "require_verified_variant",
    "resolve_action_id",
    "seal_document",
    "validate_catalog",
]
