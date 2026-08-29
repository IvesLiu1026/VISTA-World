from __future__ import annotations

import copy
import hashlib
import importlib
import importlib.util
import json
import shutil
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from unittest import mock

import pytest
from tools.blender.vista_playable_home_r9_fixtures import forge as fixture_forge
from tools.tests.test_vista_playable_home_r9_fixtures import _write_artifact_fixture

from tools.runtime.vista_playable_home import (
    hssd_r2_human_visual_demo_launch as launcher,
)


def _load_composition_materializer():
    qualified_name = "tools.ue.vista_playable_home.materialize_hssd_r2_citysample_live"
    try:
        return importlib.import_module(qualified_name)
    except ModuleNotFoundError:
        for root in map(Path, sys.path):
            source = root / Path(*qualified_name.split(".")).with_suffix(".py")
            if not source.is_file():
                continue
            spec = importlib.util.spec_from_file_location(qualified_name, source)
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            sys.modules[qualified_name] = module
            spec.loader.exec_module(module)
            return module
        raise


composition_materializer = _load_composition_materializer()

base = launcher.base


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _pin(path: Path) -> dict[str, object]:
    return {"path": str(path), "sha256": _sha(path), "size_bytes": path.stat().st_size}


def _write(path: Path, content: bytes, *, mode: int = 0o600) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    path.chmod(mode)
    return path


def _write_document(path: Path, payload: dict[str, object]) -> dict[str, object]:
    payload = copy.deepcopy(payload)
    payload["content_digest"] = base.content_digest(payload)
    _write(path, base.canonical_json(payload))
    return payload


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


