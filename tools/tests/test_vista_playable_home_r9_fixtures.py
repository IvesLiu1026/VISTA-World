from __future__ import annotations

import copy
import hashlib
import inspect
import json
import pathlib
import struct
import zlib
from collections.abc import Callable
from types import SimpleNamespace

import pytest

from tools.blender.vista_playable_home_r9_fixtures import blender_worker, forge


def _fake_authority(*, tree_sha256: str = "3" * 64) -> dict:
    return {
        "schema_version": forge.blender_authority.MANIFEST_SCHEMA_VERSION,
        "source_archive": {
            "official_url": forge.blender_authority.OFFICIAL_ARCHIVE_URL,
            "sha256": forge.blender_authority.OFFICIAL_ARCHIVE_SHA256,
            "size_bytes": forge.blender_authority.OFFICIAL_ARCHIVE_BYTES,
        },
        "authority_root": str(forge.DEFAULT_BLENDER_AUTHORITY_ROOT),
        "distribution_root": str(forge.DEFAULT_BLENDER_DISTRIBUTION_ROOT),
        "manifest": {
            "path": str(forge.blender_authority.MANIFEST_PATH),
            "sha256": "1" * 64,
            "size_bytes": 4096,
            "content_tree_sha256": "2" * 64,
            "tree_sha256": tree_sha256,
            "entry_count": 5626,
        },
        "blender": {
            "path": str(forge.DEFAULT_BLENDER),
            "sha256": forge.PINNED_BLENDER_SHA256,
            "size_bytes": forge.PINNED_BLENDER_BYTES,
        },
        "wrapper_python": {
            "path": str(
                forge.DEFAULT_BLENDER_DISTRIBUTION_ROOT
                / forge.blender_authority.WRAPPER_PYTHON_RELATIVE_PATH
            ),
            "sha256": "4" * 64,
            "size_bytes": 8_000_000,
        },
    }


def _fake_toolchain(**_: object) -> dict:
    return {
        "blender": {
            "path": str(forge.DEFAULT_BLENDER),
            "sha256": forge.PINNED_BLENDER_SHA256,
            "size_bytes": forge.PINNED_BLENDER_BYTES,
            "version": forge.PINNED_BLENDER_VERSION,
            "execution_device": "CPU",
            "authority": _fake_authority(),
            "execution_binding": "root_owned_distribution_fd_read_only",
        },
        "bubblewrap": {
            "path": str(forge.DEFAULT_BWRAP),
            "sha256": forge.PINNED_BWRAP_SHA256,
            "size_bytes": forge.PINNED_BWRAP_BYTES,
            "network_namespace": "unshared",
            "device_policy": "private_dev_without_gpu_nodes",
        },
    }


