from __future__ import annotations

import ast
import json
import pathlib
import struct

import pytest

from tools.blender.vista_playable_home_makehuman import blender_worker as worker


def _glb(materials: list[dict[str, str]]) -> bytes:
    document = json.dumps(
        {"asset": {"version": "2.0"}, "materials": materials},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    document += b" " * (-len(document) % 4)
    body = struct.pack("<II", len(document), 0x4E4F534A) + document
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


def test_worker_pins_cc0_skin_provenance_and_has_no_network_surface() -> None:
    assert worker.EXPECTED_LICENSE == "CC0-1.0"
    assert (
        worker.SKINS_PACK_SHA256
        == "7495ab99287053bd19ff1636114e64b608994d9f7437fea6cc75ea387f96dba9"
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
