from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import pytest

from tools.runtime.vista_playable_home import human_visual_demo_launch as source_lane
from tools.runtime.vista_playable_home import human_visual_packaged_launch as launcher
from tools.ue.vista_playable_home import human_visual_package_receipt as package
from tools.ue.vista_playable_home import human_visual_pso_seed as pso


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write(path: Path, raw: bytes, mode: int = 0o600) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    path.chmod(mode)
    return path


def _source_descriptor() -> dict[str, Any]:
    return {
        "Category": "Simulation",
        "Description": "Private human-operated VISTA City Sample visual demo",
        "EngineAssociation": "5.7",
        "FileVersion": 3,
        "Plugins": [
            {"Enabled": enabled, "Name": name}
            for name, enabled in package.SOURCE_PLUGIN_INVENTORY
        ],
    }


def _plugin_payload(dependencies: list[dict[str, Any]] | None = None) -> bytes:
    return json.dumps(
        {
            "FileVersion": 3,
            "Version": 1,
            "FriendlyName": "fixture",
            "Plugins": dependencies or [],
        },
        separators=(",", ":"),
        sort_keys=True,
    ).encode()


def _write_descriptor_graph(
    engine_root: Path,
    project_root: Path,
    *,
    niagara_python_game_dependency: bool = False,
    real_metahuman_dependencies: bool = False,
) -> None:
    def enabled(name: str, **extra: Any) -> dict[str, Any]:
        return {"Name": name, "Enabled": True, **extra}

    graph: dict[str, list[dict[str, Any]]] = {
        "VistaPlayableHome": [
            enabled("EnhancedInput"),
            enabled("IKRig"),
            enabled("PerformanceCaptureCore"),
            enabled("MetaHumanCharacter"),
        ],
        "HairStrands": [
            enabled("Niagara"),
            enabled("GeometryCache"),
            enabled("DeformerGraph"),
            enabled("Dataflow"),
            enabled("ComputeFramework"),
        ],
        "MassGameplay": [
            enabled("ZoneGraph"),
            enabled("ZoneGraphAnnotations"),
            enabled("SmartObjects"),
            enabled("StateTree"),
            enabled("DataValidation"),
        ],
        "RigLogic": [enabled("ControlRig")],
        "IKRig": [enabled("ControlRig"), enabled("FullBodyIK")],
        "FullBodyIK": [enabled("ControlRig")],
        "MetaHumanCharacter": (
            [
                enabled("MeshModelingToolset"),
                enabled("EditorScriptingUtilities"),
                enabled("AppleARKit", TargetAllowList=["Editor"]),
                enabled("AppleARKitFaceSupport", TargetAllowList=["Editor"]),
                enabled("LiveLink"),
                enabled("LiveLinkControlRig"),
                enabled("RigLogic"),
                enabled("MetaHumanSDK"),
                enabled("HairStrands"),
                enabled("Dataflow"),
                enabled("MetaHuman", TargetAllowList=["Editor"]),
                enabled("TextureGraph", TargetAllowList=["Editor"]),
                enabled("ChaosClothAsset"),
                enabled("ChaosClothAssetEditor"),
                enabled("ChaosOutfitAsset"),
                enabled("PerformanceCaptureCore"),
                enabled("IKRig"),
                enabled("PluginUtils"),
                enabled("GeometryScripting", TargetAllowList=["Editor"]),
            ]
            if real_metahuman_dependencies
            else [
                enabled("HairStrands"),
                enabled("RigLogic"),
                enabled("IKRig"),
                enabled("PerformanceCaptureCore"),
            ]
        ),
        "Niagara": [
            enabled("PythonScriptPlugin")
            if niagara_python_game_dependency
            else enabled("PythonScriptPlugin", TargetAllowList=["Editor"])
        ],
        "GeometryCache": [enabled("Niagara")],
        "DeformerGraph": [enabled("ComputeFramework"), enabled("ControlRig")],
        "Dataflow": [enabled("GeometryCache")],
        "ZoneGraphAnnotations": [enabled("ZoneGraph")],
    }
    if real_metahuman_dependencies:
        graph.update(
            {
                "LiveLinkControlRig": [enabled("ControlRig")],
                "MetaHumanSDK": [
                    enabled("EditorScriptingUtilities"),
                    enabled("ControlRig"),
                    enabled("HairStrands"),
                    enabled("RigLogic"),
                    enabled("Interchange", TargetAllowList=["Editor"]),
                ],
                "PluginUtils": [enabled("EditorScriptingUtilities")],
            }
        )
    leaves = {
        *package.ENABLED_PLUGIN_ALLOWLIST,
        "EnhancedInput",
        "PerformanceCaptureCore",
        "ComputeFramework",
        "ZoneGraph",
        "SmartObjects",
        "StateTree",
        "DataValidation",
        "ControlRig",
        "PythonScriptPlugin",
        "MeshModelingToolset",
        "EditorScriptingUtilities",
        "LiveLink",
        "LiveLinkControlRig",
        "MetaHumanSDK",
        "ChaosClothAsset",
        "ChaosClothAssetEditor",
        "ChaosOutfitAsset",
        "PluginUtils",
    }
    graph.update({name: graph.get(name, []) for name in leaves})
    for name, dependencies in graph.items():
        if name == "VistaPlayableHome":
            path = project_root / "Plugins/VistaPlayableHome/VistaPlayableHome.uplugin"
        else:
            path = engine_root / "Engine/Plugins/Fixture" / name / f"{name}.uplugin"
        if name == "ZoneGraphAnnotations":
            raw = (
                b'{"FileVersion":3,"Plugins":[{"Name":"ZoneGraph","Enabled":true},],}\n'
            )
        elif name == "PerformanceCaptureCore":
            raw = b"\xef\xbb\xbf" + _plugin_payload(dependencies)
        else:
            raw = _plugin_payload(dependencies)
        _write(path, raw)


