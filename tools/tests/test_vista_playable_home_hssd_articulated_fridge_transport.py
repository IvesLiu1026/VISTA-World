from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path

import pytest

from blender.vista_playable_home_hssd import articulated_fridge_transport as module


def _sha(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def _fake_document(root: Path) -> dict:
    records = []
    for role in module.OUTPUT_ROLES:
        raw = (role + "-source").encode()
        path = root / f"{role}.glb"
        path.write_bytes(raw)
        records.append(
            {
                "role": role,
                "relative_path": path.name,
                "sha256": _sha(raw),
                "size_bytes": len(raw),
            }
        )
    return {
        "content_digest": "1" * 64,
        "contract_id": "hssd_side_by_side_fridge_r1",
        "semantic_target_id": "home.r1/room.kitchen_dining/entity.fridge.01",
        "dataset": {
            "provider": "HSSD",
            "license_spdx": "CC-BY-NC-4.0",
            "use_class": "private_noncommercial_research_only",
            "payload_policy": "external_payload_never_in_git",
        },
        "source_files": records,
    }


def _patch_transport(monkeypatch: pytest.MonkeyPatch, document: dict) -> None:
    monkeypatch.setattr(
        module.contract, "load_contract", lambda _path: copy.deepcopy(document)
    )
    monkeypatch.setattr(module.contract, "validate_contract", lambda _value: None)
    monkeypatch.setattr(
        module.contract,
        "verify_source_tree",
        lambda _value, _root: {
            "schema_version": "vista.playable-articulated-fridge-source-receipt/v1",
            "source_file_count": 3,
        },
    )
    gltf = {
        "extensionsRequired": ["KHR_texture_basisu"],
        "accessors": [{"min": [-0.4, -0.3, -0.8], "max": [0.4, 0.1, 0.8]}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}}]}],
    }
    monkeypatch.setattr(module, "read_glb", lambda _path: (copy.deepcopy(gltf), b""))
    monkeypatch.setattr(module, "uses_required_basisu", lambda value: True)

    def surrogate(_source: Path, output: Path) -> dict:
        output.write_bytes(b"surrogate")
        return {"mode": "basisu_material_index_surrogate", "source_material_count": 1}

    def rehydrate(_source: Path, _surrogate: Path, output: Path, **_kwargs) -> dict:
        output.write_bytes(b"transported-core-png")
        return {
            "mode": "KHR_texture_basisu_to_core_png",
            "converted_image_count": 1,
            "embedded_png_images_valid": True,
        }

    validation = {
        "self_contained": True,
        "single_buffer": True,
        "single_mesh": True,
        "embedded_png_images_valid": True,
        "image_payloads": [{"image_index": 0}],
    }
    monkeypatch.setattr(module, "write_blender_surrogate", surrogate)
    monkeypatch.setattr(module, "rehydrate_core_png_materials", rehydrate)
    monkeypatch.setattr(
        module, "validate_core_png_glb", lambda *_args: copy.deepcopy(validation)
    )


def test_three_link_transport_is_append_only_and_seals_source_pins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_root = tmp_path / "hssd"
    source_root.mkdir()
    document = _fake_document(source_root)
    _patch_transport(monkeypatch, document)
    node = tmp_path / "node"
    js = tmp_path / "basis.js"
    wasm = tmp_path / "basis.wasm"
    node.write_bytes(b"node")
    node.chmod(0o700)
    js.write_bytes(b"js")
    wasm.write_bytes(b"wasm")
    output = tmp_path / "transport"

    receipt = module.build_transport(
        contract_path=module.contract.CONTRACT_PATH,
        hssd_root=source_root,
        output_root=output,
        node_path=node,
        transcoder_js_path=js,
        transcoder_wasm_path=wasm,
    )

    assert receipt["schema_version"] == module.SCHEMA_VERSION
    assert receipt["accepted"] is False
    assert receipt["ue_imported"] is False
    assert [item["role"] for item in receipt["outputs"]] == list(module.OUTPUT_ROLES)
    assert all(
        item["source"]["sha256"] == document["source_files"][index]["sha256"]
        for index, item in enumerate(receipt["outputs"])
    )
    assert all(
        item["validation"]["embedded_png_images_valid"] is True
        for item in receipt["outputs"]
    )
    assert receipt["outputs"][1]["mesh_bounds"] == {
        "min_m": [-0.4, -0.3, -0.8],
        "max_m": [0.4, 0.1, 0.8],
    }
    raw = (output / module.RECEIPT_NAME).read_bytes()
    assert raw == module._canonical_json(receipt)
    assert json.loads(raw)["content_digest"] == module._content_digest(receipt)
    assert sorted(path.name for path in (output / "assets").iterdir()) == sorted(
        module.OUTPUT_NAMES.values()
    )


def test_manifest_hash_drift_fails_before_output_creation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_root = tmp_path / "hssd"
    source_root.mkdir()
    document = _fake_document(source_root)
    document["source_files"][0]["sha256"] = "0" * 64
    _patch_transport(monkeypatch, document)
    node = tmp_path / "node"
    js = tmp_path / "basis.js"
    wasm = tmp_path / "basis.wasm"
    for path in (node, js, wasm):
        path.write_bytes(b"x")
    node.chmod(0o700)
    output = tmp_path / "transport"

    with pytest.raises(module.ArticulatedFridgeTransportError, match="manifest pin"):
        module.build_transport(
            contract_path=module.contract.CONTRACT_PATH,
            hssd_root=source_root,
            output_root=output,
            node_path=node,
            transcoder_js_path=js,
            transcoder_wasm_path=wasm,
        )

    assert not output.exists()


def test_existing_output_root_is_never_reused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source_root = tmp_path / "hssd"
    source_root.mkdir()
    document = _fake_document(source_root)
    _patch_transport(monkeypatch, document)
    node = tmp_path / "node"
    js = tmp_path / "basis.js"
    wasm = tmp_path / "basis.wasm"
    for path in (node, js, wasm):
        path.write_bytes(b"x")
    node.chmod(0o700)
    output = tmp_path / "transport"
    output.mkdir()

    with pytest.raises(module.ArticulatedFridgeTransportError, match="already exists"):
        module.build_transport(
            contract_path=module.contract.CONTRACT_PATH,
            hssd_root=source_root,
            output_root=output,
            node_path=node,
            transcoder_js_path=js,
            transcoder_wasm_path=wasm,
        )
