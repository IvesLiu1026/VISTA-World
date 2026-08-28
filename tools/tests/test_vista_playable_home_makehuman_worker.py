from __future__ import annotations

import ast
import json
import pathlib
import struct

import pytest

from tools.blender.vista_playable_home_makehuman import blender_worker as worker


def _glb(
    materials: list[dict[str, str]],
    meshes: list[dict[str, object]] | None = None,
    accessors: list[dict[str, object]] | None = None,
    buffer_views: list[dict[str, object]] | None = None,
    binary: bytes = b"",
) -> bytes:
    graph: dict[str, object] = {
        "asset": {"version": "2.0"},
        "materials": materials,
        "meshes": meshes or [],
        "accessors": accessors or [],
    }
    if binary:
        graph["buffers"] = [{"byteLength": len(binary)}]
        graph["bufferViews"] = buffer_views or []
    document = json.dumps(
        graph,
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    document += b" " * (-len(document) % 4)
    body = struct.pack("<II", len(document), 0x4E4F534A) + document
    if binary:
        binary += b"\0" * (-len(binary) % 4)
        body += struct.pack("<II", len(binary), 0x004E4942) + binary
    return struct.pack("<4sII", b"glTF", 2, 12 + len(body)) + body


def test_glb_alpha_mode_gate_accepts_exact_opaque_and_mask_contract(
    tmp_path: pathlib.Path,
) -> None:
    path = tmp_path / "character.glb"
    path.write_bytes(
        _glb(
            [
                {"name": "body"},
                {"name": "hair", "alphaMode": "MASK"},
            ]
        )
    )

    assert worker._verify_glb_material_alpha_modes(
        path, {"body": "OPAQUE", "hair": "MASK"}
    ) == {"body": "OPAQUE", "hair": "MASK"}


def test_glb_alpha_mode_gate_rejects_translucent_character_material(
    tmp_path: pathlib.Path,
) -> None:
    path = tmp_path / "character.glb"
    path.write_bytes(_glb([{"name": "body", "alphaMode": "BLEND"}]))

    with pytest.raises(worker.WorkerError, match="GLB alpha modes differ"):
        worker._verify_glb_material_alpha_modes(path, {"body": "OPAQUE"})


def test_glb_face_target_gate_requires_one_complete_mesh(
    tmp_path: pathlib.Path,
) -> None:
    path = tmp_path / "character.glb"
    path.write_bytes(
        _glb(
            [],
            [
                {
                    "name": "body",
                    "extras": {"targetNames": ["smile", "blink"]},
                    "primitives": [
                        {
                            "attributes": {"POSITION": 0},
                            "targets": [{"POSITION": 1}, {"POSITION": 2}],
                        }
                    ],
                },
                {"name": "shirt", "extras": {"targetNames": ["smile"]}},
            ],
            [
                {"componentType": 5126, "count": 3, "type": "VEC3", "bufferView": 0},
                {"componentType": 5126, "count": 3, "type": "VEC3", "bufferView": 1},
                {"componentType": 5126, "count": 3, "type": "VEC3", "bufferView": 2},
            ],
            [
                {"buffer": 0, "byteOffset": 0, "byteLength": 36},
                {"buffer": 0, "byteOffset": 36, "byteLength": 36},
                {"buffer": 0, "byteOffset": 72, "byteLength": 36},
            ],
            b"\0" * 108,
        )
    )

    observed = worker._verify_glb_face_targets(path, ("smile", "blink"))
    assert observed["verified_mesh"] == "body"
    assert observed["required_target_count"] == 2

    with pytest.raises(worker.WorkerError, match="complete facial target mesh"):
        worker._verify_glb_face_targets(path, ("smile", "jawOpen"))

    metadata_only = tmp_path / "metadata-only.glb"
    metadata_only.write_bytes(
        _glb(
            [],
            [{"name": "body", "extras": {"targetNames": ["smile", "blink"]}}],
        )
    )
    with pytest.raises(worker.WorkerError, match="complete facial target mesh"):
        worker._verify_glb_face_targets(metadata_only, ("smile", "blink"))


@pytest.mark.parametrize(
    "accessors,targets,buffer_views",
    [
        (
            [
                {"componentType": 5126, "type": "VEC3", "bufferView": 0},
                {"componentType": 5126, "type": "VEC3", "bufferView": 1},
                {"componentType": 5126, "type": "VEC3", "bufferView": 2},
            ],
            [{"POSITION": 1}, {"POSITION": 2}],
            [
                {"buffer": 0, "byteOffset": 0, "byteLength": 36},
                {"buffer": 0, "byteOffset": 36, "byteLength": 36},
                {"buffer": 0, "byteOffset": 72, "byteLength": 36},
            ],
        ),
        (
            [
                {"componentType": 5126, "count": 3, "type": "VEC3", "bufferView": 0},
                {"componentType": 5126, "count": 3, "type": "VEC3", "bufferView": 1},
            ],
            [{"POSITION": 1}, {"POSITION": 1}],
            [
                {"buffer": 0, "byteOffset": 0, "byteLength": 36},
                {"buffer": 0, "byteOffset": 36, "byteLength": 36},
            ],
        ),
        (
            [
                {"componentType": 5126, "count": 3, "type": "VEC3", "bufferView": 999},
                {"componentType": 5126, "count": 3, "type": "VEC3", "bufferView": 1},
                {"componentType": 5126, "count": 3, "type": "VEC3", "bufferView": 2},
            ],
            [{"POSITION": 1}, {"POSITION": 2}],
            [
                {"buffer": 0, "byteOffset": 0, "byteLength": 36},
                {"buffer": 0, "byteOffset": 36, "byteLength": 36},
                {"buffer": 0, "byteOffset": 72, "byteLength": 36},
            ],
        ),
    ],
    ids=("missing-counts", "reused-accessor", "invalid-buffer-view"),
)
def test_glb_face_target_gate_rejects_fake_morph_storage(
    tmp_path: pathlib.Path,
    accessors: list[dict[str, object]],
    targets: list[dict[str, int]],
    buffer_views: list[dict[str, object]],
) -> None:
    path = tmp_path / "fake.glb"
    path.write_bytes(
        _glb(
            [],
            [
                {
                    "name": "body",
                    "extras": {"targetNames": ["smile", "blink"]},
                    "primitives": [{"attributes": {"POSITION": 0}, "targets": targets}],
                }
            ],
            accessors,
            buffer_views,
            b"\0" * 108,
        )
    )
    with pytest.raises(worker.WorkerError, match="complete facial target mesh"):
        worker._verify_glb_face_targets(path, ("smile", "blink"))


def test_worker_pins_cc0_skin_provenance_and_has_no_network_surface() -> None:
    assert worker.EXPECTED_LICENSE == "CC0-1.0"
    assert (
        worker.SKINS_PACK_SHA256
        == "7495ab99287053bd19ff1636114e64b608994d9f7437fea6cc75ea387f96dba9"
    )
    assert (
        worker.FACEUNITS_PACK_SHA256
        == "d113107bd7eb59f3af4df6fc0ec29bfcc593f496d0b336aec14f086a80ce7146"
    )
    assert (
        worker.VISEMES_PACK_SHA256
        == "a69ab6fb95ddd5f56f70acc7e859f5f9c6ae613c527d577ea1571eff2183d29e"
    )
    source = pathlib.Path(worker.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported_roots = {
        alias.name.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported_roots.update(
        node.module.split(".", 1)[0]
        for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom) and node.module
    )
    assert not imported_roots & {"requests", "socket", "urllib", "http", "ftplib"}
    assert '"gta_level_quality": False' in source
    assert '"photoreal_character_accepted": False' in source