class ClosedFixture:
    def __init__(self, root: Path, monkeypatch: pytest.MonkeyPatch):
        self.root = root
        self.attempt = root / "runs/attempt-closed-fixture"
        project = _write(
            root / "source/project/VistaPlayableHome.uproject",
            source_lane.canonical_json(_source_descriptor()),
        )
        assert _sha(project) == (
            "fe11c7e48eb895eec74e48868fc458a24a2290e826f8cbe75edea0e8ba8b674a"
        )
        source_receipt = _write(
            root / "source/human-visual-demo-combined-receipt.json", b"{}\n"
        )
        executable = _write(root / "source/UnrealEditor", b"editor", 0o555)
        map_package = _write(root / "source/project/Content/Map.umap", b"map")
        self.map_package = map_package
        self.source_default_engine = _write(
            root / "source/project/Config/DefaultEngine.ini",
            b"[Fixture]\nSource=True\n",
        )
        self.engine = root / "ue"
        _write_descriptor_graph(self.engine, project.parent)
        self.source = source_lane.HumanVisualDemoInputs(
            receipt=source_receipt,
            receipt_sha256=package.PINNED_SOURCE_RECEIPT_SHA256,
            receipt_content_digest=package.PINNED_SOURCE_CONTENT_DIGEST,
            project=source_lane.ArtifactPin(
                project, _sha(project), project.stat().st_size
            ),
            project_static_tree=source_lane.compute_project_static_tree(project),
            source_provenance={"plugin_source_git_commit": "b" * 40},
            executable=source_lane.ArtifactPin(
                executable, _sha(executable), executable.stat().st_size
            ),
            map_object_path=package.MAP_PATH,
            map_package=source_lane.ArtifactPin(
                map_package, _sha(map_package), map_package.stat().st_size
            ),
        )
        monkeypatch.setattr(
            package.source_lane, "load_combined_receipt", lambda _path: self.source
        )
        self.run_uat = _write(
            self.engine / package.RUN_UAT_SUFFIX, b"#!/bin/sh\n", 0o555
        )
        self.editor_cmd = _write(
            self.engine / package.EDITOR_CMD_SUFFIX, b"editor-cmd\n", 0o555
        )
        self.build_version = _write(
            self.engine / package.BUILD_VERSION_SUFFIX,
            json.dumps(
                {
                    "MajorVersion": 5,
                    "MinorVersion": 7,
                    "PatchVersion": 3,
                    "Changelist": package.PINNED_ENGINE_CHANGELIST,
                    "BranchName": "++UE5+Release-5.7",
                }
            ).encode(),
            0o444,
        )
        self.bwrap = _write(root / "tools/bwrap", b"bwrap-fixture\n", 0o555)
        monkeypatch.setattr(package, "PINNED_RUN_UAT_SHA256", _sha(self.run_uat))
        monkeypatch.setattr(package, "PINNED_EDITOR_CMD_SHA256", _sha(self.editor_cmd))
        monkeypatch.setattr(
            package, "PINNED_BUILD_VERSION_SHA256", _sha(self.build_version)
        )
        monkeypatch.setattr(package, "NETWORK_WRAPPER_PATH", self.bwrap)
        monkeypatch.setattr(package, "NETWORK_WRAPPER_SHA256", _sha(self.bwrap))
        monkeypatch.setattr(package, "NETWORK_WRAPPER_SIZE", self.bwrap.stat().st_size)
        self.config = package.PackagePlanConfig(
            self.source.receipt,
            package.PINNED_SOURCE_RECEIPT_SHA256,
            self.run_uat,
            _sha(self.run_uat),
            self.editor_cmd,
            _sha(self.editor_cmd),
            self.attempt,
        )
        self.stage_receipts: dict[str, Path] = {}

    def fresh_inputs(self) -> package.PackagePlanInputs:
        return package.validate_plan_inputs(self.config)

    def inputs(self) -> package.PackagePlanInputs:
        return package.validate_plan_inputs(self.config, require_fresh_attempt=False)

    def record(self, path: Path) -> dict[str, Any]:
        return {
            "relative_path": path.relative_to(self.attempt).as_posix(),
            "sha256": _sha(path),
            "size_bytes": path.stat().st_size,
            "mode": path.stat().st_mode & 0o7777,
        }

    def _sidecar(self, receipt: Path) -> None:
        _write(
            receipt.with_name(receipt.name + ".sha256"),
            f"{_sha(receipt)}  {receipt.name}\n".encode(),
        )

    def materialize_artifacts(self) -> package.PackagePlanInputs:
        self.attempt.mkdir(parents=True)
        for project_root in (
            package.SEED_PROJECT_RELATIVE,
            package.FINAL_PROJECT_RELATIVE,
        ):
            materialized_root = self.attempt / project_root
            _write(
                materialized_root / package.PROJECT_NAME,
                package.canonical_json(package.package_project_descriptor()),
            )
            _write_descriptor_graph(self.engine, materialized_root)
            _write(
                materialized_root / "Content/Map.umap",
                self.map_package.read_bytes(),
            )
            _write(
                materialized_root / "Config/DefaultEngine.ini",
                package.projected_default_engine_ini(
                    self.source_default_engine.read_bytes()
                ),
            )
            _write(
                materialized_root / "Config/DefaultGame.ini",
                package.PSO_GAME_INI,
            )
        _write(
            self.attempt / "seed-cook/archive/Linux/VistaPlayableHome.sh",
            b"#!/bin/sh\n",
            0o555,
        )
        _write(self.attempt / "seed-cook/archive/Linux/seed.bin", b"seed")
        _write(
            self.attempt
            / "seed-cook/cooked/Linux/VistaPlayableHome/Metadata/PipelineCaches/"
            "ShaderStableInfo-VistaPlayableHome-SF_VULKAN_SM6.shk",
            b"stable-key-bytes",
        )
        _write(
            self.attempt / "seed-cook/runuat.log",
            b"BUILD SUCCESSFUL\nAutomationTool exiting with ExitCode=0 (Success)\n",
        )
        _write(
            self.attempt
            / "pso-capture/user/Saved/CollectedPSOs/++VistaPlayableHome.rec.upipelinecache",
            b"recorded-pso-bytes",
        )
        _write(
            self.attempt / "pso-capture/capture.log",
            b"LogShaderPipelineCache: Display: Saved 9 PSOs\nLogExit: Exiting.\n",
        )
        coverage: dict[str, Any] = {
            "schema_version": "simworld.vista.human-visual-pso-coverage-ledger/v1",
            "status": "human_traversal_attested",
            "rooms": list(pso.COVERAGE_ROOMS),
            "interactions": list(pso.COVERAGE_INTERACTIONS),
            "human_operator_attested": True,
            "agent_adapter_used": False,
            "ai_vlm_pixel_review_used": False,
        }
        coverage["content_digest"] = pso.content_digest(coverage)
        _write(
            self.attempt / "pso-capture/human-coverage-ledger.json",
            pso.canonical_json(coverage),
        )
        _write(
            self.attempt / "expand/" / pso.STABLE_CACHE_NAME,
            b"expanded-spc-bytes",
        )
        expand_output = self.attempt / "expand" / pso.STABLE_CACHE_NAME
        recorded_glob = (
            self.attempt / "pso-capture/user/Saved/CollectedPSOs/*.rec.upipelinecache"
        )
        stable_glob = (
            self.attempt
            / "seed-cook/cooked/Linux/VistaPlayableHome/Metadata/PipelineCaches/*.shk"
        )
        _write(
            self.attempt / "expand/expand.log",
            (
                f"Expanding matched    1 files: {recorded_glob}\n"
                f"Expanding matched    1 files: {stable_glob}\n"
                "Loaded 11 unique shader info lines total.\n"
                "Loaded 9 PSOs total [Usage Mask Merged = 0].\n"
                f"Wrote 9 binary PSOs (graphics: 8 compute: 1 RT: 0), (4KB) to "
                f"{expand_output}\n"
            ).encode(),
        )
        _write(
            self.attempt
            / package.FINAL_PROJECT_RELATIVE
            / "Build/Linux/PipelineCaches"
            / pso.STABLE_CACHE_NAME,
            b"expanded-spc-bytes",
        )
        _write(
            self.attempt / "final-cook/archive/Linux/VistaPlayableHome.sh",
            b"#!/bin/sh\n",
            0o555,
        )
        _write(
            self.attempt / "final-cook/archive/Linux/VistaPlayableHome/Binaries/Linux/"
            "VistaPlayableHome",
            b"elf-final",
            0o555,
        )
        _write(
            self.attempt / "final-cook/archive/Linux/VistaPlayableHome/Content/Paks/"
            "VistaPlayableHome-Linux.pak",
            b"pak-final",
            0o444,
        )
        _write(
            self.attempt
            / "final-cook/cooked/Linux/VistaPlayableHome/Content/PipelineCaches/Linux/"
            / pso.BAKED_CACHE_BASENAME,
            b"baked-pipeline-cache",
        )
        _write(
            self.attempt / "final-cook/runuat.log",
            b"BUILD SUCCESSFUL\nAutomationTool exiting with ExitCode=0 (Success)\n",
        )
        inputs = self.inputs()
        self._write_projection_manifests(inputs)
        self._write_plugin_closure()
        self._write_stage_receipts(inputs)
        self._write_final_receipt(inputs)
        return inputs

    def _write_projection_manifests(self, inputs: package.PackagePlanInputs) -> None:
        for stage, relative in (
            ("seed_cook", package.SEED_PROJECTION_MANIFEST_RELATIVE),
            ("final_cook", package.PROJECTION_MANIFEST_RELATIVE),
        ):
            payload = package.derive_source_projection_manifest(
                inputs.source, self.attempt, stage=stage
            )
            receipt = _write(
                self.attempt / relative,
                package.canonical_json(payload),
            )
            self._sidecar(receipt)

    def _write_plugin_closure(self) -> None:
        descriptor = self.attempt / package.MATERIALIZED_DESCRIPTOR_RELATIVE
        graph = package.derive_plugin_graph(
            engine_root=self.engine,
            project_root=self.attempt / package.FINAL_PROJECT_RELATIVE,
            project_descriptor=package.package_project_descriptor(),
        )
        payload: dict[str, Any] = {
            "schema_version": package.PLUGIN_CLOSURE_SCHEMA,
            "status": package.PLUGIN_CLOSURE_STATUS,
            "attempt_root": str(self.attempt),
            "project_descriptor": self.record(descriptor),
            "source_projection_manifest": self.record(
                self.attempt / package.PROJECTION_MANIFEST_RELATIVE
            ),
            "descriptor_graph": dict(graph.evidence),
            "engine_plugins_disabled_by_default": True,
            "resolution_complete": True,
            "target": dict(package.PLUGIN_TARGET),
        }
        payload["content_digest"] = package.content_digest(payload)
        receipt = _write(
            self.attempt / package.PLUGIN_CLOSURE_RELATIVE,
            package.canonical_json(payload),
        )
        self._sidecar(receipt)

    def _artifacts(self, stage: str) -> dict[str, Any]:
        if stage == "seed_cook":
            archive = self.attempt / "seed-cook/archive"
            stable = sorted(
                (
                    self.attempt
                    / "seed-cook/cooked/Linux/VistaPlayableHome/Metadata/PipelineCaches"
                ).glob("*.shk")
            )
            return {
                "archive": package.compute_archive_tree(archive),
                "launcher": self.record(archive / "Linux/VistaPlayableHome.sh"),
                "project_descriptor": self.record(
                    self.attempt / package.SEED_PROJECT_RELATIVE / package.PROJECT_NAME
                ),
                "source_projection_manifest": self.record(
                    self.attempt / package.SEED_PROJECTION_MANIFEST_RELATIVE
                ),
                "stable_keys": [self.record(path) for path in stable],
            }
        if stage == "human_capture":
            recorded = sorted(
                (self.attempt / "pso-capture/user/Saved/CollectedPSOs").glob(
                    "*.rec.upipelinecache"
                )
            )
            return {
                "recorded_psos": [self.record(path) for path in recorded],
                "coverage_ledger": self.record(
                    self.attempt / "pso-capture/human-coverage-ledger.json"
                ),
                "seed_projection_manifest": self.record(
                    self.attempt / package.SEED_PROJECTION_MANIFEST_RELATIVE
                ),
            }
        if stage == "expand":
            return {
                "stable_cache": self.record(
                    self.attempt / "expand" / pso.STABLE_CACHE_NAME
                )
            }
        archive = self.attempt / "final-cook/archive"
        baked = sorted(
            (self.attempt / "final-cook/cooked/Linux").rglob("*.stable.upipelinecache")
        )
        return {
            "archive": package.compute_archive_tree(archive),
            "launcher": self.record(archive / "Linux/VistaPlayableHome.sh"),
            "executable": self.record(
                archive / "Linux/VistaPlayableHome/Binaries/Linux/VistaPlayableHome"
            ),
            "pak": self.record(
                archive / "Linux/VistaPlayableHome/Content/Paks/"
                "VistaPlayableHome-Linux.pak"
            ),
            "project_descriptor": self.record(
                self.attempt / package.MATERIALIZED_DESCRIPTOR_RELATIVE
            ),
            "stable_cache_input": self.record(
                self.attempt
                / package.FINAL_PROJECT_RELATIVE
                / "Build/Linux/PipelineCaches"
                / pso.STABLE_CACHE_NAME
            ),
            "baked_pipeline_caches": [self.record(path) for path in baked],
        }

    def _write_stage_receipts(self, inputs: package.PackagePlanInputs) -> None:
        loaded: dict[str, pso.StageReceiptBinding] = {}
        for stage in pso.STAGE_IDS:
            log = self.attempt / pso.STAGE_LOG_RELATIVE[stage]
            argv = pso.expected_command(inputs, stage)
            payload: dict[str, Any] = {
                "schema_version": pso.STAGE_SCHEMA[stage],
                "status": pso.STAGE_STATUS[stage],
                "stage": stage,
                "attempt_root": str(self.attempt),
                "source": pso.source_record(inputs),
                "parents": pso.expected_parents(inputs, stage, loaded),
                "toolchain": pso.toolchain_record(inputs),
                "command": {
                    "argv": argv,
                    "argv_sha256": pso._command_sha256(argv),
                    "shell": False,
                    "returncode": 0,
                    "log": self.record(log),
                },
                "artifacts": self._artifacts(stage),
                "legal_scope": dict(package.HUMAN_ONLY_LEGAL_BOUNDARY),
                "claims": dict(package.CLAIMS),
            }
            payload["content_digest"] = pso.content_digest(payload)
            receipt = _write(
                self.attempt / pso.STAGE_RECEIPT_RELATIVE[stage],
                pso.canonical_json(payload),
            )
            self._sidecar(receipt)
            self.stage_receipts[stage] = receipt
            loaded[stage] = pso.load_stage_receipt(inputs, stage, loaded)

    def _write_final_receipt(self, inputs: package.PackagePlanInputs) -> None:
        archive = self.attempt / "final-cook/archive"
        source = {
            **pso.source_record(inputs),
            "run_uat": str(inputs.run_uat.path),
            "run_uat_sha256": inputs.run_uat.sha256,
            "editor_cmd": str(inputs.editor_cmd.path),
            "editor_cmd_sha256": inputs.editor_cmd.sha256,
        }
        payload: dict[str, Any] = {
            "schema_version": package.FINAL_RECEIPT_SCHEMA,
            "status": package.FINAL_RECEIPT_STATUS,
            "stage": "final_cook",
            "attempt_root": str(self.attempt),
            "source": source,
            "dag": {
                stage: self.record(path) for stage, path in self.stage_receipts.items()
            },
            "legal_scope": dict(package.HUMAN_ONLY_LEGAL_BOUNDARY),
            "plugin_policy": dict(package.PLUGIN_POLICY),
            "runtime": dict(package.RUNTIME_BINDING),
            "project_descriptor": self.record(
                self.attempt / package.MATERIALIZED_DESCRIPTOR_RELATIVE
            ),
            "source_projection_manifest": self.record(
                self.attempt / package.PROJECTION_MANIFEST_RELATIVE
            ),
            "plugin_closure": self.record(
                self.attempt / package.PLUGIN_CLOSURE_RELATIVE
            ),
            "pso": {
                "expand_receipt_sha256": _sha(self.stage_receipts["expand"]),
                "stable_cache": self.record(
                    self.attempt / "expand" / pso.STABLE_CACHE_NAME
                ),
            },
            "archive": package.compute_archive_tree(archive),
            "artifacts": {
                "launcher": self.record(archive / "Linux/VistaPlayableHome.sh"),
                "executable": self.record(
                    archive / "Linux/VistaPlayableHome/Binaries/Linux/VistaPlayableHome"
                ),
                "pak": self.record(
                    archive / "Linux/VistaPlayableHome/Content/Paks/"
                    "VistaPlayableHome-Linux.pak"
                ),
            },
            "uat": {
                "command_sha256": package.command_sha256(
                    package.build_uat_command(inputs, phase="final_cook")
                ),
                "log": self.record(self.attempt / "final-cook/runuat.log"),
                "success": True,
            },
            "claims": dict(package.CLAIMS),
        }
        payload["content_digest"] = package.content_digest(payload)
        receipt = _write(
            self.attempt / package.FINAL_RECEIPT_RELATIVE,
            package.canonical_json(payload),
        )
        self._sidecar(receipt)

    def replace_stage_log(self, stage: str, raw: bytes) -> None:
        log = _write(self.attempt / pso.STAGE_LOG_RELATIVE[stage], raw)
        receipt = self.stage_receipts[stage]
        payload = json.loads(receipt.read_text())
        payload["command"]["log"] = self.record(log)
        payload["content_digest"] = pso.content_digest(payload)
        receipt.write_bytes(pso.canonical_json(payload))
        self._sidecar(receipt)

    @property
    def final_receipt(self) -> Path:
        return self.attempt / package.FINAL_RECEIPT_RELATIVE


