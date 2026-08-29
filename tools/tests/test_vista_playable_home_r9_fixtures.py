from __future__ import annotations

import copy
import json
import pathlib
import struct
import zlib

import pytest

from tools.blender.vista_playable_home_r9_fixtures import forge


def _fake_toolchain() -> dict:
    return {
        "blender": {
            "path": str(forge.DEFAULT_BLENDER),
            "sha256": forge.PINNED_BLENDER_SHA256,
            "size_bytes": forge.PINNED_BLENDER_BYTES,
            "version": forge.PINNED_BLENDER_VERSION,
            "execution_device": "CPU",
        },
        "bubblewrap": {
            "path": str(forge.DEFAULT_BWRAP),
            "sha256": forge.PINNED_BWRAP_SHA256,
            "size_bytes": forge.PINNED_BWRAP_BYTES,
            "network_namespace": "unshared",
            "device_policy": "private_dev_without_gpu_nodes",
        },
    }


def _glb_bytes(archetype: dict, **overrides: object) -> bytes:
    expected = archetype["expected_mesh_local_bounds_cm"]
    minimum = expected["min_cm"]
    maximum = expected["max_cm"]
    gltf_min = [minimum[0] / 100.0, minimum[2] / 100.0, -maximum[1] / 100.0]
    gltf_max = [maximum[0] / 100.0, maximum[2] / 100.0, -minimum[1] / 100.0]
    document = {
        "asset": {"version": "2.0", "generator": "fixture-test"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [
            {"name": archetype["root_node_name"], "children": [1]},
            {"name": archetype["mesh_node_name"], "mesh": 0},
        ],
        "meshes": [
            {
                "name": archetype["mesh_name"],
                "primitives": [
                    {"attributes": {"POSITION": 0}, "material": 0, "mode": 4},
                    {"attributes": {"POSITION": 1}, "material": 1, "mode": 4},
                ],
            }
        ],
        "materials": [
            {
                "name": name,
                "pbrMetallicRoughness": {
                    "baseColorFactor": [0.5, 0.5, 0.5, 1.0],
                    "metallicFactor": 0.5,
                    "roughnessFactor": 0.5,
                },
            }
            for name in archetype["material_names"]
        ],
        "accessors": [
            {
                "bufferView": index,
                "componentType": 5126,
                "count": 1,
                "type": "VEC3",
                "min": gltf_min,
                "max": gltf_max,
            }
            for index in range(2)
        ],
        "bufferViews": [
            {"buffer": 0, "byteOffset": index * 12, "byteLength": 12}
            for index in range(2)
        ],
        "buffers": [{"byteLength": 24}],
    }
    document.update(overrides)
    json_raw = json.dumps(document, separators=(",", ":"), sort_keys=True).encode()
    json_raw += b" " * (-len(json_raw) % 4)
    binary = b"\0" * 24
    total = 12 + 8 + len(json_raw) + 8 + len(binary)
    return b"".join(
        (
            struct.pack("<4sII", b"glTF", 2, total),
            struct.pack("<II", len(json_raw), 0x4E4F534A),
            json_raw,
            struct.pack("<II", len(binary), 0x004E4942),
            binary,
        )
    )


def _png_bytes(*, blank: bool = False) -> bytes:
    width = height = 256
    rows = bytearray()
    for y in range(height):
        rows.append(0)
        for x in range(width):
            visible = not blank and 64 <= x < 192 and 64 <= y < 192
            rows.extend(
                (
                    x if visible else 0,
                    y if visible else 0,
                    (x + y) % 256 if visible else 0,
                    255 if visible else 0,
                )
            )

    def chunk(kind: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + kind
            + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
        )

    return b"".join(
        (
            b"\x89PNG\r\n\x1a\n",
            chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)),
            chunk(b"IDAT", zlib.compress(bytes(rows), level=9)),
            chunk(b"IEND", b""),
        )
    )


