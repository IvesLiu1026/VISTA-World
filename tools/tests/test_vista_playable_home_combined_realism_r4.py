from __future__ import annotations

import copy
import dataclasses
import errno
import hashlib
import importlib.util
import json
import os
import shutil
import signal
import subprocess
import sys
import threading
import time
import types
from pathlib import Path
from unittest import mock

import pytest

from tools.runtime.vista_playable_home import human_visual_demo_launch as launcher
from tools.ue.vista_playable_home import materialize_combined_realism_r4 as r4


PROFILE_SOURCE = (
    Path(__file__).resolve().parents[2]
    / "world_packs/vista_playable_home_r1/visual_profiles/realistic_interior_r4.json"
)
COMMANDLET_SOURCE = (
    Path(__file__).resolve().parents[1]
    / "ue/vista_playable_home/compose_combined_realism_r4_commandlet.py"
)
MATERIALIZER_SOURCE = Path(r4.__file__).resolve()


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _pin(path: Path) -> dict[str, object]:
    return {"path": str(path), "sha256": _sha(path), "size_bytes": path.stat().st_size}


def _write_parent_receipt(root: Path) -> tuple[Path, dict[str, object]]:
    project = root / "source/project/VistaPlayableHome.uproject"
    map_package = (
        root / "source/project/Content/VISTA/PlayableHome/vista_playable_home_r1/Maps/"
        "VistaPlayableHome.umap"
    )
    config = root / "source/project/Config/DefaultEngine.ini"
    plugin = root / "source/project/Plugins/VistaPlayableHome/VistaPlayableHome.uplugin"
    executable = root / "engine/UnrealEditor"
    project.parent.mkdir(parents=True)
    map_package.parent.mkdir(parents=True)
    config.parent.mkdir(parents=True)
    plugin.parent.mkdir(parents=True)
    executable.parent.mkdir(parents=True)
    project.write_text('{"FileVersion":3}\n', encoding="utf-8")
    map_package.write_bytes(b"sealed-r3-map\n")
    config.write_text(
        "[/Script/Engine.RendererSettings]\n"
        "r.DynamicGlobalIlluminationMethod=1\n"
        "r.ReflectionMethod=1\n"
        "r.Shadow.Virtual.Enable=1\n"
        "r.AntiAliasingMethod=4\n"
        "r.RayTracing=False\n"
        "r.Lumen.HardwareRayTracing=0\n",
        encoding="utf-8",
    )
    plugin.write_text('{"FileVersion":3}\n', encoding="utf-8")
    executable.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    executable.chmod(0o500)

    provenance: dict[str, object] = {}
    for key in launcher.SOURCE_PROVENANCE_ARTIFACT_KEYS:
        artifact = root / "source-provenance" / f"{key}.json"
        artifact.parent.mkdir(parents=True, exist_ok=True)
        artifact.write_text(f'{{"source":"{key}"}}\n', encoding="utf-8")
        provenance[key] = _pin(artifact)
    provenance["plugin_package_tree_sha256"] = "a" * 64
    provenance["plugin_source_git_commit"] = "b" * 40
    receipt: dict[str, object] = {
        "schema_version": launcher.COMBINED_RECEIPT_SCHEMA_V2,
        "status": launcher.COMBINED_RECEIPT_STATUS,
        "provider_id": launcher.PROVIDER_ID,
        "human_operated_visual_demo_only": True,
        "prohibited_agent_adapter": True,
        "project": _pin(project),
        "project_static_tree": launcher.compute_project_static_tree(project),
        "source_provenance": provenance,
        "executable": _pin(executable),
        "map": {"object_path": r4.MAP_OBJECT_PATH, "package": _pin(map_package)},
        "legal_scope": copy.deepcopy(launcher.LEGAL_SCOPE),
        "claims": copy.deepcopy(launcher.CLAIMS),
    }
    receipt["content_digest"] = launcher.content_digest(receipt)
    receipt_path = root / "source" / launcher.COMBINED_RECEIPT_NAME
    raw = launcher.canonical_json(receipt)
    receipt_path.write_bytes(raw)
    receipt_path.with_name(launcher.COMBINED_RECEIPT_SIDECAR_NAME).write_text(
        f"{hashlib.sha256(raw).hexdigest()}  {launcher.COMBINED_RECEIPT_NAME}\n",
        encoding="ascii",
    )
    return receipt_path, receipt


def _fixture_config(tmp_path: Path) -> tuple[r4.Config, Path, dict[str, object]]:
    run_parent = tmp_path / "runs"
    run_parent.mkdir(mode=0o700)
    receipt_path, receipt = _write_parent_receipt(run_parent)
    profile = tmp_path / "inputs/realistic_interior_r4.json"
    commandlet = tmp_path / "inputs/compose_combined_realism_r4_commandlet.py"
    materializer = tmp_path / "inputs/materialize_combined_realism_r4.py"
    editor_cmd = tmp_path / "engine/UnrealEditor-Cmd"
    build_version = tmp_path / "engine/Build.version"
    profile.parent.mkdir(parents=True)
    editor_cmd.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(PROFILE_SOURCE, profile)
    shutil.copyfile(COMMANDLET_SOURCE, commandlet)
    shutil.copyfile(MATERIALIZER_SOURCE, materializer)
    editor_cmd.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    editor_cmd.chmod(0o500)
    build_version.write_text('{"MajorVersion":5}\n', encoding="utf-8")
    config = r4.Config(
        repository_root=tmp_path,
        run_parent=run_parent,
        source_receipt=receipt_path,
        source_receipt_sha256=_sha(receipt_path),
        source_receipt_bytes=receipt_path.stat().st_size,
        source_project_tree=copy.deepcopy(receipt["project_static_tree"]),
        source_map_sha256=receipt["map"]["package"]["sha256"],
        source_map_bytes=receipt["map"]["package"]["size_bytes"],
        profile_source=profile,
        profile_sha256=_sha(profile),
        profile_bytes=profile.stat().st_size,
        materializer_source=materializer,
        commandlet_source=commandlet,
        unreal_editor_cmd=editor_cmd,
        unreal_editor_cmd_sha256=_sha(editor_cmd),
        unreal_editor_cmd_bytes=editor_cmd.stat().st_size,
        build_version=build_version,
        build_version_sha256=_sha(build_version),
        build_version_bytes=build_version.stat().st_size,
    )
    return config, receipt_path, receipt


def _all_files(root: Path) -> list[tuple[str, bytes]]:
    return sorted(
        (path.relative_to(root).as_posix(), path.read_bytes())
        for path in root.rglob("*")
        if path.is_file()
    )