def test_plan_is_zero_write_and_rehashes_bwrap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = ClosedFixture(tmp_path, monkeypatch)
    inputs = fixture.fresh_inputs()
    plan = package.build_package_plan(inputs)
    assert not fixture.attempt.exists()
    assert plan["engine"]["network_wrapper"] == {
        "path": str(fixture.bwrap),
        "sha256": _sha(fixture.bwrap),
        "size_bytes": fixture.bwrap.stat().st_size,
    }
    descriptor = plan["project_projection"]["descriptor"]
    assert descriptor["DisableEnginePluginsByDefault"] is True
    assert [p["Name"] for p in descriptor["Plugins"] if p["Enabled"]] == list(
        package.ENABLED_PLUGIN_ALLOWLIST
    )
    graph = plan["project_projection"]["derived_plugin_graph"]
    edges = {(edge["source"], edge["target"]) for edge in graph["dependency_edges"]}
    assert {
        ("HairStrands", "Niagara"),
        ("HairStrands", "GeometryCache"),
        ("HairStrands", "DeformerGraph"),
        ("HairStrands", "Dataflow"),
        ("HairStrands", "ComputeFramework"),
        ("MassGameplay", "ZoneGraph"),
        ("MassGameplay", "ZoneGraphAnnotations"),
        ("MassGameplay", "SmartObjects"),
        ("MassGameplay", "StateTree"),
        ("MassGameplay", "DataValidation"),
        ("IKRig", "ControlRig"),
        ("IKRig", "FullBodyIK"),
    } <= edges
    assert {
        (item["source"], item["target"], item["reason"])
        for item in graph["skipped_references"]
    } >= {("Niagara", "PythonScriptPlugin", "target_not_applicable")}
    projections = plan["project_projection"]["source_projection_manifests"]
    assert projections["seed_cook_relative_path"] == (
        package.SEED_PROJECTION_MANIFEST_RELATIVE.as_posix()
    )
    assert projections["final_cook_relative_path"] == (
        package.PROJECTION_MANIFEST_RELATIVE.as_posix()
    )
    assert projections["static_roots"] == ["Config", "Content", "Plugins", "Source"]
    assert (
        projections["seed_manifest_rederived_before_seed_and_capture_acceptance"]
        is True
    )


