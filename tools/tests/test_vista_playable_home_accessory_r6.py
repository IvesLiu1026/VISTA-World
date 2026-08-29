from __future__ import annotations

import copy
import dataclasses
import hashlib
import importlib.util
import json
import sys
import types
from pathlib import Path

import pytest

from tools.runtime.vista_playable_home import human_visual_demo_launch as launcher
from tools.ue.vista_playable_home import materialize_accessory_r6 as r6
from tools.ue.vista_playable_home import materialize_combined_realism_r4 as r4


COMMANDLET = (
    Path(__file__).resolve().parents[1]
    / "ue/vista_playable_home/compose_accessory_r6_commandlet.py"
)
SEALED_R4_RECEIPT = Path(
    "/data/sysx/vista-world/runs/vista-action-world-r1/"
    "combined-realism-r4-human-demo-20260829c/"
    "human-visual-demo-combined-receipt.json"
)


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _pin(path: Path) -> dict[str, object]:
    return {"path": str(path), "sha256": _sha(path), "size_bytes": path.stat().st_size}


def _all_files(root: Path) -> list[tuple[str, bytes]]:
    return sorted(
        (path.relative_to(root).as_posix(), path.read_bytes())
        for path in root.rglob("*")
        if path.is_file()
    )


def _seal(path: Path) -> r4.FileSeal:
    metadata = path.stat()
    return r4.FileSeal(
        path=path.resolve(),
        sha256=_sha(path),
        size_bytes=metadata.st_size,
        mode=metadata.st_mode & 0o7777,
        device=metadata.st_dev,
        inode=metadata.st_ino,
        mtime_ns=metadata.st_mtime_ns,
    )


def _fake_plan_state(tmp_path: Path):
    run_parent = tmp_path / "runs"
    run_parent.mkdir(mode=0o700)
    inputs_root = tmp_path / "inputs"
    inputs_root.mkdir()
    receipt = inputs_root / launcher.COMBINED_RECEIPT_NAME
    project = inputs_root / "project/VistaPlayableHome.uproject"
    map_package = (
        inputs_root / "project/Content/VISTA/PlayableHome/vista_playable_home_r1/Maps/"
        "VistaPlayableHome.umap"
    )
    executable = inputs_root / "engine/UnrealEditor"
    materializer = inputs_root / r6.MATERIALIZER_NAME
    commandlet = inputs_root / r6.COMMANDLET_NAME
    editor_cmd = inputs_root / "engine/UnrealEditor-Cmd"
    build_version = inputs_root / "engine/Build.version"
    support = inputs_root / r6.R4_SUPPORT_NAME
    for path in (
        receipt,
        project,
        map_package,
        executable,
        materializer,
        commandlet,
        editor_cmd,
        build_version,
        support,
    ):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((path.name + "\n").encode())
    executable.chmod(0o500)
    editor_cmd.chmod(0o500)
    project_pin = launcher.ArtifactPin(
        project.resolve(), _sha(project), project.stat().st_size
    )
    map_pin = launcher.ArtifactPin(
        map_package.resolve(), _sha(map_package), map_package.stat().st_size
    )
    executable_pin = launcher.ArtifactPin(
        executable.resolve(), _sha(executable), executable.stat().st_size
    )
    source_tree = {
        "algorithm": launcher.PROJECT_STATIC_TREE_ALGORITHM,
        "file_count": 0,
        "total_bytes": 0,
        "tree_sha256": "0" * 64,
    }
    inputs = launcher.HumanVisualDemoInputs(
        receipt=receipt.resolve(),
        receipt_sha256=_sha(receipt),
        receipt_content_digest="1" * 64,
        project=project_pin,
        project_static_tree=source_tree,
        source_provenance={},
        executable=executable_pin,
        map_object_path=r6.MAP_OBJECT_PATH,
        map_package=map_pin,
        receipt_schema_version=launcher.COMBINED_RECEIPT_SCHEMA_V3,
        realism_r4_upgrade={"commandlet": _pin(support)},
    )
    config = r6.Config(
        repository_root=tmp_path,
        run_parent=run_parent.resolve(),
        source_receipt=receipt.resolve(),
        source_receipt_sha256=_sha(receipt),
        source_receipt_bytes=receipt.stat().st_size,
        source_project_tree=source_tree,
        source_map_sha256=_sha(map_package),
        source_map_bytes=map_package.stat().st_size,
        materializer_source=materializer.resolve(),
        materializer_source_sha256=_sha(materializer),
        materializer_source_bytes=materializer.stat().st_size,
        commandlet_source=commandlet.resolve(),
        commandlet_source_sha256=_sha(commandlet),
        commandlet_source_bytes=commandlet.stat().st_size,
        unreal_editor_cmd=editor_cmd.resolve(),
        unreal_editor_cmd_sha256=_sha(editor_cmd),
        unreal_editor_cmd_bytes=editor_cmd.stat().st_size,
        build_version=build_version.resolve(),
        build_version_sha256=_sha(build_version),
        build_version_bytes=build_version.stat().st_size,
        network_namespace=launcher.NETWORK_NAMESPACE_EXECUTABLE,
        network_namespace_sha256=launcher.NETWORK_NAMESPACE_EXECUTABLE_SHA256,
        network_namespace_bytes=launcher.NETWORK_NAMESPACE_EXECUTABLE_BYTES,
    )
    tool_seals = {
        "unreal_editor_cmd": _seal(editor_cmd),
        "build_version": _seal(build_version),
        "network_namespace": _seal(launcher.NETWORK_NAMESPACE_EXECUTABLE),
    }
    script_seals = {
        "materializer": _seal(materializer),
        "commandlet": _seal(commandlet),
    }
    assets = {
        "citysample_result": _pin(receipt),
        "dependency_asset_records": [
            {
                "asset_class": row["asset_class"],
                "object_path": row["object_path"],
                "package_name": row["package_name"],
            }
            for _semantic, row in sorted(launcher.ACCESSORY_R6_TARGET_ASSETS.items())
        ],
    }
    assets["dependency_asset_records"].sort(key=lambda row: row["object_path"])
    contract = {
        "targets": [],
        "pot_semantic_id": launcher.ACCESSORY_R6_POT_SEMANTIC_ID,
        "fit_policy": launcher.ACCESSORY_R6_FIT_POLICY,
    }
    state = (
        inputs,
        tuple(),
        tool_seals,
        script_seals,
        _seal(support),
        assets,
        contract,
    )
    return config, state, receipt