def _write_artifact_fixture(root: pathlib.Path) -> tuple[dict, dict]:
    profile = forge.load_profile()
    recipe = forge.load_recipe()
    for directory in ("artifacts", "previews", "receipts"):
        (root / directory).mkdir(parents=True, exist_ok=True)
    plan = {
        "content_digest": "a" * 64,
        "profile": {
            **forge.file_pin(forge.PROFILE_PATH),
            "content_digest": profile["content_digest"],
        },
        "recipe": {
            **forge.file_pin(forge.RECIPE_PATH),
            "content_digest": recipe["content_digest"],
        },
        "toolchain": _fake_toolchain(),
        "archetypes": [],
        "ue_package_inventory": {
            "package_root": profile["fixture_imports"]["package_root"],
            "exact_package_names": profile["fixture_imports"]["exact_package_names"],
            "expected_package_count": 9,
        },
    }
    worker_rows = []
    for archetype in recipe["archetypes"]:
        archetype_id = archetype["archetype_id"]
        paths = forge.EXPECTED_ARTIFACT_RELATIVE_PATHS[archetype_id]
        plan["archetypes"].append(
            {
                "archetype_id": archetype_id,
                **paths,
                "mesh_name": archetype["mesh_name"],
                "material_names": archetype["material_names"],
                "expected_mesh_local_bounds_cm": archetype[
                    "expected_mesh_local_bounds_cm"
                ],
            }
        )
        glb_path = root / paths["glb"]
        preview_path = root / paths["preview"]
        glb_path.write_bytes(_glb_bytes(archetype))
        preview_path.write_bytes(_png_bytes())
        glb = forge.inspect_glb(glb_path, archetype)
        preview = forge.inspect_png(preview_path, recipe["preview"])
        receipt = forge.seal_document(
            {
                "schema_version": forge.ARTIFACT_RECEIPT_SCHEMA,
                "plan_content_digest": plan["content_digest"],
                "profile_content_digest": profile["content_digest"],
                "recipe_content_digest": recipe["content_digest"],
                "archetype_id": archetype_id,
                "glb": {"path": paths["glb"], **glb},
                "preview": {"path": paths["preview"], **preview},
                "determinism": {
                    "glb_reexport_byte_identical": True,
                    "glb_sha256": glb["sha256"],
                    "preview_rerender_byte_identical": True,
                    "preview_sha256": preview["sha256"],
                },
                "execution": {
                    "blender_version": "4.5.8 LTS",
                    "render_engine": "CYCLES",
                    "render_device": "CPU",
                    "gpu_devices_visible": False,
                    "camera_exported": False,
                    "light_exported": False,
                    "texture_exported": False,
                },
                "claims": {
                    "ue_imported": False,
                    "visual_acceptance": False,
                    "gta_quality_accepted": False,
                },
                "status": "fixture_artifact_sealed_not_ue_imported",
            }
        )
        (root / paths["receipt"]).write_bytes(forge.canonical_json_bytes(receipt))
        worker_rows.append(
            {
                "archetype_id": archetype_id,
                "glb_sha256": glb["sha256"],
                "preview_sha256": preview["sha256"],
                "receipt_content_digest": receipt["content_digest"],
            }
        )
    worker_result = forge.seal_document(
        {
            "schema_version": forge.WORKER_RESULT_SCHEMA,
            "plan_content_digest": plan["content_digest"],
            "profile_content_digest": profile["content_digest"],
            "recipe_content_digest": recipe["content_digest"],
            "artifact_count": 3,
            "artifacts": worker_rows,
            "execution": {
                "blender_version": "4.5.8 LTS",
                "render_engine": "CYCLES",
                "render_device": "CPU",
                "network_namespace": "unshared_by_host",
                "gpu_devices_visible": False,
            },
            "claims": {
                "ue_imported": False,
                "visual_acceptance": False,
                "gta_quality_accepted": False,
            },
            "status": "three_fixture_artifacts_sealed_not_ue_imported",
        }
    )
    return plan, worker_result


def test_profile_and_recipe_are_exact_closed_sealed_documents() -> None:
    profile = forge.load_profile()
    recipe = forge.load_recipe()

    assert profile["schema_version"] == forge.PROFILE_SCHEMA
    assert profile["content_digest"] == forge.PINNED_PROFILE_CONTENT_DIGEST
    assert recipe["schema_version"] == forge.RECIPE_SCHEMA
    assert recipe["content_digest"] == forge.PINNED_RECIPE_CONTENT_DIGEST
    assert forge.file_pin(forge.PROFILE_PATH) == {
        "path": str(forge.PROFILE_PATH),
        "sha256": "7de515303934928162ff20d56c52c1276ccc051694994ac32b4c9d2d15e0fe1a",
        "size_bytes": 70250,
    }
    assert forge.file_pin(forge.RECIPE_PATH) == {
        "path": str(forge.RECIPE_PATH),
        "sha256": "a976fb53a645d9af093fd0be666a64f8bcda572e3d6ce698200b85e9d8e6416c",
        "size_bytes": 3280,
    }