def _composition_contract(profile: dict[str, object]) -> dict[str, object]:
    inventory = profile["hssd_r2_inventory"]
    visual_ids = sorted(inventory["visual_slot_instance_ids"])
    dynamic_ids = set(inventory["dynamic_presentation_instance_ids"])
    static_ids = sorted(set(visual_ids) - dynamic_ids)
    legacy_ids = [composition_materializer.DELETION_INSTANCE_ID, *static_ids[:41]]

    def actor(index: int, instance_id: str | None = None) -> dict[str, object]:
        tags = ["VistaRole=unrelated"]
        if instance_id is not None:
            tags = [
                "VistaHssdInstanceId=" + instance_id,
                "VistaRole=hssd_visual_shell",
            ]
        return {
            "actor_path": f"{launcher.MAP_OBJECT_PATH}.Actor_{index:03d}",
            "actor_class_path": composition_materializer.STATIC_MESH_CLASS,
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
                "semantic_target_id": composition_materializer.DYNAMIC_SLOT_BINDINGS.get(
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
            },
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

    dynamic_observations = {
        instance_id: observation(semantic_id, index)
        for index, (instance_id, semantic_id) in enumerate(
            composition_materializer.DYNAMIC_SLOT_BINDINGS.items()
        )
    }
    pot_id = "hssd.r1/kitchen_dining.pot.01"
    r6_result = {
        "actor_inventory_reloaded": actors,
        "target_observations_reloaded": [
            dynamic_observations[key]
            for key in sorted(dynamic_observations)
            if key != pot_id
        ],
        "pot_observation_reloaded": dynamic_observations[pot_id],
    }
    return composition_materializer.build_migration_contract(
        actors, placements, r6_result, collision
    )


def _write_t2_fixture_bundle(root: Path) -> tuple[dict, dict, dict]:
    partial, worker = _write_artifact_fixture(root)
    plan = fixture_forge.seal_document(
        {
            "schema_version": fixture_forge.PLAN_SCHEMA,
            "mode": "apply",
            "attempt_name": "fixture-test-apply",
            "output_root": str(root),
            "profile": partial["profile"],
            "recipe": partial["recipe"],
            "builder_sources": fixture_forge._source_pins(),
            "toolchain": partial["toolchain"],
            "archetypes": partial["archetypes"],
            "ue_package_inventory": partial["ue_package_inventory"],
            "execution_policy": {
                "headless": True,
                "factory_startup": True,
                "autoexec_disabled": True,
                "network_namespace": "unshared",
                "pid_namespace": "unshared",
                "gpu_devices_visible": False,
                "display_environment_forwarded": False,
                "preview_device": "CPU",
                "caller_selected_binary": False,
                "caller_selected_script": False,
                "caller_selected_assets": False,
            },
            "will_write": True,
            "will_execute_blender": True,
            "binary_payload_in_git": False,
            "claims": {
                "visual_acceptance": False,
                "ue_imported": False,
                "gta_quality_accepted": False,
            },
            "status": "authorized_apply_preflight",
        }
    )
    worker_rows = []
    for archetype_id in fixture_forge.EXPECTED_ARCHETYPE_IDS:
        receipt_path = (
            root
            / fixture_forge.EXPECTED_ARTIFACT_RELATIVE_PATHS[archetype_id]["receipt"]
        )
        receipt = fixture_forge.load_json(receipt_path)
        receipt["plan_content_digest"] = plan["content_digest"]
        receipt = fixture_forge.seal_document(receipt)
        receipt_path.write_bytes(fixture_forge.canonical_json_bytes(receipt))
        worker_row = next(
            row for row in worker["artifacts"] if row["archetype_id"] == archetype_id
        )
        worker_row["receipt_content_digest"] = receipt["content_digest"]
        worker_rows.append(worker_row)
    worker["plan_content_digest"] = plan["content_digest"]
    worker["artifacts"] = worker_rows
    worker = fixture_forge.seal_document(worker)
    inventory = fixture_forge._build_inventory(plan, worker, root)
    (root / "forge-plan.json").write_bytes(fixture_forge.canonical_json_bytes(plan))
    (root / "worker-result.json").write_bytes(
        fixture_forge.canonical_json_bytes(worker)
    )
    return plan, worker, inventory


@dataclass
class Fixture:
    receipt_path: Path
    receipt: dict[str, object]
    trust: launcher.LauncherTrust
    parent: base.HumanVisualDemoInputs

    def parent_loader(self, path: Path) -> base.HumanVisualDemoInputs:
        assert path == self.trust.r6_receipt.path
        return self.parent

    def load(self) -> launcher.R9HumanVisualDemoInputs:
        return launcher.load_combined_receipt(
            self.receipt_path, trust=self.trust, parent_loader=self.parent_loader
        )

    def reseal(self) -> None:
        self.receipt["content_digest"] = base.content_digest(self.receipt)
        raw = base.canonical_json(self.receipt)
        self.receipt_path.write_bytes(raw)
        self.receipt_path.with_name(base.COMBINED_RECEIPT_SIDECAR_NAME).write_text(
            f"{hashlib.sha256(raw).hexdigest()}  {base.COMBINED_RECEIPT_NAME}\n",
            encoding="ascii",
        )


def _fixture(tmp_path: Path) -> Fixture:
    source_project, source_map = _write_project(
        tmp_path / "r6-project", b"sealed-r6-map\n"
    )
    output_root = tmp_path / "r9-attempt"
    output_project, output_map = _write_project(
        output_root / "project", b"sealed-r9-map-plus-hssd-finish\n"
    )
    namespace_relative = Path(launcher.HSSD_NAMESPACE_RELATIVE)
    namespace_bytes = b"byte-identical-hssd-namespace\n"
    _write(
        source_project.parent / namespace_relative / "Fixture.uasset", namespace_bytes
    )
    _write(
        output_project.parent / namespace_relative / "Fixture.uasset", namespace_bytes
    )
    executable = _write(
        tmp_path / "UE/Engine/Binaries/Linux/UnrealEditor",
        b"#!/bin/sh\nexit 0\n",
        mode=0o500,
    )
    unreal_cmd = _write(
        executable.with_name("UnrealEditor-Cmd"), b"#!/bin/sh\nexit 0\n", mode=0o500
    )
    build_version = _write(
        tmp_path / "UE/Engine/Build/Build.version", b'{"MajorVersion":5}\n'
    )

    provenance: dict[str, object] = {}
    for key in base.SOURCE_PROVENANCE_ARTIFACT_KEYS:
        artifact = _write(tmp_path / "provenance" / f"{key}.json", b'{"sealed":true}\n')
        provenance[key] = _pin(artifact)
    provenance["plugin_package_tree_sha256"] = "a" * 64
    provenance["plugin_source_git_commit"] = "b" * 40

    r6_receipt = _write(
        tmp_path / "rollback-evidence" / base.COMBINED_RECEIPT_NAME,
        b'{"sealed":"r6-v4-parent"}\n',
    )
    r6_workdir = tmp_path / "r6-worktree"
    r6_launcher = _write(
        r6_workdir / "tools/runtime/vista_playable_home/human_visual_demo_launch.py",
        b"# sealed rollback launcher\n",
    )
    uv = _write(tmp_path / "bin/uv", b"#!/bin/sh\nexit 0\n", mode=0o500)
    systemd_run = _write(
        tmp_path / "bin/systemd-run", b"#!/bin/sh\nexit 0\n", mode=0o500
    )
    hssd_host = _write(tmp_path / "hssd/host.json", b'{"sealed":"host"}\n')
    hssd_scene = _write(tmp_path / "hssd/scene.json", b'{"sealed":"scene"}\n')
    hssd_plan = _write(tmp_path / "hssd/build-plan.json", b'{"sealed":"plan"}\n')
    hssd_map = _write(tmp_path / "hssd/VistaPlayableHome.umap", b"hssd-authority-map\n")

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
        finish_profile_sha256=launcher.FINISH_PROFILE_SHA256,
        finish_profile_size_bytes=launcher.FINISH_PROFILE_BYTES,
        finish_profile_content_digest="0" * 64,
        engine_version=launcher.ENGINE_VERSION,
        hssd_namespace_relative=launcher.HSSD_NAMESPACE_RELATIVE,
        hssd_namespace_tree={},
    )
    source_project_pin = base.ArtifactPin(
        source_project, _sha(source_project), source_project.stat().st_size
    )
    source_map_pin = base.ArtifactPin(
        source_map, _sha(source_map), source_map.stat().st_size
    )
    executable_pin = base.ArtifactPin(
        executable, _sha(executable), executable.stat().st_size
    )
    r6_accessory_result = _write(
        tmp_path / "rollback-evidence/accessory-r6-result.json",
        b'{"sealed":"r6-accessory-result"}\n',
    )
    parent = base.HumanVisualDemoInputs(
        receipt=r6_receipt,
        receipt_sha256=_sha(r6_receipt),
        receipt_content_digest="c" * 64,
        project=source_project_pin,
        project_static_tree=base.compute_project_static_tree(source_project),
        source_provenance=copy.deepcopy(provenance),
        executable=executable_pin,
        map_object_path=launcher.MAP_OBJECT_PATH,
        map_package=source_map_pin,
        receipt_schema_version=base.COMBINED_RECEIPT_SCHEMA_V4,
        realism_r4_upgrade={"sealed": True},
        accessory_r6_upgrade={"result": _pin(r6_accessory_result)},
    )

    materializer = _write(
        output_root / "materialize_hssd_r2_citysample_live.py",
        b"# sealed materializer\n",
    )
    commandlet = _write(
        output_root / "compose_hssd_r2_citysample_live_commandlet.py",
        b"# sealed commandlet\n",
    )
    authority = {
        "host_receipt": trust.hssd_host_receipt.document(),
        "scene_receipt": trust.hssd_scene_receipt.document(),
        "build_plan": trust.hssd_build_plan.document(),
        "map_package": trust.hssd_map_package.document(),
        **launcher.HSSD_AUTHORITY_COUNTS,
    }
    profile_path = output_root / launcher.LOCAL_ARTIFACT_NAMES["finish_profile"]
    shutil.copyfile(fixture_forge.PROFILE_PATH, profile_path)
    profile_path.chmod(0o600)
    profile_document = fixture_forge.load_profile(profile_path)
    _plan, _worker_result, inventory_document = _write_t2_fixture_bundle(output_root)
    inventory_path = output_root / launcher.LOCAL_ARTIFACT_NAMES["fixture_inventory"]
    inventory_path.write_bytes(fixture_forge.canonical_json_bytes(inventory_document))
    inventory_path.chmod(0o600)
    for package_name in profile_document["fixture_imports"]["exact_package_names"]:
        package_relative = Path(
            "Content/" + package_name.removeprefix("/Game/") + ".uasset"
        )
        _write(
            output_project.parent / package_relative,
            (package_name + "\n").encode("utf-8"),
        )
    source_manifest = base._project_static_manifest(source_project)
    namespace_manifest = {
        relative: record
        for relative, record in source_manifest.items()
        if relative.startswith(launcher.HSSD_NAMESPACE_RELATIVE + "/")
    }
    namespace_tree = launcher._manifest_tree(namespace_manifest)
    trust = replace(
        trust,
        finish_profile_sha256=_sha(profile_path),
        finish_profile_size_bytes=profile_path.stat().st_size,
        finish_profile_content_digest=str(profile_document["content_digest"]),
        hssd_namespace_tree=namespace_tree,
    )
    output_tree = base.compute_project_static_tree(output_project)
    result_path = output_root / launcher.LOCAL_ARTIFACT_NAMES["result"]
    result_sidecar = result_path.with_name(result_path.name + ".sha256")
    execution_path = output_root / launcher.LOCAL_ARTIFACT_NAMES["execution"]
    acknowledgements = {
        key: f"acknowledged {key}" for key in launcher.EXECUTION_ACKNOWLEDGEMENT_KEYS
    }
    _write_document(
        execution_path,
        {
            "schema_version": launcher.EXECUTION_SCHEMA,
            "status": launcher.EXECUTION_STATUS,
            "attempt_root": str(output_root),
            "project": _pin(output_project),
            "materializer": _pin(materializer),
            "commandlet": _pin(commandlet),
            "finish_profile": _pin(profile_path),
            "fixture_inventory": _pin(inventory_path),
            "parent_combined_receipt": trust.r6_receipt.document(),
            "r6_accessory_result": _pin(r6_accessory_result),
            "hssd_r2_authority": authority,
            "source_project_static_tree": copy.deepcopy(parent.project_static_tree),
            "source_static_manifest": copy.deepcopy(source_manifest),
            "hssd_namespace": copy.deepcopy(namespace_tree),
            "composition_contract": _composition_contract(profile_document),
            "engine": {
                "version": trust.engine_version,
                "unreal_editor_cmd": _pin(unreal_cmd),
                "build_version": _pin(build_version),
                "bwrap": trust.bwrap.document(),
                "null_rhi": True,
            },
            "map": {
                "object_path": launcher.MAP_OBJECT_PATH,
                "relative_path": (
                    "Content/VISTA/PlayableHome/vista_playable_home_r1/Maps/"
                    "VistaPlayableHome.umap"
                ),
                "source_package": _pin(source_map),
            },
            "result": {"path": str(result_path), "sidecar_path": str(result_sidecar)},
            "legal_scope": copy.deepcopy(base.LEGAL_SCOPE),
            "acknowledgements": acknowledgements,
            "claims": copy.deepcopy(base.CLAIMS),
            "acceptance": copy.deepcopy(launcher.ACCEPTANCE),
        },
    )
    _write_document(
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
            "project_static_tree": copy.deepcopy(output_tree),
            "observations": copy.deepcopy(launcher.OBSERVATIONS),
            "legal_scope": copy.deepcopy(base.LEGAL_SCOPE),
            "claims": copy.deepcopy(base.CLAIMS),
            "acceptance": copy.deepcopy(launcher.ACCEPTANCE),
            "gates": {key: True for key in launcher.RESULT_GATES},
            "error": None,
        },
    )
    result_sidecar.write_text(
        f"{_sha(result_path)}  {result_path.name}\n", encoding="ascii"
    )
    scene_path = output_root / launcher.LOCAL_ARTIFACT_NAMES["scene_receipt"]
    _write_document(
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
            "project_static_tree": copy.deepcopy(output_tree),
            "observations": copy.deepcopy(launcher.OBSERVATIONS),
            "legal_scope": copy.deepcopy(base.LEGAL_SCOPE),
            "claims": copy.deepcopy(base.CLAIMS),
            "acceptance": copy.deepcopy(launcher.ACCEPTANCE),
        },
    )
    log_path = _write(
        output_root / "hssd-r2-citysample-live-commandlet.log", b"UE zero\n"
    )
    logs = [_pin(log_path)]
    host_path = output_root / launcher.LOCAL_ARTIFACT_NAMES["host_receipt"]
    _write_document(
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
            "project_static_tree": copy.deepcopy(output_tree),
            "logs": logs,
            "current_byte_revalidation": {
                "execution": _pin(execution_path),
                "result": _pin(result_path),
                "scene_receipt": _pin(scene_path),
                "map": _pin(output_map),
                "project_static_tree": copy.deepcopy(output_tree),
                "logs": logs,
                "passed": True,
            },
            "legal_scope": copy.deepcopy(base.LEGAL_SCOPE),
            "claims": copy.deepcopy(base.CLAIMS),
            "acceptance": copy.deepcopy(launcher.ACCEPTANCE),
        },
    )
    local_paths = {
        "finish_profile": profile_path,
        "fixture_inventory": inventory_path,
        "execution": execution_path,
        "result": result_path,
        "scene_receipt": scene_path,
        "host_receipt": host_path,
    }
    upgrade: dict[str, object] = {
        "schema_version": launcher.UPGRADE_SCHEMA,
        "status": launcher.UPGRADE_STATUS,
        "parent_combined_receipt": trust.r6_receipt.document(),
        "source_map": _pin(source_map),
        "source_project_static_tree": copy.deepcopy(parent.project_static_tree),
        "hssd_r2_authority": authority,
        **{key: _pin(path) for key, path in local_paths.items()},
        "materializer": _pin(materializer),
        "commandlet": _pin(commandlet),
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
    receipt: dict[str, object] = {
        "schema_version": launcher.COMBINED_RECEIPT_SCHEMA_V5,
        "status": base.COMBINED_RECEIPT_STATUS,
        "provider_id": base.PROVIDER_ID,
        "human_operated_visual_demo_only": True,
        "prohibited_agent_adapter": True,
        "project": _pin(output_project),
        "project_static_tree": copy.deepcopy(upgrade["output_project_static_tree"]),
        "source_provenance": provenance,
        "executable": _pin(executable),
        "map": {"object_path": launcher.MAP_OBJECT_PATH, "package": _pin(output_map)},
        "legal_scope": copy.deepcopy(base.LEGAL_SCOPE),
        "claims": copy.deepcopy(base.CLAIMS),
        "hssd_r2_citysample_live_r1_upgrade": upgrade,
    }
    receipt["content_digest"] = base.content_digest(receipt)
    receipt_path = output_root / base.COMBINED_RECEIPT_NAME
    raw = base.canonical_json(receipt)
    _write(receipt_path, raw)
    receipt_path.with_name(base.COMBINED_RECEIPT_SIDECAR_NAME).write_text(
        f"{hashlib.sha256(raw).hexdigest()}  {base.COMBINED_RECEIPT_NAME}\n",
        encoding="ascii",
    )
    return Fixture(
        receipt_path=receipt_path, receipt=receipt, trust=trust, parent=parent
    )


def test_v5_receipt_closes_r6_hssd_finish_and_pending_boundaries(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    inputs = fixture.load()

    assert inputs.runtime.receipt_schema_version == launcher.COMBINED_RECEIPT_SCHEMA_V5
    assert inputs.runtime.map_object_path == launcher.MAP_OBJECT_PATH
    assert inputs.parent_r6 == fixture.parent
    assert inputs.upgrade["hssd_r2_authority"]["placement_count"] == 60
    assert inputs.upgrade["observations"] == launcher.OBSERVATIONS
    assert inputs.upgrade["acceptance"] == launcher.ACCEPTANCE
    local_profile = Path(inputs.upgrade["finish_profile"]["path"])
    assert local_profile.read_bytes() == fixture_forge.PROFILE_PATH.read_bytes()
    assert local_profile.read_bytes().startswith(b'{\n  "schema_version"')


def test_v5_revalidates_current_fixture_glb_and_local_receipt_pin(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    fixture.load()
    glb = fixture.receipt_path.parent / "artifacts/flush_dome.glb"
    glb.write_bytes(glb.read_bytes() + b"drift")
    with pytest.raises(base.HumanVisualDemoError, match="current artifact validation"):
        fixture.load()

    fixture = _fixture(tmp_path / "pin")
    result_path = Path(
        fixture.receipt["hssd_r2_citysample_live_r1_upgrade"]["result"]["path"]
    )
    result_path.write_bytes(result_path.read_bytes() + b"drift")
    with pytest.raises(base.HumanVisualDemoError, match="receipt pin"):
        fixture.load()


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda receipt: receipt.update({"extra": True}), "key inventory"),
        (
            lambda receipt: receipt.update({"prohibited_agent_adapter": False}),
            "identity differs",
        ),
        (
            lambda receipt: receipt["claims"].update({"gta_level_quality": True}),
            "claims boolean values differ",
        ),
        (
            lambda receipt: receipt["hssd_r2_citysample_live_r1_upgrade"][
                "acceptance"
            ].update({"human_visual_acceptance": "accepted"}),
            "acceptance boundary differs",
        ),
        (
            lambda receipt: receipt["hssd_r2_citysample_live_r1_upgrade"][
                "observations"
            ].update({"secondary_query_proxies": 19}),
            "observations differ",
        ),
        (
            lambda receipt: receipt["hssd_r2_citysample_live_r1_upgrade"][
                "hssd_r2_authority"
            ].update({"placement_count": 59}),
            "placement_count differs",
        ),
    ],
)
def test_v5_scope_inventory_and_counts_fail_closed(
    tmp_path: Path, mutation, message: str
) -> None:
    fixture = _fixture(tmp_path)
    mutation(fixture.receipt)
    fixture.reseal()

    with pytest.raises(base.HumanVisualDemoError, match=message):
        fixture.load()


