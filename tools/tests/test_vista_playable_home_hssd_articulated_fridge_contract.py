from __future__ import annotations

import copy
import json
from pathlib import Path

import jsonschema
import pytest

from ue.vista_playable_home import hssd_articulated_fridge_contract as contract


ROOT = Path(__file__).resolve().parents[2]


def test_schema_is_closed_and_canonical_contract_validates() -> None:
    schema = json.loads(contract.SCHEMA_PATH.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator.check_schema(schema)
    assert schema["additionalProperties"] is False
    document = contract.load_contract()
    contract.validate_contract(document)
    assert document["content_digest"] == contract.content_digest(document)
    assert document["acceptance"] == {
        "accepted": False,
        "status": "source_verified_pending_ue_import_runtime_and_human_review",
        "ue_imported": False,
        "runtime_verified": False,
        "human_reviewed": False,
        "gta_quality": False,
    }


def test_contract_pins_exact_link_joint_and_receptacle_topology() -> None:
    document = contract.load_contract()
    assert [item["role"] for item in document["links"]] == [
        "body",
        "primary_door",
        "secondary_door",
    ]
    assert [item["axis"] for item in document["joints"]] == [
        [0, 0, -1],
        [0, 0, 1],
    ]
    assert all(item["upper_rad"] == 2.7925267219543457 for item in document["joints"])
    assert all(item["velocity_rad_s"] == 3 for item in document["joints"])
    assert len(document["receptacles"]) == 11
    assert len({item["anchor_id"] for item in document["receptacles"]}) == 11


def test_contract_has_no_private_path_or_payload() -> None:
    raw = contract.CONTRACT_PATH.read_text(encoding="utf-8")
    for forbidden in ("/home/", "/root/", "/mnt/", "/data/", "file://"):
        assert forbidden not in raw
    assert not list((ROOT / "world_packs").rglob("*.glb"))
    assert not list((ROOT / "world_packs").rglob("*.urdf"))


def test_digest_and_duplicate_source_path_fail_closed() -> None:
    document = contract.load_contract()
    drift = copy.deepcopy(document)
    drift["runtime_binding"]["primary_open_angle_deg"] = 120
    with pytest.raises(contract.ArticulatedFridgeContractError, match="content digest"):
        contract.validate_contract(drift)

    duplicate = copy.deepcopy(document)
    duplicate["source_files"][-1] = copy.deepcopy(duplicate["source_files"][-2])
    duplicate["content_digest"] = contract.content_digest(duplicate)
    with pytest.raises(contract.ArticulatedFridgeContractError, match="source paths repeat"):
        contract.validate_contract(duplicate)


def test_unsafe_source_path_is_rejected_before_io(tmp_path: Path) -> None:
    tmp_path.mkdir(exist_ok=True)
    with pytest.raises(contract.ArticulatedFridgeContractError, match="unsafe"):
        contract._safe_source_path(tmp_path.resolve(), "../escape.glb")


def test_local_pinned_hssd_tree_verifies_when_present() -> None:
    document = contract.load_contract()
    if contract.DEFAULT_HSSD_ROOT.is_dir():
        receipt = contract.verify_source_tree(document, contract.DEFAULT_HSSD_ROOT)
        assert receipt["source_file_count"] == 16
        assert receipt["joint_count"] == 2
        assert receipt["receptacle_count"] == 11
        assert receipt["accepted"] is False
    else:
        # Portable environments still verify every committed byte/semantic
        # relation without weakening or skipping the external-payload gate.
        contract.validate_contract(document)
