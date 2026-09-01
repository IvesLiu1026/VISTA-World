from __future__ import annotations

import copy
import json
from pathlib import Path

import jsonschema
import pytest

from actions.vista_playable_home import catalog_v3, catalog_v4


ROOT = Path(__file__).resolve().parents[2]
PACK = ROOT / "world_packs/vista_playable_home_r1"
CATALOG = catalog_v4.load_catalog(PACK / "action_catalogs/vista_indoor_actions_r4.json")
SOURCE = catalog_v3.load_catalog(PACK / "action_catalogs/vista_indoor_actions_r3.json")


def assert_error(code: str, value: dict, **kwargs: object) -> None:
    with pytest.raises(catalog_v4.ActionCatalogContractError) as caught:
        catalog_v4.validate_catalog(value, **kwargs)
    assert caught.value.code == code, str(caught.value)


def test_v4_schema_is_meta_valid_and_every_object_is_closed() -> None:
    schema = json.loads(catalog_v4.SCHEMA_PATH.read_text(encoding="utf-8"))
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


def test_v4_preserves_all_exact_v3_semantics_and_binds_r15_candidate() -> None:
    token = catalog_v4.validate_catalog(CATALOG)
    source_token = catalog_v3.validate_catalog(SOURCE)
    assert CATALOG["source_catalog_binding"] == catalog_v4.SOURCE_CATALOG_BINDING
    assert CATALOG["candidate_animation_sources"][-1] == catalog_v4.R15_SOURCE
    assert tuple(item["action_id"] for item in CATALOG["actions"]) == catalog_v4.CANONICAL_ACTION_IDS
    for action_id in catalog_v4.CANONICAL_ACTION_IDS:
        actual = dict(catalog_v4.resolve_action(token, action_id))
        expected = dict(catalog_v3.resolve_action(source_token, action_id))
        actual.pop("readiness")
        expected.pop("readiness")
        assert actual == expected


def test_new_event_actions_are_candidate_only_and_never_runtime_accepted() -> None:
    token = catalog_v4.validate_catalog(CATALOG)
    for action_id in ("sit_down", "seated_idle", "stand_up", "pour"):
        action = catalog_v4.resolve_action(token, action_id)
        assert action["readiness"]["animation"]["status"] == "candidate"
        assert action["readiness"]["runtime_acceptance"] == {
            "status": "blocked",
            "evidence_digest": None,
        }
    for action in CATALOG["actions"]:
        for layer in action["readiness"].values():
            assert layer["status"] != "verified"
            assert layer["evidence_digest"] is None
    with pytest.raises(catalog_v4.ActionCatalogContractError) as caught:
        catalog_v4.require_runtime_accepted(token, "pour")
    assert caught.value.code == "VISTA_ACTION_V4_RUNTIME_NOT_ACCEPTED"


def test_forged_readiness_and_unknown_keys_fail_closed() -> None:
    forged = copy.deepcopy(CATALOG)
    pour = next(item for item in forged["actions"] if item["action_id"] == "pour")
    pour["readiness"]["runtime_acceptance"] = {"status": "verified", "evidence_digest": "f" * 64}
    forged = catalog_v4.seal_document(forged)
    assert_error("VISTA_ACTION_V4_READINESS_INVALID", forged)

    widened = copy.deepcopy(CATALOG)
    widened["nlp_fallback_command"] = "unreal-editor /Game/anything"
    widened = catalog_v4.seal_document(widened)
    assert_error("VISTA_ACTION_V4_SCHEMA_INVALID", widened)


def test_r15_digest_or_required_action_tamper_is_rejected() -> None:
    profile = catalog_v4.load_catalog(catalog_v4.R15_PROFILE_PATH)
    profile["clips"] = [clip for clip in profile["clips"] if clip.get("event_action") != "pour"]
    profile = catalog_v4.seal_document(profile)
    assert_error("VISTA_ACTION_V4_R15_PROFILE_MISMATCH", CATALOG, r15_profile=profile)