def test_default_plan_is_zero_write_and_apply_is_exactly_acknowledged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, state, receipt = _fake_plan_state(tmp_path)
    monkeypatch.setattr(r6, "_source_state", lambda _config: state)
    before = _all_files(tmp_path)
    parent_raw = receipt.read_bytes()
    attempt = config.run_parent / "accessory-r6-zero-write"

    prepared = r6.build_plan(attempt, config=config)

    assert prepared.report["status"] == r6.DRY_RUN_STATUS
    assert prepared.report["mode"] == "dry_run_zero_writes"
    assert prepared.report["will_write"] is False
    assert prepared.report["execution"]["pixel_access"] is False
    assert prepared.report["execution"]["ue_reflection_bounds_only"] is True
    assert prepared.report["execution"]["private_network_namespace"] is True
    assert prepared.report["toolchain"]["network_namespace"] == {
        "path": str(launcher.NETWORK_NAMESPACE_EXECUTABLE),
        "sha256": launcher.NETWORK_NAMESPACE_EXECUTABLE_SHA256,
        "size_bytes": launcher.NETWORK_NAMESPACE_EXECUTABLE_BYTES,
    }
    assert receipt.read_bytes() == parent_raw
    assert not attempt.exists()
    assert _all_files(tmp_path) == before

    acknowledgements = copy.deepcopy(r6.ACKNOWLEDGEMENTS)
    acknowledgements["sealed_r4_large_copy"] = None
    with pytest.raises(r6.AccessoryR6Error, match="every exact"):
        r6.build_plan(
            config.run_parent / "accessory-r6-missing-ack",
            apply=True,
            acknowledgements=acknowledgements,
            config=config,
        )


