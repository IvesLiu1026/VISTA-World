from __future__ import annotations

import copy
import hashlib
import json
import stat
from dataclasses import dataclass, replace
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import pytest

from tools.blender.vista_playable_home_r9_fixtures import forge as final_forge
from tools.runtime.vista_playable_home import (
    hssd_r2_human_visual_demo_launch as launcher,
)
from tools.tests.test_vista_playable_home_hssd_r2_citysample_live_commandlet import (
    document_fixture as final_t4_document_fixture,
)
from tools.ue.vista_playable_home import (
    compose_hssd_r2_citysample_live_commandlet as final_commandlet,
)

base = launcher.base

DYNAMIC_SLOT_BINDINGS = {
    "hssd.r1/bedroom.phone.01": "home.r1/room.bedroom/entity.phone.01",
    "hssd.r1/kitchen_dining.coffee_cup.01": (
        "home.r1/room.kitchen_dining/entity.coffee_cup.01"
    ),
    "hssd.r1/kitchen_dining.pot.01": "home.r1/room.kitchen_dining/entity.pot.01",
}
DELETION_INSTANCE_ID = "hssd.r1/bedroom.phone.01"
STATIC_MESH_CLASS = "/Script/Engine.StaticMeshActor"


def _build_migration_contract(
    actor_inventory: list[dict[str, object]],
    placements: list[dict[str, object]],
    r6_result: dict[str, object],
    collision_ledger: list[dict[str, object]],
) -> dict[str, object]:
    legacy = {
        next(
            tag.removeprefix("VistaHssdInstanceId=")
            for tag in row["tags"]
            if tag.startswith("VistaHssdInstanceId=")
        ): copy.deepcopy(row)
        for row in actor_inventory
        if any(tag.startswith("VistaHssdInstanceId=") for tag in row["tags"])
    }
    unrelated = [
        copy.deepcopy(row)
        for row in actor_inventory
        if not any(tag.startswith("VistaHssdInstanceId=") for tag in row["tags"])
    ]
    by_id = {row["instance_id"]: row for row in placements}
    static_ids = set(by_id) - set(DYNAMIC_SLOT_BINDINGS)
    reuse_ids = set(legacy) - {DELETION_INSTANCE_ID}
    spawn_ids = static_ids - reuse_ids
    dynamic_observations = {
        row["semantic_id"]: row
        for row in [
            *r6_result["target_observations_reloaded"],
            r6_result["pot_observation_reloaded"],
        ]
    }
    collision_by_id = {row["instance_id"]: row for row in collision_ledger}
    policies = (
        "retained_r1_semantic_proxy_authority_unchanged",
        "secondary_simple_aabb_candidate_review_pending",
        "explicit_detail_no_collision",
    )
    return {
        "legacy_shells": [legacy[key] for key in sorted(legacy)],
        "reuse": [
            {
                "source_actor": legacy[key],
                "r2_placement": copy.deepcopy(by_id[key]),
            }
            for key in sorted(reuse_ids)
        ],
        "delete": {
            "instance_id": DELETION_INSTANCE_ID,
            "source_actor": legacy[DELETION_INSTANCE_ID],
        },
        "spawn": [copy.deepcopy(by_id[key]) for key in sorted(spawn_ids)],
        "final_static_slots": [copy.deepcopy(by_id[key]) for key in sorted(static_ids)],
        "dynamic_slots": [
            {
                "instance_id": key,
                "semantic_id": DYNAMIC_SLOT_BINDINGS[key],
                "logical_r2_slot": copy.deepcopy(by_id[key]),
                "preserved_r6_observation": copy.deepcopy(
                    dynamic_observations[DYNAMIC_SLOT_BINDINGS[key]]
                ),
                "transform_policy": (
                    "preserve_complete_r6_fit_never_apply_raw_r2_transform"
                ),
            }
            for key in sorted(DYNAMIC_SLOT_BINDINGS)
        ],
        "preserved_non_hssd_actor_inventory": sorted(
            unrelated, key=lambda row: row["actor_path"]
        ),
        "collision": {
            "policy_counts": {
                policy: sum(
                    row["collision_policy"] == policy for row in collision_ledger
                )
                for policy in policies
            },
            "rows": [copy.deepcopy(collision_by_id[key]) for key in sorted(by_id)],
        },
        "counts": {
            "legacy_observed": 42,
            "reused": 41,
            "deleted": 1,
            "spawned": 16,
            "final_static": 57,
            "dynamic": 3,
            "final_visual_slots": 60,
            "preserved_non_hssd": 108,
        },
    }


materializer = SimpleNamespace(
    DYNAMIC_SLOT_BINDINGS=DYNAMIC_SLOT_BINDINGS,
    DELETION_INSTANCE_ID=DELETION_INSTANCE_ID,
    STATIC_MESH_CLASS=STATIC_MESH_CLASS,
    build_migration_contract=_build_migration_contract,
)
BUILDER_SOURCE_RELATIVE_PATHS = (
    "tools/admin/__init__.py",
    "tools/admin/vista_blender_authority.py",
    "tools/blender/vista_playable_home_r9_fixtures/__init__.py",
    "tools/blender/vista_playable_home_r9_fixtures/__main__.py",
    "tools/blender/vista_playable_home_r9_fixtures/blender_worker.py",
    "tools/blender/vista_playable_home_r9_fixtures/forge.py",
    "tools/blender/vista_playable_home_r9_fixtures/recipe.json",
    (
        "world_packs/vista_playable_home_r1/visual_profiles/"
        "hssd_r2_citysample_live_r1.json"
    ),
)


def _expected_t2_tree(_stage: str) -> dict[str, tuple[str, int]]:
    value = {
        "artifacts": ("directory", 0o700),
        "previews": ("directory", 0o700),
        "receipts": ("directory", 0o700),
        "source-snapshot": ("directory", 0o500),
        "source-snapshot.json": ("file", 0o600),
        "forge-plan.json": ("file", 0o600),
        "worker-request.json": ("file", 0o600),
        "worker-result.json": ("file", 0o600),
        "blender-worker.log": ("file", 0o600),
        "fixture-inventory.json": ("file", 0o600),
    }
    for archetype in ("flush_dome", "linear_panel", "pendant"):
        value[f"artifacts/{archetype}.glb"] = ("file", 0o600)
        value[f"previews/{archetype}.png"] = ("file", 0o600)
        value[f"receipts/{archetype}.json"] = ("file", 0o600)
    for relative in BUILDER_SOURCE_RELATIVE_PATHS:
        path = Path("source-snapshot") / relative
        value[path.as_posix()] = ("file", 0o400)
        parent = path.parent
        while parent != Path("."):
            value[parent.as_posix()] = ("directory", 0o500)
            if parent == Path("source-snapshot"):
                break
            parent = parent.parent
    return value


fixture_forge = SimpleNamespace(
    PROFILE_SCHEMA=launcher.FINISH_PROFILE_SCHEMA,
    INVENTORY_SCHEMA=launcher.FIXTURE_INVENTORY_SCHEMA,
    _expected_output_tree=_expected_t2_tree,
)


