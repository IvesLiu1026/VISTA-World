from __future__ import annotations

import copy
import json
from pathlib import Path

import jsonschema
import pytest

from actions.vista_playable_home import catalog_v4, catalog_v5


ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / "world_packs/vista_playable_home_r1"
CATALOG = catalog_v5.load_catalog(PACK / "action_catalogs/vista_indoor_actions_r5.json")
SOURCE = catalog_v4.load_catalog(PACK / "action_catalogs/vista_indoor_actions_r4.json")


def assert_error(code: str, value: dict, **kwargs: object) -> None:
    with pytest.raises(catalog_v5.ActionCatalogContractError) as caught:
        catalog_v5.validate_catalog(value, **kwargs)
    assert caught.value.code == code, str(caught.value)


def test_v5_schema_is_meta_valid_and_every_object_is_closed() -> None:
    schema = json.loads(catalog_v5.SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)

    def visit(node: object, path: str) -> None:
        if isinstance(node, dict):
            if node.get("type") == "object":
                assert node.get("additionalProperties") is False, path
            for key, value in node.items():
                visit(value, f"{path}.{key}")
        elif isinstance(node, list):
            for index, value in enumerate(node):
                visit(value, f"{path}[{index}]")

    visit(schema, "$")


def test_v5_preserves_exact_38_record_v4_prefix_then_appends_storage() -> None:
    token = catalog_v5.validate_catalog(CATALOG)
    assert CATALOG["actions"][:38] == SOURCE["actions"]
    assert tuple(item["action_id"] for item in CATALOG["actions"]) == (
        *catalog_v4.CANONICAL_ACTION_IDS,
        "storage.insert",
        "storage.remove",
    )
    assert (
        CATALOG["candidate_animation_sources"] == SOURCE["candidate_animation_sources"]
    )
    assert CATALOG["accepted"] is False
    assert CATALOG["runtime_execution_authorized"] is False

    for action_id in catalog_v4.CANONICAL_ACTION_IDS:
        actual = dict(catalog_v5.resolve_action(token, action_id))
        source = dict(catalog_v4.resolve_action(token._source_token, action_id))
        assert actual == source


def test_storage_actions_are_distinct_native_actions_not_legacy_aliases() -> None:
    token = catalog_v5.validate_catalog(CATALOG)
    legacy = catalog_v5.resolve_action(token, "insert")
    storage_insert = catalog_v5.resolve_storage_wire_action(token, "insert")
    storage_remove = catalog_v5.resolve_storage_wire_action(token, "remove")
    assert legacy["action_id"] == "insert"
    assert storage_insert["action_id"] == "storage.insert"
    assert storage_remove["action_id"] == "storage.remove"
    assert storage_insert["aliases"] == []
    assert storage_remove["aliases"] == []
    assert storage_insert["runtime_binding"] == {
        "wire_action": "insert",
        "backend_action": "Insert",
        "runtime_type": "insert",
    }
    with pytest.raises(catalog_v5.ActionCatalogContractError):
        catalog_v5.resolve_action(token, "remove")


def test_storage_animation_gate_requires_dedicated_contact_and_completion() -> None:
    token = catalog_v5.validate_catalog(CATALOG)
    for action_id in catalog_v5.STORAGE_ACTION_IDS:
        action = catalog_v5.resolve_action(token, action_id)
        assert action["effect"] == {
            "effect_id": "multi_entity_state",
            "commit_phase": "contact",
        }
        assert action["animation_acceptance"] == {
            "status": "blocked",
            "montage_policy": "dedicated_action_montage_required",
            "contact_signal": "required",
            "completion_signal": "required",
            "prohibited_reuse_action_ids": ["pick_up", "place"],
        }
        assert action["readiness"]["animation"] == {
            "status": "blocked",
            "evidence_digest": None,
        }
        assert action["readiness"]["runtime_acceptance"]["status"] == "blocked"
        with pytest.raises(catalog_v5.ActionCatalogContractError) as caught:
            catalog_v5.require_runtime_accepted(token, action_id)
        assert caught.value.code == "VISTA_ACTION_V5_RUNTIME_NOT_ACCEPTED"


def test_prefix_native_gate_and_acceptance_tamper_fail_closed() -> None:
    prefix = copy.deepcopy(CATALOG)
    prefix["actions"][13]["readiness"]["backend"]["status"] = "candidate"
    assert_error(
        "VISTA_ACTION_V5_SOURCE_PREFIX_DRIFT", catalog_v5.seal_document(prefix)
    )

    reused = copy.deepcopy(CATALOG)
    reused["actions"][-2]["native_definition"]["animation_acceptance"][
        "prohibited_reuse_action_ids"
    ] = []
    assert_error("VISTA_ACTION_V5_SCHEMA_INVALID", catalog_v5.seal_document(reused))

    accepted = copy.deepcopy(CATALOG)
    accepted["runtime_execution_authorized"] = True
    assert_error("VISTA_ACTION_V5_SCHEMA_INVALID", catalog_v5.seal_document(accepted))

    widened = copy.deepcopy(CATALOG)
    widened["shell_command"] = "unreal-editor /Game/Anything"
    widened = catalog_v5.seal_document(widened)
    assert_error("VISTA_ACTION_PROHIBITED_FIELD", widened)


def test_strict_loader_rejects_duplicate_and_nonfinite_json(tmp_path: Path) -> None:
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text(
        '{"schema_version":"x","schema_version":"y"}', encoding="utf-8"
    )
    with pytest.raises(catalog_v5.ActionCatalogContractError) as caught:
        catalog_v5.load_catalog(duplicate)
    assert caught.value.code == "VISTA_ACTION_DUPLICATE_KEY"

    nonfinite = tmp_path / "nonfinite.json"
    nonfinite.write_text('{"value":NaN}', encoding="utf-8")
    with pytest.raises(catalog_v5.ActionCatalogContractError) as caught:
        catalog_v5.load_catalog(nonfinite)
    assert caught.value.code == "VISTA_ACTION_JSON_NON_FINITE"