def test_profile_closes_hssd_r2_slots_collision_and_negative_claims() -> None:
    profile = forge.load_profile()
    inventory = profile["hssd_r2_inventory"]
    collision = profile["collision_policy"]
    visual = set(inventory["visual_slot_instance_ids"])
    semantic = set(collision["semantic_proxies"]["instance_ids"])
    secondary = {
        row["instance_id"] for row in collision["secondary_query_proxies"]["rows"]
    }
    detail = set(collision["detail_no_collision"]["instance_ids"])

    assert len(visual) == 60
    assert len(semantic) == 19
    assert len(secondary) == 20
    assert len(detail) == 21
    assert semantic.isdisjoint(secondary)
    assert semantic.isdisjoint(detail)
    assert secondary.isdisjoint(detail)
    assert semantic | secondary | detail == visual
    assert inventory["static_shell_count"] == 57
    assert inventory["dynamic_presentation_instance_ids"] == [
        "hssd.r1/bedroom.phone.01",
        "hssd.r1/kitchen_dining.coffee_cup.01",
        "hssd.r1/kitchen_dining.pot.01",
    ]
    assert set(inventory["transform_override_instance_ids"]) <= visual
    assert len(set(inventory["transform_override_instance_ids"])) == 17
    assert len(set(inventory["protected_portal_ids"])) == 5
    assert all(value is False for value in profile["claims"].values())
    assert collision["playable_collision_accepted"] is False


def test_secondary_query_proxy_bounds_are_finite_positive_and_closed() -> None:
    profile = forge.load_profile()
    rows = profile["collision_policy"]["secondary_query_proxies"]["rows"]
    assert len({row["instance_id"] for row in rows}) == 20
    for row in rows:
        minimum = row["world_bounds_m"]["min_m"]
        maximum = row["world_bounds_m"]["max_m"]
        assert len(minimum) == len(maximum) == 3
        assert all(isinstance(value, (int, float)) for value in minimum + maximum)
        assert all(low < high for low, high in zip(minimum, maximum, strict=True))


def test_six_room_finish_is_explicit_and_rear_material_quality_is_honest() -> None:
    rooms = {
        row["room_id"].rsplit(".", 1)[-1]: row for row in forge.load_profile()["rooms"]
    }
    assert set(rooms) == {
        "bathroom_laundry",
        "bedroom",
        "entry_hall",
        "kitchen_dining",
        "living_room",
        "office",
    }
    for room in rooms.values():
        assert set(room["surface_materials"]) == {"floor", "wall", "ceiling", "trim"}
        assert room["architecture_actor"]["cast_shadow"] is True
        assert room["fixture_light_binding"]["cast_shadow"] is True
    for room_id in ("bathroom_laundry", "bedroom", "office"):
        room = rooms[room_id]
        assert room["baseboards"]["expected_segment_count"] == 5
        assert room["door_trim"]["expected_segment_count"] == 3
        for role in ("floor", "wall", "ceiling"):
            assert (
                room["surface_materials"][role]["quality_disposition"]
                == "existing_generic_interchange_fallback_not_photoreal"
            )
    assert rooms["bathroom_laundry"]["wet_zone"] == {
        "enabled": True,
        "policy": "spawn_exact_no_collision_wall_panels",
        "material_role": "floor",
        "expected_segment_count": 2,
        "segments": rooms["bathroom_laundry"]["wet_zone"]["segments"],
    }
    for room_id in ("bedroom", "entry_hall", "kitchen_dining", "living_room", "office"):
        assert rooms[room_id]["wet_zone"]["enabled"] is False