@pytest.fixture(autouse=True)
def _use_final_materializer_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        launcher, "_composition_materializer_module", lambda: materializer
    )
    monkeypatch.setattr(
        launcher,
        "_composition_commandlet_module",
        lambda: SimpleNamespace(validate_result_document=lambda *_args: None),
    )
    monkeypatch.setattr(launcher, "_fixture_forge_module", lambda: fixture_forge)
    monkeypatch.setattr(launcher, "_validate_copied_t2_bundle", lambda *_args: None)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _pin(path: Path) -> dict[str, object]:
    return {"path": str(path), "sha256": _sha(path), "size_bytes": path.stat().st_size}


def _write(path: Path, raw: bytes, *, mode: int = 0o600) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.write_bytes(raw)
    path.chmod(mode)
    return path


def _write_t3(path: Path, value: dict[str, object]) -> dict[str, object]:
    document = copy.deepcopy(value)
    document.pop("content_digest", None)
    document["content_digest"] = base.content_digest(document)
    _write(path, base.canonical_json(document))
    return document


def _t2_digest(value: dict[str, object]) -> str:
    body = copy.deepcopy(value)
    body.pop("content_digest", None)
    return hashlib.sha256(
        json.dumps(
            body,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


def _write_t2(path: Path, value: dict[str, object]) -> dict[str, object]:
    document = copy.deepcopy(value)
    document.pop("content_digest", None)
    document["content_digest"] = _t2_digest(document)
    raw = (
        json.dumps(
            document,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        + "\n"
    ).encode("utf-8")
    _write(path, raw)
    return document


def _strict_content(path: Path) -> str:
    return json.loads(path.read_text(encoding="utf-8"))["content_digest"]


def _write_project(root: Path, map_bytes: bytes) -> tuple[Path, Path]:
    project = _write(root / "VistaPlayableHome.uproject", b'{"FileVersion":3}\n')
    map_package = _write(
        root / "Content/VISTA/PlayableHome/vista_playable_home_r1/Maps/"
        "VistaPlayableHome.umap",
        map_bytes,
    )
    _write(root / "Config/DefaultEngine.ini", b"[/Script/Engine.Engine]\n")
    _write(root / "Plugins/VistaFixture/VistaFixture.uplugin", b'{"FileVersion":3}\n')
    return project, map_package


def _profile() -> dict[str, object]:
    dynamic = sorted(materializer.DYNAMIC_SLOT_BINDINGS)
    static = [f"hssd.r1/test.static.{index:02d}" for index in range(57)]
    glb_inventory = []
    package_names = []
    for archetype in ("flush_dome", "linear_panel", "pendant"):
        root = "/Game/VISTA/PlayableHome/vista_playable_home_r1/R9Fixtures/" + archetype
        materials = [root + f"/M_{archetype}_{suffix}" for suffix in ("A", "B")]
        packages = [root + "/" + archetype, *materials]
        package_names.extend(packages)
        glb_inventory.append(
            {
                "archetype_id": archetype,
                "glb_relative_path": f"artifacts/{archetype}.glb",
                "static_mesh_object_path": root + f"/{archetype}.{archetype}",
                "static_mesh_package_name": packages[0],
                "material_object_paths": [
                    value + "." + value.rsplit("/", 1)[-1] for value in materials
                ],
                "material_package_names": materials,
            }
        )
    value: dict[str, object] = {
        "schema_version": launcher.FINISH_PROFILE_SCHEMA,
        "profile_id": "hssd_r2_citysample_live_r1",
        "source_lineage": {"fixture": True},
        "rooms": [
            {
                "room_id": f"room-{index}",
                "architecture_actor": {
                    "actor_path": f"{launcher.MAP_OBJECT_PATH}.Actor_{42 + index:03d}"
                },
                "fixture_light_binding": {
                    "fixture_actor_path": (
                        f"{launcher.MAP_OBJECT_PATH}.Actor_{48 + index:03d}"
                    )
                },
            }
            for index in range(6)
        ],
        "fixture_forge": {
            "inventory_schema_version": launcher.FIXTURE_INVENTORY_SCHEMA,
            "inventory_status": "fixture_inventory_sealed_snapshot_provenance_not_ue_imported",
        },
        "fixture_imports": {
            "package_root": "/Game/VISTA/PlayableHome/vista_playable_home_r1/R9Fixtures",
            "glb_inventory": glb_inventory,
            "exact_package_names": sorted(package_names),
            "expected_package_count": 9,
            "import_policy": {"fixture": True},
            "binary_payload_in_git": False,
        },
        "hssd_r2_inventory": {
            "visual_slot_count": 60,
            "static_shell_count": 57,
            "visual_slot_instance_ids": sorted([*static, *dynamic]),
            "dynamic_presentation_instance_ids": dynamic,
            "protected_portal_count": 5,
        },
        "collision_policy": {"fixture": True},
        "claims": {
            "runtime_visual_acceptance": False,
            "interaction_accepted": False,
            "playable_collision_accepted": False,
            "photoreal_character_accepted": False,
            "gta_level_quality": False,
        },
    }
    value["content_digest"] = _t2_digest(value)
    return value


def _migration(profile: dict[str, object]) -> dict[str, object]:
    inventory = profile["hssd_r2_inventory"]
    visual_ids = sorted(inventory["visual_slot_instance_ids"])
    dynamic_ids = set(inventory["dynamic_presentation_instance_ids"])
    static_ids = sorted(set(visual_ids) - dynamic_ids)
    legacy_ids = [materializer.DELETION_INSTANCE_ID, *static_ids[:41]]

    def actor(index: int, instance_id: str | None = None) -> dict[str, object]:
        tags = ["VistaRole=unrelated"]
        if instance_id is not None:
            tags = ["VistaHssdInstanceId=" + instance_id]
        return {
            "actor_path": f"{launcher.MAP_OBJECT_PATH}.Actor_{index:03d}",
            "actor_class_path": materializer.STATIC_MESH_CLASS,
            "tags": tags,
        }

    placements = []
    collision = []
    policies = (
        ["retained_r1_semantic_proxy_authority_unchanged"] * 19
        + ["secondary_simple_aabb_candidate_review_pending"] * 20
        + ["explicit_detail_no_collision"] * 21
    )
    for index, instance_id in enumerate(visual_ids):
        placements.append(
            {
                "instance_id": instance_id,
                "room_id": "home.r1/room.bedroom",
                "source_asset_id": "hssd.static.test",
                "semantic_target_id": materializer.DYNAMIC_SLOT_BINDINGS.get(
                    instance_id
                ),
                "object_path": "/Game/VISTA/HSSD/Test.Test",
                "world_transform_cm": {
                    "location_cm": [float(index), 0.0, 50.0],
                    "rotation_deg": [0.0, 0.0, 0.0],
                    "scale": [1.0, 1.0, 1.0],
                },
                "tags": ["VistaHssdInstanceId=" + instance_id],
                "visual_policy": {"collision_profile": "NoCollision"},
            }
        )
        collision.append(
            {"instance_id": instance_id, "collision_policy": policies[index]}
        )
    actors = [actor(index, value) for index, value in enumerate(legacy_ids)]
    actors.extend(actor(index + 42) for index in range(108))

    def observation(semantic_id: str, index: int) -> dict[str, object]:
        return {
            "semantic_id": semantic_id,
            "actor_path": f"{launcher.MAP_OBJECT_PATH}.Dynamic_{index}",
            "actor_class_path": "/Script/VistaPlayableHome.VistaPickupActor",
            "actor_transform": {
                "location_cm": [1.0, 2.0, 64.0 + index],
                "rotation_deg": [0.0, 0.0, 10.0],
                "scale": [1.0, 1.0, 1.0],
            },
            "presentation": {
                "component_name": "PresentationMesh",
                "relative_transform": {
                    "location_cm": [0.0, 0.0, -5.0 + index],
                    "rotation_deg": [0.0, 0.0, 10.0],
                    "scale": [0.966105, 0.966105, 0.966105],
                },
                "mesh_object_path": "/Game/CitySampleCrowd/Test.Test",
                "collision_mode": "NoCollision",
                "visible": True,
                "cast_shadow": True,
            },
            "proxy": {
                "component_name": "PickupMesh",
                "collision_mode": "QueryOnly",
                "visible": False,
            },
            "portable": True,
        }

    observations = {
        instance_id: observation(semantic_id, index)
        for index, (instance_id, semantic_id) in enumerate(
            materializer.DYNAMIC_SLOT_BINDINGS.items()
        )
    }
    pot_id = "hssd.r1/kitchen_dining.pot.01"
    return materializer.build_migration_contract(
        actors,
        placements,
        {
            "actor_inventory_reloaded": actors,
            "target_observations_reloaded": [
                observations[key] for key in sorted(observations) if key != pot_id
            ],
            "pot_observation_reloaded": observations[pot_id],
        },
        collision,
    )


def _relative_pin(path: Path, root: Path) -> dict[str, object]:
    return {
        "path": path.relative_to(root).as_posix(),
        "sha256": _sha(path),
        "size_bytes": path.stat().st_size,
    }


def _evidence_manifest(root: Path, relatives: list[str]) -> dict[str, object]:
    rows = []
    manifest = {}
    directories: set[str] = set()
    for relative in sorted(relatives):
        path = root / relative
        mode = stat.S_IMODE(path.stat().st_mode)
        rows.append({"relative_path": relative, **_pin(path), "mode": mode})
        manifest[relative] = {
            "sha256": _sha(path),
            "size_bytes": path.stat().st_size,
            "mode": mode,
        }
        parent = Path(relative).parent
        while parent != Path("."):
            directories.add(parent.as_posix())
            parent = parent.parent
    value: dict[str, object] = {
        "schema_version": launcher.FIXTURE_EVIDENCE_SCHEMA,
        "root": str(root),
        "files": rows,
        "directories": [
            {
                "relative_path": relative,
                "path": str(root / relative),
                "mode": stat.S_IMODE((root / relative).stat().st_mode),
            }
            for relative in sorted(directories)
        ],
        "tree": launcher._manifest_tree(manifest),
    }
    value["content_digest"] = base.content_digest(value)
    return value


def _log_snapshot(path: Path) -> dict[str, object]:
    metadata = path.stat()
    return {
        "device": metadata.st_dev,
        "inode": metadata.st_ino,
        "size_bytes": metadata.st_size,
        "mtime_ns": metadata.st_mtime_ns,
        "ctime_ns": metadata.st_ctime_ns,
        "sha256": _sha(path),
    }


@dataclass
class Fixture:
    receipt_path: Path
    receipt: dict[str, object]
    trust: launcher.LauncherTrust
    parent: base.HumanVisualDemoInputs
    profile: dict[str, object]
    inventory: dict[str, object]
    evidence: dict[str, object]
    result: dict[str, object]
    host: dict[str, object]

    def parent_loader(self, path: Path) -> base.HumanVisualDemoInputs:
        assert path == self.trust.r6_receipt.path
        return self.parent

    def load(self) -> launcher.R9HumanVisualDemoInputs:
        return launcher.load_combined_receipt(
            self.receipt_path,
            trust=self.trust,
            parent_loader=self.parent_loader,
        )


def _fixture(tmp_path: Path) -> Fixture:
    source_project, source_map = _write_project(tmp_path / "r6-project", b"r6-map\n")
    attempt = tmp_path / "r9-attempt"
    output_project, output_map = _write_project(
        attempt / "project", b"r9-map-with-finish\n"
    )
    namespace = Path(launcher.HSSD_NAMESPACE_RELATIVE) / "Fixture.uasset"
    _write(source_project.parent / namespace, b"same-hssd\n")
    _write(output_project.parent / namespace, b"same-hssd\n")

    executable = _write(
        tmp_path / "UE/Engine/Binaries/Linux/UnrealEditor",
        b"#!/bin/sh\nexit 0\n",
        mode=0o500,
    )
    unreal_cmd = _write(executable.with_name("UnrealEditor-Cmd"), b"cmd\n", mode=0o500)
    build_version = _write(tmp_path / "UE/Engine/Build/Build.version", b"{}\n")
    provenance: dict[str, object] = {}
    for key in base.SOURCE_PROVENANCE_ARTIFACT_KEYS:
        provenance[key] = _pin(_write(tmp_path / "provenance" / f"{key}.json", b"{}\n"))
    provenance["plugin_package_tree_sha256"] = "a" * 64
    provenance["plugin_source_git_commit"] = "b" * 40

    r6_receipt = _write(tmp_path / "r6" / base.COMBINED_RECEIPT_NAME, b"r6\n")
    r6_workdir = tmp_path / "r6-worktree"
    r6_launcher = _write(
        r6_workdir / "tools/runtime/vista_playable_home/human_visual_demo_launch.py",
        b"# launcher\n",
    )
    uv = _write(tmp_path / "bin/uv", b"#!/bin/sh\n", mode=0o500)
    systemd_run = _write(tmp_path / "bin/systemd-run", b"#!/bin/sh\n", mode=0o500)
    hssd_host = _write(tmp_path / "hssd/host.json", b"host\n")
    hssd_scene = _write(tmp_path / "hssd/scene.json", b"scene\n")
    hssd_plan = _write(tmp_path / "hssd/plan.json", b"plan\n")
    hssd_map = _write(tmp_path / "hssd/map.umap", b"map\n")
    accessory = _write(tmp_path / "r6/accessory.json", b"accessory\n")

    source_pin = base.ArtifactPin(
        source_project, _sha(source_project), source_project.stat().st_size
    )
    source_map_pin = base.ArtifactPin(
        source_map, _sha(source_map), source_map.stat().st_size
    )
    executable_pin = base.ArtifactPin(
        executable, _sha(executable), executable.stat().st_size
    )
    parent = base.HumanVisualDemoInputs(
        receipt=r6_receipt,
        receipt_sha256=_sha(r6_receipt),
        receipt_content_digest="c" * 64,
        project=source_pin,
        project_static_tree=base.compute_project_static_tree(source_project),
        source_provenance=copy.deepcopy(provenance),
        executable=executable_pin,
        map_object_path=launcher.MAP_OBJECT_PATH,
        map_package=source_map_pin,
        receipt_schema_version=base.COMBINED_RECEIPT_SCHEMA_V4,
        realism_r4_upgrade={"sealed": True},
        accessory_r6_upgrade={"result": _pin(accessory)},
    )
    trust = launcher.LauncherTrust(
        r6_receipt=launcher.TrustedArtifact(
            r6_receipt, _sha(r6_receipt), r6_receipt.stat().st_size
        ),
        r6_launcher=launcher.TrustedArtifact(
            r6_launcher, _sha(r6_launcher), r6_launcher.stat().st_size
        ),
        r6_workdir=r6_workdir,
        uv=launcher.TrustedArtifact(uv, _sha(uv), uv.stat().st_size),
        systemd_run=launcher.TrustedArtifact(
            systemd_run, _sha(systemd_run), systemd_run.stat().st_size
        ),
        bwrap=launcher.PRODUCTION_TRUST.bwrap,
        hssd_host_receipt=launcher.TrustedArtifact(
            hssd_host, _sha(hssd_host), hssd_host.stat().st_size
        ),
        hssd_scene_receipt=launcher.TrustedArtifact(
            hssd_scene, _sha(hssd_scene), hssd_scene.stat().st_size
        ),
        hssd_build_plan=launcher.TrustedArtifact(
            hssd_plan, _sha(hssd_plan), hssd_plan.stat().st_size
        ),
        hssd_map_package=launcher.TrustedArtifact(
            hssd_map, _sha(hssd_map), hssd_map.stat().st_size
        ),
        finish_profile_sha256="0" * 64,
        finish_profile_size_bytes=0,
        finish_profile_content_digest="0" * 64,
        engine_version=launcher.ENGINE_VERSION,
        hssd_namespace_relative=launcher.HSSD_NAMESPACE_RELATIVE,
        hssd_namespace_tree={},
    )

    profile = _profile()
    profile_path = attempt / launcher.LOCAL_ARTIFACT_NAMES["finish_profile"]
    profile = _write_t2(profile_path, profile)
    for archetype in ("flush_dome", "linear_panel", "pendant"):
        _write(attempt / f"artifacts/{archetype}.glb", ("glb-" + archetype).encode())
        _write(attempt / f"previews/{archetype}.png", ("png-" + archetype).encode())
        _write_t2(attempt / f"receipts/{archetype}.json", {"archetype_id": archetype})
    for relative in (
        "forge-plan.json",
        "worker-request.json",
        "worker-result.json",
        "source-snapshot.json",
    ):
        _write_t2(attempt / relative, {"fixture": relative})
    _write(attempt / "blender-worker.log", b"Blender worker completed\n")
    for relative in BUILDER_SOURCE_RELATIVE_PATHS:
        _write(
            attempt / "source-snapshot" / relative,
            ("snapshot:" + relative + "\n").encode(),
            mode=0o400,
        )
    snapshot_directories = sorted(
        {
            parent
            for relative in BUILDER_SOURCE_RELATIVE_PATHS
            for parent in (attempt / "source-snapshot" / relative).parents
            if parent != attempt and attempt in parent.parents
        },
        key=lambda path: len(path.parts),
        reverse=True,
    )
    for directory in snapshot_directories:
        directory.chmod(0o500)

    by_profile = {
        row["archetype_id"]: row for row in profile["fixture_imports"]["glb_inventory"]
    }
    artifacts = []
    for archetype in ("flush_dome", "linear_panel", "pendant"):
        glb = attempt / f"artifacts/{archetype}.glb"
        preview = attempt / f"previews/{archetype}.png"
        receipt = attempt / f"receipts/{archetype}.json"
        artifacts.append(
            {
                "archetype_id": archetype,
                "glb": _relative_pin(glb, attempt),
                "preview": _relative_pin(preview, attempt),
                "artifact_receipt": {
                    **_relative_pin(receipt, attempt),
                    "content_digest": _strict_content(receipt),
                },
                "ue_import": copy.deepcopy(by_profile[archetype]),
            }
        )
    inventory_path = attempt / launcher.LOCAL_ARTIFACT_NAMES["fixture_inventory"]
    inventory = _write_t2(
        inventory_path,
        {
            "schema_version": launcher.FIXTURE_INVENTORY_SCHEMA,
            "archetypes": [
                {"archetype_id": value}
                for value in ("flush_dome", "linear_panel", "pendant")
            ],
            "execution_policy": {"fixture": True},
            "output_root": str(attempt),
            "profile": {
                "path": "profile.json",
                "sha256": _sha(profile_path),
                "size_bytes": profile_path.stat().st_size,
                "content_digest": profile["content_digest"],
            },
            "recipe": {"fixture": True},
            "forge_plan": {"fixture": True},
            "worker_request": {"fixture": True},
            "worker_result": {"fixture": True},
            "source_snapshot": {"fixture": True},
            "toolchain": {"fixture": True},
            "artifact_count": 3,
            "artifacts": artifacts,
            "ue_package_inventory": {
                "package_root": profile["fixture_imports"]["package_root"],
                "exact_package_names": profile["fixture_imports"][
                    "exact_package_names"
                ],
                "expected_package_count": 9,
            },
            "binary_payload_in_git": False,
            "claims": {"runtime_visual_acceptance": False},
            "status": "fixture_inventory_sealed_snapshot_provenance_not_ue_imported",
        },
    )
    evidence_relatives = [
        launcher.LOCAL_ARTIFACT_NAMES["finish_profile"],
        launcher.LOCAL_ARTIFACT_NAMES["fixture_inventory"],
        "forge-plan.json",
        "worker-request.json",
        "worker-result.json",
        "blender-worker.log",
        "source-snapshot.json",
        *["source-snapshot/" + value for value in BUILDER_SOURCE_RELATIVE_PATHS],
        *[
            f"artifacts/{value}.glb"
            for value in ("flush_dome", "linear_panel", "pendant")
        ],
        *[
            f"previews/{value}.png"
            for value in ("flush_dome", "linear_panel", "pendant")
        ],
        *[
            f"receipts/{value}.json"
            for value in ("flush_dome", "linear_panel", "pendant")
        ],
    ]
    evidence = _evidence_manifest(attempt, evidence_relatives)

    for package_name in profile["fixture_imports"]["exact_package_names"]:
        relative = Path("Content/" + package_name.removeprefix("/Game/") + ".uasset")
        _write(output_project.parent / relative, (package_name + "\n").encode())
    source_manifest = base._project_static_manifest(source_project)
    output_manifest = base._project_static_manifest(output_project)
    output_tree = base.compute_project_static_tree(output_project)
    namespace_manifest = {
        key: row
        for key, row in source_manifest.items()
        if key.startswith(launcher.HSSD_NAMESPACE_RELATIVE + "/")
    }
    namespace_tree = launcher._manifest_tree(namespace_manifest)
    trust = replace(
        trust,
        finish_profile_sha256=_sha(profile_path),
        finish_profile_size_bytes=profile_path.stat().st_size,
        finish_profile_content_digest=profile["content_digest"],
        hssd_namespace_tree=namespace_tree,
    )
    materializer_path = _write(
        attempt / "materialize_hssd_r2_citysample_live.py", b"# materializer\n"
    )
    commandlet_path = _write(
        attempt / "compose_hssd_r2_citysample_live_commandlet.py", b"# commandlet\n"
    )
    result_path = attempt / launcher.LOCAL_ARTIFACT_NAMES["result"]
    scene_path = attempt / launcher.LOCAL_ARTIFACT_NAMES["scene_receipt"]
    execution_path = attempt / launcher.LOCAL_ARTIFACT_NAMES["execution"]
    migration = _migration(profile)
    authority = {
        "host_receipt": trust.hssd_host_receipt.document(),
        "scene_receipt": trust.hssd_scene_receipt.document(),
        "build_plan": trust.hssd_build_plan.document(),
        "map_package": trust.hssd_map_package.document(),
        **launcher.HSSD_AUTHORITY_COUNTS,
    }
    _write_t3(
        execution_path,
        {
            "schema_version": launcher.EXECUTION_SCHEMA,
            "status": launcher.EXECUTION_STATUS,
            "attempt_root": str(attempt),
            "project": _pin(output_project),
            "materializer": _pin(materializer_path),
            "commandlet": _pin(commandlet_path),
            "finish_profile": _pin(profile_path),
            "fixture_inventory": _pin(inventory_path),
            "fixture_evidence_manifest": copy.deepcopy(evidence),
            "parent_combined_receipt": trust.r6_receipt.document(),
            "r6_accessory_result": _pin(accessory),
            "hssd_r2_authority": authority,
            "source_project_static_tree": copy.deepcopy(parent.project_static_tree),
            "source_static_manifest": source_manifest,
            "hssd_namespace": namespace_tree,
            "composition_contract": {
                "migration": migration,
                "fixture_imports": copy.deepcopy(profile["fixture_imports"]),
                "collision_policy": copy.deepcopy(profile["collision_policy"]),
                "finish_profile_content_digest": profile["content_digest"],
                "expected_counts": copy.deepcopy(launcher.COMPOSITION_EXPECTED_COUNTS),
            },
            "engine": {
                "version": launcher.ENGINE_VERSION,
                "unreal_editor_cmd": _pin(unreal_cmd),
                "build_version": _pin(build_version),
                "bwrap": trust.bwrap.document(),
                "null_rhi": True,
                "trace_server": "disabled",
                "gpu": None,
                "display": None,
            },
            "map": {
                "object_path": launcher.MAP_OBJECT_PATH,
                "relative_path": "Content/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome.umap",
                "source_package": {
                    "path": str(output_map),
                    "sha256": _sha(source_map),
                    "size_bytes": source_map.stat().st_size,
                },
            },
            "result": {
                "result_path": str(result_path),
                "result_sidecar_path": str(result_path) + ".sha256",
                "scene_receipt_path": str(scene_path),
                "scene_receipt_sidecar_path": str(scene_path) + ".sha256",
            },
            "legal_scope": copy.deepcopy(base.LEGAL_SCOPE),
            "acknowledgements": {
                key: "confirmed" for key in launcher.EXECUTION_ACKNOWLEDGEMENT_KEYS
            },
            "claims": copy.deepcopy(base.CLAIMS),
            "acceptance": copy.deepcopy(launcher.ACCEPTANCE),
        },
    )

    fixture_rows = []
    evidence_by_relative = {row["relative_path"]: row for row in evidence["files"]}
    for profile_row in profile["fixture_imports"]["glb_inventory"]:
        archetype = profile_row["archetype_id"]
        source = evidence_by_relative[f"artifacts/{archetype}.glb"]
        package_names = sorted(
            [
                profile_row["static_mesh_package_name"],
                *profile_row["material_package_names"],
            ]
        )
        packages = []
        for package_name in package_names:
            relative = "Content/" + package_name.removeprefix("/Game/") + ".uasset"
            current = output_manifest[relative]
            packages.append(
                {
                    "package_name": package_name,
                    "path": str(output_project.parent / relative),
                    "sha256": current["sha256"],
                    "size_bytes": current["size_bytes"],
                }
            )
        fixture_rows.append(
            {
                "archetype_id": archetype,
                "source_glb": {key: source[key] for key in base.ARTIFACT_KEYS},
                "mesh_object_path": profile_row["static_mesh_object_path"],
                "material_object_paths": sorted(profile_row["material_object_paths"]),
                "mesh_bounds_cm": {
                    "min_cm": [-1, -1, -1],
                    "max_cm": [1, 1, 1],
                },
                "simple_collision_count": 0,
                "has_navigation_data": False,
                "nanite_enabled": False,
                "package_artifacts": packages,
            }
        )
    dynamic = [
        {"instance_id": key} for key in sorted(materializer.DYNAMIC_SLOT_BINDINGS)
    ]
    architecture_rows = [
        {"actor_path": room["architecture_actor"]["actor_path"]}
        for room in profile["rooms"]
    ]
    fixture_actor_rows = [
        {"actor_path": room["fixture_light_binding"]["fixture_actor_path"]}
        for room in profile["rooms"]
    ]
    finish = {
        "architecture_before": copy.deepcopy(architecture_rows),
        "architecture_after_save": copy.deepcopy(architecture_rows),
        "architecture_reloaded": copy.deepcopy(architecture_rows),
        "fixtures_before": copy.deepcopy(fixture_actor_rows),
        "fixtures_after_save": copy.deepcopy(fixture_actor_rows),
        "fixtures_reloaded": copy.deepcopy(fixture_actor_rows),
        "r4_lights_before": [{"actor_path": f"light-{i}"} for i in range(6)],
        "r4_lights_reloaded": [{"actor_path": f"light-{i}"} for i in range(6)],
        "segments_after_save": [{"segment_id": f"s-{i}"} for i in range(26)],
        "segments_reloaded": [{"segment_id": f"s-{i}"} for i in range(26)],
    }
    preserved_paths = {
        row["actor_path"] for row in migration["preserved_non_hssd_actor_inventory"]
    }
    finish_owned_paths = {
        row["actor_path"] for row in architecture_rows + fixture_actor_rows
    }
    observations = {
        "source_actor_inventory": [
            *migration["legacy_shells"],
            *migration["preserved_non_hssd_actor_inventory"],
        ],
        "legacy_shells_before": migration["legacy_shells"],
        "shell_migration": {
            "reuse_before": migration["reuse"],
            "reuse_after_save": [{} for _ in range(41)],
            "deleted": migration["delete"],
            "spawn_after_save": [{} for _ in range(16)],
            "static_reloaded": [{} for _ in range(57)],
        },
        "dynamic_presentations": {
            "before": dynamic,
            "after_save": dynamic,
            "reloaded": dynamic,
        },
        "preserved_non_hssd": {
            "source_inventory": migration["preserved_non_hssd_actor_inventory"],
            "reloaded_inventory": migration["preserved_non_hssd_actor_inventory"],
            "unchanged_actor_paths": sorted(preserved_paths - finish_owned_paths),
        },
        "fixture_imports": fixture_rows,
        "six_room_finish": finish,
        "collision": {
            "policy_counts": {
                "semantic_proxies": 19,
                "secondary_query_proxies": 20,
                "detail_no_collision": 21,
            },
            "semantic_static_before": [{} for _ in range(16)],
            "semantic_static_after_save": [{} for _ in range(16)],
            "semantic_static_reloaded": [{} for _ in range(16)],
            "semantic_dynamic_instance_ids": sorted(materializer.DYNAMIC_SLOT_BINDINGS),
            "secondary_after_save": [{} for _ in range(20)],
            "secondary_reloaded": [{} for _ in range(20)],
            "detail_reloaded": [{} for _ in range(21)],
            "remaining_review_items": {"pending": True},
        },
        "world_before": {"game_mode": "preserved"},
        "world_reloaded": {"game_mode": "preserved"},
    }
    result = _write_t3(
        result_path,
        {
            "schema_version": launcher.RESULT_SCHEMA,
            "status": launcher.UPGRADE_STATUS,
            "provider_id": base.PROVIDER_ID,
            "human_operated_visual_demo_only": True,
            "prohibited_agent_adapter": True,
            "execution_sha256": _sha(execution_path),
            "map_object_path": launcher.MAP_OBJECT_PATH,
            "map_package": _pin(output_map),
            "project_static_tree": output_tree,
            "observations": observations,
            "legal_scope": copy.deepcopy(base.LEGAL_SCOPE),
            "claims": copy.deepcopy(base.CLAIMS),
            "acceptance": copy.deepcopy(launcher.ACCEPTANCE),
            "gates": {key: True for key in launcher.UE_RESULT_GATES},
            "error": None,
        },
    )
    _write(
        result_path.with_name(result_path.name + ".sha256"),
        f"{_sha(result_path)}  {result_path.name}\n".encode("ascii"),
    )
    _write_t3(
        scene_path,
        {
            "schema_version": launcher.SCENE_RECEIPT_SCHEMA,
            "status": launcher.UPGRADE_STATUS,
            "provider_id": base.PROVIDER_ID,
            "human_operated_visual_demo_only": True,
            "prohibited_agent_adapter": True,
            "execution": _pin(execution_path),
            "result": _pin(result_path),
            "map_object_path": launcher.MAP_OBJECT_PATH,
            "map_package": _pin(output_map),
            "project_static_tree": output_tree,
            "observations": observations,
            "legal_scope": copy.deepcopy(base.LEGAL_SCOPE),
            "claims": copy.deepcopy(base.CLAIMS),
            "acceptance": copy.deepcopy(launcher.ACCEPTANCE),
        },
    )
    _write(
        scene_path.with_name(scene_path.name + ".sha256"),
        f"{_sha(scene_path)}  {scene_path.name}\n".encode("ascii"),
    )
    engine_log = _write(attempt / launcher.ENGINE_LOG_NAME, b"engine closed\n")
    stdout_log = _write(attempt / launcher.STDOUT_NAME, b"stdout closed\n")
    logs = [_pin(engine_log), _pin(stdout_log)]
    static_delta = launcher._validate_source_output_delta(
        source_manifest=source_manifest,
        output_manifest=output_manifest,
        finish_document=profile,
        output_project_root=output_project.parent,
    )
    host_path = attempt / launcher.LOCAL_ARTIFACT_NAMES["host_receipt"]
    host = _write_t3(
        host_path,
        {
            "schema_version": launcher.HOST_RECEIPT_SCHEMA,
            "status": launcher.UPGRADE_STATUS,
            "provider_id": base.PROVIDER_ID,
            "human_operated_visual_demo_only": True,
            "prohibited_agent_adapter": True,
            "execution": _pin(execution_path),
            "result": _pin(result_path),
            "scene_receipt": _pin(scene_path),
            "project": _pin(output_project),
            "map": {
                "object_path": launcher.MAP_OBJECT_PATH,
                "package": _pin(output_map),
            },
            "project_static_tree": output_tree,
            "logs": logs,
            "log_closure": {
                "policy": copy.deepcopy(launcher.HOST_LOG_CLOSURE_POLICY),
                "residual_process_disposition": "absent_after_descendant_tracker",
                "snapshots": {
                    "engine_log": _log_snapshot(engine_log),
                    "stdout_log": _log_snapshot(stdout_log),
                },
            },
            "static_delta": static_delta,
            "fixture_evidence_manifest": evidence,
            "containment": {
                "command_prefix": list(launcher.HOST_CONTAINMENT_PREFIX),
                "credential_hidden_policy": copy.deepcopy(
                    launcher.HOST_CREDENTIAL_HIDDEN_POLICY
                ),
            },
            "current_byte_revalidation": {
                "execution": _pin(execution_path),
                "result": _pin(result_path),
                "scene_receipt": _pin(scene_path),
                "map": _pin(output_map),
                "project_static_tree": output_tree,
                "logs": logs,
                "fixture_evidence_manifest": evidence,
                "passed": True,
            },
            "gates": {key: True for key in launcher.HOST_GATES},
            "legal_scope": copy.deepcopy(base.LEGAL_SCOPE),
            "claims": copy.deepcopy(base.CLAIMS),
            "acceptance": copy.deepcopy(launcher.ACCEPTANCE),
        },
    )
    upgrade = {
        "schema_version": launcher.UPGRADE_SCHEMA,
        "status": launcher.UPGRADE_STATUS,
        "parent_combined_receipt": trust.r6_receipt.document(),
        "source_map": _pin(source_map),
        "source_project_static_tree": parent.project_static_tree,
        "hssd_r2_authority": authority,
        "finish_profile": _pin(profile_path),
        "fixture_inventory": _pin(inventory_path),
        "fixture_evidence_manifest": evidence,
        "execution": _pin(execution_path),
        "result": _pin(result_path),
        "scene_receipt": _pin(scene_path),
        "host_receipt": _pin(host_path),
        "materializer": _pin(materializer_path),
        "commandlet": _pin(commandlet_path),
        "unreal_editor_cmd": _pin(unreal_cmd),
        "build_version": _pin(build_version),
        "bwrap": trust.bwrap.document(),
        "map_object_path": launcher.MAP_OBJECT_PATH,
        "output_project_static_tree": output_tree,
        "observations": copy.deepcopy(launcher.OBSERVATIONS),
        "legal_scope": copy.deepcopy(base.LEGAL_SCOPE),
        "claims": copy.deepcopy(base.CLAIMS),
        "acceptance": copy.deepcopy(launcher.ACCEPTANCE),
    }
    receipt = {
        "schema_version": launcher.COMBINED_RECEIPT_SCHEMA_V5,
        "status": base.COMBINED_RECEIPT_STATUS,
        "provider_id": base.PROVIDER_ID,
        "human_operated_visual_demo_only": True,
        "prohibited_agent_adapter": True,
        "project": _pin(output_project),
        "project_static_tree": output_tree,
        "source_provenance": provenance,
        "executable": _pin(executable),
        "map": {
            "object_path": launcher.MAP_OBJECT_PATH,
            "package": _pin(output_map),
        },
        "legal_scope": copy.deepcopy(base.LEGAL_SCOPE),
        "claims": copy.deepcopy(base.CLAIMS),
        "hssd_r2_citysample_live_r1_upgrade": upgrade,
    }
    receipt["content_digest"] = base.content_digest(receipt)
    receipt_path = attempt / base.COMBINED_RECEIPT_NAME
    _write(receipt_path, base.canonical_json(receipt))
    sidecar_path = attempt / base.COMBINED_RECEIPT_SIDECAR_NAME
    _write(
        sidecar_path,
        f"{_sha(receipt_path)}  {receipt_path.name}\n".encode("ascii"),
    )
    current_state = {
        "execution": _pin(execution_path),
        "result": _pin(result_path),
        "scene_receipt": _pin(scene_path),
        "map": _pin(output_map),
        "project_static_tree": output_tree,
        "logs": logs,
        "static_delta": static_delta,
        "fixture_evidence_manifest": evidence,
    }
    _write_t3(
        attempt / launcher.COMPLETE_NAME,
        {
            "schema_version": launcher.COMPLETE_SCHEMA,
            "status": launcher.COMPLETE_STATUS,
            "attempt_root": str(attempt),
            "combined_receipt": _pin(receipt_path),
            "combined_receipt_sidecar": _pin(sidecar_path),
            "host_receipt": _pin(host_path),
            "current_state": current_state,
            "failure_absent": True,
        },
    )
    return Fixture(
        receipt_path,
        receipt,
        trust,
        parent,
        profile,
        inventory,
        evidence,
        result,
        host,
    )


def test_final_contract_constants_are_exact() -> None:
    assert launcher.FIXTURE_INVENTORY_SCHEMA.endswith("/v3")
    assert launcher.FINISH_PROFILE_SHA256 == (
        "065782f443fd659a20d9a2ed5419403b2cf0faf04e336f05b11fc38528e999cb"
    )
    assert launcher.FINISH_PROFILE_BYTES == 71_082
    assert len(launcher.FIXTURE_INVENTORY_KEYS) == 18
    assert len(launcher.UE_RESULT_GATES) == 22
    assert len(launcher.HOST_GATES) == 9


def test_v5_complete_receipt_loads_and_closes_current_state(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    inputs = fixture.load()
    assert inputs.runtime.receipt_schema_version == launcher.COMBINED_RECEIPT_SCHEMA_V5
    assert inputs.upgrade["fixture_evidence_manifest"] == fixture.evidence
    assert inputs.upgrade["acceptance"] == launcher.ACCEPTANCE
    assert set(fixture.result["gates"]) == launcher.UE_RESULT_GATES
    assert set(fixture.host["gates"]) == launcher.HOST_GATES
    preserved = fixture.result["observations"]["preserved_non_hssd"]
    finish = fixture.result["observations"]["six_room_finish"]
    finish_owned = {
        row["actor_path"]
        for row in [*finish["architecture_before"], *finish["fixtures_before"]]
    }
    preserved_paths = {row["actor_path"] for row in preserved["source_inventory"]}
    assert len(finish_owned) == 12
    assert preserved["unchanged_actor_paths"] == sorted(preserved_paths - finish_owned)
    assert len(preserved["unchanged_actor_paths"]) == 96


def test_real_final_t4_documents_pass_and_nested_drift_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    execution, result, scene = final_t4_document_fixture()
    finish = result["observations"]["six_room_finish"]
    finish_document = {
        "rooms": [
            {
                "room_id": f"room-{index}",
                "architecture_actor": {
                    "actor_path": finish["architecture_before"][index]["actor_path"]
                },
                "fixture_light_binding": {
                    "fixture_actor_path": finish["fixtures_before"][index]["actor_path"]
                },
            }
            for index in range(6)
        ]
    }
    monkeypatch.setattr(
        launcher, "_composition_commandlet_module", lambda: final_commandlet
    )
    execution_pin = base.ArtifactPin(
        Path(scene["execution"]["path"]),
        result["execution_sha256"],
        scene["execution"]["size_bytes"],
    )
    map_pin = base.ArtifactPin(
        Path(result["map_package"]["path"]),
        result["map_package"]["sha256"],
        result["map_package"]["size_bytes"],
    )
    launcher._validate_result_document(
        result,
        execution_document=execution,
        scene_document=scene,
        execution=execution_pin,
        map_package=map_pin,
        project_tree=result["project_static_tree"],
        finish_document=finish_document,
        migration=execution["composition_contract"]["migration"],
    )

    malformed = copy.deepcopy(result)
    malformed["observations"]["shell_migration"]["static_reloaded"][0]["component"][
        "mesh_object_path"
    ] = "/Game/Malformed.Mismatched"
    malformed = final_commandlet.seal(malformed)
    malformed_raw = final_commandlet.canonical_json(malformed)
    malformed_scene = copy.deepcopy(scene)
    malformed_scene["result"] = {
        "path": scene["result"]["path"],
        "sha256": hashlib.sha256(malformed_raw).hexdigest(),
        "size_bytes": len(malformed_raw),
    }
    malformed_scene["observations"] = copy.deepcopy(malformed["observations"])
    malformed_scene = final_commandlet.seal(malformed_scene)
    with pytest.raises(base.HumanVisualDemoError, match="T4 nested"):
        launcher._validate_result_document(
            malformed,
            execution_document=execution,
            scene_document=malformed_scene,
            execution=execution_pin,
            map_package=map_pin,
            project_tree=malformed["project_static_tree"],
            finish_document=finish_document,
            migration=execution["composition_contract"]["migration"],
        )


def test_execution_acknowledgements_require_exact_confirmed_values() -> None:
    launcher._validate_execution_acknowledgements(
        copy.deepcopy(launcher.EXECUTION_ACKNOWLEDGEMENTS)
    )
    malformed = copy.deepcopy(launcher.EXECUTION_ACKNOWLEDGEMENTS)
    malformed["hssd_attribution"] = "yes"
    with pytest.raises(base.HumanVisualDemoError, match="acknowledgement"):
        launcher._validate_execution_acknowledgements(malformed)


@pytest.mark.parametrize("drift", ["missing", "extra", "mode"])
def test_final_t2_evidence_tree_rejects_omission_extra_and_mode_drift(
    tmp_path: Path, drift: str
) -> None:
    fixture = _fixture(tmp_path)
    files = {
        row["relative_path"]: copy.deepcopy(row) for row in fixture.evidence["files"]
    }
    directories = {
        row["relative_path"]: copy.deepcopy(row)
        for row in fixture.evidence["directories"]
    }
    if drift == "missing":
        files.pop("worker-request.json")
    elif drift == "extra":
        extra = fixture.receipt_path.parent / "artifacts/unexpected.bin"
        _write(extra, b"unexpected")
    else:
        files["blender-worker.log"]["mode"] = 0o640
    with pytest.raises(base.HumanVisualDemoError, match="evidence|namespace"):
        launcher._validate_t2_evidence_tree(
            fixture.receipt_path.parent,
            fixture_forge,
            file_rows=files,
            directory_rows=directories,
        )


def test_final_forge_contract_accepts_the_complete_copied_evidence_tree(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    launcher._validate_t2_evidence_tree(
        fixture.receipt_path.parent,
        final_forge,
        file_rows={row["relative_path"]: row for row in fixture.evidence["files"]},
        directory_rows={
            row["relative_path"]: row for row in fixture.evidence["directories"]
        },
    )


def test_fixture_manifest_invokes_full_copied_t2_bundle_validator(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = _fixture(tmp_path)
    validator = mock.Mock()
    monkeypatch.setattr(launcher, "_validate_copied_t2_bundle", validator)
    fixture.load()
    validator.assert_called_once()
    assert validator.call_args.args[1] == fixture.inventory


@pytest.mark.parametrize("terminal", ["missing", "failure", "coexistence"])
def test_complete_is_required_and_any_failure_is_rejected(
    tmp_path: Path, terminal: str
) -> None:
    fixture = _fixture(tmp_path)
    complete = fixture.receipt_path.parent / launcher.COMPLETE_NAME
    failure = fixture.receipt_path.parent / launcher.FAILURE_NAME
    if terminal == "missing":
        complete.unlink()
    elif terminal == "failure":
        complete.unlink()
        _write_t3(
            failure,
            {
                "schema_version": launcher.HOST_RECEIPT_SCHEMA,
                "status": launcher.FAILURE_STATUS,
            },
        )
    else:
        _write_t3(
            failure,
            {
                "schema_version": launcher.HOST_RECEIPT_SCHEMA,
                "status": launcher.FAILURE_STATUS,
            },
        )
    with pytest.raises(base.HumanVisualDemoError, match="COMPLETE|FAILURE"):
        fixture.load()


def test_fixture_evidence_current_bytes_and_modes_are_revalidated(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path / "bytes")
    glb = fixture.receipt_path.parent / "artifacts/flush_dome.glb"
    glb.write_bytes(glb.read_bytes() + b"drift")
    with pytest.raises(base.HumanVisualDemoError, match="fixture evidence|receipt pin"):
        fixture.load()

    fixture = _fixture(tmp_path / "mode")
    glb = fixture.receipt_path.parent / "artifacts/flush_dome.glb"
    glb.chmod(0o640)
    with pytest.raises(base.HumanVisualDemoError, match="project static tree|mode"):
        fixture.load()


def test_static_delta_and_private_package_mode_are_revalidated(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path / "extra")
    _write(fixture.receipt_path.parent / "project/Content/Untrusted/Extra.uasset", b"x")
    with pytest.raises(
        base.HumanVisualDemoError, match="project static tree|map plus nine"
    ):
        fixture.load()

    fixture = _fixture(tmp_path / "mode")
    package = min(
        fixture.receipt_path.parent / "project" / relative
        for relative in launcher._fixture_package_paths(fixture.profile)
    )
    package.chmod(0o640)
    with pytest.raises(base.HumanVisualDemoError, match="project static tree|mode"):
        fixture.load()


def test_static_delta_rejects_package_hardlink_inode_alias(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    project_root = fixture.receipt_path.parent / "project"
    packages = [
        project_root / relative
        for relative in launcher._fixture_package_paths(fixture.profile)
    ]
    packages[1].unlink()
    packages[1].hardlink_to(packages[0])
    with pytest.raises(base.HumanVisualDemoError, match="linked|alias"):
        launcher._validate_source_output_delta(
            source_manifest=base._project_static_manifest(fixture.parent.project.path),
            output_manifest=base._project_static_manifest(
                project_root / "VistaPlayableHome.uproject"
            ),
            finish_document=fixture.profile,
            output_project_root=project_root,
        )


def test_ue_and_host_gate_namespaces_are_disjoint_and_closed(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    assert launcher.UE_RESULT_GATES.isdisjoint(launcher.HOST_GATES)
    execution = json.loads(
        Path(
            fixture.receipt["hssd_r2_citysample_live_r1_upgrade"]["execution"]["path"]
        ).read_text(encoding="utf-8")
    )
    malformed = copy.deepcopy(fixture.result)
    malformed["gates"]["process_group_closed"] = True
    with pytest.raises(base.HumanVisualDemoError, match="result gates"):
        launcher._validate_result_document(
            malformed,
            execution_document=execution,
            scene_document=json.loads(
                Path(
                    fixture.receipt["hssd_r2_citysample_live_r1_upgrade"][
                        "scene_receipt"
                    ]["path"]
                ).read_text(encoding="utf-8")
            ),
            execution=base._artifact_pin(
                fixture.receipt["hssd_r2_citysample_live_r1_upgrade"]["execution"],
                "execution",
            ),
            map_package=base._artifact_pin(fixture.receipt["map"]["package"], "map"),
            project_tree=fixture.receipt["project_static_tree"],
            finish_document=fixture.profile,
            migration=execution["composition_contract"]["migration"],
        )


def test_complete_current_state_and_host_current_bytes_fail_closed(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path / "complete")
    complete_path = fixture.receipt_path.parent / launcher.COMPLETE_NAME
    complete = json.loads(complete_path.read_text(encoding="utf-8"))
    complete["current_state"]["static_delta"]["changed_file_count"] = 9
    _write_t3(complete_path, complete)
    with pytest.raises(base.HumanVisualDemoError, match="COMPLETE"):
        fixture.load()

    fixture = _fixture(tmp_path / "host")
    host_path = Path(
        fixture.receipt["hssd_r2_citysample_live_r1_upgrade"]["host_receipt"]["path"]
    )
    host = json.loads(host_path.read_text(encoding="utf-8"))
    host["current_byte_revalidation"]["passed"] = False
    _write_t3(host_path, host)
    with pytest.raises(base.HumanVisualDemoError, match="receipt pin"):
        fixture.load()


def test_fixed_command_is_human_only_gpu0_display118_1080p60(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    inputs = fixture.load()
    command = launcher.build_command(inputs)
    environment = base.sanitized_environment(
        tmp_path / "private", base.runtime_cache_root(inputs.runtime)
    )
    rendered = " ".join(command).lower()
    assert "-graphicsadapter=0" in command
    assert "-ResX=1920" in command and "-ResY=1080" in command
    assert "-VistaHumanOperatedVisualDemo" in command
    assert environment["DISPLAY"] == ":118"
    assert environment["CUDA_VISIBLE_DEVICES"] == "0"
    assert "agent-adapter" not in rendered and "vlm" not in rendered


def test_r6_rollback_is_exact_reconstructive_zero_write(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    with (
        mock.patch.object(launcher.subprocess, "Popen") as popen,
        mock.patch.object(launcher.subprocess, "run") as run,
    ):
        plan = launcher.preflight_r6_rollback(
            trust=fixture.trust, parent_loader=fixture.parent_loader
        )
    popen.assert_not_called()
    run.assert_not_called()
    assert plan["zero_write"] is True
    assert plan["service_change_performed"] is False
    assert plan["gpu_process_change_performed"] is False
    assert plan["command"][0] == str(fixture.trust.systemd_run.path)


def test_launch_acknowledgements_precede_any_process(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    inputs = fixture.load()
    popen = mock.Mock()
    with pytest.raises(base.HumanVisualDemoError, match="human-operated"):
        launcher.run_human_visual_demo(
            inputs,
            human_ack="",
            epic_ack=launcher.EPIC_UE_ONLY_ACK,
            popen_factory=popen,
        )
    popen.assert_not_called()


def test_pre_popen_revalidation_rejects_changed_receipt(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    inputs = fixture.load()
    changed = replace(inputs, runtime=replace(inputs.runtime, receipt_sha256="0" * 64))
    popen = mock.Mock()
    with (
        mock.patch.object(base, "LOCK_ROOT", tmp_path / "locks"),
        mock.patch.object(base, "CACHE_PARENT", tmp_path / "cache"),
        pytest.raises(base.HumanVisualDemoError, match="before launch"),
    ):
        launcher.run_human_visual_demo(
            inputs,
            human_ack=launcher.HUMAN_OPERATION_ACK,
            epic_ack=launcher.EPIC_UE_ONLY_ACK,
            trust=fixture.trust,
            loader=lambda _path: changed,
            rollback_loader=fixture.parent_loader,
            popen_factory=popen,
            startup_grace_seconds=0,
        )
    popen.assert_not_called()


def test_v2_v4_contract_bytes_and_shapes_remain_owned_by_base() -> None:
    assert base.COMBINED_RECEIPT_SCHEMA_V2.endswith("/v2")
    assert base.COMBINED_RECEIPT_SCHEMA_V3.endswith("/v3")
    assert base.COMBINED_RECEIPT_SCHEMA_V4.endswith("/v4")
    assert "hssd_r2_citysample_live_r1_upgrade" not in base.RECEIPT_V4_KEYS
    assert launcher.COMBINED_RECEIPT_SCHEMA_V5 not in {
        base.COMBINED_RECEIPT_SCHEMA_V2,
        base.COMBINED_RECEIPT_SCHEMA_V3,
        base.COMBINED_RECEIPT_SCHEMA_V4,
    }
