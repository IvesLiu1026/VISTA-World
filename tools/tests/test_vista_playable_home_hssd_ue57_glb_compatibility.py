from __future__ import annotations

import copy
import hashlib
import json
import pathlib
import struct
import sys

import pytest


ROOT = pathlib.Path(__file__).resolve().parents[2]
COMMANDLET_ROOT = ROOT / "tools/ue/vista_playable_home"
sys.path.insert(0, str(COMMANDLET_ROOT))
import hssd_ue57_glb_compatibility as compat  # noqa: E402


SCRIPT_SHA = "a" * 64


def _glb(
    *,
    transmission: dict | None,
    clearcoat: dict | None,
    unknown_transmission: bool = False,
) -> tuple[bytes, dict]:
    extensions = {}
    if transmission is not None:
        extensions[compat.TRANSMISSION] = copy.deepcopy(transmission)
    if clearcoat is not None:
        extensions[compat.CLEARCOAT] = copy.deepcopy(clearcoat)
    if unknown_transmission:
        extensions[compat.TRANSMISSION]["futureField"] = 1
    material = {
        "name": "TestMaterial",
        "pbrMetallicRoughness": {"baseColorTexture": {"index": 0}},
        "normalTexture": {"index": 1},
        "extensions": extensions,
    }
    graph = {
        "asset": {"version": "2.0"},
        "extensionsUsed": sorted(extensions),
        "materials": [material],
        "meshes": [
            {
                "primitives": [
                    {
                        "attributes": {"POSITION": 0},
                        "indices": 1,
                        "material": 0,
                    }
                ]
            }
        ],
        "accessors": [{"count": 3}, {"count": 3}],
        "bufferViews": [{"buffer": 0, "byteLength": 16}],
        "buffers": [{"byteLength": 16}],
        "textures": [{"source": 0}, {"source": 1}],
        "images": [
            {"bufferView": 0, "mimeType": "image/png"},
            {"bufferView": 0, "mimeType": "image/png"},
        ],
        "samplers": [],
        "nodes": [{"mesh": 0}],
        "scenes": [{"nodes": [0]}],
        "scene": 0,
        "extras": {"mustRemain": True},
    }
    json_raw = compat.canonical_json(graph)
    json_raw += b" " * ((4 - len(json_raw) % 4) % 4)
    binary = bytes(range(16))
    body = (
        struct.pack("<II", len(json_raw), compat.GLB_JSON_CHUNK)
        + json_raw
        + struct.pack("<II", len(binary), 0x004E4942)
        + binary
    )
    raw = struct.pack("<4sII", compat.GLB_MAGIC, 2, 12 + len(body)) + body
    return raw, graph


def _derive(raw: bytes):
    return compat.derive_glb(
        raw,
        source_asset_id="hssd.static.fixture",
        transform_script_sha256=SCRIPT_SHA,
    )


def _raw_json_glb(payload: bytes) -> bytes:
    payload += b" " * ((4 - len(payload) % 4) % 4)
    body = struct.pack("<II", len(payload), compat.GLB_JSON_CHUNK) + payload
    return struct.pack("<4sII", compat.GLB_MAGIC, 2, 12 + len(body)) + body


def test_noop_transmission_is_removed_without_changing_clearcoat_or_binary() -> None:
    raw, source_graph = _glb(
        transmission={"transmissionFactor": 0},
        clearcoat={
            "clearcoatFactor": 1,
            "clearcoatTexture": {"index": 1},
        },
    )

    output, receipt = _derive(raw)
    output_graph, output_chunks = compat._parse_glb(output)
    source_parsed, source_chunks = compat._parse_glb(raw)

    assert output_chunks[1:] == source_chunks[1:]
    assert output_graph["extras"] == source_graph["extras"]
    assert output_graph["meshes"] == source_graph["meshes"]
    assert output_graph["textures"] == source_graph["textures"]
    assert compat.TRANSMISSION not in output_graph["materials"][0]["extensions"]
    assert (
        output_graph["materials"][0]["extensions"][compat.CLEARCOAT]
        == (source_parsed["materials"][0]["extensions"][compat.CLEARCOAT])
    )
    assert receipt["status"] == "derived_ue57_compatible_candidate"
    assert receipt["removed_noop_transmission"] == [
        {
            "material_index": 0,
            "material_name": "TestMaterial",
            "transmission": {"transmissionFactor": 0},
        }
    ]
    assert receipt["retained_active_dual_conflicts"] == []
    assert receipt["blocks_full_material_fidelity"] is False
    compat.validate_receipt(receipt)


def test_derivation_is_byte_deterministic() -> None:
    raw, _ = _glb(
        transmission={},
        clearcoat={"clearcoatFactor": 0.7, "clearcoatTexture": {"index": 1}},
    )

    first_output, first_receipt = _derive(raw)
    second_output, second_receipt = _derive(raw)

    assert first_output == second_output
    assert first_receipt == second_receipt
    assert first_receipt["output_sha256"] == hashlib.sha256(first_output).hexdigest()


def test_active_dual_material_is_retained_and_blocks_full_fidelity() -> None:
    raw, _ = _glb(
        transmission={"transmissionFactor": 1},
        clearcoat={"clearcoatFactor": 1},
    )

    output, receipt = _derive(raw)
    graph, _chunks = compat._parse_glb(output)

    assert graph["materials"][0]["extensions"][compat.TRANSMISSION] == {
        "transmissionFactor": 1
    }
    assert receipt["removed_noop_transmission"] == []
    assert len(receipt["retained_active_transmission"]) == 1
    assert len(receipt["retained_active_dual_conflicts"]) == 1
    assert receipt["blocks_full_material_fidelity"] is True
    assert receipt["status"] == "derived_with_active_dual_material_blocker"