def test_nested_result_cannot_reseal_positive_agent_or_gta_claim(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    upgrade = fixture.receipt["hssd_r2_citysample_live_r1_upgrade"]
    result_path = Path(upgrade["result"]["path"])
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["claims"]["gta_level_quality"] = True
    _write_document(result_path, result)
    result_path.with_name(result_path.name + ".sha256").write_text(
        f"{_sha(result_path)}  {result_path.name}\n", encoding="ascii"
    )
    upgrade["result"] = _pin(result_path)
    fixture.reseal()

    with pytest.raises(base.HumanVisualDemoError, match="claims boolean values differ"):
        fixture.load()


def test_execution_cannot_select_different_materializer_even_when_resealed(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    upgrade = fixture.receipt["hssd_r2_citysample_live_r1_upgrade"]
    execution_path = Path(upgrade["execution"]["path"])
    execution = json.loads(execution_path.read_text(encoding="utf-8"))
    execution["materializer"] = copy.deepcopy(execution["commandlet"])
    _write_document(execution_path, execution)
    upgrade["execution"] = _pin(execution_path)
    fixture.reseal()

    with pytest.raises(base.HumanVisualDemoError, match="source/script binding"):
        fixture.load()


@pytest.mark.parametrize(
    ("field", "replacement", "message"),
    [
        ("engine", {"version": "5.7.999"}, "engine binding"),
        ("hssd_namespace", {"tree_sha256": "0" * 64}, "HSSD namespace"),
    ],
)
def test_execution_rejects_engine_and_hssd_namespace_drift(
    tmp_path: Path, field: str, replacement: dict[str, object], message: str
) -> None:
    fixture = _fixture(tmp_path)
    upgrade = fixture.receipt["hssd_r2_citysample_live_r1_upgrade"]
    execution_path = Path(upgrade["execution"]["path"])
    execution = json.loads(execution_path.read_text(encoding="utf-8"))
    if field == "engine":
        execution["engine"].update(replacement)
    else:
        execution[field] = replacement
    _write_document(execution_path, execution)
    upgrade["execution"] = _pin(execution_path)
    fixture.reseal()

    with pytest.raises(base.HumanVisualDemoError, match=message):
        fixture.load()


def test_static_delta_rejects_extra_content_and_missing_fixture_package(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path / "extra")
    source = base._project_static_manifest(fixture.parent.project.path)
    project = Path(fixture.receipt["project"]["path"])
    profile = fixture_forge.load_profile(
        Path(
            fixture.receipt["hssd_r2_citysample_live_r1_upgrade"]["finish_profile"][
                "path"
            ]
        )
    )
    _write(project.parent / "Content/Untrusted/Extra.uasset", b"extra\n")
    with pytest.raises(base.HumanVisualDemoError, match="map plus nine"):
        launcher._validate_source_output_delta(
            source_manifest=source,
            output_manifest=base._project_static_manifest(project),
            finish_document=profile,
        )

    fixture = _fixture(tmp_path / "missing")
    source = base._project_static_manifest(fixture.parent.project.path)
    project = Path(fixture.receipt["project"]["path"])
    profile = fixture_forge.load_profile(
        Path(
            fixture.receipt["hssd_r2_citysample_live_r1_upgrade"]["finish_profile"][
                "path"
            ]
        )
    )
    missing = min(launcher._fixture_package_paths(profile))
    (project.parent / missing).unlink()
    with pytest.raises(base.HumanVisualDemoError, match="map plus nine"):
        launcher._validate_source_output_delta(
            source_manifest=source,
            output_manifest=base._project_static_manifest(project),
            finish_document=profile,
        )


def test_result_and_host_have_closed_semantic_current_byte_envelopes(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    upgrade = fixture.receipt["hssd_r2_citysample_live_r1_upgrade"]
    result_path = Path(upgrade["result"]["path"])
    result = json.loads(result_path.read_text(encoding="utf-8"))
    result["extra"] = True
    _write_document(result_path, result)
    result_path.with_name(result_path.name + ".sha256").write_text(
        f"{_sha(result_path)}  {result_path.name}\n", encoding="ascii"
    )
    upgrade["result"] = _pin(result_path)
    fixture.reseal()

    with pytest.raises(base.HumanVisualDemoError, match="R9 result.*key inventory"):
        fixture.load()

    fixture = _fixture(tmp_path / "host")
    upgrade = fixture.receipt["hssd_r2_citysample_live_r1_upgrade"]
    host_path = Path(upgrade["host_receipt"]["path"])
    host = json.loads(host_path.read_text(encoding="utf-8"))
    host["current_byte_revalidation"]["passed"] = False
    _write_document(host_path, host)
    upgrade["host_receipt"] = _pin(host_path)
    fixture.reseal()
    with pytest.raises(base.HumanVisualDemoError, match="current-byte receipt differs"):
        fixture.load()


def test_v5_rejects_caller_selected_project_map_executable_and_provider(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    alternate = _write(tmp_path / "alternate.uproject", b'{"FileVersion":3}\n')
    fixture.receipt["project"] = _pin(alternate)
    fixture.reseal()

    with pytest.raises(base.HumanVisualDemoError, match="project descriptor binding"):
        fixture.load()

    destinations = {action.dest for action in launcher.parser()._actions}
    assert destinations == {
        "help",
        "combined_receipt",
        "rollback_preflight",
        "ack_human_operated",
        "ack_epic_ue_only",
        "launch",
    }
    for arguments in (
        ["--provider", "other"],
        ["--map", "/Game/Other"],
        ["--executable", "/tmp/UE"],
        ["--project", "/tmp/demo.uproject"],
        ["--display", ":117"],
        ["--gpu", "1"],
        ["--agent-adapter", "claude"],
        ["--vlm-review", "on"],
    ):
        with pytest.raises(SystemExit):
            launcher.parser().parse_args(arguments)


def test_fixed_command_is_human_only_gpu0_display118_1080p60(tmp_path: Path) -> None:
    fixture = _fixture(tmp_path)
    inputs = fixture.load()
    command = launcher.build_command(inputs)
    environment = base.sanitized_environment(
        tmp_path / "private", base.runtime_cache_root(inputs.runtime)
    )
    rendered = " ".join(command).lower()

    assert command[:7] == [
        "/usr/bin/bwrap",
        "--unshare-net",
        "--die-with-parent",
        "--dev-bind",
        "/",
        "/",
        "--",
    ]
    assert "-graphicsadapter=0" in command
    assert "-ResX=1920" in command
    assert "-ResY=1080" in command
    assert "-VistaHumanOperatedVisualDemo" in command
    assert f"-VistaCharacterProvider={base.PROVIDER_ID}" in command
    assert any("t.MaxFPS 60" in value for value in command)
    assert environment["DISPLAY"] == ":118"
    assert environment["CUDA_VISIBLE_DEVICES"] == "0"
    assert "agent-adapter" not in rendered
    assert "vlm" not in rendered


def test_rollback_preflight_is_executable_reconstructive_and_zero_write(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    before = sorted(
        (path.relative_to(tmp_path).as_posix(), path.read_bytes())
        for path in tmp_path.rglob("*")
        if path.is_file()
    )
    with (
        mock.patch.object(launcher.subprocess, "Popen") as popen,
        mock.patch.object(launcher.subprocess, "run") as run,
    ):
        plan = launcher.preflight_r6_rollback(
            trust=fixture.trust, parent_loader=fixture.parent_loader
        )
    popen.assert_not_called()
    run.assert_not_called()
    after = sorted(
        (path.relative_to(tmp_path).as_posix(), path.read_bytes())
        for path in tmp_path.rglob("*")
        if path.is_file()
    )

    assert after == before
    assert plan["zero_write"] is True
    assert plan["service_change_performed"] is False
    assert plan["gpu_process_change_performed"] is False
    assert plan["transient_unit_restart_assumed"] is False
    command = plan["command"]
    assert command[0] == str(fixture.trust.systemd_run.path)
    assert "--user" in command
    assert "--property=Type=exec" in command
    assert f"--working-directory={fixture.trust.r6_workdir}" in command
    assert (
        str(fixture.trust.r6_launcher.path.relative_to(fixture.trust.r6_workdir))
        in command
    )
    assert "systemctl" not in " ".join(command)


@pytest.mark.parametrize("drift", ["r6_receipt", "r6_launcher", "uv", "systemd_run"])
def test_rollback_preflight_rejects_any_current_byte_drift(
    tmp_path: Path, drift: str
) -> None:
    fixture = _fixture(tmp_path)
    target = getattr(fixture.trust, drift).path
    target.chmod(0o700)
    target.write_bytes(target.read_bytes() + b"drift\n")
    if drift in {"uv", "systemd_run"}:
        target.chmod(0o500)

    with pytest.raises(base.HumanVisualDemoError, match="receipt pin|trust anchor"):
        launcher.preflight_r6_rollback(
            trust=fixture.trust, parent_loader=fixture.parent_loader
        )


def test_launch_acknowledgements_are_required_before_lock_cache_or_popen(
    tmp_path: Path,
) -> None:
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
    with pytest.raises(base.HumanVisualDemoError, match="Epic UE-only"):
        launcher.run_human_visual_demo(
            inputs,
            human_ack=launcher.HUMAN_OPERATION_ACK,
            epic_ack="",
            popen_factory=popen,
        )
    popen.assert_not_called()
    assert not (tmp_path / "locks").exists()


def test_launch_revalidates_before_popen_and_after_grace_without_ready(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    fixture = _fixture(tmp_path)
    inputs = fixture.load()
    process = mock.Mock(pid=4242)
    process.poll.return_value = None
    popen = mock.Mock(return_value=process)
    changed = replace(
        inputs,
        runtime=replace(inputs.runtime, receipt_sha256="0" * 64),
    )
    loader = mock.Mock(side_effect=[inputs, changed])

    with (
        mock.patch.object(base, "LOCK_ROOT", tmp_path / "locks"),
        mock.patch.object(base, "CACHE_PARENT", tmp_path / "cache/human"),
        mock.patch.object(base, "_terminate_process_group") as terminate,
        pytest.raises(base.HumanVisualDemoError, match="during startup grace"),
    ):
        launcher.run_human_visual_demo(
            inputs,
            human_ack=launcher.HUMAN_OPERATION_ACK,
            epic_ack=launcher.EPIC_UE_ONLY_ACK,
            trust=fixture.trust,
            loader=loader,
            rollback_loader=fixture.parent_loader,
            popen_factory=popen,
            startup_grace_seconds=0,
        )

    popen.assert_called_once()
    terminate.assert_called()
    statuses = [
        json.loads(line)["status"] for line in capsys.readouterr().out.splitlines()
    ]
    assert statuses == [base.PENDING_STATUS]


def test_pre_popen_revalidation_refuses_changed_binding_without_process(
    tmp_path: Path,
) -> None:
    fixture = _fixture(tmp_path)
    inputs = fixture.load()
    changed = replace(inputs, runtime=replace(inputs.runtime, receipt_sha256="0" * 64))
    popen = mock.Mock()

    with (
        mock.patch.object(base, "LOCK_ROOT", tmp_path / "locks"),
        mock.patch.object(base, "CACHE_PARENT", tmp_path / "cache/human"),
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


def test_existing_v2_v4_launcher_contract_is_not_extended_in_place() -> None:
    assert base.COMBINED_RECEIPT_SCHEMA_V2.endswith("/v2")
    assert base.COMBINED_RECEIPT_SCHEMA_V3.endswith("/v3")
    assert base.COMBINED_RECEIPT_SCHEMA_V4.endswith("/v4")
    assert launcher.COMBINED_RECEIPT_SCHEMA_V5 not in {
        base.COMBINED_RECEIPT_SCHEMA_V2,
        base.COMBINED_RECEIPT_SCHEMA_V3,
        base.COMBINED_RECEIPT_SCHEMA_V4,
    }
    assert "hssd_r2_citysample_live_r1_upgrade" not in base.RECEIPT_V4_KEYS