def test_tampered_commandlet_is_rejected_before_any_popen(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, state, _receipt = _fake_plan_state(tmp_path)
    monkeypatch.setattr(r6, "_source_state", lambda _config: state)
    attempt = config.run_parent / "accessory-r6-preexec-script-drift"
    prepared = r6.build_plan(
        attempt,
        apply=True,
        acknowledgements=copy.deepcopy(r6.ACKNOWLEDGEMENTS),
        config=config,
    )
    config.commandlet_source.write_text(
        "# valid Python replacement that is not the trusted commandlet\n",
        encoding="utf-8",
    )
    popen_calls = []

    def forbidden_popen(*args, **kwargs):
        popen_calls.append((args, kwargs))
        raise AssertionError("Popen must not be reached for a drifted R6 commandlet")

    with pytest.raises(r4.CombinedRealismR4Error, match="trusted R6 commandlet"):
        r6.apply_plan(prepared, popen_factory=forbidden_popen)

    assert popen_calls == []
    assert not attempt.exists()


def test_unreal_command_is_bwrap_prefixed_with_closed_environment_and_no_shell(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    config, state, _receipt = _fake_plan_state(tmp_path)
    monkeypatch.setattr(r6, "_source_state", lambda _config: state)
    prepared = r6.build_plan(config.run_parent / "accessory-r6-command", config=config)
    private_root = tmp_path / "private"
    project = prepared.source_inputs.project.path
    commandlet = config.commandlet_source
    command = r6.build_unreal_command(
        prepared,
        project=project,
        commandlet=commandlet,
        private_root=private_root,
    )
    assert command[:8] == [
        str(launcher.NETWORK_NAMESPACE_EXECUTABLE),
        "--unshare-net",
        "--die-with-parent",
        "--dev-bind",
        "/",
        "/",
        "--",
        str(config.unreal_editor_cmd),
    ]
    assert command[8] == str(project)
    assert "-nullrhi" in command
    environment = r6.sanitized_environment(
        private_root,
        execution_path=tmp_path / r6.EXECUTION_NAME,
        execution_sha256="a" * 64,
        attempt=prepared.attempt_root,
    )
    assert set(environment) == {
        "LANG",
        "LC_ALL",
        "PATH",
        "HOME",
        "TMPDIR",
        "XDG_CACHE_HOME",
        "XDG_CONFIG_HOME",
        "XDG_DATA_HOME",
        r6.EXECUTION_ENV,
        r6.EXECUTION_SHA_ENV,
        r6.RESULT_ENV,
        r6.RESULT_SIDECAR_ENV,
    }
    assert not any(
        key in environment
        for key in ("DISPLAY", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "NO_PROXY")
    )
    materializer_source = Path(r6.__file__).read_text(encoding="utf-8")
    assert "shell=False" in materializer_source
    assert "Popen(command" not in materializer_source
    prepared.attempt_root.mkdir(mode=0o700)
    captured = {}

    def fake_popen(observed_command, **kwargs):
        captured["command"] = observed_command
        captured["kwargs"] = kwargs
        (prepared.attempt_root / r6.ENGINE_LOG_NAME).write_text(
            "fixture engine log\n", encoding="utf-8"
        )
        return object()

    monkeypatch.setattr(r4, "_snapshot_preexisting_descendants", lambda: frozenset())
    monkeypatch.setattr(r4, "_signal_handlers", lambda: ({}, None))
    monkeypatch.setattr(r4, "_restore_handlers", lambda _previous: None)
    monkeypatch.setattr(r4, "_process_start_floor", lambda: 1)
    monkeypatch.setattr(r4, "_set_child_subreaper", lambda _enabled: False)
    stdout_path, engine_log = r6._run_unreal(
        prepared,
        project=project,
        commandlet=commandlet,
        execution_path=tmp_path / r6.EXECUTION_NAME,
        execution_sha256="a" * 64,
        popen_factory=fake_popen,
        process_tree_waiter=lambda _process, **_kwargs: 0,
        timeout_seconds=1.0,
    )
    assert stdout_path.is_file()
    assert engine_log.is_file()
    assert captured["command"][:8] == command[:8]
    assert captured["kwargs"]["shell"] is False
    assert captured["kwargs"]["start_new_session"] is True
    assert captured["kwargs"]["stdin"] is r6.subprocess.DEVNULL
    assert set(captured["kwargs"]["env"]) == set(environment)


def test_production_receipt_inventory_and_uasset_pins_are_textually_sealed() -> None:
    assert r6.NETWORK_NAMESPACE == Path("/usr/bin/bwrap")
    assert r6.NETWORK_NAMESPACE.stat().st_size == r6.NETWORK_NAMESPACE_BYTES
    assert _sha(r6.NETWORK_NAMESPACE) == r6.NETWORK_NAMESPACE_SHA256
    raw = SEALED_R4_RECEIPT.read_bytes()
    receipt = json.loads(raw)
    assert len(raw) == r6.SOURCE_RECEIPT_BYTES
    assert hashlib.sha256(raw).hexdigest() == r6.SOURCE_RECEIPT_SHA256
    assert receipt["schema_version"] == launcher.COMBINED_RECEIPT_SCHEMA_V3
    assert receipt["project_static_tree"] == r6.SOURCE_PROJECT_TREE
    assert receipt["map"]["package"]["sha256"] == r6.SOURCE_MAP_SHA256
    city_result = json.loads(
        Path(receipt["source_provenance"]["citysample_result"]["path"]).read_bytes()
    )
    assert city_result["accepted"] is False
    assert city_result["runtime_visual_acceptance"] is False
    assert city_result["gates"]["asset_registry_dependency_closure_validated"] is True
    project_root = Path(receipt["project"]["path"]).parent
    for expected in launcher.ACCESSORY_R6_TARGET_ASSETS.values():
        dependency = {
            "asset_class": expected["asset_class"],
            "object_path": expected["object_path"],
            "package_name": expected["package_name"],
        }
        assert city_result["dependency_asset_records"].count(dependency) == 1
        uasset = project_root / expected["relative_path"]
        assert uasset.stat().st_size == expected["size_bytes"]
        assert uasset.stat().st_mode & 0o7777 == expected["mode"]
        assert _sha(uasset) == expected["sha256"]


def test_launcher_contract_is_closed_and_requires_exact_staticmesh_provenance() -> None:
    manifest = {}
    records = []
    targets = []
    for semantic_id, expected in sorted(launcher.ACCESSORY_R6_TARGET_ASSETS.items()):
        manifest[expected["relative_path"]] = {
            "sha256": expected["sha256"],
            "size_bytes": expected["size_bytes"],
            "mode": expected["mode"],
        }
        asset = {
            "asset_class": expected["asset_class"],
            "object_path": expected["object_path"],
            "package_name": expected["package_name"],
        }
        records.append(asset)
        targets.append(
            {
                "semantic_id": semantic_id,
                "actor_path": expected["actor_path"],
                "source_mesh_object_path": expected["source_mesh_object_path"],
                "asset": asset,
                "uasset": {
                    "relative_path": expected["relative_path"],
                    **manifest[expected["relative_path"]],
                },
                "fit_policy": launcher.ACCESSORY_R6_FIT_POLICY,
            }
        )
    records.sort(key=lambda row: row["object_path"])
    payload = {
        "targets": targets,
        "pot_semantic_id": launcher.ACCESSORY_R6_POT_SEMANTIC_ID,
        "fit_policy": launcher.ACCESSORY_R6_FIT_POLICY,
    }
    accepted = launcher._validate_r6_contract(
        payload,
        source_manifest=manifest,
        asset_inventory={"dependency_asset_records": records},
    )
    assert accepted == payload

    for mutation in ("asset_class", "fit_policy", "extra"):
        drift = copy.deepcopy(payload)
        if mutation == "asset_class":
            drift["targets"][0]["asset"]["asset_class"] = "SkeletalMesh"
        elif mutation == "fit_policy":
            drift["fit_policy"] = "heuristic"
        else:
            drift["targets"][0]["extra"] = True
        with pytest.raises(launcher.HumanVisualDemoError):
            launcher._validate_r6_contract(
                drift,
                source_manifest=manifest,
                asset_inventory={"dependency_asset_records": records},
            )


def test_launcher_rejects_alternate_v3_parent_and_alternate_r6_scripts(
    tmp_path: Path,
) -> None:
    trusted = launcher.ACCESSORY_R6_TRUSTED_R4_PARENT
    parent_pin = launcher.ArtifactPin(
        Path(trusted["receipt"]["path"]),
        trusted["receipt"]["sha256"],
        trusted["receipt"]["size_bytes"],
    )
    parent_inputs = launcher.HumanVisualDemoInputs(
        receipt=parent_pin.path,
        receipt_sha256=parent_pin.sha256,
        receipt_content_digest="a" * 64,
        project=launcher.ArtifactPin(
            Path(trusted["project"]["path"]),
            trusted["project"]["sha256"],
            trusted["project"]["size_bytes"],
        ),
        project_static_tree=copy.deepcopy(trusted["project_static_tree"]),
        source_provenance={},
        executable=launcher.ArtifactPin(Path("/fixture/UnrealEditor"), "b" * 64, 1),
        map_object_path=r6.MAP_OBJECT_PATH,
        map_package=launcher.ArtifactPin(
            Path(trusted["map"]["path"]),
            trusted["map"]["sha256"],
            trusted["map"]["size_bytes"],
        ),
        receipt_schema_version=launcher.COMBINED_RECEIPT_SCHEMA_V3,
        realism_r4_upgrade={
            "commandlet": copy.deepcopy(trusted["r4_commandlet"]),
            "unreal_editor_cmd": {
                "path": "/fixture/UnrealEditor-Cmd",
                "sha256": "c" * 64,
                "size_bytes": 1,
            },
            "build_version": {
                "path": "/fixture/Build.version",
                "sha256": "d" * 64,
                "size_bytes": 1,
            },
        },
    )
    launcher._validate_r6_trusted_parent(parent_pin, parent_inputs)
    launcher._validate_r6_parent_passthrough(
        parent_inputs.source_provenance,
        parent_inputs.executable,
        parent_inputs,
    )

    with pytest.raises(
        launcher.HumanVisualDemoError, match="provenance/executable differs"
    ):
        launcher._validate_r6_parent_passthrough(
            {"mixed_from_another_v3": True},
            parent_inputs.executable,
            parent_inputs,
        )
    with pytest.raises(
        launcher.HumanVisualDemoError, match="provenance/executable differs"
    ):
        launcher._validate_r6_parent_passthrough(
            parent_inputs.source_provenance,
            dataclasses.replace(parent_inputs.executable, sha256="f" * 64),
            parent_inputs,
        )

    alternate_parent = dataclasses.replace(
        parent_pin, path=tmp_path / launcher.COMBINED_RECEIPT_NAME
    )
    with pytest.raises(launcher.HumanVisualDemoError, match="exact trusted R4-C"):
        launcher._validate_r6_trusted_parent(alternate_parent, parent_inputs)
    drifted_tree = dataclasses.replace(
        parent_inputs,
        project_static_tree={**trusted["project_static_tree"], "tree_sha256": "e" * 64},
    )
    with pytest.raises(launcher.HumanVisualDemoError, match="exact trusted R4-C"):
        launcher._validate_r6_trusted_parent(parent_pin, drifted_tree)

    for key, expected in launcher.ACCESSORY_R6_TRUSTED_SCRIPTS.items():
        trusted_copy_pin = launcher.ArtifactPin(
            tmp_path / Path(expected["path"]).name,
            expected["sha256"],
            expected["size_bytes"],
        )
        launcher._validate_r6_trusted_script(trusted_copy_pin, key)
        alternate = tmp_path / key / Path(expected["path"]).name
        alternate.parent.mkdir()
        alternate.write_text("# valid but untrusted replacement\n", encoding="utf-8")
        with pytest.raises(
            launcher.HumanVisualDemoError, match="Git-tracked trust anchor"
        ):
            launcher._validate_r6_trusted_script(
                launcher.ArtifactPin(
                    alternate, _sha(alternate), alternate.stat().st_size
                ),
                key,
            )


def test_resealed_tampered_r6_result_still_fails_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    result_path = tmp_path / r6.RESULT_NAME
    sidecar_path = tmp_path / (r6.RESULT_NAME + ".sha256")
    map_path = tmp_path / "VistaPlayableHome.umap"
    map_path.write_bytes(b"fixture upgraded map\n")
    map_pin_payload = _pin(map_path)
    map_pin = launcher.ArtifactPin(
        map_path, map_pin_payload["sha256"], map_pin_payload["size_bytes"]
    )
    execution = {
        "map": {"object_path": r6.MAP_OBJECT_PATH},
        "result": {"sidecar_path": str(sidecar_path)},
    }
    identity = {
        "location_cm": [0.0, 0.0, 0.0],
        "rotation_deg": [0.0, 0.0, 0.0],
        "scale": [1.0, 1.0, 1.0],
    }
    targets = []
    before = []
    after = []
    fits = []
    asset_records = []
    for semantic, expected in sorted(launcher.ACCESSORY_R6_TARGET_ASSETS.items()):
        asset = {
            "asset_class": expected["asset_class"],
            "object_path": expected["object_path"],
            "package_name": expected["package_name"],
        }
        asset_records.append(asset)
        targets.append(
            {
                "semantic_id": semantic,
                "actor_path": expected["actor_path"],
                "source_mesh_object_path": expected["source_mesh_object_path"],
                "asset": asset,
            }
        )
        source = {
            "semantic_id": semantic,
            "actor_path": expected["actor_path"],
            "authority": "sealed",
            "presentation": {
                "mesh_object_path": expected["source_mesh_object_path"],
                "relative_transform": copy.deepcopy(identity),
                "policy": "unchanged",
            },
        }
        upgraded = copy.deepcopy(source)
        upgraded["presentation"]["mesh_object_path"] = expected["object_path"]
        before.append(source)
        after.append(upgraded)
        fits.append(
            {
                "semantic_id": semantic,
                "source_mesh_object_path": expected["source_mesh_object_path"],
                "target_mesh_object_path": expected["object_path"],
                "final_relative_transform": copy.deepcopy(identity),
            }
        )
    asset_records.sort(key=lambda row: row["object_path"])
    pot = {
        "semantic_id": launcher.ACCESSORY_R6_POT_SEMANTIC_ID,
        "presentation": {"mesh_object_path": "/Game/Fixture/pot.pot"},
    }
    result = {
        "schema_version": launcher.ACCESSORY_R6_RESULT_SCHEMA,
        "status": launcher.ACCESSORY_R6_UPGRADE_STATUS,
        "provider_id": launcher.PROVIDER_ID,
        "human_operated_visual_demo_only": True,
        "prohibited_agent_adapter": True,
        "execution_sha256": hashlib.sha256(
            launcher.canonical_json(execution)
        ).hexdigest(),
        "map_object_path": r6.MAP_OBJECT_PATH,
        "map_package": map_pin_payload,
        "actor_inventory_before": [{"fixture": True}],
        "actor_inventory_reloaded": [{"fixture": True}],
        "target_observations_before": before,
        "target_asset_records": asset_records,
        "target_fit_records": fits,
        "target_observations_after_save": after,
        "target_observations_reloaded": copy.deepcopy(after),
        "pot_observation_before": pot,
        "pot_observation_reloaded": copy.deepcopy(pot),
        "legal_scope": copy.deepcopy(launcher.LEGAL_SCOPE),
        "claims": copy.deepcopy(launcher.CLAIMS),
        "acceptance": copy.deepcopy(launcher.ACCESSORY_R6_ACCEPTANCE),
        "gates": {key: True for key in launcher.ACCESSORY_R6_RESULT_GATE_KEYS},
        "error": None,
    }

    def write_result(payload):
        payload["content_digest"] = launcher.content_digest(payload)
        raw = launcher.canonical_json(payload)
        result_path.write_bytes(raw)
        digest = hashlib.sha256(raw).hexdigest()
        sidecar_path.write_text(f"{digest}  {r6.RESULT_NAME}\n", encoding="ascii")
        return launcher.ArtifactPin(result_path, digest, len(raw))

    monkeypatch.setattr(
        launcher, "_validate_actor_inventory", lambda value, _label: value
    )
    monkeypatch.setattr(
        launcher, "_validate_r6_observation", lambda value, _label: value
    )
    monkeypatch.setattr(launcher, "_validate_r6_fit", lambda value, _label: value)
    monkeypatch.setattr(launcher, "_validate_r6_fit_derivation", lambda *_args: None)
    contract = {"targets": targets}
    good_pin = write_result(result)
    launcher._validate_r6_result(
        good_pin, execution=execution, map_package=map_pin, contract=contract
    )

    tampered = copy.deepcopy(result)
    tampered["gates"]["only_map_static_artifact_changed"] = False
    tampered_pin = write_result(tampered)
    with pytest.raises(launcher.HumanVisualDemoError, match="result gates differ"):
        launcher._validate_r6_result(
            tampered_pin, execution=execution, map_package=map_pin, contract=contract
        )


def _load_commandlet(monkeypatch: pytest.MonkeyPatch):
    class Vector:
        def __init__(self, x=0.0, y=0.0, z=0.0):
            self.x, self.y, self.z = x, y, z

        def rotate(self, _rotator):
            return self

    class Rotator:
        def __init__(self, roll=0.0, pitch=0.0, yaw=0.0):
            self.roll, self.pitch, self.yaw = roll, pitch, yaw

    fake = types.SimpleNamespace(
        StaticMesh=type("StaticMesh", (), {}),
        StaticMeshComponent=type("StaticMeshComponent", (), {}),
        Vector=Vector,
        Rotator=Rotator,
    )
    monkeypatch.setitem(sys.modules, "unreal", fake)
    spec = importlib.util.spec_from_file_location(
        "accessory_r6_commandlet_test", COMMANDLET
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, fake


def test_reflection_bounds_fit_is_deterministic_and_uniform(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    commandlet, unreal = _load_commandlet(monkeypatch)

    class Box:
        def __init__(self, minimum, maximum):
            self.min, self.max = minimum, maximum

    class Mesh(unreal.StaticMesh):
        def __init__(self, path, minimum, maximum):
            self.path, self.box = path, Box(minimum, maximum)

        def get_bounding_box(self):
            return self.box

        def get_path_name(self):
            return self.path

    source = Mesh(
        "/Game/Fixture/source.source",
        unreal.Vector(-1, -2, -3),
        unreal.Vector(1, 2, 3),
    )
    target = Mesh(
        "/Game/Fixture/target.target",
        unreal.Vector(-2, -1, -1),
        unreal.Vector(2, 1, 1),
    )

    class Component:
        values = {
            "static_mesh": source,
            "relative_location": unreal.Vector(10, 20, 30),
            "relative_rotation": unreal.Rotator(0, 0, 0),
            "relative_scale3d": unreal.Vector(2, 1, 0.5),
        }

        def get_editor_property(self, name):
            return self.values[name]

    fit = commandlet.compute_fit(Component(), target, "fixture.semantic")
    assert fit["bounds_method"] == "StaticMesh.get_bounding_box"
    assert fit["source_envelope_cm"] == [4.0, 4.0, 3.0]
    assert fit["uniform_scale"] == 1.0
    assert fit["final_relative_transform"] == {
        "location_cm": [10.0, 20.0, 30.0],
        "rotation_deg": [0.0, 0.0, 0.0],
        "scale": [1.0, 1.0, 1.0],
    }
    source_observation = {
        "presentation": {
            "relative_transform": {
                "location_cm": [10.0, 20.0, 30.0],
                "rotation_deg": [0.0, 0.0, 0.0],
                "scale": [2.0, 1.0, 0.5],
            }
        }
    }
    launcher._validate_r6_fit_derivation(
        launcher._validate_r6_fit(fit, "fixture fit"),
        source_observation,
        "fixture fit",
    )
    drift = copy.deepcopy(fit)
    drift["target_bounds"]["center_cm"][0] = 0.25
    with pytest.raises(launcher.HumanVisualDemoError, match="bounds derivation"):
        launcher._validate_r6_fit_derivation(
            launcher._validate_r6_fit(drift, "fixture fit"),
            source_observation,
            "fixture fit",
        )


def test_commandlet_mutation_surface_is_exactly_two_presentations_and_cold_reload() -> (
    None
):
    source = COMMANDLET.read_text(encoding="utf-8")
    assert source.count('"semantic_id": "home.r1/room.bedroom/entity.phone.01"') == 1
    assert (
        source.count(
            '"semantic_id": "home.r1/room.kitchen_dining/entity.coffee_cup.01"'
        )
        == 1
    )
    assert "/Game/CitySampleCrowd/Character/Accessories/phoneA.phoneA" in source
    assert "/Game/CitySampleCrowd/Character/Accessories/cupA.cupA" in source
    assert "mesh.get_bounding_box()" in source
    assert "unreal.AssetRegistryHelpers.get_asset_registry()" in source
    assert "registry.get_assets_by_package_name" in source
    assert "uniform_contain_existing_visual_envelope_v1" in source
    assert source.count("actor.configure_presentation_mesh(") == 1
    assert "destroy_actor(" not in source
    assert "set_actor_transform" not in source
    assert "set_editor_property(" not in source
    assert "save_map(world, MAP_OBJECT_PATH)" in source
    assert source.count("level_subsystem.load_level(MAP_OBJECT_PATH)") == 2
    assert "support.only_map_changed(" in source
    assert "pot_reloaded == pot_before" in source


def _write_base_receipt(root: Path) -> Path:
    project = root / "project/VistaPlayableHome.uproject"
    map_path = (
        root
        / "project/Content/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome.umap"
    )
    executable = root / "engine/UnrealEditor"
    config = root / "project/Config/DefaultEngine.ini"
    plugin = root / "project/Plugins/VistaPlayableHome/VistaPlayableHome.uplugin"
    for path in (project, map_path, executable, config, plugin):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((path.name + "\n").encode())
    executable.chmod(0o500)
    provenance = {}
    for key in launcher.SOURCE_PROVENANCE_ARTIFACT_KEYS:
        path = root / "provenance" / (key + ".json")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('{"fixture":true}\n', encoding="utf-8")
        provenance[key] = _pin(path)
    provenance["plugin_package_tree_sha256"] = "a" * 64
    provenance["plugin_source_git_commit"] = "b" * 40
    receipt = {
        "schema_version": launcher.COMBINED_RECEIPT_SCHEMA_V2,
        "status": launcher.COMBINED_RECEIPT_STATUS,
        "provider_id": launcher.PROVIDER_ID,
        "human_operated_visual_demo_only": True,
        "prohibited_agent_adapter": True,
        "project": _pin(project),
        "project_static_tree": launcher.compute_project_static_tree(project),
        "source_provenance": provenance,
        "executable": _pin(executable),
        "map": {"object_path": r6.MAP_OBJECT_PATH, "package": _pin(map_path)},
        "legal_scope": copy.deepcopy(launcher.LEGAL_SCOPE),
        "claims": copy.deepcopy(launcher.CLAIMS),
    }
    receipt["content_digest"] = launcher.content_digest(receipt)
    path = root / launcher.COMBINED_RECEIPT_NAME
    raw = launcher.canonical_json(receipt)
    path.write_bytes(raw)
    path.with_name(launcher.COMBINED_RECEIPT_SIDECAR_NAME).write_text(
        f"{hashlib.sha256(raw).hexdigest()}  {launcher.COMBINED_RECEIPT_NAME}\n",
        encoding="ascii",
    )
    return path


def test_launcher_v4_dispatch_is_additive_and_v2_v3_shapes_remain_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parent_path = _write_base_receipt(tmp_path / "parent")
    parent_inputs = launcher.load_combined_receipt(parent_path)
    receipt_path = _write_base_receipt(tmp_path / "r6")
    receipt = json.loads(receipt_path.read_bytes())
    receipt["schema_version"] = launcher.COMBINED_RECEIPT_SCHEMA_V4
    receipt["accessory_r6_upgrade"] = {"fixture": True}
    receipt["content_digest"] = launcher.content_digest(receipt)
    raw = launcher.canonical_json(receipt)
    receipt_path.write_bytes(raw)
    receipt_path.with_name(launcher.COMBINED_RECEIPT_SIDECAR_NAME).write_text(
        f"{hashlib.sha256(raw).hexdigest()}  {launcher.COMBINED_RECEIPT_NAME}\n",
        encoding="ascii",
    )
    monkeypatch.setattr(
        launcher,
        "_validate_accessory_r6_upgrade",
        lambda payload, **_kwargs: (copy.deepcopy(payload), parent_inputs),
    )
    loaded = launcher.load_combined_receipt(receipt_path)
    assert loaded.receipt_schema_version == launcher.COMBINED_RECEIPT_SCHEMA_V4
    assert loaded.accessory_r6_upgrade == {"fixture": True}
    assert loaded.realism_r4_upgrade is None
    assert "accessory_r6_upgrade" not in launcher.RECEIPT_V3_KEYS
    assert "realism_r4_upgrade" not in launcher.RECEIPT_V4_KEYS

    receipt["realism_r4_upgrade"] = {}
    receipt["content_digest"] = launcher.content_digest(receipt)
    raw = launcher.canonical_json(receipt)
    receipt_path.write_bytes(raw)
    receipt_path.with_name(launcher.COMBINED_RECEIPT_SIDECAR_NAME).write_text(
        f"{hashlib.sha256(raw).hexdigest()}  {launcher.COMBINED_RECEIPT_NAME}\n",
        encoding="ascii",
    )
    with pytest.raises(launcher.HumanVisualDemoError, match="non-closed key"):
        launcher.load_combined_receipt(receipt_path)