def test_active_transmission_without_clearcoat_is_retained() -> None:
    raw, _ = _glb(
        transmission={"transmissionFactor": 0.1},
        clearcoat={"clearcoatFactor": 0},
    )

    output, receipt = _derive(raw)
    graph, _chunks = compat._parse_glb(output)

    assert compat.TRANSMISSION in graph["materials"][0]["extensions"]
    assert receipt["blocks_full_material_fidelity"] is False
    assert receipt["retained_active_dual_conflicts"] == []


def test_unknown_transmission_field_fails_closed() -> None:
    raw, _ = _glb(
        transmission={"transmissionFactor": 0},
        clearcoat={"clearcoatFactor": 1},
        unknown_transmission=True,
    )

    with pytest.raises(compat.CompatibilityError, match="unknown fields"):
        _derive(raw)


@pytest.mark.parametrize(
    "transmission",
    [
        {"transmissionFactor": None},
        {"transmissionFactor": 0, "transmissionTexture": None},
    ],
)
def test_explicit_null_transmission_value_fails_closed(transmission: dict) -> None:
    raw, _ = _glb(transmission=transmission, clearcoat={"clearcoatFactor": 1})

    with pytest.raises(compat.CompatibilityError):
        _derive(raw)


@pytest.mark.parametrize(
    "clearcoat",
    [None, {"clearcoatFactor": None}],
)
def test_explicit_null_active_clearcoat_value_fails_closed(clearcoat) -> None:
    raw, graph = _glb(
        transmission={"transmissionFactor": 1},
        clearcoat={"clearcoatFactor": 1},
    )
    graph["materials"][0]["extensions"][compat.CLEARCOAT] = clearcoat
    graph["extensionsUsed"] = [compat.TRANSMISSION, compat.CLEARCOAT]
    _source_graph, chunks = compat._parse_glb(raw)
    raw = compat._pack_glb(graph, chunks)

    with pytest.raises(compat.CompatibilityError):
        _derive(raw)


def test_required_transmission_cannot_be_removed() -> None:
    raw, graph = _glb(
        transmission={"transmissionFactor": 0},
        clearcoat={"clearcoatFactor": 1},
    )
    graph["extensionsRequired"] = [compat.TRANSMISSION]
    _source_graph, chunks = compat._parse_glb(raw)
    raw = compat._pack_glb(graph, chunks)

    with pytest.raises(compat.CompatibilityError, match="required"):
        _derive(raw)


def test_unrelated_extension_declaration_order_is_preserved() -> None:
    raw, graph = _glb(
        transmission={"transmissionFactor": 0},
        clearcoat={"clearcoatFactor": 1},
    )
    graph["extensionsUsed"] = ["EXT_z", compat.TRANSMISSION, compat.CLEARCOAT, "EXT_a"]
    _source_graph, chunks = compat._parse_glb(raw)
    raw = compat._pack_glb(graph, chunks)

    output, receipt = _derive(raw)
    output_graph, _output_chunks = compat._parse_glb(output)

    assert output_graph["extensionsUsed"] == ["EXT_z", compat.CLEARCOAT, "EXT_a"]
    assert receipt["extensions_used_before"] == graph["extensionsUsed"]
    assert receipt["extensions_used_after"] == output_graph["extensionsUsed"]
    assert receipt["changed_json_pointers"] == [
        "/extensionsUsed",
        "/materials/0/extensions/KHR_materials_transmission",
    ]


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (b'{"asset":{"version":"2.0"},"asset":{"version":"2.0"}}', "duplicate"),
        (b'{"asset":{"version":"2.0"},"value":NaN}', "non-finite"),
    ],
)
def test_noncanonical_json_is_rejected(payload: bytes, message: str) -> None:
    with pytest.raises(compat.CompatibilityError, match=message):
        compat._parse_glb(_raw_json_glb(payload))


def test_asset_id_injection_is_rejected() -> None:
    raw, _ = _glb(
        transmission={"transmissionFactor": 0},
        clearcoat={"clearcoatFactor": 1},
    )

    with pytest.raises(compat.CompatibilityError, match="asset ID"):
        compat.derive_glb(
            raw,
            source_asset_id="hssd.static.fixture/../../escape",
            transform_script_sha256=SCRIPT_SHA,
        )


def test_receipt_tamper_is_rejected() -> None:
    raw, _ = _glb(
        transmission={"transmissionFactor": 0},
        clearcoat={"clearcoatFactor": 1},
    )
    output, receipt = _derive(raw)
    tampered = json.loads(json.dumps(receipt))
    tampered["output_bytes"] += 1
    tampered["content_digest"] = compat._content_digest(tampered)

    with pytest.raises(compat.CompatibilityError, match="receipt differs"):
        compat.validate_derivation(
            raw,
            output,
            tampered,
            source_asset_id="hssd.static.fixture",
            transform_script_sha256=SCRIPT_SHA,
        )


def test_semantically_invalid_receipt_fails_even_with_recomputed_digest() -> None:
    raw, _ = _glb(
        transmission={"transmissionFactor": 0},
        clearcoat={"clearcoatFactor": 1},
    )
    _output, receipt = _derive(raw)
    tampered = json.loads(json.dumps(receipt))
    tampered["status"] = "accepted"
    tampered["content_digest"] = compat._content_digest(tampered)

    with pytest.raises(compat.CompatibilityError, match="identity or digest"):
        compat.validate_receipt(tampered)