def test_default_plan_is_zero_write_and_keeps_v2_receipt_bytes(tmp_path: Path) -> None:
    config, receipt_path, _receipt = _fixture_config(tmp_path)
    before = _all_files(tmp_path)
    parent_raw = receipt_path.read_bytes()
    attempt = config.run_parent / "combined-realism-r4-zero-write"

    prepared = r4.build_plan(attempt, config=config)

    assert prepared.report["status"] == r4.DRY_RUN_STATUS
    assert prepared.report["mode"] == "dry_run_zero_writes"
    assert prepared.report["will_write"] is False
    assert (
        prepared.source_inputs.receipt_schema_version
        == launcher.COMBINED_RECEIPT_SCHEMA_V2
    )
    assert launcher.COMBINED_RECEIPT_SCHEMA == launcher.COMBINED_RECEIPT_SCHEMA_V2
    assert receipt_path.read_bytes() == parent_raw
    assert not attempt.exists()
    assert _all_files(tmp_path) == before


def test_apply_requires_all_exact_legal_and_sealed_large_copy_acknowledgements(
    tmp_path: Path,
) -> None:
    config, _receipt_path, _receipt = _fixture_config(tmp_path)
    acknowledgements = copy.deepcopy(r4.ACKNOWLEDGEMENTS)
    acknowledgements["sealed_r3_large_copy"] = None

    with pytest.raises(r4.CombinedRealismR4Error, match="every exact legal"):
        r4.build_plan(
            config.run_parent / "combined-realism-r4-missing-copy-ack",
            apply=True,
            acknowledgements=acknowledgements,
            config=config,
        )


@pytest.mark.parametrize("target", ["source", "profile", "commandlet", "tool"])
def test_revalidation_rejects_source_profile_commandlet_or_tool_drift(
    tmp_path: Path, target: str
) -> None:
    config, _receipt_path, receipt = _fixture_config(tmp_path)
    prepared = r4.build_plan(
        config.run_parent / f"combined-realism-r4-drift-{target}", config=config
    )
    if target == "source":
        Path(receipt["project"]["path"]).write_text("changed\n", encoding="utf-8")
    elif target == "profile":
        config.profile_source.write_bytes(config.profile_source.read_bytes() + b"\n")
    elif target == "commandlet":
        config.commandlet_source.write_bytes(
            config.commandlet_source.read_bytes() + b"# drift\n"
        )
    else:
        config.unreal_editor_cmd.chmod(0o700)
        config.unreal_editor_cmd.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        config.unreal_editor_cmd.chmod(0o500)

    with pytest.raises((r4.CombinedRealismR4Error, launcher.HumanVisualDemoError)):
        r4._assert_prepared_sources(prepared)