def _sandbox_authority_fixture(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[dict, pathlib.Path, pathlib.Path]:
    authority_root = tmp_path / "authority"
    distribution = authority_root / "distribution"
    blender = distribution / "blender"
    wrapper = distribution / forge.blender_authority.WRAPPER_PYTHON_RELATIVE_PATH
    member = distribution / "lib" / "noncritical-runtime-member.bin"
    manifest_path = authority_root / "distribution-manifest.json"
    wrapper.parent.mkdir(parents=True)
    member.parent.mkdir(parents=True)
    blender.write_bytes(b"sandbox-projected Blender bytes")
    wrapper.write_bytes(b"sandbox-projected Python bytes")
    member.write_bytes(b"sandbox-projected noncritical runtime bytes")
    blender.chmod(0o555)
    wrapper.chmod(0o555)
    member.chmod(0o444)
    distribution.chmod(0o555)
    blender_sha = hashlib.sha256(blender.read_bytes()).hexdigest()
    wrapper_sha = hashlib.sha256(wrapper.read_bytes()).hexdigest()
    content_entries = forge.blender_authority._scan_content_entries(distribution)
    security_entries = [
        forge.blender_authority._security_entry(distribution, row)
        for row in content_entries
    ]
    content_tree_sha = forge.blender_authority._content_digest(content_entries)
    tree_sha = forge.blender_authority._tree_digest(security_entries)
    entry_count = len(content_entries)
    manifest = {
        "schema_version": forge.blender_authority.MANIFEST_SCHEMA_VERSION,
        "authority_id": "blender-4.5.8-r1",
        "source_archive": {
            "official_url": forge.blender_authority.OFFICIAL_ARCHIVE_URL,
            "sha256": forge.blender_authority.OFFICIAL_ARCHIVE_SHA256,
            "size_bytes": forge.blender_authority.OFFICIAL_ARCHIVE_BYTES,
        },
        "root_install": {},
        "content_tree_sha256": content_tree_sha,
        "entry_count": entry_count,
        "entries": security_entries,
        "tree_sha256": tree_sha,
        "critical_files": {
            "blender": {
                "path": str(forge.blender_authority.BLENDER_RELATIVE_PATH),
                "kind": "file",
                "uid": 0,
                "gid": 0,
                "mode": "0555",
                "sha256": blender_sha,
                "size_bytes": blender.stat().st_size,
            },
            "wrapper_python": {
                "path": str(forge.blender_authority.WRAPPER_PYTHON_RELATIVE_PATH),
                "kind": "file",
                "uid": 0,
                "gid": 0,
                "mode": "0555",
                "sha256": wrapper_sha,
                "size_bytes": wrapper.stat().st_size,
            },
        },
        "policy": {
            "all_ancestors_root_owned": True,
            "all_entries_root_owned": True,
            "group_world_writable_prohibited": True,
            "relative_non_escaping_symlinks_only": True,
            "special_files_prohibited": True,
        },
    }
    manifest_raw = forge.canonical_json_bytes(manifest)
    manifest_path.write_bytes(manifest_raw)
    manifest_path.chmod(0o440)
    authority_root.chmod(0o555)
    expected = {
        "schema_version": forge.blender_authority.MANIFEST_SCHEMA_VERSION,
        "source_archive": copy.deepcopy(manifest["source_archive"]),
        "authority_root": str(authority_root),
        "distribution_root": str(distribution),
        "manifest": {
            "path": str(manifest_path),
            "sha256": hashlib.sha256(manifest_raw).hexdigest(),
            "size_bytes": len(manifest_raw),
            "content_tree_sha256": content_tree_sha,
            "tree_sha256": tree_sha,
            "entry_count": entry_count,
        },
        "blender": {
            "path": str(blender),
            "sha256": blender_sha,
            "size_bytes": blender.stat().st_size,
        },
        "wrapper_python": {
            "path": str(wrapper),
            "sha256": wrapper_sha,
            "size_bytes": wrapper.stat().st_size,
        },
    }
    monkeypatch.setattr(forge, "DEFAULT_BLENDER_AUTHORITY_ROOT", authority_root)
    monkeypatch.setattr(forge, "DEFAULT_BLENDER_DISTRIBUTION_ROOT", distribution)
    monkeypatch.setattr(forge, "DEFAULT_BLENDER", blender)
    monkeypatch.setattr(forge.blender_authority, "MANIFEST_PATH", manifest_path)
    monkeypatch.setattr(forge, "PINNED_BLENDER_SHA256", blender_sha)
    monkeypatch.setattr(forge, "PINNED_BLENDER_BYTES", blender.stat().st_size)
    real_lstat = forge.os.lstat
    projected_paths = {authority_root, distribution, manifest_path, blender, wrapper}

    class ProjectedRootStat:
        def __init__(self, observed: object) -> None:
            self._observed = observed
            self.st_uid = 0
            self.st_gid = 0

        def __getattr__(self, name: str) -> object:
            return getattr(self._observed, name)

    def projected_lstat(path: object) -> object:
        observed = real_lstat(path)
        return (
            ProjectedRootStat(observed)
            if pathlib.Path(path) in projected_paths
            else observed
        )

    monkeypatch.setattr(forge.os, "lstat", projected_lstat)
    monkeypatch.setattr(
        forge.os,
        "statvfs",
        lambda _path: SimpleNamespace(f_flag=forge.os.ST_RDONLY),
    )
    return expected, blender, member


def _glb_bytes(
    archetype: dict,
    *,
    root_overrides: dict | None = None,
    mesh_node_overrides: dict | None = None,
    material_overrides: dict[int, dict] | None = None,
    scene_nodes: list[int] | None = None,
    **overrides: object,
) -> bytes:
    expected = archetype["expected_mesh_local_bounds_cm"]
    minimum = expected["min_cm"]
    maximum = expected["max_cm"]
    gltf_min = [minimum[0] / 100.0, minimum[2] / 100.0, -maximum[1] / 100.0]
    gltf_max = [maximum[0] / 100.0, maximum[2] / 100.0, -minimum[1] / 100.0]
    root_node = {"name": archetype["root_node_name"], "children": [1]}
    mesh_node = {"name": archetype["mesh_node_name"], "mesh": 0}
    root_node.update(root_overrides or {})
    mesh_node.update(mesh_node_overrides or {})
    materials = []
    for name, contract in zip(
        archetype["material_names"], forge.load_recipe()["materials"], strict=True
    ):
        material = {
            "name": name,
            "pbrMetallicRoughness": {
                "baseColorFactor": contract["base_color_rgba"],
                "metallicFactor": contract["metallic"],
                "roughnessFactor": contract["roughness"],
            },
            "extras": {
                "vista_r9_alpha_mode": "OPAQUE",
                "vista_r9_material_role": contract["role"],
            },
        }
        emissive = [
            contract["emission_color_rgba"][index] * contract["emission_strength"]
            for index in range(3)
        ]
        if any(emissive):
            material["emissiveFactor"] = emissive
        materials.append(material)
    for index, override in (material_overrides or {}).items():
        materials[index].update(override)
    document = {
        "asset": {"version": "2.0", "generator": "fixture-test"},
        "scene": 0,
        "scenes": [{"nodes": [0] if scene_nodes is None else scene_nodes}],
        "nodes": [root_node, mesh_node],
        "meshes": [
            {
                "name": archetype["mesh_name"],
                "primitives": [
                    {"attributes": {"POSITION": 0}, "material": 0, "mode": 4},
                    {"attributes": {"POSITION": 1}, "material": 1, "mode": 4},
                ],
            }
        ],
        "materials": materials,
        "accessors": [
            {
                "bufferView": index,
                "componentType": 5126,
                "count": 2,
                "type": "VEC3",
                "min": gltf_min,
                "max": gltf_max,
            }
            for index in range(2)
        ],
        "bufferViews": [
            {"buffer": 0, "byteOffset": index * 24, "byteLength": 24}
            for index in range(2)
        ],
        "buffers": [{"byteLength": 48}],
    }
    document.update(overrides)
    json_raw = json.dumps(document, separators=(",", ":"), sort_keys=True).encode()
    json_raw += b" " * (-len(json_raw) % 4)
    binary = b"".join(struct.pack("<ffffff", *gltf_min, *gltf_max) for _ in range(2))
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


def _rewrite_glb_json(raw: bytes, transform: Callable[[str], str]) -> bytes:
    json_length, json_kind = struct.unpack_from("<II", raw, 12)
    assert json_kind == 0x4E4F534A
    json_start = 20
    binary_header = json_start + json_length
    binary_length, binary_kind = struct.unpack_from("<II", raw, binary_header)
    assert binary_kind == 0x004E4942
    binary = raw[binary_header + 8 : binary_header + 8 + binary_length]
    document = raw[json_start:binary_header].rstrip(b" \t\r\n\x00").decode("utf-8")
    rewritten = transform(document).encode("utf-8")
    rewritten += b" " * (-len(rewritten) % 4)
    total = 12 + 8 + len(rewritten) + 8 + len(binary)
    return b"".join(
        (
            struct.pack("<4sII", b"glTF", 2, total),
            struct.pack("<II", len(rewritten), 0x4E4F534A),
            rewritten,
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


def _write_artifact_fixture(
    root: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[dict, dict]:
    forge.load_profile()
    recipe = forge.load_recipe()
    root.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(forge, "DEFAULT_RUN_PARENT", root.parent)
    monkeypatch.setattr(forge, "_verify_toolchain", _fake_toolchain)
    config = forge.ForgeConfig(attempt_name=root.name, apply=True)
    plan = forge.build_plan(config)
    forge.validate_plan(plan, expected_mode="apply")
    assert forge._prepare_output_root(config) == root
    forge._create_source_snapshot(root, plan)
    request = forge._worker_request(plan)
    forge.validate_worker_request(request, expected_plan=plan)
    forge._write_exclusive(root / "forge-plan.json", forge.canonical_json_bytes(plan))
    forge._write_exclusive(
        root / "worker-request.json", forge.canonical_json_bytes(request)
    )
    forge._validate_output_tree(root, stage="request")
    worker_rows = []
    for archetype, plan_row in zip(
        recipe["archetypes"], plan["archetypes"], strict=True
    ):
        archetype_id = archetype["archetype_id"]
        paths = forge.EXPECTED_ARTIFACT_RELATIVE_PATHS[archetype_id]
        assert plan_row["archetype_id"] == archetype_id
        glb_path = root / paths["glb"]
        preview_path = root / paths["preview"]
        glb_path.write_bytes(_glb_bytes(archetype))
        preview_path.write_bytes(_png_bytes())
        glb_path.chmod(0o600)
        preview_path.chmod(0o600)
        glb = forge.inspect_glb(glb_path, archetype)
        preview = forge.inspect_png(preview_path, recipe["preview"])
        receipt = forge.seal_document(
            {
                "schema_version": forge.ARTIFACT_RECEIPT_SCHEMA,
                "plan_content_digest": plan["content_digest"],
                "profile": copy.deepcopy(plan["profile"]),
                "recipe": copy.deepcopy(plan["recipe"]),
                "builder_sources": copy.deepcopy(plan["builder_sources"]),
                "source_snapshot_content_digest": request[
                    "source_snapshot_content_digest"
                ],
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
        receipt_path = root / paths["receipt"]
        receipt_path.write_bytes(forge.canonical_json_bytes(receipt))
        receipt_path.chmod(0o600)
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
            "profile": copy.deepcopy(plan["profile"]),
            "recipe": copy.deepcopy(plan["recipe"]),
            "builder_sources": copy.deepcopy(plan["builder_sources"]),
            "source_snapshot_content_digest": request["source_snapshot_content_digest"],
            "output_root": plan["output_root"],
            "toolchain": copy.deepcopy(plan["toolchain"]),
            "archetypes": copy.deepcopy(plan["archetypes"]),
            "ue_package_inventory": copy.deepcopy(plan["ue_package_inventory"]),
            "execution_policy": copy.deepcopy(plan["execution_policy"]),
            "artifact_count": 3,
            "artifacts": worker_rows,
            "execution": {
                "blender_version": "4.5.8 LTS",
                "render_engine": "CYCLES",
                "render_device": "CPU",
                "network_namespace": "unshared_by_host",
                "gpu_devices_visible": False,
                "source_snapshot_root": forge.SOURCE_SNAPSHOT_ROOT.as_posix(),
                "source_tree_read_only_bind": True,
            },
            "claims": {
                "ue_imported": False,
                "visual_acceptance": False,
                "gta_quality_accepted": False,
            },
            "status": "three_fixture_artifacts_sealed_not_ue_imported",
        }
    )
    forge._write_exclusive(
        root / "worker-result.json", forge.canonical_json_bytes(worker_result)
    )
    forge._write_exclusive(root / "blender-worker.log", b"fixture test log\n")
    forge._validate_worker_result(worker_result, expected_plan=plan)
    forge._validate_output_tree(root, stage="worker")
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
        "sha256": "065782f443fd659a20d9a2ed5419403b2cf0faf04e336f05b11fc38528e999cb",
        "size_bytes": 71082,
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
    assert first["status"] == "dry_run_validated_zero_write_toolchain_probe_executed"
    assert first["will_write"] is False
    assert first["will_execute_toolchain_probe"] is True
    assert first["will_execute_blender_generation"] is False
    assert first["profile"]["relative_path"] == forge.PROFILE_RELATIVE_PATH.as_posix()
    assert first["recipe"]["relative_path"] == forge.RECIPE_RELATIVE_PATH.as_posix()
    assert all(row["content_digest"] is not None for row in first["builder_sources"])
    for row in first["builder_sources"]:
        if row["relative_path"].endswith(".py"):
            assert row["content_digest_kind"] == "raw_sha256"
            assert row["content_digest"] == row["sha256"]
        else:
            assert row["content_digest_kind"] == "canonical_json_sha256"
    assert "path" not in first["profile"]
    assert "path" not in first["recipe"]
    assert str(forge.REPOSITORY_ROOT) not in json.dumps(first, sort_keys=True)
    request = forge._worker_request(first)
    forge.validate_worker_request(request)
    assert request["profile"] == first["profile"]
    assert request["recipe"] == first["recipe"]
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


def test_plan_fails_closed_on_output_policy_archetype_package_and_source_drift(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(forge, "DEFAULT_RUN_PARENT", tmp_path)
    monkeypatch.setattr(forge, "_verify_toolchain", _fake_toolchain)
    plan = forge.build_plan(
        forge.ForgeConfig(attempt_name="closed-plan-test", apply=False)
    )
    mutations = (
        lambda row: row.__setitem__("output_root", "/tmp/caller-selected"),
        lambda row: row["execution_policy"].__setitem__("caller_selected_script", True),
        lambda row: row["archetypes"][0].__setitem__("glb", "artifacts/other.glb"),
        lambda row: row["ue_package_inventory"]["exact_package_names"].pop(),
        lambda row: row["builder_sources"][0].__setitem__("sha256", "0" * 64),
        lambda row: row.__setitem__("status", "visual_acceptance_complete"),
    )
    for mutate in mutations:
        candidate = copy.deepcopy(plan)
        mutate(candidate)
        candidate = forge.seal_document(candidate)
        with pytest.raises(forge.FixtureForgeError):
            forge.validate_plan(candidate, expected_mode="dry_run")


def test_cli_and_worker_command_offer_no_binary_script_asset_or_output_override(
    tmp_path: pathlib.Path,
) -> None:
    parser = forge._parser()
    for option in ("--blender", "--worker", "--asset", "--output-root"):
        with pytest.raises(SystemExit):
            parser.parse_args([option, "untrusted"])
    command = forge._worker_command(tmp_path / "attempt", distribution_fd=17)
    assert command[0] == str(forge.DEFAULT_BWRAP)
    assert "--unshare-net" in command
    assert "--unshare-pid" in command
    assert "--dev" in command
    assert str(forge.DEFAULT_BLENDER) in command
    assert str(forge.DEFAULT_BLENDER_DISTRIBUTION_ROOT) in command
    assert "--ro-bind-fd" in command
    assert "17" in command
    assert str(forge.WORKER_PATH) not in command
    assert str(tmp_path / "attempt" / forge.SOURCE_SNAPSHOT_ROOT) in command
    probe = forge._version_probe_command(distribution_fd=19)
    assert probe[0] == str(forge.DEFAULT_BWRAP)
    assert "--unshare-net" in probe
    assert "--unshare-pid" in probe
    assert "--dev" in probe
    assert "--ro-bind-fd" in probe
    assert "19" in probe
    assert str(forge.DEFAULT_BLENDER_DISTRIBUTION_ROOT) in probe
    assert probe[-2:] == [str(forge.DEFAULT_BLENDER), "--version"]
    environment = forge._subprocess_environment()
    assert environment["CUDA_VISIBLE_DEVICES"] == ""
    assert environment["HIP_VISIBLE_DEVICES"] == ""
    assert environment["ROCR_VISIBLE_DEVICES"] == ""
    assert environment["DISPLAY"] == ""
    assert environment["WAYLAND_DISPLAY"] == ""
    assert environment["CYCLES_DEVICE"] == "CPU"


def test_blender_458_gltf_export_contract_uses_current_vertex_color_api() -> None:
    assert blender_worker.GLTF_EXPORT_OPTIONS == {
        "export_format": "GLB",
        "use_selection": True,
        "export_apply": True,
        "export_yup": True,
        "export_cameras": False,
        "export_lights": False,
        "export_animations": False,
        "export_materials": "EXPORT",
        "export_texcoords": True,
        "export_normals": True,
        "export_tangents": False,
        "export_vertex_color": "NONE",
        "export_extras": True,
    }
    assert "export_colors" not in blender_worker.GLTF_EXPORT_OPTIONS


def test_empty_factory_scene_gets_a_fixed_preview_world() -> None:
    color = SimpleNamespace(default_value=None)
    strength = SimpleNamespace(default_value=None)
    background = SimpleNamespace(inputs={"Color": color, "Strength": strength})
    world = SimpleNamespace(
        use_nodes=False,
        node_tree=SimpleNamespace(nodes={"Background": background}),
    )

    class Worlds:
        def new(self, name: str) -> SimpleNamespace:
            assert name == blender_worker.PREVIEW_WORLD_NAME
            return world

    scene = SimpleNamespace(world=None)
    bpy = SimpleNamespace(data=SimpleNamespace(worlds=Worlds()))
    blender_worker._configure_preview_world(bpy, scene)

    assert scene.world is world
    assert world.use_nodes is True
    assert color.default_value == blender_worker.PREVIEW_WORLD_COLOR_RGBA
    assert strength.default_value == blender_worker.PREVIEW_WORLD_STRENGTH


def test_root_owned_authority_is_required_and_runtime_tree_drift_fails(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def unavailable() -> dict:
        raise forge.blender_authority.BlenderAuthorityError(
            "IMMUTABLE_BLENDER_AUTHORITY_REQUIRED", "not deployed"
        )

    monkeypatch.setattr(forge.blender_authority, "audit_fixed_authority", unavailable)
    with pytest.raises(
        forge.FixtureForgeError,
        match="FIXTURE_BLENDER_AUTHORITY_ADMIN_PREFLIGHT_REQUIRED",
    ):
        forge._audit_fixed_blender_authority()

    for relative_name in ("lib/libOpenImageIO.so", "addons_core/io_scene_gltf2.py"):
        runtime_member = tmp_path / relative_name
        runtime_member.parent.mkdir(parents=True, exist_ok=True)
        runtime_member.write_bytes(b"pinned runtime member")

        def observed_authority(path: pathlib.Path = runtime_member) -> dict:
            return _fake_authority(
                tree_sha256=hashlib.sha256(path.read_bytes()).hexdigest()
            )

        monkeypatch.setattr(forge, "_audit_fixed_blender_authority", observed_authority)
        expected = observed_authority()
        runtime_member.write_bytes(b"mutated after authority pin")
        with pytest.raises(
            forge.FixtureForgeError, match="FIXTURE_BLENDER_AUTHORITY_DRIFT"
        ):
            forge._assert_blender_authority_current(
                expected, phase=f"after {relative_name} pin"
            )


def test_worker_revalidates_fd_bound_authority_as_read_only_projection(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    expected, blender, member = _sandbox_authority_fixture(tmp_path, monkeypatch)

    assert forge._sandbox_authority_projection(expected) == expected

    blender.chmod(0o755)
    blender.write_bytes(b"mutated sandbox Blender")
    blender.chmod(0o555)
    with pytest.raises(
        forge.FixtureForgeError,
        match="FIXTURE_BLENDER_SANDBOX_AUTHORITY_INVALID",
    ):
        forge._sandbox_authority_projection(expected)

    blender.chmod(0o755)
    blender.write_bytes(b"sandbox-projected Blender bytes")
    blender.chmod(0o555)
    member.chmod(0o644)
    member.write_bytes(b"mutated noncritical runtime member")
    member.chmod(0o444)
    with pytest.raises(
        forge.FixtureForgeError,
        match="FIXTURE_BLENDER_SANDBOX_AUTHORITY_INVALID",
    ):
        forge._sandbox_authority_projection(expected)


def test_sandbox_validation_context_is_worker_only_and_not_a_cli_override(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert tuple(inspect.signature(forge._verify_toolchain).parameters) == (
        "execute_version_probe",
    )
    assert tuple(inspect.signature(forge._validate_plan_contract).parameters) == (
        "plan",
        "expected_mode",
    )
    assert tuple(
        inspect.signature(forge._validate_worker_request_contract).parameters
    ) == ("value", "expected_plan")
    assert tuple(
        inspect.signature(forge._validate_worker_result_contract).parameters
    ) == ("value", "expected_plan")
    monkeypatch.setattr(forge, "DEFAULT_RUN_PARENT", tmp_path)
    monkeypatch.setattr(forge, "_verify_toolchain", _fake_toolchain)
    plan = forge.build_plan(
        forge.ForgeConfig(attempt_name="sandbox-context-test", apply=True)
    )
    request = forge._worker_request(plan)
    result = forge.seal_document(
        {
            "schema_version": forge.WORKER_RESULT_SCHEMA,
            "plan_content_digest": plan["content_digest"],
            "profile": copy.deepcopy(plan["profile"]),
            "recipe": copy.deepcopy(plan["recipe"]),
            "builder_sources": copy.deepcopy(plan["builder_sources"]),
            "source_snapshot_content_digest": request["source_snapshot_content_digest"],
            "output_root": plan["output_root"],
            "toolchain": copy.deepcopy(plan["toolchain"]),
            "archetypes": copy.deepcopy(plan["archetypes"]),
            "ue_package_inventory": copy.deepcopy(plan["ue_package_inventory"]),
            "execution_policy": copy.deepcopy(plan["execution_policy"]),
            "artifact_count": 3,
            "artifacts": [
                {
                    "archetype_id": archetype_id,
                    "glb_sha256": "a" * 64,
                    "preview_sha256": "b" * 64,
                    "receipt_content_digest": "c" * 64,
                }
                for archetype_id in forge.EXPECTED_ARCHETYPE_IDS
            ],
            "execution": {
                "blender_version": forge.PINNED_BLENDER_VERSION,
                "render_engine": "CYCLES",
                "render_device": "CPU",
                "network_namespace": "unshared_by_host",
                "gpu_devices_visible": False,
                "source_snapshot_root": forge.SOURCE_SNAPSHOT_ROOT.as_posix(),
                "source_tree_read_only_bind": True,
            },
            "claims": {
                "ue_imported": False,
                "visual_acceptance": False,
                "gta_quality_accepted": False,
            },
            "status": "three_fixture_artifacts_sealed_not_ue_imported",
        }
    )
    observed_authorities: list[dict] = []

    def context_toolchain(expected_authority: dict) -> dict:
        observed_authorities.append(copy.deepcopy(expected_authority))
        return _fake_toolchain()

    monkeypatch.setattr(forge, "_verify_bound_worker_toolchain", context_toolchain)
    forge._validate_bound_worker_plan(plan, expected_mode="apply")
    forge._validate_bound_worker_request(
        request,
        expected_plan=plan,
    )
    forge._validate_bound_worker_result(result, expected_plan=plan)
    assert observed_authorities == [
        plan["toolchain"]["blender"]["authority"],
        plan["toolchain"]["blender"]["authority"],
        plan["toolchain"]["blender"]["authority"],
    ]
    worker_source = forge.WORKER_PATH.read_text(encoding="utf-8")
    assert worker_source.count("_validate_bound_worker_plan(") == 1
    assert worker_source.count("_validate_bound_worker_request(") == 1
    assert worker_source.count("_validate_bound_worker_result(") == 1
    assert "_sandbox_worker" not in worker_source
    assert "--sandbox-worker" not in forge._parser().format_help()

    def host_audit_fails(
        *,
        execute_version_probe: bool = True,
    ) -> dict:
        assert execute_version_probe is False
        raise forge.FixtureForgeError(
            "FIXTURE_BLENDER_AUTHORITY_SECURITY_INVALID",
            "host ownership audit remains mandatory",
        )

    monkeypatch.setattr(forge, "_verify_toolchain", host_audit_fails)
    with pytest.raises(
        forge.FixtureForgeError,
        match="FIXTURE_BLENDER_AUTHORITY_SECURITY_INVALID",
    ):
        forge.validate_plan(plan, expected_mode="apply")


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
        inspection["contracted_mesh_local_bounds_cm"]
        == archetype["expected_mesh_local_bounds_cm"]
    )
    assert inspection["maximum_bounds_delta_cm"] <= inspection["bounds_tolerance_cm"]

    path.write_bytes(_glb_bytes(archetype, cameras=[{"type": "perspective"}]))
    with pytest.raises(forge.FixtureForgeError, match="contains cameras"):
        forge.inspect_glb(path, archetype)


def test_glb_json_rejects_duplicate_keys_before_structural_inspection(
    tmp_path: pathlib.Path,
) -> None:
    archetype = forge.load_recipe()["archetypes"][2]
    raw = _glb_bytes(archetype)

    def duplicate_scene(document: str) -> str:
        marker = '"scene":0,'
        assert marker in document
        return document.replace(marker, '"scene":0,"scene":0,', 1)

    path = tmp_path / "duplicate-key.glb"
    path.write_bytes(_rewrite_glb_json(raw, duplicate_scene))
    with pytest.raises(forge.FixtureForgeError, match="FIXTURE_JSON_DUPLICATE_KEY"):
        forge.inspect_glb(path, archetype)


@pytest.mark.parametrize("nonfinite", [float("nan"), float("inf"), float("-inf")])
def test_glb_json_rejects_nonfinite_constants_before_structural_inspection(
    tmp_path: pathlib.Path, nonfinite: float
) -> None:
    archetype = forge.load_recipe()["archetypes"][2]
    path = tmp_path / "nonfinite.glb"
    path.write_bytes(_glb_bytes(archetype, extras={"nonfinite": nonfinite}))
    with pytest.raises(forge.FixtureForgeError, match="FIXTURE_JSON_NON_FINITE"):
        forge.inspect_glb(path, archetype)


@pytest.mark.parametrize(
    ("payload", "message"),
    (
        ({"mesh_node_overrides": {"translation": [1.0, 0.0, 0.0]}}, "TRS"),
        ({"mesh_node_overrides": {"scale": [2.0, 2.0, 2.0]}}, "TRS"),
        ({"scene_nodes": [1]}, "fixture root"),
        ({"animations": [{"channels": [], "samplers": []}]}, "animation"),
        (
            {
                "extensionsUsed": ["KHR_lights_punctual"],
                "extensions": {"KHR_lights_punctual": {"lights": []}},
            },
            "extensions",
        ),
    ),
)
def test_glb_inspection_rejects_transform_hierarchy_animation_and_light_payloads(
    tmp_path: pathlib.Path, payload: dict, message: str
) -> None:
    archetype = forge.load_recipe()["archetypes"][2]
    path = tmp_path / "malicious.glb"
    path.write_bytes(_glb_bytes(archetype, **payload))
    with pytest.raises(forge.FixtureForgeError, match=message):
        forge.inspect_glb(path, archetype)


@pytest.mark.parametrize(
    ("payload", "message"),
    (
        ({"extensionsUsed": ["KHR_materials_unlit"]}, "extensions"),
        (
            {
                "material_overrides": {
                    0: {"extensions": {"EXT_vista_unknown": {"enabled": True}}}
                }
            },
            "extension payload",
        ),
        (
            {
                "material_overrides": {
                    0: {
                        "pbrMetallicRoughness": {
                            "baseColorFactor": [1.0, 0.0, 1.0, 1.0],
                            "metallicFactor": 0.82,
                            "roughnessFactor": 0.26,
                        }
                    }
                }
            },
            "differs from recipe",
        ),
        (
            {
                "material_overrides": {
                    1: {
                        "pbrMetallicRoughness": {
                            "baseColorFactor": [0.93, 0.88, 0.74, 1.0],
                            "metallicFactor": 0.75,
                            "roughnessFactor": 0.32,
                        }
                    }
                }
            },
            "differs from recipe",
        ),
        (
            {"material_overrides": {1: {"emissiveFactor": [0.0, 0.0, 0.0]}}},
            "differs from recipe",
        ),
        (
            {"material_overrides": {0: {"alphaMode": "BLEND"}}},
            "alpha",
        ),
        (
            {"material_overrides": {0: {"doubleSided": True}}},
            "double_sided",
        ),
    ),
)
def test_glb_inspection_rejects_all_extensions_and_nonrecipe_materials(
    tmp_path: pathlib.Path, payload: dict, message: str
) -> None:
    archetype = forge.load_recipe()["archetypes"][2]
    path = tmp_path / "material-drift.glb"
    path.write_bytes(_glb_bytes(archetype, **payload))
    with pytest.raises(forge.FixtureForgeError, match=message):
        forge.inspect_glb(path, archetype)


def test_glb_inspection_recomputes_position_bounds_from_binary(
    tmp_path: pathlib.Path,
) -> None:
    archetype = forge.load_recipe()["archetypes"][2]
    path = tmp_path / "bounds-drift.glb"
    raw = bytearray(_glb_bytes(archetype))
    raw[-4:] = struct.pack("<f", 0.75)
    path.write_bytes(raw)
    with pytest.raises(forge.FixtureForgeError, match="bounds differ from bytes"):
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
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_root = tmp_path / "fixture-run"
    plan, worker_result = _write_artifact_fixture(output_root, monkeypatch)
    inventory = forge._build_inventory(plan, worker_result, output_root)
    inventory_path = output_root / "fixture-inventory.json"
    forge._write_exclusive(inventory_path, forge.canonical_json_bytes(inventory))

    observed = forge.validate_fixture_inventory_file(inventory_path)
    assert observed["schema_version"] == forge.INVENTORY_SCHEMA
    assert (
        observed["status"]
        == "fixture_inventory_sealed_snapshot_provenance_not_ue_imported"
    )
    assert observed["artifact_count"] == 3
    assert observed["ue_package_inventory"]["expected_package_count"] == 9
    assert all(value is False for value in observed["claims"].values())

    for relative_path in (
        "forge-plan.json",
        "worker-request.json",
        "worker-result.json",
    ):
        document_path = output_root / relative_path
        original = document_path.read_bytes()
        document_path.write_bytes(original + b" ")
        with pytest.raises(forge.FixtureForgeError):
            forge.validate_fixture_inventory_file(inventory_path)
        document_path.write_bytes(original)

    original_inventory_raw = inventory_path.read_bytes()
    request_path = output_root / "worker-request.json"
    original_request_raw = request_path.read_bytes()
    mutated_request = forge.load_json(request_path)
    mutated_request["output_root"] = str(output_root / "caller-selected")
    mutated_request = forge.seal_document(mutated_request)
    request_path.write_bytes(forge.canonical_json_bytes(mutated_request))
    inventory_with_request_pin = copy.deepcopy(inventory)
    inventory_with_request_pin["worker_request"] = forge._document_pin(
        request_path, relative_path="worker-request.json"
    )
    inventory_with_request_pin = forge.seal_document(inventory_with_request_pin)
    inventory_path.write_bytes(forge.canonical_json_bytes(inventory_with_request_pin))
    with pytest.raises(forge.FixtureForgeError, match="request output root drifted"):
        forge.validate_fixture_inventory_file(inventory_path)
    request_path.write_bytes(original_request_raw)
    inventory_path.write_bytes(original_inventory_raw)

    worker_result_path = output_root / "worker-result.json"
    original_worker_result_raw = worker_result_path.read_bytes()
    mutated_worker_result = forge.load_json(worker_result_path)
    mutated_worker_result["artifacts"][0]["glb_sha256"] = "0" * 64
    mutated_worker_result = forge.seal_document(mutated_worker_result)
    worker_result_path.write_bytes(forge.canonical_json_bytes(mutated_worker_result))
    inventory_with_result_pin = copy.deepcopy(inventory)
    inventory_with_result_pin["worker_result"] = forge._document_pin(
        worker_result_path, relative_path="worker-result.json"
    )
    inventory_with_result_pin = forge.seal_document(inventory_with_result_pin)
    inventory_path.write_bytes(forge.canonical_json_bytes(inventory_with_result_pin))
    with pytest.raises(
        forge.FixtureForgeError,
        match="worker-result artifact row differs from current inventory bytes",
    ):
        forge.validate_fixture_inventory_file(inventory_path)
    worker_result_path.write_bytes(original_worker_result_raw)
    inventory_path.write_bytes(original_inventory_raw)

    snapshot_worker = output_root.joinpath(
        forge.SOURCE_SNAPSHOT_ROOT.as_posix(),
        "tools/blender/vista_playable_home_r9_fixtures/blender_worker.py",
    )
    snapshot_bytes = snapshot_worker.read_bytes()
    snapshot_worker.chmod(0o600)
    snapshot_worker.write_bytes(snapshot_bytes + b"\n# drift\n")
    snapshot_worker.chmod(0o400)
    with pytest.raises(forge.FixtureForgeError):
        forge.validate_fixture_inventory_file(inventory_path)
    snapshot_worker.chmod(0o600)
    snapshot_worker.write_bytes(snapshot_bytes)
    snapshot_worker.chmod(0o400)

    target = output_root / observed["artifacts"][0]["glb"]["path"]
    target.write_bytes(target.read_bytes() + b"drift")
    with pytest.raises(forge.FixtureForgeError):
        forge.validate_fixture_inventory_file(inventory_path)


def test_final_output_tree_rejects_extras_links_and_mode_drift(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    output_root = tmp_path / "tree-run"
    plan, worker_result = _write_artifact_fixture(output_root, monkeypatch)
    inventory = forge._build_inventory(plan, worker_result, output_root)
    inventory_path = output_root / "fixture-inventory.json"
    forge._write_exclusive(inventory_path, forge.canonical_json_bytes(inventory))
    forge._validate_output_tree(output_root, stage="final")

    for relative_path in (
        "artifacts/extra.glb",
        "previews/extra.png",
        "receipts/extra.json",
        "unexpected-root-file.txt",
    ):
        extra = output_root / relative_path
        extra.write_bytes(b"unexpected")
        extra.chmod(0o600)
        with pytest.raises(forge.FixtureForgeError, match="extra="):
            forge._validate_output_tree(output_root, stage="final")
        extra.unlink()

    symlink = output_root / "unexpected-link"
    symlink.symlink_to("forge-plan.json")
    with pytest.raises(forge.FixtureForgeError, match="symlink prohibited"):
        forge._validate_output_tree(output_root, stage="final")
    symlink.unlink()

    hardlink = output_root / "unexpected-hardlink"
    hardlink.hardlink_to(output_root / "blender-worker.log")
    with pytest.raises(forge.FixtureForgeError, match="hard-linked file prohibited"):
        forge._validate_output_tree(output_root, stage="final")
    hardlink.unlink()

    target = output_root / plan["archetypes"][0]["glb"]
    target.chmod(0o644)
    with pytest.raises(forge.FixtureForgeError, match="mode_drift="):
        forge._validate_output_tree(output_root, stage="final")


def test_inventory_source_identity_survives_equivalent_repo_relocation(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository_a = tmp_path / "checkout-a"
    repository_b = tmp_path / "checkout-b"
    original_repository = forge.REPOSITORY_ROOT
    for repository in (repository_a, repository_b):
        for relative_path in forge.BUILDER_SOURCE_RELATIVE_PATHS:
            source = original_repository.joinpath(*relative_path.parts)
            target = repository.joinpath(*relative_path.parts)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(source.read_bytes())

    monkeypatch.setattr(forge, "REPOSITORY_ROOT", repository_a)
    monkeypatch.setattr(
        forge, "PROFILE_PATH", repository_a.joinpath(*forge.PROFILE_RELATIVE_PATH.parts)
    )
    monkeypatch.setattr(
        forge, "RECIPE_PATH", repository_a.joinpath(*forge.RECIPE_RELATIVE_PATH.parts)
    )
    output_root = tmp_path / "external-run"
    plan, worker_result = _write_artifact_fixture(output_root, monkeypatch)
    inventory = forge._build_inventory(plan, worker_result, output_root)
    inventory_path = output_root / "fixture-inventory.json"
    forge._write_exclusive(inventory_path, forge.canonical_json_bytes(inventory))
    assert str(repository_a) not in inventory_path.read_text(encoding="utf-8")

    monkeypatch.setattr(forge, "REPOSITORY_ROOT", repository_b)
    monkeypatch.setattr(
        forge, "PROFILE_PATH", repository_b.joinpath(*forge.PROFILE_RELATIVE_PATH.parts)
    )
    monkeypatch.setattr(
        forge, "RECIPE_PATH", repository_b.joinpath(*forge.RECIPE_RELATIVE_PATH.parts)
    )
    assert forge.validate_fixture_inventory_file(inventory_path) == inventory

    relocated_forge = (
        repository_b / "tools/blender/vista_playable_home_r9_fixtures/forge.py"
    )
    original_forge_bytes = relocated_forge.read_bytes()
    relocated_forge.write_bytes(original_forge_bytes + b"\n# drift\n")
    with pytest.raises(forge.FixtureForgeError, match="differs from current bytes"):
        forge.validate_fixture_inventory_file(inventory_path)
    relocated_forge.write_bytes(original_forge_bytes)

    relocated_worker = (
        repository_b / "tools/blender/vista_playable_home_r9_fixtures/blender_worker.py"
    )
    relocated_worker.write_bytes(relocated_worker.read_bytes() + b"\n# drift\n")
    with pytest.raises(forge.FixtureForgeError, match="differs from current bytes"):
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