def test_fixture_actor_paths_transforms_bounds_and_r4_lights_are_exact() -> None:
    profile = forge.load_profile()
    bindings = {
        row["room_id"].rsplit(".", 1)[-1]: row["fixture_light_binding"]
        for row in profile["rooms"]
    }
    assert {
        room: binding["fixture_actor_path"].rsplit(".", 1)[-1]
        for room, binding in bindings.items()
    } == {
        "bathroom_laundry": "StaticMeshActor_64",
        "bedroom": "StaticMeshActor_70",
        "entry_hall": "StaticMeshActor_71",
        "kitchen_dining": "StaticMeshActor_72",
        "living_room": "StaticMeshActor_73",
        "office": "StaticMeshActor_74",
    }
    assert {
        room: binding["light"]["actor_path"].rsplit(".", 1)[-1]
        for room, binding in bindings.items()
    } == {
        "bathroom_laundry": "SpotLight_1",
        "bedroom": "SpotLight_2",
        "entry_hall": "SpotLight_3",
        "kitchen_dining": "RectLight_2",
        "living_room": "RectLight_3",
        "office": "RectLight_4",
    }
    for binding in bindings.values():
        assert (
            binding["source_mesh_object_path"]
            == "/Engine/BasicShapes/Cylinder.Cylinder"
        )
        assert binding["final_transform"]["scale"] == [1.0, 1.0, 1.0]
        location = binding["final_transform"]["location_cm"]
        local = binding["expected_mesh_local_bounds_cm"]
        expected_world = {
            "min_cm": [
                round(value + offset, 6)
                for value, offset in zip(local["min_cm"], location, strict=True)
            ],
            "max_cm": [
                round(value + offset, 6)
                for value, offset in zip(local["max_cm"], location, strict=True)
            ],
        }
        assert binding["expected_world_bounds_cm"] == expected_world
        assert binding["mesh_bounds_tolerance_cm"] == 0.05
        assert binding["light"]["mutation_policy"] == "preserve_exact_r4_observation"


def test_fixture_package_allowlist_is_exact_unique_and_git_external() -> None:
    profile = forge.load_profile()
    imports = profile["fixture_imports"]
    packages = imports["exact_package_names"]
    assert len(packages) == len(set(packages)) == 9
    assert packages == sorted(packages)
    assert all(
        package.startswith(imports["package_root"] + "/") for package in packages
    )
    assert sum("/Materials/" not in package for package in packages) == 3
    assert sum("/Materials/" in package for package in packages) == 6
    assert imports["binary_payload_in_git"] is False
    assert not list(forge.PACKAGE_ROOT.glob("*.glb"))
    assert not list(forge.PACKAGE_ROOT.glob("*.png"))
    assert not list(forge.PACKAGE_ROOT.glob("*.uasset"))


def test_recipe_has_three_unique_one_mesh_two_material_archetypes() -> None:
    recipe = forge.load_recipe()
    assert [item["role"] for item in recipe["materials"]] == [
        "brushed_metal",
        "opal_diffuser",
    ]
    names = []
    for archetype in recipe["archetypes"]:
        assert archetype["expected_mesh_count"] == 1
        assert archetype["expected_primitive_count"] == 2
        assert archetype["expected_material_count"] == 2
        names.extend(
            [
                archetype["root_node_name"],
                archetype["mesh_node_name"],
                archetype["mesh_name"],
                *archetype["material_names"],
            ]
        )
    assert len(names) == len(set(names))
    assert recipe["export"]["include_cameras"] is False
    assert recipe["export"]["include_lights"] is False
    assert recipe["export"]["include_textures"] is False
    assert recipe["preview"]["device"] == "CPU"