def test_real_niagara_python_dependency_conflicts_with_denylist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = ClosedFixture(tmp_path, monkeypatch)
    niagara = fixture.engine / "Engine/Plugins/Fixture/Niagara/Niagara.uplugin"
    niagara.write_bytes(
        _plugin_payload([{"Name": "PythonScriptPlugin", "Enabled": True}])
    )
    with pytest.raises(
        package.HumanVisualPackageError,
        match=r"PLUGIN_DENY_CONFLICT: .*Niagara->PythonScriptPlugin:denied",
    ):
        package.build_package_plan(fixture.fresh_inputs())


def test_real_metahuman_and_niagara_descriptor_conflicts_are_all_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = ClosedFixture(tmp_path, monkeypatch)
    _write_descriptor_graph(
        fixture.engine,
        fixture.source.project.path.parent,
        niagara_python_game_dependency=True,
        real_metahuman_dependencies=True,
    )
    with pytest.raises(package.HumanVisualPackageError) as caught:
        package.build_package_plan(fixture.fresh_inputs())
    message = str(caught.value)
    assert message.startswith("PLUGIN_DENY_CONFLICT:")
    assert "MetaHumanCharacter->EditorScriptingUtilities:denied" in message
    assert "Niagara->PythonScriptPlugin:denied" in message
    assert "MetaHumanSDK->EditorScriptingUtilities:denied" in message
    assert "PluginUtils->EditorScriptingUtilities:denied" in message


