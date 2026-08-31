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
from .catalog_v2 import (
    CANONICAL_ACTION_IDS as CANONICAL_ACTION_IDS_V2,
    EXPECTED_WIRE_BINDINGS as EXPECTED_WIRE_BINDINGS_V2,
    ValidatedActionCatalogV2,
    load_catalog as load_catalog_v2,
    require_verified_variant as require_verified_variant_v2,
    resolve_action_id as resolve_action_id_v2,
    validate_catalog as validate_catalog_v2,
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
    "CANONICAL_ACTION_IDS_V2",
    "EXPECTED_WIRE_BINDINGS_V2",
    "ValidatedActionCatalogV2",
    "load_catalog_v2",
    "require_verified_variant_v2",
    "resolve_action_id_v2",
    "validate_catalog_v2",
]