def test_dry_run_is_deterministic_and_zero_write(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(forge, "DEFAULT_RUN_PARENT", tmp_path)
    monkeypatch.setattr(forge, "_verify_toolchain", _fake_toolchain)
    config = forge.ForgeConfig(attempt_name="fixture-test-dry-run", apply=False)
    before = list(tmp_path.iterdir())
    first = forge.build_plan(config)
    second = forge.build_plan(config)

    forge.validate_plan(first, expected_mode="dry_run")
    assert first == second
    assert first["status"] == "dry_run_validated_zero_write"
    assert first["will_write"] is False
    assert first["will_execute_blender"] is False
    assert not config.output_root.exists()
    assert list(tmp_path.iterdir()) == before


def test_production_config_has_no_run_parent_or_toolchain_override() -> None:
    with pytest.raises(TypeError):
        forge.ForgeConfig(  # type: ignore[call-arg]
            attempt_name="fixture-test", run_parent=pathlib.Path("/tmp")
        )
    with pytest.raises(TypeError):
        forge.build_plan(  # type: ignore[call-arg]
            forge.ForgeConfig(attempt_name="fixture-test"),
            toolchain=_fake_toolchain(),
        )


def test_cli_and_worker_command_offer_no_binary_script_asset_or_output_override(
    tmp_path: pathlib.Path,
) -> None:
    parser = forge._parser()
    for option in ("--blender", "--worker", "--asset", "--output-root"):
        with pytest.raises(SystemExit):
            parser.parse_args([option, "untrusted"])
    command = forge._worker_command(tmp_path / "attempt")
    assert command[0] == str(forge.DEFAULT_BWRAP)
    assert "--unshare-net" in command
    assert "--unshare-pid" in command
    assert "--dev" in command
    assert str(forge.DEFAULT_BLENDER) in command
    assert str(forge.WORKER_PATH) in command
    environment = forge._subprocess_environment()
    assert environment["CUDA_VISIBLE_DEVICES"] == ""
    assert environment["HIP_VISIBLE_DEVICES"] == ""
    assert environment["ROCR_VISIBLE_DEVICES"] == ""
    assert environment["DISPLAY"] == ""
    assert environment["WAYLAND_DISPLAY"] == ""
    assert environment["CYCLES_DEVICE"] == "CPU"


def test_glb_inspection_closes_structure_materials_and_bounds(
    tmp_path: pathlib.Path,
) -> None:
    archetype = forge.load_recipe()["archetypes"][2]
    path = tmp_path / "pendant.glb"
    path.write_bytes(_glb_bytes(archetype))
    inspection = forge.inspect_glb(path, archetype)
    assert inspection["mesh_count"] == 1
    assert inspection["primitive_count"] == 2
    assert inspection["material_count"] == 2
    assert inspection["camera_count"] == 0
    assert inspection["light_count"] == 0
    assert inspection["texture_count"] == 0
    assert (
        inspection["mesh_local_bounds_cm"] == archetype["expected_mesh_local_bounds_cm"]
    )

    path.write_bytes(_glb_bytes(archetype, cameras=[{"type": "perspective"}]))
    with pytest.raises(forge.FixtureForgeError, match="contains cameras"):
        forge.inspect_glb(path, archetype)


def test_png_inspection_requires_nonblank_rgba8_preview(tmp_path: pathlib.Path) -> None:
    preview = forge.load_recipe()["preview"]
    path = tmp_path / "preview.png"
    path.write_bytes(_png_bytes())
    inspection = forge.inspect_png(path, preview)
    assert inspection["width_px"] == 256
    assert inspection["height_px"] == 256
    assert inspection["nontransparent_pixel_count"] == 128 * 128
    assert inspection["nonblank"] is True

    path.write_bytes(_png_bytes(blank=True))
    with pytest.raises(forge.FixtureForgeError, match="too few visible pixels"):
        forge.inspect_png(path, preview)


def test_inventory_is_canonical_current_byte_closed_and_detects_drift(
    tmp_path: pathlib.Path,
) -> None:
    plan, worker_result = _write_artifact_fixture(tmp_path)
    inventory = forge._build_inventory(plan, worker_result, tmp_path)
    inventory_path = tmp_path / "fixture-inventory.json"
    inventory_path.write_bytes(forge.canonical_json_bytes(inventory))

    observed = forge.validate_fixture_inventory_file(inventory_path)
    assert observed["schema_version"] == forge.INVENTORY_SCHEMA
    assert observed["status"] == "fixture_inventory_sealed_not_ue_imported"
    assert observed["artifact_count"] == 3
    assert observed["ue_package_inventory"]["expected_package_count"] == 9
    assert all(value is False for value in observed["claims"].values())

    target = tmp_path / observed["artifacts"][0]["glb"]["path"]
    target.write_bytes(target.read_bytes() + b"drift")
    with pytest.raises(forge.FixtureForgeError):
        forge.validate_fixture_inventory_file(inventory_path)


def test_json_duplicate_nonfinite_and_digest_drift_fail_closed(
    tmp_path: pathlib.Path,
) -> None:
    duplicate = tmp_path / "duplicate.json"
    duplicate.write_text('{"a":1,"a":2}', encoding="utf-8")
    with pytest.raises(forge.FixtureForgeError, match="duplicate object key"):
        forge.load_json(duplicate)

    nonfinite = tmp_path / "nonfinite.json"
    nonfinite.write_text('{"a":NaN}', encoding="utf-8")
    with pytest.raises(forge.FixtureForgeError, match="prohibited"):
        forge.load_json(nonfinite)

    profile = copy.deepcopy(forge.load_profile())
    profile["claims"]["gta_level_quality"] = True
    tampered = tmp_path / "tampered.json"
    tampered.write_bytes(forge.canonical_json_bytes(profile))
    with pytest.raises(forge.FixtureForgeError, match="content digest drifted"):
        forge.load_profile(tampered)