def test_plugin_optional_and_target_restrictions_are_derived(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = ClosedFixture(tmp_path, monkeypatch)
    sun = fixture.engine / "Engine/Plugins/Fixture/SunPosition/SunPosition.uplugin"
    sun.write_bytes(
        _plugin_payload(
            [
                {"Name": "MissingOptional", "Enabled": True, "Optional": True},
                {
                    "Name": "WindowsOnlyMissing",
                    "Enabled": True,
                    "PlatformAllowList": ["Win64"],
                },
            ]
        )
    )
    graph = package.derive_plugin_graph(
        engine_root=fixture.engine,
        project_root=fixture.source.project.path.parent,
        project_descriptor=package.package_project_descriptor(),
    )
    skipped = {
        (item["target"], item["reason"])
        for item in graph.evidence["skipped_references"]
    }
    assert ("MissingOptional", "optional_descriptor_missing") in skipped
    assert ("WindowsOnlyMissing", "platform_not_applicable") in skipped


def test_missing_mandatory_plugin_dependency_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = ClosedFixture(tmp_path, monkeypatch)
    sun = fixture.engine / "Engine/Plugins/Fixture/SunPosition/SunPosition.uplugin"
    sun.write_bytes(_plugin_payload([{"Name": "MissingRuntime", "Enabled": True}]))
    with pytest.raises(
        package.HumanVisualPackageError, match="PLUGIN_DEPENDENCY_CONFLICT"
    ):
        package.derive_plugin_graph(
            engine_root=fixture.engine,
            project_root=fixture.source.project.path.parent,
            project_descriptor=package.package_project_descriptor(),
        )


def test_malformed_target_restriction_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = ClosedFixture(tmp_path, monkeypatch)
    sun = fixture.engine / "Engine/Plugins/Fixture/SunPosition/SunPosition.uplugin"
    sun.write_bytes(
        _plugin_payload(
            [
                {
                    "Name": "EditorOnlyButMalformed",
                    "Enabled": True,
                    "TargetAllowList": "Editor",
                }
            ]
        )
    )
    with pytest.raises(
        package.HumanVisualPackageError, match="PLUGIN_RESTRICTION_INVALID"
    ):
        package.derive_plugin_graph(
            engine_root=fixture.engine,
            project_root=fixture.source.project.path.parent,
            project_descriptor=package.package_project_descriptor(),
        )


def test_has_explicit_platforms_requires_linux_platform_allowlist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = ClosedFixture(tmp_path, monkeypatch)
    sun = fixture.engine / "Engine/Plugins/Fixture/SunPosition/SunPosition.uplugin"
    sun.write_bytes(
        _plugin_payload(
            [
                {
                    "Name": "ZoneGraph",
                    "Enabled": True,
                    "HasExplicitPlatforms": True,
                    "SupportedTargetPlatforms": ["Linux"],
                }
            ]
        )
    )
    graph = package.derive_plugin_graph(
        engine_root=fixture.engine,
        project_root=fixture.source.project.path.parent,
        project_descriptor=package.package_project_descriptor(),
    )
    assert {
        (item["source"], item["target"], item["reason"])
        for item in graph.evidence["skipped_references"]
    } >= {("SunPosition", "ZoneGraph", "explicit_platform_missing")}

    sun.write_bytes(
        _plugin_payload(
            [
                {
                    "Name": "ZoneGraph",
                    "Enabled": True,
                    "HasExplicitPlatforms": True,
                    "PlatformAllowList": ["Linux"],
                }
            ]
        )
    )
    graph = package.derive_plugin_graph(
        engine_root=fixture.engine,
        project_root=fixture.source.project.path.parent,
        project_descriptor=package.package_project_descriptor(),
    )
    assert ("SunPosition", "ZoneGraph") in {
        (item["source"], item["target"]) for item in graph.evidence["dependency_edges"]
    }


def test_plugin_dependency_cycle_is_refused_with_ubt_style_chain(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = ClosedFixture(tmp_path, monkeypatch)
    sun = fixture.engine / "Engine/Plugins/Fixture/SunPosition/SunPosition.uplugin"
    cycle = fixture.engine / "Engine/Plugins/Fixture/CycleA/CycleA.uplugin"
    sun.write_bytes(_plugin_payload([{"Name": "CycleA", "Enabled": True}]))
    _write(cycle, _plugin_payload([{"Name": "SunPosition", "Enabled": True}]))
    with pytest.raises(
        package.HumanVisualPackageError,
        match=(
            "PLUGIN_CIRCULAR_DEPENDENCY: circular dependency: "
            "CycleA -> SunPosition -> CycleA|"
            "SunPosition -> CycleA -> SunPosition"
        ),
    ):
        package.derive_plugin_graph(
            engine_root=fixture.engine,
            project_root=fixture.source.project.path.parent,
            project_descriptor=package.package_project_descriptor(),
        )


def test_bwrap_drift_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = ClosedFixture(tmp_path, monkeypatch)
    fixture.bwrap.chmod(0o700)
    fixture.bwrap.write_bytes(b"changed-bwrap\n")
    fixture.bwrap.chmod(0o555)
    with pytest.raises(
        package.HumanVisualPackageError, match="NETWORK_WRAPPER_PIN_MISMATCH"
    ):
        fixture.fresh_inputs()


def test_bwrap_drift_between_validation_and_plan_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = ClosedFixture(tmp_path, monkeypatch)
    inputs = fixture.fresh_inputs()
    fixture.bwrap.chmod(0o700)
    fixture.bwrap.write_bytes(b"changed-after-validation\n")
    fixture.bwrap.chmod(0o555)
    with pytest.raises(
        package.HumanVisualPackageError, match="NETWORK_WRAPPER_PIN_MISMATCH"
    ):
        package.build_package_plan(inputs)


def test_closed_receipt_chain_and_final_receipt_pass(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = ClosedFixture(tmp_path, monkeypatch)
    inputs = fixture.materialize_artifacts()
    chain = pso.load_receipt_chain(inputs)
    assert chain.expand.artifact_sha256s == (
        _sha(fixture.attempt / "expand" / pso.STABLE_CACHE_NAME),
    )
    binding = package.load_final_package_receipt(fixture.final_receipt)
    assert binding.archive_root == fixture.attempt / "final-cook/archive"
    assert binding.pso_expand_receipt_sha256 == _sha(fixture.stage_receipts["expand"])
    seed_projection = package.load_source_projection_manifest(
        fixture.attempt, inputs.source, stage="seed_cook"
    )
    assert seed_projection.projected_project_root == (
        fixture.attempt / package.SEED_PROJECT_RELATIVE
    )
    seed_manifest = json.loads(seed_projection.receipt.path.read_text())
    assert seed_manifest["projection_stage"] == "seed_cook"
    manifest = json.loads(
        (fixture.attempt / package.PROJECTION_MANIFEST_RELATIVE).read_text()
    )
    plugin_entry = next(
        entry
        for entry in manifest["files"]
        if entry["relative_path"]
        == "Plugins/VistaPlayableHome/VistaPlayableHome.uplugin"
    )
    source_plugin = (
        fixture.source.project.path.parent
        / "Plugins/VistaPlayableHome/VistaPlayableHome.uplugin"
    )
    assert plugin_entry["operation"] == "copy_exact"
    for key in ("sha256", "size_bytes", "mode"):
        assert plugin_entry["source"][key] == plugin_entry["projected"][key]
    assert (
        plugin_entry["source"]["st_dev"],
        plugin_entry["source"]["st_ino"],
    ) != (
        plugin_entry["projected"]["st_dev"],
        plugin_entry["projected"]["st_ino"],
    )
    assert plugin_entry["source"]["st_nlink"] == 1
    assert plugin_entry["projected"]["st_nlink"] == 1
    assert plugin_entry["source"]["sha256"] == _sha(source_plugin)


def test_packaged_plan_rehashes_archive_and_refuses_post_load_tamper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = ClosedFixture(tmp_path, monkeypatch)
    fixture.materialize_artifacts()
    binding = package.load_final_package_receipt(fixture.final_receipt)
    inputs = launcher.PackagedLaunchInputs(
        package=binding,
        cache_root=launcher.CACHE_PARENT / binding.receipt_sha256,
        network_wrapper=fixture.inputs().network_wrapper,
    )
    plan = launcher.build_plan(inputs)
    assert plan["package"]["archive_rehashed_during_plan"] is True
    binding.pak.path.chmod(0o600)
    binding.pak.path.write_bytes(binding.pak.path.read_bytes() + b"tamper-after-load")
    binding.pak.path.chmod(0o444)
    with pytest.raises(
        launcher.HumanVisualPackagedLaunchError,
        match="final package changed during launch planning",
    ):
        launcher.build_plan(inputs)


@pytest.mark.parametrize("replacement", ["rename", "same_byte_symlink"])
def test_packaged_plan_revalidates_projected_path_identity_after_load(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    replacement: str,
) -> None:
    fixture = ClosedFixture(tmp_path, monkeypatch)
    fixture.materialize_artifacts()
    binding = package.load_final_package_receipt(fixture.final_receipt)
    inputs = launcher.PackagedLaunchInputs(
        package=binding,
        cache_root=launcher.CACHE_PARENT / binding.receipt_sha256,
        network_wrapper=fixture.inputs().network_wrapper,
    )
    projected = (
        fixture.attempt
        / package.FINAL_PROJECT_RELATIVE
        / "Plugins/VistaPlayableHome/VistaPlayableHome.uplugin"
    )
    original = fixture.attempt / "held-vista-playable-home.uplugin"
    raw = projected.read_bytes()
    mode = projected.stat().st_mode & 0o7777
    projected.rename(original)
    if replacement == "rename":
        _write(projected, raw, mode)
    else:
        projected.symlink_to(original)
    with pytest.raises(
        launcher.HumanVisualPackagedLaunchError,
        match="final package changed during launch planning",
    ):
        launcher.build_plan(inputs)


@pytest.mark.parametrize(
    ("relative", "expected"),
    [
        (
            "seed-cook/cooked/Linux/VistaPlayableHome/Metadata/PipelineCaches/"
            "ShaderStableInfo-VistaPlayableHome-SF_VULKAN_SM6.shk",
            "ARTIFACT_PIN_MISMATCH",
        ),
        (
            "pso-capture/user/Saved/CollectedPSOs/"
            "++VistaPlayableHome.rec.upipelinecache",
            "ARTIFACT_PIN_MISMATCH",
        ),
        (
            "expand/VistaPlayableHome_SF_VULKAN_SM6.spc",
            "ARTIFACT_PIN_MISMATCH",
        ),
        (
            "final-cook/cooked/Linux/VistaPlayableHome/Content/PipelineCaches/Linux/"
            "VistaPlayableHome_SF_VULKAN_SM6.stable.upipelinecache",
            "ARTIFACT_PIN_MISMATCH",
        ),
    ],
)
def test_each_real_pso_artifact_drift_is_refused(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    relative: str,
    expected: str,
) -> None:
    fixture = ClosedFixture(tmp_path, monkeypatch)
    fixture.materialize_artifacts()
    path = fixture.attempt / relative
    path.write_bytes(path.read_bytes() + b"drift")
    with pytest.raises(
        (package.HumanVisualPackageError, pso.HumanVisualPsoError), match=expected
    ):
        package.load_final_package_receipt(fixture.final_receipt)


@pytest.mark.parametrize(
    ("stage", "raw", "expected"),
    [
        ("seed_cook", b"BUILD SUCCESSFUL\n", "STAGE_LOG_SUCCESS_MISSING"),
        (
            "seed_cook",
            b"BUILD SUCCESSFUL\nError: hidden cook failure\n"
            b"AutomationTool exiting with ExitCode=0 (Success)\n",
            "STAGE_LOG_FAILURE",
        ),
        (
            "seed_cook",
            b"BUILD SUCCESSFUL\n"
            b"AutomationTool exiting with ExitCode=0 (Success)\n"
            b"Cook completed with errors.\n",
            "STAGE_LOG_FAILURE",
        ),
        (
            "seed_cook",
            b"No stable keys found.\nBUILD SUCCESSFUL\n"
            b"AutomationTool exiting with ExitCode=0 (Success)\n",
            "STAGE_LOG_FAILURE",
        ),
        (
            "seed_cook",
            b"Package was not written.\nBUILD SUCCESSFUL\n"
            b"AutomationTool exiting with ExitCode=0 (Success)\n",
            "STAGE_LOG_FAILURE",
        ),
        (
            "seed_cook",
            b"BUILD SUCCESSFUL\n"
            b"AutomationTool exiting with ExitCode=0 (Success)\n"
            b"benign-looking tail\n",
            "STAGE_LOG_SUCCESS_MISSING",
        ),
        (
            "human_capture",
            b"LogShaderPipelineCache: Display: Saved 0 PSOs\nLogExit: Exiting.\n",
            "CAPTURE_LOG_REJECTED",
        ),
        (
            "human_capture",
            b"LogShaderPipelineCache: Display: NotSaved 9 PSOs\nLogExit: Exiting.\n",
            "CAPTURE_LOG_REJECTED",
        ),
        (
            "human_capture",
            b"LogShaderPipelineCache: Display: Saved 9 PSOs\n"
            b"No PSOs saved.\nLogExit: Exiting.\n",
            "CAPTURE_LOG_REJECTED",
        ),
        (
            "human_capture",
            b"Missing PSOs.\nSaved 9 PSOs\nLogExit: Exiting.\n",
            "STAGE_LOG_FAILURE",
        ),
        (
            "human_capture",
            b"Saved 9 PSOs\nLogExit: Exiting.\nbenign-looking tail\n",
            "CAPTURE_LOG_REJECTED",
        ),
        (
            "human_capture",
            b"Saved 9 PSOs\nLogExit: Exiting.\n17 PSOs rejected\n",
            "CAPTURE_LOG_REJECTED",
        ),
        (
            "human_capture",
            b"Saved 9 PSOs\nLogExit: Exiting.\nSegmentation fault (core dumped)\n",
            "STAGE_LOG_FAILURE",
        ),
        (
            "human_capture",
            b"Saved 9 PSOs\nLogExit: Exiting.\nProcess exited with exit code 7\n",
            "STAGE_LOG_FAILURE",
        ),
        (
            "human_capture",
            b"Saved 9 PSOs\nLogExit: Exiting.\nCook failed\n",
            "STAGE_LOG_FAILURE",
        ),
        (
            "human_capture",
            b"Saved 9 PSOs\nLogExit: Exiting.\nFatal error\n",
            "STAGE_LOG_FAILURE",
        ),
        (
            "expand",
            b"Expanding recorded/*.rec.upipelinecache....did not match anything.\n",
            "EXPAND_LOG_REJECTED",
        ),
        (
            "expand",
            b"Expanding matched 1 files: recorded\n"
            b"Expanding matched 1 files: stable\n"
            b"Loaded 0 unique shader info lines total.\n"
            b"Loaded 9 PSOs total [Usage Mask Merged = 0].\n",
            "STAGE_LOG_SUCCESS_MISSING",
        ),
        (
            "expand",
            b"Expanding matched 1 files: recorded\n"
            b"Expanding matched 1 files: stable\n"
            b"Loaded 11 unique shader info lines total.\n"
            b"Loaded 9 stable PSOs. 1 PSOs rejected, 0 PSOs merged\n",
            "EXPAND_LOG_REJECTED",
        ),
        (
            "final_cook",
            b"BUILD FAILED\nAutomationTool exiting with ExitCode=0 (Success)\n",
            "STAGE_LOG_FAILURE",
        ),
        (
            "final_cook",
            b"No PSOs were saved.\nBUILD SUCCESSFUL\n"
            b"AutomationTool exiting with ExitCode=0 (Success)\n",
            "STAGE_LOG_FAILURE",
        ),
    ],
)
def test_semantic_stage_log_adversarial_cases_are_refused(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    stage: str,
    raw: bytes,
    expected: str,
) -> None:
    fixture = ClosedFixture(tmp_path, monkeypatch)
    inputs = fixture.materialize_artifacts()
    fixture.replace_stage_log(stage, raw)
    with pytest.raises(pso.HumanVisualPsoError, match=expected):
        pso.load_receipt_chain(inputs)


def test_uat_benign_zero_rejected_summary_is_allowed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = ClosedFixture(tmp_path, monkeypatch)
    inputs = fixture.materialize_artifacts()
    fixture.replace_stage_log(
        "seed_cook",
        b"0 PSOs rejected.\nBUILD SUCCESSFUL\n"
        b"AutomationTool exiting with ExitCode=0 (Success)\n",
    )
    binding = pso.load_stage_receipt(inputs, "seed_cook", {})
    assert binding.stage == "seed_cook"


@pytest.mark.parametrize(
    ("mutation", "expected"),
    [
        ("wrong_recorded_input", "STAGE_LOG_SUCCESS_MISSING"),
        ("wrong_stable_input", "STAGE_LOG_SUCCESS_MISSING"),
        ("wrong_output", "STAGE_LOG_SUCCESS_MISSING"),
        ("rejection_word_form", "EXPAND_LOG_REJECTED"),
        ("error_loading_after_success", "STAGE_LOG_FAILURE"),
        ("crash_after_success", "STAGE_LOG_FAILURE"),
        ("fatal_after_success", "STAGE_LOG_FAILURE"),
        ("no_stable_keys_after_success", "EXPAND_LOG_REJECTED"),
        ("not_written_after_success", "STAGE_LOG_FAILURE"),
    ],
)
def test_expand_log_binds_exact_inputs_and_rejects_contradictory_success(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
    expected: str,
) -> None:
    fixture = ClosedFixture(tmp_path, monkeypatch)
    inputs = fixture.materialize_artifacts()
    log_path = fixture.attempt / pso.STAGE_LOG_RELATIVE["expand"]
    text = log_path.read_text()
    if mutation == "wrong_recorded_input":
        text = text.replace("*.rec.upipelinecache", "wrong.rec.upipelinecache")
    elif mutation == "wrong_stable_input":
        text = text.replace("*.shk", "wrong.shk")
    elif mutation == "wrong_output":
        text = text.replace(pso.STABLE_CACHE_NAME, "wrong.spc")
    elif mutation == "rejection_word_form":
        text += "PSO rejections: 1\n"
    elif mutation == "error_loading_after_success":
        text += "Error: error loading recorded cache\n"
    elif mutation == "crash_after_success":
        text += "Segmentation fault (core dumped)\n"
    elif mutation == "fatal_after_success":
        text += "Fatal error after output write\n"
    elif mutation == "no_stable_keys_after_success":
        text += "No stable keys found.\n"
    elif mutation == "not_written_after_success":
        text += "Stable keys were not written.\n"
    else:  # pragma: no cover - closed parametrization
        raise AssertionError(mutation)
    fixture.replace_stage_log("expand", text.encode())
    with pytest.raises(pso.HumanVisualPsoError, match=expected):
        pso.load_receipt_chain(inputs)


def test_arbitrary_baked_pipeline_cache_basename_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = ClosedFixture(tmp_path, monkeypatch)
    inputs = fixture.materialize_artifacts()
    canonical = fixture.attempt / pso.BAKED_CACHE_RELATIVE
    arbitrary = canonical.with_name("invented.stable.upipelinecache")
    canonical.rename(arbitrary)
    receipt = fixture.stage_receipts["final_cook"]
    payload = json.loads(receipt.read_text())
    payload["artifacts"]["baked_pipeline_caches"] = [fixture.record(arbitrary)]
    payload["content_digest"] = pso.content_digest(payload)
    receipt.write_bytes(pso.canonical_json(payload))
    fixture._sidecar(receipt)
    with pytest.raises(pso.HumanVisualPsoError, match="BAKED_CACHE_NAME_INVALID"):
        pso.load_receipt_chain(inputs)


def test_parent_edge_and_exact_argv_drift_are_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = ClosedFixture(tmp_path, monkeypatch)
    inputs = fixture.materialize_artifacts()
    receipt = fixture.stage_receipts["expand"]
    payload = json.loads(receipt.read_text())
    payload["parents"]["seed_cook"]["sha256"] = "0" * 64
    payload["command"]["argv"].append("-unsafe")
    payload["content_digest"] = pso.content_digest(payload)
    receipt.write_bytes(pso.canonical_json(payload))
    fixture._sidecar(receipt)
    with pytest.raises(pso.HumanVisualPsoError, match="RECEIPT_EDGE_INVALID"):
        pso.load_receipt_chain(inputs)


def test_final_stable_cache_input_must_equal_expand_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = ClosedFixture(tmp_path, monkeypatch)
    inputs = fixture.materialize_artifacts()
    stable_input = (
        fixture.attempt
        / package.FINAL_PROJECT_RELATIVE
        / "Build/Linux/PipelineCaches"
        / pso.STABLE_CACHE_NAME
    )
    stable_input.write_bytes(b"different-but-self-consistent-final-input")
    receipt = fixture.stage_receipts["final_cook"]
    payload = json.loads(receipt.read_text())
    payload["artifacts"]["stable_cache_input"] = fixture.record(stable_input)
    payload["content_digest"] = pso.content_digest(payload)
    receipt.write_bytes(pso.canonical_json(payload))
    fixture._sidecar(receipt)
    with pytest.raises(pso.HumanVisualPsoError, match="RECEIPT_EDGE_INVALID"):
        pso.load_receipt_chain(inputs)


def test_descriptor_default_and_plugin_closure_are_mandatory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = ClosedFixture(tmp_path, monkeypatch)
    fixture.materialize_artifacts()
    descriptor = fixture.attempt / package.MATERIALIZED_DESCRIPTOR_RELATIVE
    value = json.loads(descriptor.read_text())
    value["DisableEnginePluginsByDefault"] = False
    descriptor.write_bytes(package.canonical_json(value))
    with pytest.raises(package.HumanVisualPackageError, match="ARTIFACT_PIN_MISMATCH"):
        package.load_final_package_receipt(fixture.final_receipt)


def test_engine_descriptor_graph_drift_is_rederived_and_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = ClosedFixture(tmp_path, monkeypatch)
    fixture.materialize_artifacts()
    sun = fixture.engine / "Engine/Plugins/Fixture/SunPosition/SunPosition.uplugin"
    sun.write_bytes(_plugin_payload([{"Name": "ZoneGraph", "Enabled": True}]))
    with pytest.raises(
        package.HumanVisualPackageError, match="PLUGIN_GRAPH_PIN_MISMATCH"
    ):
        package.load_final_package_receipt(fixture.final_receipt)


def test_tampered_project_plugin_with_regenerated_receipts_cannot_self_anchor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = ClosedFixture(tmp_path, monkeypatch)
    fixture.materialize_artifacts()
    plugin = (
        fixture.attempt
        / package.FINAL_PROJECT_RELATIVE
        / "Plugins/VistaPlayableHome/VistaPlayableHome.uplugin"
    )
    plugin_payload = json.loads(plugin.read_text(encoding="utf-8-sig"))
    plugin_payload["Description"] = "attacker-regenerated-closure"
    plugin.write_text(json.dumps(plugin_payload, sort_keys=True))

    manifest_path = fixture.attempt / package.PROJECTION_MANIFEST_RELATIVE
    manifest = json.loads(manifest_path.read_text())
    projected_pin = {
        "sha256": _sha(plugin),
        "size_bytes": plugin.stat().st_size,
        "mode": plugin.stat().st_mode & 0o7777,
    }
    for entry in manifest["files"]:
        if entry["relative_path"] == (
            "Plugins/VistaPlayableHome/VistaPlayableHome.uplugin"
        ):
            entry["projected"] = projected_pin
            break
    manifest["content_digest"] = package.content_digest(manifest)
    manifest_path.write_bytes(package.canonical_json(manifest))
    fixture._sidecar(manifest_path)

    closure_path = fixture.attempt / package.PLUGIN_CLOSURE_RELATIVE
    closure = json.loads(closure_path.read_text())
    closure["source_projection_manifest"] = fixture.record(manifest_path)
    closure["descriptor_graph"] = dict(
        package.derive_plugin_graph(
            engine_root=fixture.engine,
            project_root=fixture.attempt / package.FINAL_PROJECT_RELATIVE,
            project_descriptor=package.package_project_descriptor(),
        ).evidence
    )
    closure["content_digest"] = package.content_digest(closure)
    closure_path.write_bytes(package.canonical_json(closure))
    fixture._sidecar(closure_path)

    final = json.loads(fixture.final_receipt.read_text())
    final["source_projection_manifest"] = fixture.record(manifest_path)
    final["plugin_closure"] = fixture.record(closure_path)
    final["content_digest"] = package.content_digest(final)
    fixture.final_receipt.write_bytes(package.canonical_json(final))
    fixture._sidecar(fixture.final_receipt)
    with pytest.raises(
        package.HumanVisualPackageError, match="PROJECTION_COPY_MISMATCH"
    ):
        package.load_final_package_receipt(fixture.final_receipt)


def test_tampered_seed_project_with_regenerated_receipts_cannot_self_anchor(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = ClosedFixture(tmp_path, monkeypatch)
    inputs = fixture.materialize_artifacts()
    plugin = (
        fixture.attempt
        / package.SEED_PROJECT_RELATIVE
        / "Plugins/VistaPlayableHome/VistaPlayableHome.uplugin"
    )
    plugin_payload = json.loads(plugin.read_text(encoding="utf-8-sig"))
    plugin_payload["Description"] = "attacker-regenerated-seed-receipt"
    plugin.write_text(json.dumps(plugin_payload, sort_keys=True))

    manifest_path = fixture.attempt / package.SEED_PROJECTION_MANIFEST_RELATIVE
    manifest = json.loads(manifest_path.read_text())
    projected = package.seal_file(plugin, label="attacker seed plugin")
    for entry in manifest["files"]:
        if entry["relative_path"] == (
            "Plugins/VistaPlayableHome/VistaPlayableHome.uplugin"
        ):
            entry["projected"] = package._projection_pin(projected)
            break
    manifest["content_digest"] = package.content_digest(manifest)
    manifest_path.write_bytes(package.canonical_json(manifest))
    fixture._sidecar(manifest_path)

    seed_receipt = fixture.stage_receipts["seed_cook"]
    seed = json.loads(seed_receipt.read_text())
    seed["artifacts"]["source_projection_manifest"] = fixture.record(manifest_path)
    seed["content_digest"] = pso.content_digest(seed)
    seed_receipt.write_bytes(pso.canonical_json(seed))
    fixture._sidecar(seed_receipt)
    with pytest.raises(pso.HumanVisualPsoError, match="SEED_PROJECTION_INVALID"):
        pso.load_stage_receipt(inputs, "seed_cook", {})


@pytest.mark.parametrize("mutation", ["content_drift", "code_addition", "code_symlink"])
def test_human_capture_revalidates_seed_projection_after_seed_acceptance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    fixture = ClosedFixture(tmp_path, monkeypatch)
    inputs = fixture.materialize_artifacts()
    seed = pso.load_stage_receipt(inputs, "seed_cook", {})
    seed_root = fixture.attempt / package.SEED_PROJECT_RELATIVE
    if mutation == "content_drift":
        seed_map = seed_root / "Content/Map.umap"
        seed_map.write_bytes(seed_map.read_bytes() + b"tamper-after-seed-acceptance")
    elif mutation == "code_addition":
        _write(seed_root / "Source/InjectedAfterCook.cpp", b"void injected() {}\n")
    else:
        outside_source = tmp_path / "outside-source"
        _write(outside_source / "InjectedAfterCook.cpp", b"void injected() {}\n")
        (seed_root / "Source").symlink_to(outside_source, target_is_directory=True)
    with pytest.raises(pso.HumanVisualPsoError, match="SEED_PROJECTION_INVALID"):
        pso.load_stage_receipt(inputs, "human_capture", {"seed_cook": seed})


def test_projection_refuses_source_projected_hardlink_alias(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = ClosedFixture(tmp_path, monkeypatch)
    fixture.materialize_artifacts()
    source = (
        fixture.source.project.path.parent
        / "Plugins/VistaPlayableHome/VistaPlayableHome.uplugin"
    )
    projected = (
        fixture.attempt
        / package.FINAL_PROJECT_RELATIVE
        / "Plugins/VistaPlayableHome/VistaPlayableHome.uplugin"
    )
    projected.unlink()
    os.link(source, projected)
    with pytest.raises(
        package.HumanVisualPackageError,
        match=(
            "SEED_PROJECTION_INVALID|PROJECTION_HARDLINK_REFUSED|"
            "PROJECTION_INODE_ALIAS_REFUSED"
        ),
    ):
        package.load_final_package_receipt(fixture.final_receipt)


def test_projection_refuses_projected_file_with_second_hardlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = ClosedFixture(tmp_path, monkeypatch)
    fixture.materialize_artifacts()
    projected = fixture.attempt / package.MATERIALIZED_DESCRIPTOR_RELATIVE
    os.link(projected, fixture.attempt / "final-cook/project-descriptor-alias")
    with pytest.raises(
        package.HumanVisualPackageError, match="PROJECTION_HARDLINK_REFUSED"
    ):
        package.load_final_package_receipt(fixture.final_receipt)


def test_projection_refuses_sealed_source_file_with_second_hardlink(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = ClosedFixture(tmp_path, monkeypatch)
    fixture.materialize_artifacts()
    source = (
        fixture.source.project.path.parent
        / "Plugins/VistaPlayableHome/VistaPlayableHome.uplugin"
    )
    os.link(source, tmp_path / "sealed-source-alias.uplugin")
    with pytest.raises(
        package.HumanVisualPackageError,
        match="SEED_PROJECTION_INVALID|PROJECTION_SOURCE_HARDLINK_REFUSED",
    ):
        package.load_final_package_receipt(fixture.final_receipt)


def test_fd_bound_reread_refuses_same_byte_rename_replacement(tmp_path: Path) -> None:
    path = _write(tmp_path / "sealed.bin", b"same-bytes")
    seal = package.seal_file(path, label="rename-race fixture")
    original = tmp_path / "original.bin"
    path.rename(original)
    _write(path, b"same-bytes")
    with pytest.raises(package.HumanVisualPackageError, match="FILE_CHANGED"):
        package._read_after_seal(seal, label="rename-race fixture", maximum=100)


def test_fd_bound_reread_refuses_same_byte_symlink_replacement(tmp_path: Path) -> None:
    path = _write(tmp_path / "sealed.bin", b"same-bytes")
    seal = package.seal_file(path, label="symlink-race fixture")
    original = tmp_path / "original.bin"
    path.rename(original)
    path.symlink_to(original)
    with pytest.raises(package.HumanVisualPackageError, match="READ_FAILED"):
        package._read_after_seal(seal, label="symlink-race fixture", maximum=100)


def test_self_reported_unknown_plugin_closure_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = ClosedFixture(tmp_path / "unknown", monkeypatch)
    fixture.materialize_artifacts()
    closure = fixture.attempt / package.PLUGIN_CLOSURE_RELATIVE
    value = json.loads(closure.read_text())
    value["descriptor_graph"]["resolved_plugins"].append("ReceiptInventedPlugin")
    value["descriptor_graph"]["resolved_plugins"].sort()
    value["descriptor_graph"]["graph_digest"] = package.content_digest(
        value["descriptor_graph"]
    )
    value["content_digest"] = package.content_digest(value)
    closure.write_bytes(package.canonical_json(value))
    fixture._sidecar(closure)
    # Re-seal all self-reported receipt fields; re-derivation must still refuse it.
    final = json.loads(fixture.final_receipt.read_text())
    final["plugin_closure"] = fixture.record(closure)
    final["content_digest"] = package.content_digest(final)
    fixture.final_receipt.write_bytes(package.canonical_json(final))
    fixture._sidecar(fixture.final_receipt)
    with pytest.raises(
        package.HumanVisualPackageError, match="PLUGIN_GRAPH_PIN_MISMATCH"
    ):
        package.load_final_package_receipt(fixture.final_receipt)


def test_external_stage_path_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = ClosedFixture(tmp_path, monkeypatch)
    fixture.materialize_artifacts()
    outside = _write(tmp_path / "outside.log", b"outside")
    receipt = fixture.stage_receipts["seed_cook"]
    payload = json.loads(receipt.read_text())
    payload["command"]["log"] = {
        "relative_path": str(outside),
        "sha256": _sha(outside),
        "size_bytes": outside.stat().st_size,
        "mode": outside.stat().st_mode & 0o7777,
    }
    payload["content_digest"] = pso.content_digest(payload)
    receipt.write_bytes(pso.canonical_json(payload))
    fixture._sidecar(receipt)
    with pytest.raises(
        (package.HumanVisualPackageError, pso.HumanVisualPsoError),
        match="ARTIFACT_PATH_INVALID",
    ):
        pso.load_receipt_chain(fixture.inputs())


def test_symlinked_fixed_stage_artifact_is_refused(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = ClosedFixture(tmp_path, monkeypatch)
    fixture.materialize_artifacts()
    stable = fixture.attempt / "expand" / pso.STABLE_CACHE_NAME
    outside = _write(tmp_path / "outside.spc", stable.read_bytes())
    stable.unlink()
    stable.symlink_to(outside)
    with pytest.raises(
        (package.HumanVisualPackageError, pso.HumanVisualPsoError),
        match="FIXED_PATH_INVALID|PATH_INVALID|ARTIFACT_PATH_INVALID",
    ):
        pso.load_receipt_chain(fixture.inputs())


def test_final_receipt_must_be_at_fixed_attempt_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = ClosedFixture(tmp_path, monkeypatch)
    fixture.materialize_artifacts()
    with pytest.raises(
        package.HumanVisualPackageError,
        match="RECEIPT_NAME_INVALID|ATTEMPT_PATH_INVALID",
    ):
        package.load_final_package_receipt(tmp_path / package.FINAL_RECEIPT_NAME)