def test_project_copy_uses_bounded_fallback_only_for_unsupported_reflink(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source.bin"
    destination = tmp_path / "destination"
    source.write_bytes(b"sealed-copy-fixture" * 32)
    source.chmod(0o600)
    destination.mkdir(mode=0o700)
    metadata = source.stat()
    record = r4.StaticRecord(
        relative_path="Content/source.bin",
        source=source,
        size_bytes=metadata.st_size,
        mode=0o600,
        device=metadata.st_dev,
        inode=metadata.st_ino,
        mtime_ns=metadata.st_mtime_ns,
    )
    project_fd = r4._open_directory(destination)
    try:
        r4._mkdir_projection(project_fd, (record,))

        def unsupported(_target, _operation, _source):
            raise OSError(errno.EOPNOTSUPP, "fixture")

        assert (
            r4._copy_record(project_fd, record, clone_function=unsupported)
            == "stream_copy"
        )
    finally:
        os.close(project_fd)
    copied = destination / record.relative_path
    assert copied.read_bytes() == source.read_bytes()
    assert copied.stat().st_mode & 0o777 == 0o600


def _load_commandlet(monkeypatch: pytest.MonkeyPatch):
    fake_unreal = types.SimpleNamespace(
        RectLight=type("RectLight", (), {}),
        SpotLight=type("SpotLight", (), {}),
        StaticMeshActor=type("StaticMeshActor", (), {}),
        StaticMesh=type("StaticMesh", (), {}),
        StaticMeshComponent=type("StaticMeshComponent", (), {}),
        LightComponentBase=type("LightComponentBase", (), {}),
        PostProcessVolume=type("PostProcessVolume", (), {}),
        LightUnits=types.SimpleNamespace(LUMENS="lumens"),
        ComponentMobility=types.SimpleNamespace(STATIC="static", MOVABLE="movable"),
        AutoExposureMethod=types.SimpleNamespace(AEM_HISTOGRAM="histogram"),
    )
    monkeypatch.setitem(sys.modules, "unreal", fake_unreal)
    spec = importlib.util.spec_from_file_location(
        "combined_r4_commandlet_test", COMMANDLET_SOURCE
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_commandlet_actor_allowlist_is_closed_and_only_one_destroy_site(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commandlet = _load_commandlet(monkeypatch)
    source = COMMANDLET_SOURCE.read_text(encoding="utf-8")

    assert commandlet.R2_REMOVAL_ALLOWLIST == r4.R2_REMOVAL_ALLOWLIST
    assert commandlet.VISIBLE_ACTOR_ROLE_ALLOWLIST == {"room", "hssd_visual_shell"}
    assert commandlet.HIDDEN_ACTOR_ROLE_ALLOWLIST == {"room_collision_proxy"}
    assert commandlet.ALLOWED_FIXTURE_MESHES == {
        "/Engine/BasicShapes/Cylinder.Cylinder"
    }
    assert source.count("destroy_actor(") == 1
    assert "for actor in removal:" in source
    assert "PixelStreaming" not in source
    assert "Sunshine" not in source
    assert "import socket" not in source
    assert "openai" not in source.lower()


def _source_manifest(project: Path) -> dict[str, dict[str, object]]:
    return {
        relative: {
            "sha256": _sha(path),
            "size_bytes": metadata.st_size,
            "mode": metadata.st_mode & 0o7777,
        }
        for relative, path, metadata in launcher._static_tree_files(project)
    }


def _sealed_document(path: Path, payload: dict[str, object]) -> None:
    payload["content_digest"] = launcher.content_digest(payload)
    path.write_bytes(launcher.canonical_json(payload))


def _actor(path: str, class_path: str, tags: list[str]) -> dict[str, object]:
    return {
        "actor_path": path,
        "actor_class_path": class_path,
        "tags": sorted(tags),
    }


def _transform(specification: dict[str, object]) -> dict[str, object]:
    return {
        "location_cm": list(specification["location_cm"]),
        "rotation_deg": [
            ((float(value) + 180.0) % 360.0) - 180.0
            for value in specification["rotation_deg"]
        ],
        "scale": list(specification["scale"]),
    }


def _result_evidence(
    profile: dict[str, object], map_package: Path, execution_sha256: str
) -> dict[str, object]:
    prefix = "/Game/Test/VistaPlayableHome.VistaPlayableHome:PersistentLevel."
    before: list[dict[str, object]] = [
        _actor(
            prefix + "R2_Entry",
            "/Script/Engine.SpotLight",
            [
                "VistaLightingRig=neutral_day_practicals_v1",
                "VistaRole=lighting",
                "VistaVisualRevision=realistic_interior_r2",
                "VistaSemanticId=light.entry_hall.01",
            ],
        ),
        _actor(
            prefix + "R2_Kitchen",
            "/Script/Engine.RectLight",
            [
                "VistaLightingRig=neutral_day_practicals_v1",
                "VistaRole=lighting",
                "VistaVisualRevision=realistic_interior_r2",
                "VistaSemanticId=light.kitchen_dining.01",
            ],
        ),
        _actor(
            prefix + "R2_Living",
            "/Script/Engine.RectLight",
            [
                "VistaLightingRig=neutral_day_practicals_v1",
                "VistaRole=lighting",
                "VistaVisualRevision=realistic_interior_r2",
                "VistaSemanticId=light.living_room.01",
            ],
        ),
        _actor(
            prefix + "R2_Post",
            "/Script/Engine.PostProcessVolume",
            [
                "VistaExposureProfile=bounded_histogram",
                "VistaLightingRig=neutral_day_practicals_v1",
                "VistaRole=post_process",
            ],
        ),
    ]
    rooms = []
    for index in range(6):
        roles = ["VistaRole=room"]
        if index >= 3:
            roles.append("VistaRole=room_collision_proxy")
        rooms.append(
            _actor(
                prefix + f"Room_{index:02d}", "/Script/Engine.StaticMeshActor", roles
            )
        )
    hssd = [
        _actor(
            prefix + f"HSSD_{index:02d}",
            "/Script/Engine.StaticMeshActor",
            ["VistaRole=hssd_visual_shell"],
        )
        for index in range(42)
    ]
    pickups = [
        _actor(
            prefix + f"Pickup_{index:02d}",
            "/Script/Engine.StaticMeshActor",
            ["VistaRole=pickup"],
        )
        for index in range(8)
    ]
    fillers = [
        _actor(
            prefix + f"Unrelated_{index:03d}",
            "/Script/Engine.Actor",
            ["VistaRole=unrelated"],
        )
        for index in range(81)
    ]
    before = sorted(
        before + rooms + hssd + pickups + fillers, key=lambda row: row["actor_path"]
    )
    assert len(before) == 141

    rig_tag = "VistaLightingRig=" + launcher.REALISM_R4_PROFILE_ID
    pairs: list[dict[str, object]] = []
    r4_actors: list[dict[str, object]] = []
    light_classes = {
        "rect": "/Script/Engine.RectLight",
        "spot": "/Script/Engine.SpotLight",
    }
    for index, specification in enumerate(
        sorted(profile["practical_fixture_light_pairs"], key=lambda row: row["pair_id"])
    ):
        fixture = specification["fixture"]
        light = specification["light"]
        fixture_path = prefix + f"R4_Fixture_{index:02d}"
        light_path = prefix + f"R4_Light_{index:02d}"
        fixture_tags = [
            "VistaRole=practical_fixture",
            "VistaRoom=" + specification["room_id"],
            "VistaR4Pair=" + specification["pair_id"],
            "VistaFixtureId=" + fixture["fixture_id"],
            rig_tag,
        ]
        light_tags = [
            "VistaRole=lighting",
            "VistaRoom=" + specification["room_id"],
            "VistaR4Pair=" + specification["pair_id"],
            "VistaPracticalLightId=" + light["light_id"],
            "VistaFixtureId=" + fixture["fixture_id"],
            rig_tag,
        ]
        r4_actors.extend(
            [
                _actor(
                    fixture_path,
                    "/Script/Engine.StaticMeshActor",
                    fixture_tags,
                ),
                _actor(light_path, light_classes[light["type"]], light_tags),
            ]
        )
        pairs.append(
            {
                "pair_id": specification["pair_id"],
                "room_id": specification["room_id"],
                "fixture_actor_path": fixture_path,
                "fixture_class_path": "/Script/Engine.StaticMeshActor",
                "fixture_mesh_object_path": fixture["mesh_object_path"],
                "fixture_transform": _transform(fixture),
                "fixture_visible": True,
                "fixture_cast_shadow": True,
                "fixture_cast_hidden_shadow": False,
                "fixture_collision_profile": "NoCollision",
                "light_actor_path": light_path,
                "light_class_path": light_classes[light["type"]],
                "light_transform": _transform(light),
                "light_intensity": light["intensity"],
                "light_temperature_k": light["temperature_k"],
                "light_attenuation_radius_cm": light["attenuation_radius_cm"],
                "light_use_temperature": True,
                "light_cast_shadow": True,
                "light_intensity_units": light["unit"],
            }
        )
    post_path = prefix + "R4_Post"
    post_tags = sorted(
        [
            "VistaRole=post_process",
            rig_tag,
            "VistaExposureProfile=bounded_histogram",
            "VistaRealismProfile=" + launcher.REALISM_R4_PROFILE_ID,
        ]
    )
    r4_actors.append(_actor(post_path, "/Script/Engine.PostProcessVolume", post_tags))
    removed = sorted(
        row["actor_path"]
        for row in before
        if row["actor_path"].split(".")[-1].startswith("R2_")
    )
    reloaded = sorted(
        [row for row in before if row["actor_path"] not in removed] + r4_actors,
        key=lambda row: row["actor_path"],
    )
    assert len(removed) == 4 and len(reloaded) == 150

    shadows: list[dict[str, object]] = []
    shadow_specs = [
        *[(rooms[index], "RoomMesh", "room_visible") for index in range(3)],
        *[(rooms[index], "RoomMesh", "room_proxy_hidden") for index in range(3, 6)],
        *[(row, "VisualMesh", "hssd_visible") for row in hssd],
        *[
            (pickups[index], "PresentationMesh", "pickup_presentation_visible")
            for index in range(3)
        ],
        *[(pickups[index], "PickupMesh", "pickup_proxy_hidden") for index in range(3)],
    ]
    for actor, component_name, category in shadow_specs:
        hidden = category in {"room_proxy_hidden", "pickup_proxy_hidden"}
        shadows.append(
            {
                "actor_path": actor["actor_path"],
                "actor_class_path": actor["actor_class_path"],
                "component_path": actor["actor_path"] + "." + component_name,
                "component_name": component_name,
                "category": category,
                "visible": not hidden,
                "cast_shadow": not hidden,
                "cast_hidden_shadow": False,
            }
        )
    shadows.sort(key=lambda row: (row["actor_path"], row["component_path"]))
    post_profile = profile["post_process"]
    post = {
        "actor_path": post_path,
        "class_path": "/Script/Engine.PostProcessVolume",
        "tags": post_tags,
        "unbound": True,
        "priority": 100.0,
        "blend_weight": 1.0,
        "motion_blur_amount": post_profile["motion_blur_amount"],
        "chromatic_aberration_intensity": post_profile[
            "chromatic_aberration_intensity"
        ],
        "film_grain_intensity": post_profile["film_grain_intensity"],
        "bloom_intensity": post_profile["bloom_intensity"],
        "vignette_intensity": post_profile["vignette_intensity"],
        "auto_exposure_method_histogram": True,
        "override_flags": {
            key: True for key in launcher.REALISM_R4_POST_OVERRIDE_FLAGS
        },
        "exposure": {
            key: post_profile["exposure"][key]
            for key in ("min_ev100", "max_ev100", "speed_up", "speed_down")
        },
    }
    return {
        "schema_version": launcher.REALISM_R4_RESULT_SCHEMA,
        "status": launcher.REALISM_R4_UPGRADE_STATUS,
        "provider_id": launcher.PROVIDER_ID,
        "human_operated_visual_demo_only": True,
        "prohibited_agent_adapter": True,
        "execution_sha256": execution_sha256,
        "profile": None,
        "map_object_path": r4.MAP_OBJECT_PATH,
        "map_package": _pin(map_package),
        "actor_inventory_before": before,
        "actor_inventory_reloaded": reloaded,
        "removed_r2_actor_paths": removed,
        "r4_pair_observations_before_save": copy.deepcopy(pairs),
        "r4_pair_observations_reloaded": copy.deepcopy(pairs),
        "post_process_observation_before_save": copy.deepcopy(post),
        "post_process_observation_reloaded": copy.deepcopy(post),
        "shadow_observations_before_save": copy.deepcopy(shadows),
        "shadow_observations_reloaded": copy.deepcopy(shadows),
        "renderer_observation": {
            "contract": copy.deepcopy(profile["renderer_contract"]),
            "force_no_precomputed_lighting": True,
            "configuration_mutation_requested": False,
            "null_rhi_visual_proof": False,
        },
        "legal_scope": copy.deepcopy(launcher.LEGAL_SCOPE),
        "claims": copy.deepcopy(launcher.CLAIMS),
        "acceptance": copy.deepcopy(launcher.REALISM_R4_ACCEPTANCE),
        "gates": {key: True for key in launcher.REALISM_R4_RESULT_GATE_KEYS},
        "error": None,
    }


def _write_v3_receipt(
    tmp_path: Path,
    parent_path: Path,
    parent: dict[str, object],
    *,
    map_mode: str = "changed",
) -> tuple[Path, dict[str, object]]:
    attempt = tmp_path / "v3"
    source_project = Path(parent["project"]["path"]).parent
    output_project = attempt / "project"
    shutil.copytree(source_project, output_project)
    output_map = output_project / Path(r4.MAP_RELATIVE_PATH)
    source_map = Path(parent["map"]["package"]["path"])
    if map_mode == "changed":
        output_map.write_bytes(b"r4-upgraded-map\n")
    elif map_mode == "same_copy":
        output_map.write_bytes(source_map.read_bytes())
    elif map_mode == "hardlink":
        output_map.unlink()
        os.link(source_map, output_map)
    else:
        raise AssertionError(map_mode)
    profile = attempt / r4.PROFILE_NAME
    execution = attempt / r4.EXECUTION_NAME
    result = attempt / r4.RESULT_NAME
    materializer = attempt / r4.MATERIALIZER_NAME
    commandlet = attempt / r4.COMMANDLET_NAME
    shutil.copyfile(PROFILE_SOURCE, profile)
    shutil.copyfile(MATERIALIZER_SOURCE, materializer)
    shutil.copyfile(COMMANDLET_SOURCE, commandlet)
    editor_cmd = tmp_path / "v3-engine/UnrealEditor-Cmd"
    build_version = tmp_path / "v3-engine/Build.version"
    editor_cmd.parent.mkdir(parents=True)
    editor_cmd.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    editor_cmd.chmod(0o500)
    build_version.write_text('{"MajorVersion":5}\n', encoding="utf-8")
    project = output_project / r4.PROJECT_NAME
    profile_payload = json.loads(profile.read_text(encoding="utf-8"))
    execution_payload: dict[str, object] = {
        "schema_version": launcher.REALISM_R4_EXECUTION_SCHEMA,
        "status": launcher.REALISM_R4_EXECUTION_STATUS,
        "attempt_root": str(attempt),
        "project": _pin(project),
        "materializer": _pin(materializer),
        "commandlet": _pin(commandlet),
        "profile": _pin(profile),
        "result": {
            "path": str(result),
            "sidecar_path": str(result) + ".sha256",
        },
        "engine": {
            "version": "5.7.3-50162420+++UE5+Release-5.7",
            "unreal_editor_cmd": _pin(editor_cmd),
            "build_version": _pin(build_version),
            "null_rhi": True,
        },
        "map": {
            "object_path": r4.MAP_OBJECT_PATH,
            "relative_path": r4.MAP_RELATIVE_PATH.as_posix(),
            "source_package": {
                "path": str(output_map),
                "sha256": parent["map"]["package"]["sha256"],
                "size_bytes": parent["map"]["package"]["size_bytes"],
            },
        },
        "parent_combined_receipt": _pin(parent_path),
        "source_project_static_tree": copy.deepcopy(parent["project_static_tree"]),
        "source_static_manifest": _source_manifest(source_project / r4.PROJECT_NAME),
        "actor_contract": copy.deepcopy(launcher.REALISM_R4_ACTOR_CONTRACT),
        "legal_scope": copy.deepcopy(launcher.LEGAL_SCOPE),
        "acknowledgements": copy.deepcopy(launcher.REALISM_R4_ACKNOWLEDGEMENTS),
        "claims": copy.deepcopy(launcher.CLAIMS),
        "acceptance": copy.deepcopy(launcher.REALISM_R4_ACCEPTANCE),
    }
    _sealed_document(execution, execution_payload)
    result_payload = _result_evidence(profile_payload, output_map, _sha(execution))
    result_payload["profile"] = _pin(profile)
    _sealed_document(result, result_payload)
    result.with_name(result.name + ".sha256").write_text(
        f"{_sha(result)}  {result.name}\n", encoding="ascii"
    )
    tree = launcher.compute_project_static_tree(project)
    receipt: dict[str, object] = {
        "schema_version": launcher.COMBINED_RECEIPT_SCHEMA_V3,
        "status": launcher.COMBINED_RECEIPT_STATUS,
        "provider_id": launcher.PROVIDER_ID,
        "human_operated_visual_demo_only": True,
        "prohibited_agent_adapter": True,
        "project": _pin(project),
        "project_static_tree": tree,
        "source_provenance": copy.deepcopy(parent["source_provenance"]),
        "executable": copy.deepcopy(parent["executable"]),
        "map": {"object_path": r4.MAP_OBJECT_PATH, "package": _pin(output_map)},
        "legal_scope": copy.deepcopy(launcher.LEGAL_SCOPE),
        "claims": copy.deepcopy(launcher.CLAIMS),
        "realism_r4_upgrade": {
            "schema_version": launcher.REALISM_R4_UPGRADE_SCHEMA,
            "status": launcher.REALISM_R4_UPGRADE_STATUS,
            "parent_combined_receipt": _pin(parent_path),
            "source_map": copy.deepcopy(parent["map"]["package"]),
            "source_project_static_tree": copy.deepcopy(parent["project_static_tree"]),
            "profile": _pin(profile),
            "profile_id": launcher.REALISM_R4_PROFILE_ID,
            "profile_content_digest": r4.PROFILE_CONTENT_DIGEST,
            "execution": _pin(execution),
            "result": _pin(result),
            "materializer": _pin(materializer),
            "commandlet": _pin(commandlet),
            "unreal_editor_cmd": _pin(editor_cmd),
            "build_version": _pin(build_version),
            "map_object_path": r4.MAP_OBJECT_PATH,
            "output_project_static_tree": tree,
            "observations": copy.deepcopy(launcher.REALISM_R4_OBSERVATIONS),
            "acceptance": copy.deepcopy(launcher.REALISM_R4_ACCEPTANCE),
        },
    }
    receipt["content_digest"] = launcher.content_digest(receipt)
    receipt_path = attempt / launcher.COMBINED_RECEIPT_NAME
    raw = launcher.canonical_json(receipt)
    receipt_path.write_bytes(raw)
    receipt_path.with_name(launcher.COMBINED_RECEIPT_SIDECAR_NAME).write_text(
        f"{hashlib.sha256(raw).hexdigest()}  {launcher.COMBINED_RECEIPT_NAME}\n",
        encoding="ascii",
    )
    return receipt_path, receipt


def test_launcher_accepts_v2_unchanged_and_v3_rejects_nested_artifact_drift(
    tmp_path: Path,
) -> None:
    parent_path, parent = _write_parent_receipt(tmp_path)
    v2_raw = parent_path.read_bytes()
    assert (
        launcher.load_combined_receipt(parent_path).receipt_schema_version
        == launcher.COMBINED_RECEIPT_SCHEMA_V2
    )
    assert parent_path.read_bytes() == v2_raw

    receipt_path, receipt = _write_v3_receipt(tmp_path, parent_path, parent)
    loaded = launcher.load_combined_receipt(receipt_path)
    assert loaded.receipt_schema_version == launcher.COMBINED_RECEIPT_SCHEMA_V3
    assert loaded.realism_r4_upgrade == receipt["realism_r4_upgrade"]

    result_path = Path(receipt["realism_r4_upgrade"]["result"]["path"])
    result_path.write_text('{"result":"drift"}\n', encoding="utf-8")
    with pytest.raises(launcher.HumanVisualDemoError, match="R4 result differs"):
        launcher.load_combined_receipt(receipt_path)


def _rewrite_receipt(receipt_path: Path, receipt: dict[str, object]) -> None:
    receipt["content_digest"] = launcher.content_digest(receipt)
    raw = launcher.canonical_json(receipt)
    receipt_path.write_bytes(raw)
    receipt_path.with_name(launcher.COMBINED_RECEIPT_SIDECAR_NAME).write_text(
        f"{hashlib.sha256(raw).hexdigest()}  {launcher.COMBINED_RECEIPT_NAME}\n",
        encoding="ascii",
    )


def _rewrite_result(
    receipt_path: Path, receipt: dict[str, object], result: dict[str, object]
) -> None:
    result_path = Path(receipt["realism_r4_upgrade"]["result"]["path"])
    _sealed_document(result_path, result)
    result_path.with_name(result_path.name + ".sha256").write_text(
        f"{_sha(result_path)}  {result_path.name}\n", encoding="ascii"
    )
    receipt["realism_r4_upgrade"]["result"] = _pin(result_path)
    _rewrite_receipt(receipt_path, receipt)


def test_launcher_v3_rejects_fixture_execution_and_result_documents(
    tmp_path: Path,
) -> None:
    for target in ("execution", "result"):
        case = tmp_path / target
        case.mkdir()
        parent_path, parent = _write_parent_receipt(case)
        receipt_path, receipt = _write_v3_receipt(case, parent_path, parent)
        nested_path = Path(receipt["realism_r4_upgrade"][target]["path"])
        nested_path.write_text(
            launcher.canonical_json({target: "fixture"}).decode("utf-8"),
            encoding="utf-8",
        )
        receipt["realism_r4_upgrade"][target] = _pin(nested_path)
        _rewrite_receipt(receipt_path, receipt)
        with pytest.raises(launcher.HumanVisualDemoError, match="non-closed key"):
            launcher.load_combined_receipt(receipt_path)


@pytest.mark.parametrize("map_mode", ["same_copy", "hardlink"])
def test_launcher_v3_rejects_same_sha_or_same_inode_parent_map(
    tmp_path: Path, map_mode: str
) -> None:
    parent_path, parent = _write_parent_receipt(tmp_path)
    receipt_path, _receipt = _write_v3_receipt(
        tmp_path, parent_path, parent, map_mode=map_mode
    )
    with pytest.raises(
        launcher.HumanVisualDemoError, match="aliases or duplicates its parent"
    ):
        launcher.load_combined_receipt(receipt_path)


@pytest.mark.parametrize(
    ("category", "visible"),
    [("room_proxy_hidden", True), ("room_visible", False)],
)
def test_commandlet_shadow_validator_rejects_adversarial_visibility(
    monkeypatch: pytest.MonkeyPatch, category: str, visible: bool
) -> None:
    commandlet = _load_commandlet(monkeypatch)
    with pytest.raises(RuntimeError, match="shadow observation differs"):
        commandlet.shadow_rows_valid(
            [
                {
                    "category": category,
                    "visible": visible,
                    "cast_shadow": not category.endswith("hidden"),
                    "cast_hidden_shadow": False,
                }
            ]
        )


def test_launcher_v3_rejects_shadow_visibility_and_post_override_drift(
    tmp_path: Path,
) -> None:
    for target in ("shadow", "post"):
        case = tmp_path / target
        case.mkdir()
        parent_path, parent = _write_parent_receipt(case)
        receipt_path, receipt = _write_v3_receipt(case, parent_path, parent)
        result_path = Path(receipt["realism_r4_upgrade"]["result"]["path"])
        result = json.loads(result_path.read_text(encoding="utf-8"))
        if target == "shadow":
            for key in (
                "shadow_observations_before_save",
                "shadow_observations_reloaded",
            ):
                hidden = next(
                    row for row in result[key] if row["category"].endswith("hidden")
                )
                hidden["visible"] = True
        else:
            for key in (
                "post_process_observation_before_save",
                "post_process_observation_reloaded",
            ):
                result[key]["override_flags"]["override_auto_exposure_method"] = False
        _rewrite_result(receipt_path, receipt, result)
        with pytest.raises(launcher.HumanVisualDemoError, match="evidence differs"):
            launcher.load_combined_receipt(receipt_path)


def test_nullrhi_process_uses_closed_environment_and_cleans_private_root(
    tmp_path: Path,
) -> None:
    config, _receipt_path, _receipt = _fixture_config(tmp_path)
    attempt = config.run_parent / "combined-realism-r4-process-contract"
    prepared = r4.build_plan(
        attempt,
        apply=True,
        acknowledgements=r4.ACKNOWLEDGEMENTS,
        config=config,
    )
    attempt.mkdir(mode=0o700)
    project = attempt / "project/VistaPlayableHome.uproject"
    commandlet = attempt / r4.COMMANDLET_NAME
    execution = attempt / r4.EXECUTION_NAME
    project.parent.mkdir(mode=0o700)
    project.write_text('{"FileVersion":3}\n', encoding="utf-8")
    commandlet.write_text("# commandlet fixture\n", encoding="utf-8")
    execution.write_text("{}\n", encoding="utf-8")
    captured: dict[str, object] = {}

    class Process:
        pid = 4242

        def wait(self, timeout=None):
            return 0

        def poll(self):
            return 0

    def popen(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        Path(attempt / r4.ENGINE_LOG_NAME).write_text(
            "engine fixture\n", encoding="utf-8"
        )
        return Process()

    with mock.patch.dict(
        os.environ,
        {"OPENAI_API_KEY": "secret", "DISPLAY": ":999", "CUDA_VISIBLE_DEVICES": "7"},
    ):
        r4._run_unreal(
            prepared,
            project=project,
            commandlet=commandlet,
            execution_path=execution,
            execution_sha256=_sha(execution),
            popen_factory=popen,
            process_tree_waiter=lambda process, *, timeout, **_kwargs: process.wait(
                timeout=timeout
            ),
        )

    command = captured["command"]
    kwargs = captured["kwargs"]
    environment = kwargs["env"]
    rendered = " ".join(command).lower()
    assert "-nullrhi" in command
    assert "-run=pythonscript" in command
    assert f"-script={commandlet}" in command
    assert "pixelstreaming" not in rendered
    assert kwargs["shell"] is False
    assert kwargs["start_new_session"] is True
    assert set(environment) == {
        "LANG",
        "LC_ALL",
        "PATH",
        "HOME",
        "TMPDIR",
        "XDG_CACHE_HOME",
        "XDG_CONFIG_HOME",
        "XDG_DATA_HOME",
        r4.EXECUTION_ENV,
        r4.EXECUTION_SHA_ENV,
        r4.RESULT_ENV,
        r4.RESULT_SIDECAR_ENV,
    }
    assert "OPENAI_API_KEY" not in environment
    assert "DISPLAY" not in environment
    assert "CUDA_VISIBLE_DEVICES" not in environment
    assert not Path(environment["HOME"]).parent.exists()


@pytest.mark.parametrize("leader_exit", [0, 7])
def test_run_unreal_reaps_background_child_after_leader_exit(
    tmp_path: Path, leader_exit: int
) -> None:
    config, _receipt_path, _receipt = _fixture_config(tmp_path)
    editor = config.unreal_editor_cmd
    editor.chmod(0o700)
    editor.write_text(
        "#!/bin/sh\n"
        'attempt=$(dirname "$VISTA_COMBINED_REALISM_R4_RESULT")\n'
        "sleep 60 &\n"
        'echo $! > "$attempt/background-child.pid"\n'
        'for value in "$@"; do\n'
        '  case "$value" in -abslog=*) log=${value#*=} ;; esac\n'
        "done\n"
        "printf 'engine fixture\\n' > \"$log\"\n"
        f"exit {leader_exit}\n",
        encoding="utf-8",
    )
    editor.chmod(0o500)
    config = dataclasses.replace(
        config,
        unreal_editor_cmd_sha256=_sha(editor),
        unreal_editor_cmd_bytes=editor.stat().st_size,
    )
    attempt = config.run_parent / f"combined-realism-r4-real-tree-{leader_exit}"
    prepared = r4.build_plan(
        attempt,
        apply=True,
        acknowledgements=r4.ACKNOWLEDGEMENTS,
        config=config,
    )
    attempt.mkdir(mode=0o700)
    project = attempt / "project/VistaPlayableHome.uproject"
    commandlet = attempt / r4.COMMANDLET_NAME
    execution = attempt / r4.EXECUTION_NAME
    project.parent.mkdir(mode=0o700)
    project.write_text('{"FileVersion":3}\n', encoding="utf-8")
    commandlet.write_text("# commandlet fixture\n", encoding="utf-8")
    execution.write_text("{}\n", encoding="utf-8")

    if leader_exit == 0:
        r4._run_unreal(
            prepared,
            project=project,
            commandlet=commandlet,
            execution_path=execution,
            execution_sha256=_sha(execution),
        )
    else:
        with pytest.raises(r4.CombinedRealismR4Error, match="exited 7"):
            r4._run_unreal(
                prepared,
                project=project,
                commandlet=commandlet,
                execution_path=execution,
                execution_sha256=_sha(execution),
            )
    child_pid = int((attempt / "background-child.pid").read_text(encoding="ascii"))
    assert not Path(f"/proc/{child_pid}").exists()


def _escaped_process_fixture(
    tmp_path: Path, *, escape_mode: str, outcome: str
) -> tuple[r4.PreparedPlan, Path, Path, Path, Path, Path, Path]:
    config, _receipt_path, _receipt = _fixture_config(tmp_path)
    editor = config.unreal_editor_cmd
    child_program = (
        "import json,os,pathlib,sys,time\n"
        "mode,ready_value,sentinel_value=sys.argv[1:]\n"
        "if mode == 'setsid': os.setsid()\n"
        "elif mode == 'setpgid': os.setpgid(0, 0)\n"
        "elif mode == 'double_fork':\n"
        "    if os.fork(): os._exit(0)\n"
        "    os.setsid()\n"
        "    if os.fork(): os._exit(0)\n"
        "else: raise RuntimeError(mode)\n"
        "ready=pathlib.Path(ready_value)\n"
        "ready.write_text(json.dumps({'pid':os.getpid(),'pgrp':os.getpgrp(),"
        "'sid':os.getsid(0)},sort_keys=True)+'\\n')\n"
        "time.sleep(0.5)\n"
        "pathlib.Path(sentinel_value).write_text('escaped child survived\\n')\n"
        "time.sleep(60)\n"
    )
    editor.chmod(0o700)
    editor.write_text(
        "#!/usr/bin/python3\n"
        "import os,pathlib,subprocess,sys,time\n"
        f"child_program={child_program!r}\n"
        f"escape_mode={escape_mode!r}\n"
        f"outcome={outcome!r}\n"
        "attempt=pathlib.Path(os.environ['VISTA_COMBINED_REALISM_R4_RESULT']).parent\n"
        "ready=attempt/'escaped-ready.json'\n"
        "sentinel=attempt/'escaped-sentinel.txt'\n"
        "child=subprocess.Popen([sys.executable,'-c',child_program,escape_mode,"
        "str(ready),str(sentinel)],stdin=subprocess.DEVNULL,stdout=subprocess.DEVNULL,"
        "stderr=subprocess.DEVNULL,close_fds=True)\n"
        "(attempt/'escaped-child.pid').write_text(str(child.pid)+'\\n')\n"
        "deadline=time.monotonic()+2\n"
        "while not ready.exists() and time.monotonic()<deadline: time.sleep(0.005)\n"
        "if not ready.exists(): raise RuntimeError('escape handshake timed out')\n"
        "log=next(value.split('=',1)[1] for value in sys.argv[1:] "
        "if value.startswith('-abslog='))\n"
        "pathlib.Path(log).write_text('engine escaped-child fixture\\n')\n"
        "if outcome == 'timeout': time.sleep(60)\n"
        "raise SystemExit(0 if outcome == 'rc0' else 7)\n",
        encoding="utf-8",
    )
    editor.chmod(0o500)
    config = dataclasses.replace(
        config,
        unreal_editor_cmd_sha256=_sha(editor),
        unreal_editor_cmd_bytes=editor.stat().st_size,
    )
    attempt = config.run_parent / (
        f"combined-realism-r4-{escape_mode.replace('_', '-')}-{outcome}"
    )
    prepared = r4.build_plan(
        attempt,
        apply=True,
        acknowledgements=r4.ACKNOWLEDGEMENTS,
        config=config,
    )
    attempt.mkdir(mode=0o700)
    project = attempt / "project/VistaPlayableHome.uproject"
    commandlet = attempt / r4.COMMANDLET_NAME
    execution = attempt / r4.EXECUTION_NAME
    project.parent.mkdir(mode=0o700)
    project.write_text('{"FileVersion":3}\n', encoding="utf-8")
    commandlet.write_text("# escaped commandlet fixture\n", encoding="utf-8")
    execution.write_text("{}\n", encoding="utf-8")
    return (
        prepared,
        project,
        commandlet,
        execution,
        attempt / "escaped-child.pid",
        attempt / "escaped-ready.json",
        attempt / "escaped-sentinel.txt",
    )


@pytest.mark.parametrize("escape_mode", ["setsid", "setpgid", "double_fork"])
@pytest.mark.parametrize("outcome", ["rc0", "nonzero", "timeout"])
def test_run_unreal_reaps_cross_session_or_process_group_escapees(
    tmp_path: Path, escape_mode: str, outcome: str
) -> None:
    (
        prepared,
        project,
        commandlet,
        execution,
        child_pid_path,
        ready_path,
        sentinel_path,
    ) = _escaped_process_fixture(tmp_path, escape_mode=escape_mode, outcome=outcome)

    def call() -> None:
        r4._run_unreal(
            prepared,
            project=project,
            commandlet=commandlet,
            execution_path=execution,
            execution_sha256=_sha(execution),
            timeout_seconds=0.2 if outcome == "timeout" else 5.0,
        )

    if outcome == "rc0":
        call()
    elif outcome == "nonzero":
        with pytest.raises(r4.CombinedRealismR4Error, match="exited 7"):
            call()
    else:
        with pytest.raises(r4.CombinedRealismR4Error, match="timed out"):
            call()
    launched_pid = int(child_pid_path.read_text(encoding="ascii"))
    ready = json.loads(ready_path.read_text(encoding="utf-8"))
    child_pid = ready["pid"]
    if escape_mode == "double_fork":
        assert child_pid != launched_pid
        assert ready["pgrp"] == ready["sid"]
        assert ready["sid"] != child_pid
    else:
        assert child_pid == launched_pid
        assert ready["pgrp"] == child_pid
    if escape_mode == "setsid":
        assert ready["sid"] == child_pid
    elif escape_mode == "setpgid":
        assert ready["sid"] != child_pid
    assert not Path(f"/proc/{launched_pid}").exists()
    assert not Path(f"/proc/{child_pid}").exists()
    time.sleep(0.6)
    assert not sentinel_path.exists()


def test_run_unreal_signal_cleans_double_fork_and_restores_process_state(
    tmp_path: Path,
) -> None:
    (
        prepared,
        project,
        commandlet,
        execution,
        launched_pid_path,
        ready_path,
        sentinel_path,
    ) = _escaped_process_fixture(tmp_path, escape_mode="double_fork", outcome="timeout")
    handler_before = signal.getsignal(signal.SIGINT)
    subreaper_before = r4._get_child_subreaper()
    timer = threading.Timer(0.3, os.kill, args=(os.getpid(), signal.SIGINT))
    timer.start()
    try:
        with pytest.raises(r4.CombinedRealismR4Error, match="interrupted by SIGINT"):
            r4._run_unreal(
                prepared,
                project=project,
                commandlet=commandlet,
                execution_path=execution,
                execution_sha256=_sha(execution),
                timeout_seconds=5.0,
            )
    finally:
        timer.cancel()
        timer.join(timeout=1)
    ready = json.loads(ready_path.read_text(encoding="utf-8"))
    launched_pid = int(launched_pid_path.read_text(encoding="ascii"))
    assert signal.getsignal(signal.SIGINT) is handler_before
    assert r4._get_child_subreaper() is subreaper_before
    assert not Path(f"/proc/{launched_pid}").exists()
    assert not Path(f"/proc/{ready['pid']}").exists()
    time.sleep(0.6)
    assert not sentinel_path.exists()


def test_run_unreal_fails_closed_for_preexisting_unrelated_child(
    tmp_path: Path,
) -> None:
    unrelated_sentinel = tmp_path / "unrelated-survived.txt"
    unrelated = subprocess.Popen(
        [
            sys.executable,
            "-c",
            (
                "import pathlib,sys,time;time.sleep(0.4);"
                "pathlib.Path(sys.argv[1]).write_text('unrelated survived\\n')"
            ),
            str(unrelated_sentinel),
        ],
        start_new_session=True,
    )
    try:
        prepared, project, commandlet, execution, child_pid_path, _ready, sentinel = (
            _escaped_process_fixture(tmp_path, escape_mode="setsid", outcome="rc0")
        )
        subreaper_before = r4._get_child_subreaper()
        with pytest.raises(
            r4.CombinedRealismR4Error, match="preexisting child or descendant"
        ):
            r4._run_unreal(
                prepared,
                project=project,
                commandlet=commandlet,
                execution_path=execution,
                execution_sha256=_sha(execution),
                timeout_seconds=5.0,
            )
        assert r4._get_child_subreaper() is subreaper_before
        assert not child_pid_path.exists()
        assert not sentinel.exists()
        assert not (prepared.attempt_root / r4.STDOUT_NAME).exists()
        assert not (prepared.attempt_root / r4.ENGINE_LOG_NAME).exists()
        assert unrelated.wait(timeout=2) == 0
        assert unrelated_sentinel.read_text(encoding="utf-8") == "unrelated survived\n"
    finally:
        if unrelated.poll() is None:
            unrelated.terminate()
            unrelated.wait(timeout=2)


def test_fail_closed_does_not_touch_preexisting_parent_or_future_grandchild(
    tmp_path: Path,
) -> None:
    parent_sentinel = tmp_path / "preexisting-parent-survived.txt"
    grandchild_sentinel = tmp_path / "future-grandchild-survived.txt"
    grandchild_pid_path = tmp_path / "future-grandchild.pid"
    grandchild_program = (
        "import pathlib,sys,time;time.sleep(0.25);"
        "pathlib.Path(sys.argv[1]).write_text('grandchild survived\\n')"
    )
    parent_program = (
        "import pathlib,subprocess,sys,time;"
        "grand=subprocess.Popen([sys.executable,'-c',sys.argv[1],sys.argv[2]]);"
        "pathlib.Path(sys.argv[3]).write_text(str(grand.pid)+'\\n');"
        "time.sleep(0.15);"
        "pathlib.Path(sys.argv[4]).write_text('parent survived\\n');"
        "raise SystemExit(grand.wait())"
    )
    parent = subprocess.Popen(
        [
            sys.executable,
            "-c",
            parent_program,
            grandchild_program,
            str(grandchild_sentinel),
            str(grandchild_pid_path),
            str(parent_sentinel),
        ],
        start_new_session=True,
    )
    try:
        prepared, project, commandlet, execution, child_pid_path, _ready, sentinel = (
            _escaped_process_fixture(tmp_path, escape_mode="setsid", outcome="rc0")
        )
        subreaper_before = r4._get_child_subreaper()
        with pytest.raises(
            r4.CombinedRealismR4Error, match="preexisting child or descendant"
        ):
            r4._run_unreal(
                prepared,
                project=project,
                commandlet=commandlet,
                execution_path=execution,
                execution_sha256=_sha(execution),
                timeout_seconds=5.0,
            )
        assert r4._get_child_subreaper() is subreaper_before
        assert not child_pid_path.exists()
        assert not sentinel.exists()
        assert not (prepared.attempt_root / r4.STDOUT_NAME).exists()
        assert not (prepared.attempt_root / r4.ENGINE_LOG_NAME).exists()
        assert parent.wait(timeout=3) == 0
        grandchild_pid = int(grandchild_pid_path.read_text(encoding="ascii"))
        assert parent_sentinel.read_text(encoding="utf-8") == "parent survived\n"
        assert (
            grandchild_sentinel.read_text(encoding="utf-8") == "grandchild survived\n"
        )
        assert not Path(f"/proc/{grandchild_pid}").exists()
    finally:
        if parent.poll() is None:
            parent.terminate()
            parent.wait(timeout=2)


def test_publication_revalidates_state_twice_before_writing_receipt(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, _receipt_path, _receipt = _fixture_config(tmp_path)
    attempt = config.run_parent / "combined-realism-r4-publication-drift"
    prepared = r4.build_plan(
        attempt,
        apply=True,
        acknowledgements=r4.ACKNOWLEDGEMENTS,
        config=config,
    )
    attempt.mkdir(mode=0o700)
    project_root = attempt / "project"
    shutil.copytree(prepared.source_inputs.project.path.parent, project_root)
    project = project_root / r4.PROJECT_NAME
    baseline_tree, baseline_manifest = r4._project_manifest(project)
    assert baseline_tree == prepared.source_inputs.project_static_tree
    output_map = project_root / Path(r4.MAP_RELATIVE_PATH)
    output_map.write_bytes(b"changed-r4-map\n")
    for name, source in (
        (r4.PROFILE_NAME, config.profile_source),
        (r4.MATERIALIZER_NAME, config.materializer_source),
        (r4.COMMANDLET_NAME, config.commandlet_source),
    ):
        shutil.copyfile(source, attempt / name)
    execution_path = attempt / r4.EXECUTION_NAME
    result_path = attempt / r4.RESULT_NAME
    execution_path.write_text('{"execution":"fixture"}\n', encoding="utf-8")
    result = {
        "map_package": _pin(output_map),
        "r4_pair_observations_reloaded": [{} for _ in range(6)],
        "gates": {key: True for key in r4.RESULT_GATE_KEYS},
    }
    result_path.write_text('{"result":"fixture"}\n', encoding="utf-8")
    real_state = r4._publication_state
    calls = 0

    def drifting_state(*args, **kwargs):
        nonlocal calls
        calls += 1
        state = real_state(*args, **kwargs)
        if calls == 2:
            state = copy.deepcopy(state)
            state["map_package"]["sha256"] = "0" * 64
        return state

    monkeypatch.setattr(r4, "_publication_state", drifting_state)
    with pytest.raises(r4.CombinedRealismR4Error, match="publication state changed"):
        r4._publish_combined_receipt(
            prepared,
            execution_path=execution_path,
            result=result,
            baseline_manifest=baseline_manifest,
        )
    assert calls == 2
    assert not (attempt / launcher.COMBINED_RECEIPT_NAME).exists()
