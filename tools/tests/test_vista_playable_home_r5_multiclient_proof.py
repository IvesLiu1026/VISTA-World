from __future__ import annotations

import base64
import fcntl
import hashlib
import json
import os
import pathlib
import stat
import struct
import subprocess
import sys

import pytest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))

from tools.runtime.vista_playable_home import r5_multiclient_proof as proof


ROOT = pathlib.Path(__file__).resolve().parents[2]


def _canonical(value: object) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode() + b"\n"


def _write(path: pathlib.Path, raw: bytes, mode: int = 0o600) -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    path.chmod(mode)
    return path


class Fixture:
    def __init__(self, root: pathlib.Path, monkeypatch: pytest.MonkeyPatch) -> None:
        self.root = root.resolve()
        self.repo = self.root / "repo"
        self.engine = self.root / "engine"
        self.attempt = self.root / "attempt-r5-proof-0001"
        self.plugin = self.repo / proof.PLUGIN_RELATIVE
        self.project_root = self.repo / proof.TRUSTED_PROJECT_RELATIVE
        self.repo.mkdir()
        self.engine.mkdir()
        self.attempt.mkdir()

        pins: list[proof.ToolPin] = []

        def pin(
            label: str,
            relative: pathlib.Path,
            raw: bytes,
            *,
            executable: bool = False,
        ) -> None:
            path = _write(self.engine / relative, raw, 0o700 if executable else 0o600)
            pins.append(
                proof.ToolPin(
                    label,
                    relative,
                    hashlib.sha256(raw).hexdigest(),
                    path.stat().st_size,
                    executable,
                )
            )

        pin(
            "unreal_editor_cmd",
            pathlib.Path("Engine/Binaries/Linux/UnrealEditor-Cmd"),
            b"#!/bin/sh\nexit 97\n",
            executable=True,
        )
        pin(
            "build_version",
            pathlib.Path("Engine/Build/Build.version"),
            _canonical(
                {
                    "MajorVersion": 5,
                    "MinorVersion": 7,
                    "PatchVersion": 3,
                    "Changelist": 50162420,
                    "CompatibleChangelist": 47537391,
                    "IsLicenseeVersion": 0,
                    "IsPromotedBuild": 1,
                    "BranchName": "++UE5+Release-5.7",
                }
            ),
        )
        self.engine_build_id = "50162420"
        pin(
            "unreal_editor_modules",
            pathlib.Path("Engine/Binaries/Linux/UnrealEditor.modules"),
            _canonical({"BuildId": self.engine_build_id, "Modules": {}}),
        )
        pin(
            "run_ubt",
            pathlib.Path("Engine/Build/BatchFiles/RunUBT.sh"),
            b"#!/bin/sh\nexit 98\n",
            executable=True,
        )
        pin(
            "cqtest_primary_source",
            pathlib.Path(
                "Engine/Source/Developer/CQTest/Private/Components/PIENetworkComponent.cpp"
            ),
            b"primary CQTest source\n",
        )
        pin(
            "cqtest_binary",
            pathlib.Path("Engine/Binaries/Linux/libUnrealEditor-CQTest.so"),
            b"\x7fELFfixture cqtest\n",
        )

        monkeypatch.setattr(proof, "TRUSTED_REPO_ROOT", self.repo)
        monkeypatch.setattr(proof, "TRUSTED_ENGINE_ROOT", self.engine)
        monkeypatch.setattr(proof, "CRITICAL_ENGINE_EXPECTATIONS", tuple(pins))

        self.engine_manifest = self.root / "engine-full-tree-manifest.json"
        real_lstat = os.lstat

        def authority_lstat(path: os.PathLike[str] | str) -> os.stat_result:
            info = real_lstat(path)
            values = list(info)
            if stat.S_ISDIR(info.st_mode):
                values[0] = stat.S_IFDIR | 0o555
            elif stat.S_ISREG(info.st_mode):
                executable = bool(stat.S_IMODE(info.st_mode) & 0o111)
                values[0] = stat.S_IFREG | (0o555 if executable else 0o444)
            values[4] = 0
            values[5] = 0
            return os.stat_result(values)

        monkeypatch.setattr(proof, "TRUSTED_ENGINE_MANIFEST", self.engine_manifest)
        monkeypatch.setattr(proof, "AUTHORITY_LSTAT", authority_lstat)
        monkeypatch.setattr(proof, "AUTHORITY_ACCESS", lambda *args, **kwargs: False)

        engine_entries = []
        for path in proof._engine_inventory(self.engine):
            info = authority_lstat(path)
            is_directory = stat.S_ISDIR(info.st_mode)
            raw = b"" if is_directory else path.read_bytes()
            engine_entries.append(
                {
                    "path": path.relative_to(self.engine).as_posix(),
                    "type": "directory" if is_directory else "file",
                    "mode": stat.S_IMODE(info.st_mode),
                    "uid": info.st_uid,
                    "gid": info.st_gid,
                    "size_bytes": 0 if is_directory else len(raw),
                    "sha256": "" if is_directory else hashlib.sha256(raw).hexdigest(),
                }
            )
        content_entries = [
            {
                "path": entry["path"],
                "type": entry["type"],
                "size_bytes": entry["size_bytes"],
                "sha256": entry["sha256"],
            }
            for entry in engine_entries
        ]
        tree_digest = hashlib.sha256(
            _canonical({"entries": content_entries})
        ).hexdigest()
        engine_document = proof._seal_document(
            {
                "schema": proof.ENGINE_MANIFEST_SCHEMA,
                "engine_root": str(self.engine),
                "entries": engine_entries,
                "tree_root_digest": tree_digest,
            }
        )
        _write(self.engine_manifest, _canonical(engine_document))
        monkeypatch.setattr(
            proof,
            "ENGINE_MANIFEST_SHA256",
            hashlib.sha256(self.engine_manifest.read_bytes()).hexdigest(),
        )
        monkeypatch.setattr(proof, "ENGINE_TREE_ROOT_DIGEST", tree_digest)

        _write(
            self.project_root / "VistaR5Proof.uproject",
            _canonical(
                {
                    "FileVersion": 3,
                    "Plugins": [{"Name": "VistaPlayableHome", "Enabled": True}],
                }
            ),
        )
        _write(self.project_root / "Config/DefaultEngine.ini", b"[Fixture]\n")
        _write(
            self.project_root / "Source/VistaR5Proof/VistaR5Proof.cpp",
            b"fixture project source\n",
        )
        _write(self.plugin / "VistaPlayableHome.uplugin", b'{"FileVersion":3}\n')
        _write(self.plugin / "Config/DefaultEngine.ini", b"[FixturePlugin]\n")
        self.mutable_source = _write(
            self.plugin / "Source/VistaPlayableHome/Private/Fixture.cpp",
            b"trusted fixture source\n",
        )
        _write(
            self.repo / proof.SUPERVISOR_RELATIVE,
            b"trusted supervisor fixture\n",
        )
        _write(self.repo / proof.RUNTIME_WRAPPER_RELATIVE, b"trusted wrapper fixture\n")
        _write(self.repo / proof.ENGINE_ADMIN_RELATIVE, b"trusted admin fixture\n")
        _write(
            self.repo / proof.ENGINE_PROVISION_RELATIVE,
            b"#!/bin/sh\nexit 99\n",
            0o700,
        )

        self.bwrap = _write(self.root / "bwrap", b"fixture bwrap\n", 0o700)
        monkeypatch.setattr(proof, "BWRAP_PATH", self.bwrap)
        monkeypatch.setattr(
            proof,
            "BWRAP_SHA256",
            __import__("hashlib").sha256(self.bwrap.read_bytes()).hexdigest(),
        )
        monkeypatch.setattr(proof, "BWRAP_BYTES", self.bwrap.stat().st_size)

        self.reseal_projection()
        self.git("init", "-q")
        self.git("config", "user.email", "proof@example.invalid")
        self.git("config", "user.name", "R5 proof fixture")
        self.git("add", ".")
        self.git("commit", "-qm", "trusted projection")

    def git(self, *arguments: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["git", "-C", str(self.repo), *arguments],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

    def reseal_projection(self) -> None:
        entries = []
        for relative in proof._expected_bound_source_paths(self.repo):
            raw = (self.repo / relative).read_bytes()
            entries.append(
                {
                    "path": relative.as_posix(),
                    "sha256": hashlib.sha256(raw).hexdigest(),
                    "size_bytes": len(raw),
                }
            )
        document = proof._seal_document(
            {
                "schema": proof.PROJECTION_SCHEMA,
                "source_files": entries,
                "toolchain": proof._expected_toolchain_json(),
            }
        )
        _write(
            self.repo / proof.TRUSTED_PROJECTION_RELATIVE,
            _canonical(document),
        )

    def inputs(self) -> proof.ProofInputs:
        return proof.prepare_inputs(
            attempt_root=self.attempt,
            attempt_id="r5-proof-attempt-0001",
            timeout_seconds=120.0,
        )

    def create_build_outputs(self, plan: proof.ProofPlan) -> None:
        output = proof._output_directories(plan.inputs.output_root)
        _write(
            output["project_binaries"] / "Linux/libUnrealEditor-VistaR5Proof.so",
            b"\x7fELFfixture project module\n",
            0o700,
        )
        _write(
            output["plugin_binaries"] / "Linux/libUnrealEditor-VistaPlayableHome.so",
            b"\x7fELFfixture runtime module\n",
            0o700,
        )
        _write(
            output["plugin_binaries"]
            / "Linux/libUnrealEditor-VistaPlayableHomeEditor.so",
            b"\x7fELFfixture editor module\n",
            0o700,
        )
        _write(
            output["project_binaries"] / "Linux/UnrealEditor.modules",
            _canonical(
                {
                    "BuildId": self.engine_build_id,
                    "Modules": {"VistaR5Proof": "libUnrealEditor-VistaR5Proof.so"},
                }
            ),
        )
        _write(
            output["plugin_binaries"] / "Linux/UnrealEditor.modules",
            _canonical(
                {
                    "BuildId": self.engine_build_id,
                    "Modules": {
                        "VistaPlayableHome": "libUnrealEditor-VistaPlayableHome.so",
                        "VistaPlayableHomeEditor": "libUnrealEditor-VistaPlayableHomeEditor.so",
                    },
                }
            ),
        )


def _bits(value: float) -> str:
    return f"{struct.unpack('=Q', struct.pack('=d', value))[0]:016x}"


def _identity_bits(
    translation: tuple[float, float, float] = (0.0, 0.0, 0.0),
) -> list[str]:
    return [
        *(_bits(value) for value in translation),
        _bits(0.0),
        _bits(0.0),
        _bits(0.0),
        _bits(1.0),
        _bits(1.0),
        _bits(1.0),
        _bits(1.0),
    ]


def _transaction(
    command_id: str,
    *,
    status: str,
    code: str,
    mutations: int,
    attempted: bool,
    committed: bool,
    rollback: bool,
    before: str = "missing",
    contact: str = "missing",
    after: str = "missing",
) -> dict[str, object]:
    return {
        "command_id": command_id,
        "status": status,
        "code": code,
        "physical_mutation_count": mutations,
        "contact_mutation_attempted": attempted,
        "contact_committed": committed,
        "rollback_attempted": rollback,
        "rolled_back": rollback,
        "before_disposition": before,
        "contact_disposition": contact,
        "after_disposition": after,
    }


def _world(checkpoint: str, disposition: str, index: int) -> dict[str, object]:
    held = disposition == "held"
    placed = disposition == "placed"
    dropped = checkpoint == "free_after_drop"
    transform = _identity_bits((120.0, 0.0, 0.0) if placed else (0.0, 0.0, 0.0))
    linear = [_bits(37.0), _bits(-11.0), _bits(23.0)] if dropped else [_bits(0.0)] * 3
    return {
        "checkpoint": checkpoint,
        "role": "server" if index == 0 else "client",
        "client_index": -1 if index == 0 else index - 1,
        "net_mode": "dedicated_server" if index == 0 else "client",
        "net_driver_is_server": index == 0,
        "pickup_has_authority": index == 0,
        "carrier_has_authority": index == 0,
        "disposition": disposition,
        "carrier_semantic_id": proof.CARRIER_A if held else "",
        "inventory_item_semantic_id": proof.PICKUP if held else "",
        "placement_anchor_semantic_id": proof.PLACEMENT_ANCHOR if placed else "",
        "simulate_physics": disposition == "free",
        "collision_enabled": 0 if held else 3,
        "collision_profile": "PhysicsActor",
        "attachment_parent_name": "ProofCarryAnchor" if held else "",
        "attachment_socket": "",
        "world_transform_bits": transform,
        "attachment_relative_transform_bits": _identity_bits(),
        "linear_velocity_bits": linear,
        "angular_velocity_bits": [_bits(0.0)] * 3,
        "actual_simulate_physics": disposition == "free",
        "actual_collision_enabled": 0 if held else 3,
        "actual_collision_profile": "PhysicsActor",
        "actual_world_transform_bits": transform,
        "actual_relative_transform_bits": _identity_bits() if held else transform,
        "actual_linear_velocity_bits": linear,
        "actual_angular_velocity_bits": [_bits(0.0)] * 3,
    }


DEFAULT_EXPECTATION = proof.ReceiptExpectation(
    attempt_id="r5-proof-attempt-0001",
    trusted_git_commit="a" * 40,
    trusted_projection_digest="b" * 64,
    input_manifest_digest="c" * 64,
    launch_plan_digest="d" * 64,
    build_provenance_digest="e" * 64,
)


def valid_receipt(
    expectation: proof.ReceiptExpectation = DEFAULT_EXPECTATION,
) -> dict[str, object]:
    checkpoints = [
        {
            "name": name,
            "worlds": [_world(name, disposition, index) for index in range(3)],
        }
        for name, disposition in zip(
            proof.CHECKPOINT_NAMES, proof.CHECKPOINT_DISPOSITIONS, strict=True
        )
    ]
    pickup = _transaction(
        "r5-pickup-once",
        status="succeeded",
        code="ITEM_PICKED_UP",
        mutations=1,
        attempted=True,
        committed=True,
        rollback=False,
        before="free",
        contact="held",
        after="held",
    )
    return {
        "schema": proof.RECEIPT_SCHEMA,
        "status": "passed",
        "attempt_id": expectation.attempt_id,
        "engine_version": "5.7.3-50162420+++UE5+Release-5.7",
        "harness": proof.HARNESS_NAME,
        "client_count": 2,
        "worlds_per_checkpoint": 3,
        "trusted_git_commit": expectation.trusted_git_commit,
        "trusted_projection_digest": expectation.trusted_projection_digest,
        "input_manifest_digest": expectation.input_manifest_digest,
        "launch_plan_digest": expectation.launch_plan_digest,
        "build_provenance_digest": expectation.build_provenance_digest,
        "checkpoints": checkpoints,
        "transactions": {
            "event_reset_while_active": {
                "claim": "active_action_reset_rejection_only",
                "accepted": False,
                "code": "EVENT_RESET_ACTION_ACTIVE",
                "has_active_action_after_rejection": True,
                "before_event": {
                    "active_event_id": "r5-proof-event",
                    "event_status": "active",
                    "session_generation": 0,
                    "public_goal": "Remain active during proof",
                    "terminal_condition_id": "",
                },
                "after_rejection_event": {
                    "active_event_id": "r5-proof-event",
                    "event_status": "active",
                    "session_generation": 0,
                    "public_goal": "Remain active during proof",
                    "terminal_condition_id": "",
                },
                "active_transaction": _transaction(
                    "r5-event-reset-active",
                    status="canceled",
                    code="R5_PROOF_ACTIVE_RESET_CLEANUP",
                    mutations=0,
                    attempted=False,
                    committed=False,
                    rollback=False,
                    before="free",
                    contact="missing",
                    after="free",
                ),
            },
            "pickup": pickup,
            "exact_retry": dict(pickup),
            "command_id_collision": _transaction(
                "r5-pickup-once",
                status="failed",
                code="COMMAND_ID_COLLISION",
                mutations=0,
                attempted=False,
                committed=False,
                rollback=False,
            ),
            "failed_place_rollback": _transaction(
                "r5-place-forced-failure",
                status="failed",
                code="DEV_AUTOMATION_FORCED_POST_CONTACT_FAILURE",
                mutations=1,
                attempted=True,
                committed=True,
                rollback=True,
                before="held",
                contact="placed",
                after="held",
            ),
            "place": _transaction(
                "r5-place-success",
                status="succeeded",
                code="ITEM_PLACED",
                mutations=1,
                attempted=True,
                committed=True,
                rollback=False,
                before="held",
                contact="placed",
                after="placed",
            ),
            "pickup_again": _transaction(
                "r5-pickup-again",
                status="succeeded",
                code="ITEM_PICKED_UP",
                mutations=1,
                attempted=True,
                committed=True,
                rollback=False,
                before="placed",
                contact="held",
                after="held",
            ),
            "drop": _transaction(
                "r5-drop-success",
                status="succeeded",
                code="ITEM_DROPPED",
                mutations=1,
                attempted=True,
                committed=True,
                rollback=False,
                before="held",
                contact="free",
                after="free",
            ),
        },
    }


def valid_automation_report(*, succeeded: bool = True) -> dict[str, object]:
    return {
        "devices": [],
        "reportCreatedOn": "2026.08.29-00.00.00",
        "succeeded": 1 if succeeded else 0,
        "succeededWithWarnings": 0,
        "failed": 0 if succeeded else 1,
        "notRun": 0,
        "inProcess": 0,
        "totalDuration": 1.0,
        "comparisonExported": False,
        "comparisonExportDirectory": "",
        "tests": [
            {
                "testDisplayName": "R5 proof",
                "fullTestPath": proof.AUTOMATION_TEST,
                "tags": [],
                "state": "Success" if succeeded else "Fail",
                "deviceInstance": [],
                "duration": 1.0,
                "dateTime": "2026.08.29-00.00.00",
                "entries": [],
                "warnings": 0,
                "errors": 0 if succeeded else 1,
                "artifacts": [],
            }
        ],
    }


def _private_runtime_stdout_raw(receipt_raw: bytes, report_raw: bytes) -> bytes:
    envelope = {
        "schema": proof.RUNTIME_ENVELOPE_SCHEMA,
        "automation_test": proof.AUTOMATION_TEST,
        "runtime_exit_code": 0,
        "receipt_base64": base64.b64encode(receipt_raw).decode(),
        "receipt_sha256": hashlib.sha256(receipt_raw).hexdigest(),
        "automation_report_base64": base64.b64encode(report_raw).decode(),
        "automation_report_sha256": hashlib.sha256(report_raw).hexdigest(),
    }
    return (
        proof.RUNTIME_ENVELOPE_MARKER.encode()
        + base64.b64encode(_canonical(envelope))
        + b"\n"
    )


def private_runtime_stdout(
    receipt: dict[str, object], report: dict[str, object]
) -> bytes:
    return _private_runtime_stdout_raw(_canonical(receipt), _canonical(report))


def _mutate_unused_base64_pad_bit(encoded: str) -> str:
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
    padding = len(encoded) - len(encoded.rstrip("="))
    assert padding in (1, 2)
    significant_index = len(encoded) - padding - 1
    value = alphabet.index(encoded[significant_index])
    unused_bits = 2 if padding == 1 else 4
    assert value & ((1 << unused_bits) - 1) == 0
    mutated = (
        encoded[:significant_index]
        + alphabet[value + 1]
        + encoded[significant_index + 1 :]
    )
    assert base64.b64decode(mutated, validate=True) == base64.b64decode(
        encoded, validate=True
    )
    assert mutated != base64.b64encode(base64.b64decode(mutated, validate=True)).decode(
        "ascii"
    )
    return mutated


def _expectation_for_plan(plan: proof.ProofPlan) -> proof.ReceiptExpectation:
    build = json.loads((plan.inputs.output_root / "build-provenance.json").read_text())
    return proof.ReceiptExpectation(
        attempt_id=plan.inputs.attempt_id,
        trusted_git_commit=plan.inputs.git_commit,
        trusted_projection_digest=plan.inputs.projection_digest,
        input_manifest_digest=plan.inputs.input_digest,
        launch_plan_digest=plan.launch_digest,
        build_provenance_digest=build["content_digest"],
    )


def test_dry_run_plan_is_zero_write_private_nullrhi_two_client(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = Fixture(tmp_path, monkeypatch)
    before = sorted(path.relative_to(fixture.root) for path in fixture.root.rglob("*"))
    inputs = fixture.inputs()
    plan = proof.build_plan(inputs)
    after = sorted(path.relative_to(fixture.root) for path in fixture.root.rglob("*"))

    assert before == after
    assert not inputs.output_root.exists()
    payload = plan.as_json()
    assert payload["mode"] == "pinned_ubt_then_runtime"
    assert payload["pie"] == {
        "server": "dedicated_server",
        "clients": 2,
        "run_under_one_process": True,
        "real_replication_worlds": 3,
    }
    for command in (list(plan.build_command), list(plan.runtime_command_template)):
        assert command.count("--unshare-all") == 1
        assert "--ro-bind-data" in command
        assert str(fixture.repo) not in command
        assert not any("/dev/dri" in token for token in command)
        assert not any(
            command[index : index + 3] == ["--ro-bind", "/", "/"]
            for index in range(len(command) - 2)
        )
        for index, token in enumerate(command[:-1]):
            if token == "--bind":
                assert pathlib.Path(command[index + 1]).is_relative_to(
                    inputs.output_root
                )
    assert "-nullrhi" in plan.runtime_command_template
    assert any(
        proof.AUTOMATION_TEST in token for token in plan.runtime_command_template
    )
    assert payload["sandbox"]["host_root_is_not_bound"] is True
    assert payload["sandbox"]["runtime_receipt_and_report_use_private_tmpfs"] is True
    assert "/vista-private" in plan.runtime_command_template
    assert "/vista-runtime-capture.py" in plan.runtime_command_template
    assert payload["success_authority"]["log_substring_is_proof"] is False


def test_execute_accepts_only_cross_bound_closed_receipt_not_log_substrings(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = Fixture(tmp_path, monkeypatch)
    plan = proof.build_plan(fixture.inputs())

    def fake_build(
        command: tuple[str, ...],
        log_path: pathlib.Path,
        timeout: float,
        *,
        pass_fds: tuple[int, ...],
    ) -> int:
        del command, timeout
        assert pass_fds
        assert all(
            fcntl.fcntl(fd, fcntl.F_GET_SEALS) & fcntl.F_SEAL_WRITE for fd in pass_fds
        )
        _write(log_path, b"build completed\n")
        fixture.create_build_outputs(plan)
        return 0

    def fake_runtime(
        command: tuple[str, ...],
        log_path: pathlib.Path,
        timeout: float,
        *,
        pass_fds: tuple[int, ...],
    ) -> tuple[int, bytes]:
        del command, timeout, pass_fds
        _write(log_path, b"ERROR TEST FAILED -- log text is deliberately not proof\n")
        return 0, private_runtime_stdout(
            valid_receipt(_expectation_for_plan(plan)), valid_automation_report()
        )

    monkeypatch.setattr(proof, "_run_logged", fake_build)
    monkeypatch.setattr(proof, "_run_runtime_captured", fake_runtime)
    receipt = proof.execute_plan(plan)
    assert receipt["status"] == "passed"
    assert "TEST FAILED" in (plan.inputs.output_root / "runtime.log").read_text()
    assert (
        receipt["input_manifest_digest"]
        == json.loads((plan.inputs.output_root / "input-manifest.json").read_text())[
            "content_digest"
        ]
    )


def test_execute_rejects_log_substring_without_closed_receipt(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = Fixture(tmp_path, monkeypatch)
    plan = proof.build_plan(fixture.inputs())

    def fake_build(
        command: tuple[str, ...],
        log_path: pathlib.Path,
        timeout: float,
        *,
        pass_fds: tuple[int, ...],
    ) -> int:
        del command, timeout, pass_fds
        _write(log_path, b"build completed\n")
        fixture.create_build_outputs(plan)
        return 0

    def fake_runtime(
        command: tuple[str, ...],
        log_path: pathlib.Path,
        timeout: float,
        *,
        pass_fds: tuple[int, ...],
    ) -> tuple[int, bytes]:
        del command, timeout, pass_fds
        _write(log_path, b"TEST PASSED\n")
        return 0, b"TEST PASSED\n"

    monkeypatch.setattr(proof, "_run_logged", fake_build)
    monkeypatch.setattr(proof, "_run_runtime_captured", fake_runtime)
    with pytest.raises(proof.ProofError, match="exactly one sealed marker"):
        proof.execute_plan(plan)


def test_fake_caller_runtime_is_rejected_by_fixed_engine_pin(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = Fixture(tmp_path, monkeypatch)
    fake_editor = fixture.engine / "Engine/Binaries/Linux/UnrealEditor-Cmd"
    fake_editor.write_bytes(b"#!/bin/sh\nprintf fabricated-receipt\n")
    with pytest.raises(proof.ProofError, match="engine manifest metadata differs"):
        fixture.inputs()


def test_default_engine_authority_is_explicitly_unprovisioned() -> None:
    with pytest.raises(
        proof.ProofError,
        match="IMMUTABLE_ENGINE_AUTHORITY_REQUIRED:.*not provisioned",
    ):
        proof._validate_engine_authority()


def test_engine_authority_rejects_world_writable_root(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = Fixture(tmp_path, monkeypatch)
    trusted_lstat = proof.AUTHORITY_LSTAT

    def world_writable_root(path: os.PathLike[str] | str) -> os.stat_result:
        info = trusted_lstat(path)
        if pathlib.Path(path) == fixture.engine:
            values = list(info)
            values[0] = stat.S_IFDIR | 0o777
            return os.stat_result(values)
        return info

    monkeypatch.setattr(proof, "AUTHORITY_LSTAT", world_writable_root)
    with pytest.raises(
        proof.ProofError,
        match="IMMUTABLE_ENGINE_AUTHORITY_REQUIRED:.*group/world writable",
    ):
        proof._validate_engine_authority()


def test_resealed_mutable_source_cannot_replace_git_trusted_projection(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = Fixture(tmp_path, monkeypatch)
    fixture.mutable_source.write_bytes(b"fabricated proof source\n")
    fixture.reseal_projection()
    with pytest.raises(
        proof.ProofError, match="projection manifest differs from its HEAD blob"
    ):
        fixture.inputs()


def test_execute_rejects_source_toctou_after_controlled_build(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = Fixture(tmp_path, monkeypatch)
    plan = proof.build_plan(fixture.inputs())
    calls = 0

    def fake_run(
        command: tuple[str, ...],
        log_path: pathlib.Path,
        timeout: float,
        *,
        pass_fds: tuple[int, ...],
    ) -> int:
        nonlocal calls
        del command, timeout, pass_fds
        calls += 1
        _write(log_path, b"build completed\n")
        fixture.create_build_outputs(plan)
        fixture.mutable_source.write_bytes(b"changed during controlled build\n")
        return 0

    monkeypatch.setattr(proof, "_run_logged", fake_run)
    with pytest.raises(proof.ProofError, match="trusted source.*differs"):
        proof.execute_plan(plan)
    assert calls == 1


def test_execute_rejects_controlled_binary_toctou_after_runtime(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = Fixture(tmp_path, monkeypatch)
    plan = proof.build_plan(fixture.inputs())

    def fake_build(
        command: tuple[str, ...],
        log_path: pathlib.Path,
        timeout: float,
        *,
        pass_fds: tuple[int, ...],
    ) -> int:
        del command, timeout, pass_fds
        _write(log_path, b"build completed\n")
        fixture.create_build_outputs(plan)
        return 0

    def fake_runtime(
        command: tuple[str, ...],
        log_path: pathlib.Path,
        timeout: float,
        *,
        pass_fds: tuple[int, ...],
    ) -> tuple[int, bytes]:
        del command, timeout, pass_fds
        _write(log_path, b"runtime completed\n")
        binary = (
            proof._output_directories(plan.inputs.output_root)["plugin_binaries"]
            / "Linux/libUnrealEditor-VistaPlayableHomeEditor.so"
        )
        binary.write_bytes(binary.read_bytes() + b"runtime tamper\n")
        return 0, private_runtime_stdout(
            valid_receipt(_expectation_for_plan(plan)), valid_automation_report()
        )

    monkeypatch.setattr(proof, "_run_logged", fake_build)
    monkeypatch.setattr(proof, "_run_runtime_captured", fake_runtime)
    with pytest.raises(
        proof.ProofError,
        match="controlled UBT outputs changed after provenance closure",
    ):
        proof.execute_plan(plan)


@pytest.mark.parametrize("kind", ["missing", "duplicate", "malformed"])
def test_private_runtime_stdout_requires_one_canonical_marker(kind: str) -> None:
    valid = private_runtime_stdout(valid_receipt(), valid_automation_report())
    if kind == "missing":
        raw = b"TEST PASSED\n"
    elif kind == "duplicate":
        raw = valid + valid
    else:
        raw = proof.RUNTIME_ENVELOPE_MARKER.encode() + b"%%%not-base64%%%\n"
    with pytest.raises(proof.ProofError):
        proof.parse_private_runtime_envelope(raw)


@pytest.mark.parametrize("field", ["outer", "receipt", "report"])
def test_private_runtime_stdout_rejects_unused_base64_pad_bits(field: str) -> None:
    receipt_raw = b"{}"
    report_raw = b"{}"
    stdout = _private_runtime_stdout_raw(receipt_raw, report_raw)
    prefix = proof.RUNTIME_ENVELOPE_MARKER.encode()
    outer_encoded = stdout[len(prefix) : -1].decode("ascii")

    if field == "outer":
        for suffix_size in range(16):
            stdout = _private_runtime_stdout_raw(
                receipt_raw + b"x" * suffix_size, report_raw
            )
            outer_encoded = stdout[len(prefix) : -1].decode("ascii")
            if outer_encoded.endswith("="):
                break
        else:  # pragma: no cover - bounded construction invariant
            raise AssertionError("could not construct padded outer envelope")
        mutated_stdout = (
            prefix
            + _mutate_unused_base64_pad_bit(outer_encoded).encode("ascii")
            + b"\n"
        )
    else:
        envelope = json.loads(base64.b64decode(outer_encoded, validate=True))
        key = "receipt_base64" if field == "receipt" else "automation_report_base64"
        assert envelope[key].endswith("=")
        envelope[key] = _mutate_unused_base64_pad_bit(envelope[key])
        mutated_stdout = prefix + base64.b64encode(_canonical(envelope)) + b"\n"

    with pytest.raises(proof.ProofError, match="not canonical base64"):
        proof.parse_private_runtime_envelope(mutated_stdout)


def test_zero_exit_failed_report_rejects_perfect_host_filesystem_receipt(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = Fixture(tmp_path, monkeypatch)
    plan = proof.build_plan(fixture.inputs())

    def fake_build(
        command: tuple[str, ...],
        log_path: pathlib.Path,
        timeout: float,
        *,
        pass_fds: tuple[int, ...],
    ) -> int:
        del command, timeout, pass_fds
        _write(log_path, b"build completed\n")
        fixture.create_build_outputs(plan)
        return 0

    def fake_runtime(
        command: tuple[str, ...],
        log_path: pathlib.Path,
        timeout: float,
        *,
        pass_fds: tuple[int, ...],
    ) -> tuple[int, bytes]:
        del command, timeout, pass_fds
        _write(log_path, b"runtime returned zero\n")
        receipt = valid_receipt(_expectation_for_plan(plan))
        forged_host_receipt = (
            proof._output_directories(plan.inputs.output_root)["evidence"]
            / "r5-multiclient-proof-receipt.json"
        )
        _write(forged_host_receipt, _canonical(receipt))
        return 0, private_runtime_stdout(
            receipt, valid_automation_report(succeeded=False)
        )

    monkeypatch.setattr(proof, "_run_logged", fake_build)
    monkeypatch.setattr(proof, "_run_runtime_captured", fake_runtime)
    with pytest.raises(proof.ProofError, match="Automation report .* differs"):
        proof.execute_plan(plan)


@pytest.mark.parametrize(
    "field",
    [
        "trusted_git_commit",
        "trusted_projection_digest",
        "input_manifest_digest",
        "launch_plan_digest",
        "build_provenance_digest",
    ],
)
def test_resealed_receipt_cannot_change_launch_or_input_provenance(
    tmp_path: pathlib.Path, field: str
) -> None:
    path = tmp_path / "receipt.json"
    payload = valid_receipt()
    payload[field] = ("f" * 40) if field == "trusted_git_commit" else ("f" * 64)
    path.write_bytes(_canonical(payload))
    with pytest.raises(proof.ProofError, match=rf"closed receipt {field} differs"):
        proof.validate_closed_receipt_bytes(path.read_bytes(), DEFAULT_EXPECTATION)


def test_closed_receipt_rejects_extra_key_and_missing_second_client(
    tmp_path: pathlib.Path,
) -> None:
    path = tmp_path / "receipt.json"
    payload = valid_receipt()
    payload["unexpected"] = True
    path.write_bytes(_canonical(payload))
    with pytest.raises(proof.ProofError, match="keys differ"):
        proof.validate_closed_receipt_bytes(path.read_bytes(), DEFAULT_EXPECTATION)

    payload = valid_receipt()
    payload["checkpoints"][1]["worlds"].pop()
    path.write_bytes(_canonical(payload))
    with pytest.raises(proof.ProofError, match="server and two clients"):
        proof.validate_closed_receipt_bytes(path.read_bytes(), DEFAULT_EXPECTATION)


def test_closed_receipt_rejects_stale_attempt_and_velocity_drift(
    tmp_path: pathlib.Path,
) -> None:
    path = tmp_path / "receipt.json"
    payload = valid_receipt()
    payload["attempt_id"] = "different-attempt-0001"
    path.write_bytes(_canonical(payload))
    with pytest.raises(proof.ProofError, match="attempt_id differs"):
        proof.validate_closed_receipt_bytes(path.read_bytes(), DEFAULT_EXPECTATION)

    payload = valid_receipt()
    payload["checkpoints"][-1]["worlds"][1]["linear_velocity_bits"][0] = _bits(
        37.0000000001
    )
    path.write_bytes(_canonical(payload))
    with pytest.raises(proof.ProofError, match="release velocity bits differ"):
        proof.validate_closed_receipt_bytes(path.read_bytes(), DEFAULT_EXPECTATION)


def test_closed_receipt_rejects_typed_authority_attachment_and_transaction_drift(
    tmp_path: pathlib.Path,
) -> None:
    path = tmp_path / "receipt.json"
    payload = valid_receipt()
    payload["checkpoints"][0]["worlds"][0]["pickup_has_authority"] = 1
    path.write_bytes(_canonical(payload))
    with pytest.raises(proof.ProofError, match="must be bool"):
        proof.validate_closed_receipt_bytes(path.read_bytes(), DEFAULT_EXPECTATION)

    payload = valid_receipt()
    payload["checkpoints"][1]["worlds"][1]["attachment_parent_name"] = (
        "WrongCarryAnchor"
    )
    path.write_bytes(_canonical(payload))
    with pytest.raises(proof.ProofError, match="attachment parent differs"):
        proof.validate_closed_receipt_bytes(path.read_bytes(), DEFAULT_EXPECTATION)

    payload = valid_receipt()
    payload["checkpoints"][1]["worlds"][1]["world_transform_bits"][0] = _bits(
        0.0000000001
    )
    path.write_bytes(_canonical(payload))
    with pytest.raises(proof.ProofError, match="payload differs"):
        proof.validate_closed_receipt_bytes(path.read_bytes(), DEFAULT_EXPECTATION)

    payload = valid_receipt()
    payload["checkpoints"][3]["worlds"][2]["actual_collision_profile"] = "NoCollision"
    path.write_bytes(_canonical(payload))
    with pytest.raises(proof.ProofError, match="live collision profile differs"):
        proof.validate_closed_receipt_bytes(path.read_bytes(), DEFAULT_EXPECTATION)

    payload = valid_receipt()
    payload["checkpoints"][-1]["worlds"][2]["actual_world_transform_bits"][0] = _bits(
        float("nan")
    )
    path.write_bytes(_canonical(payload))
    with pytest.raises(proof.ProofError, match="non-finite physical scalar"):
        proof.validate_closed_receipt_bytes(path.read_bytes(), DEFAULT_EXPECTATION)

    payload = valid_receipt()
    payload["transactions"]["drop"]["code"] = "ITEM_PLACED"
    path.write_bytes(_canonical(payload))
    with pytest.raises(proof.ProofError, match=r"transactions\.drop\.code differs"):
        proof.validate_closed_receipt_bytes(path.read_bytes(), DEFAULT_EXPECTATION)

    payload = valid_receipt()
    payload["transactions"]["event_reset_while_active"]["active_transaction"][
        "before_disposition"
    ] = "missing"
    path.write_bytes(_canonical(payload))
    with pytest.raises(
        proof.ProofError,
        match=r"event_reset_while_active\.active_transaction\.before_disposition",
    ):
        proof.validate_closed_receipt_bytes(path.read_bytes(), DEFAULT_EXPECTATION)

    payload = valid_receipt()
    payload["transactions"]["event_reset_while_active"]["after_rejection_event"][
        "session_generation"
    ] = 1
    path.write_bytes(_canonical(payload))
    with pytest.raises(
        proof.ProofError,
        match=r"after_rejection_event\.session_generation differs",
    ):
        proof.validate_closed_receipt_bytes(path.read_bytes(), DEFAULT_EXPECTATION)

    payload = valid_receipt()
    payload["transactions"]["event_reset_while_active"][
        "has_active_action_after_rejection"
    ] = False
    path.write_bytes(_canonical(payload))
    with pytest.raises(
        proof.ProofError, match="active Event reset did not fail closed"
    ):
        proof.validate_closed_receipt_bytes(path.read_bytes(), DEFAULT_EXPECTATION)


def test_prepare_rejects_existing_proof_output(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = Fixture(tmp_path, monkeypatch)
    (fixture.attempt / "proof-output").mkdir()
    with pytest.raises(proof.ProofError, match="fresh empty output directory"):
        fixture.inputs()


def test_source_keeps_license_gate_shipping_closed_and_test_bypass_guarded() -> None:
    header = (
        ROOT
        / "unreal_plugins/VistaPlayableHome/Source/VistaPlayableHome/Public/VistaActionExecutorComponent.h"
    ).read_text()
    source = (
        ROOT
        / "unreal_plugins/VistaPlayableHome/Source/VistaPlayableHome/Private/VistaActionExecutorComponent.cpp"
    ).read_text()
    animation = (
        ROOT
        / "unreal_plugins/VistaPlayableHome/Source/VistaPlayableHome/Private/VistaAnimationComponent.cpp"
    ).read_text()

    guarded = header.index("#if WITH_DEV_AUTOMATION_TESTS")
    begin_test = header.index("BeginPhysicalInteractionForDevAutomation")
    drive_test = header.index("DrivePhysicalInteractionForDevAutomation")
    guard_end = header.index("#endif", guarded)
    assert guarded < begin_test < drive_test < guard_end
    assert (
        "return BeginPhysicalInteractionImpl(InputRequest, OutRecord, false);" in source
    )
    assert (
        "return BeginPhysicalInteractionImpl(InputRequest, OutRecord, true);" in source
    )
    assert source.index("#if WITH_DEV_AUTOMATION_TESTS") < source.index(
        "BeginPhysicalInteractionForDevAutomation"
    )
    assert "HasApprovedMutationAnimation(" in source
    readiness = source.index("bool bAnimationReady =")
    bypass_guard = source.index("#if WITH_DEV_AUTOMATION_TESTS", readiness)
    bypass = source.index("bAnimationReady = bAnimationReady ||", bypass_guard)
    bypass_guard_end = source.index("#else", bypass)
    assert readiness < bypass_guard < bypass < bypass_guard_end
    assert (
        "static_cast<void>(bDevAutomationBypassesAnimationReadiness);"
        in source[bypass_guard_end : source.index("#endif", bypass_guard_end)]
    )
    assert 'OutCode = TEXT("ANIMATION_SOURCE_LICENSE_UNAPPROVED")' in animation
    assert "Type == EVistaNpcActionType::PickUp" in animation
    assert "Type == EVistaNpcActionType::Place" in animation


def test_source_is_real_dedicated_server_two_client_replication_proof() -> None:
    source = (
        ROOT
        / "unreal_plugins/VistaPlayableHome/Source/VistaPlayableHomeEditor/Private/Tests/VistaR5MultiClientProof.cpp"
    ).read_text()
    build = (
        ROOT
        / "unreal_plugins/VistaPlayableHome/Source/VistaPlayableHomeEditor/VistaPlayableHomeEditor.Build.cs"
    ).read_text()
    supervisor = (
        ROOT / "tools/runtime/vista_playable_home/r5_multiclient_proof.py"
    ).read_text()

    for atom in (
        "WithClients(2)",
        ".AsDedicatedServer()",
        "NM_DedicatedServer",
        "NM_Client",
        "GetNetDriver()->IsServer()",
        "Pickup->HasAuthority()",
        "EVENT_RESET_ACTION_ACTIVE",
        "SnapshotBitsEqual(",
        "COMMAND_ID_COLLISION",
        "GetReplicatedDispositionForDevAutomation",
        "actual_world_transform_bits",
        "actual_linear_velocity_bits",
        "GetCollisionProfileName()",
        "VistaR5ProofGitCommit",
        "VistaR5ProofProjectionDigest",
        "VistaR5ProofInputDigest",
        "VistaR5ProofLaunchDigest",
        "VistaR5ProofBuildDigest",
        "/vista-private/r5-multiclient-proof-receipt.json",
        "active_action_reset_rejection_only",
        "has_active_action_after_rejection",
        "before_event",
        "after_rejection_event",
        "WriteClosedReceipt()",
    ):
        assert atom in source
    assert '"CQTest"' in build
    assert '"Slate"' in build
    assert '"VistaPlayableHome"' in build
    assert '"UnrealEd"' in build
    assert "SetupIrisSupport(Target);" in build
    assert '"--unshare-all"' in supervisor
    assert '"-nullrhi"' in supervisor
    assert '"--ro-bind-data"' in supervisor
    assert "_load_trusted_projection" in supervisor
    assert "_immutable_input_snapshot" in supervisor
    assert "_capture_build_provenance" in supervisor
    assert "validate_closed_receipt_bytes(" in supervisor
    assert "parse_private_runtime_envelope(" in supervisor
    assert "validate_automation_report_bytes(" in supervisor
    assert '"--sync-fd"' not in supervisor
    assert '"--ro-bind",\n        "/",\n        "/"' not in supervisor
    assert "process_log.read_text" not in supervisor
    assert "log substring" not in supervisor.lower().split("success requires", 1)[-1]


def test_cli_does_not_accept_caller_selected_engine_project_or_binary() -> None:
    parser = proof._parser()
    destinations = {action.dest for action in parser._actions}
    assert "attempt_root" in destinations
    assert "attempt_id" in destinations
    assert "engine_root" not in destinations
    assert "project" not in destinations
    assert "binary" not in destinations


def test_root_provisioner_is_fixed_atomic_and_syntax_valid() -> None:
    script = (
        ROOT
        / "tools/runtime/vista_playable_home/provision_immutable_engine_authority.sh"
    )
    source = script.read_text()
    completed = subprocess.run(
        ["bash", "-n", str(script)],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr
    for atom in (
        "SOURCE=/mnt/NAS2/yhliu/UE_5.7.3_prebuilt",
        "FINAL_AUTHORITY=/data/vista-authorities/ue-5.7.3-r1",
        "INSTALL_ROOT=/root/vista-r5-engine-authority-r1",
        "INSTALLED_SCRIPT=/root/vista-r5-engine-authority-r1/provision_immutable_engine_authority.sh",
        "MANIFEST_HELPER=/root/vista-r5-engine-authority-r1/r5_engine_authority_admin.py",
        "EXPECTED_HELPER_SHA256=",
        "verify_root_chain_directory",
        "verify_installed_file",
        "/usr/bin/sha256sum -c -",
        "compare-content",
        "chown -R root:root",
        "chmod 0555",
        "chmod 0444",
        "mv -T",
        "Refusing to replace",
        "refuses symlink escape",
    ):
        assert atom in source
    assert "sudo " not in source


def test_root_provisioner_refuses_user_owned_checkout_execution() -> None:
    script = (
        ROOT
        / "tools/runtime/vista_playable_home/provision_immutable_engine_authority.sh"
    )
    completed = subprocess.run(
        [str(script)],
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert completed.returncode == 2
    assert "worktree execution is forbidden" in completed.stderr


def test_root_provisioner_pins_helper_and_rejects_helper_drift(
    tmp_path: pathlib.Path,
) -> None:
    script = (
        ROOT
        / "tools/runtime/vista_playable_home/provision_immutable_engine_authority.sh"
    )
    helper = ROOT / "tools/runtime/vista_playable_home/r5_engine_authority_admin.py"
    source = script.read_text()
    expected_line = next(
        line
        for line in source.splitlines()
        if line.startswith("EXPECTED_HELPER_SHA256=")
    )
    expected = expected_line.partition("=")[2]
    assert expected == hashlib.sha256(helper.read_bytes()).hexdigest()

    drifted = _write(tmp_path / "r5_engine_authority_admin.py", helper.read_bytes())
    drifted.write_bytes(drifted.read_bytes() + b"# drift\n")
    completed = subprocess.run(
        ["/usr/bin/sha256sum", "-c", "-"],
        input=f"{expected}  {drifted}\n",
        check=False,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    assert completed.returncode != 0
    assert "FAILED" in completed.stdout


def test_runbook_independently_pins_checkout_and_installed_bootstrap() -> None:
    script = (
        ROOT
        / "tools/runtime/vista_playable_home/provision_immutable_engine_authority.sh"
    )
    helper = ROOT / "tools/runtime/vista_playable_home/r5_engine_authority_admin.py"
    runbook = (ROOT / "docs/runbooks/vista-r5-multiclient-proof-r1.md").read_text()
    script_digest = hashlib.sha256(script.read_bytes()).hexdigest()
    helper_digest = hashlib.sha256(helper.read_bytes()).hexdigest()
    assert runbook.count(f"EXPECTED_SCRIPT={script_digest}") == 2
    assert runbook.count(f"EXPECTED_HELPER={helper_digest}") == 2
    assert runbook.count("sha256sum -c -") >= 4
    assert "sudo chmod 0555 /root/vista-r5-engine-authority-r1" in runbook
    assert 'sudo "$INSTALLED_SCRIPT"' in runbook
    assert 'sudo "$CHECKOUT_SCRIPT"' not in runbook


def test_admin_manifest_content_root_detects_source_drift(
    tmp_path: pathlib.Path,
) -> None:
    from tools.runtime.vista_playable_home import r5_engine_authority_admin as admin

    root = tmp_path / "engine"
    file_path = _write(root / "Engine/Binaries/Linux/fixture", b"first\n")
    first = admin.build_manifest(root, pathlib.Path("/fixed/engine"))
    file_path.write_bytes(b"second\n")
    second = admin.build_manifest(root, pathlib.Path("/fixed/engine"))
    assert first["tree_root_digest"] != second["tree_root_digest"]


def test_checked_in_projection_exactly_seals_current_trusted_source_inputs() -> None:
    manifest_path = ROOT / proof.TRUSTED_PROJECTION_RELATIVE
    manifest = json.loads(manifest_path.read_text())
    proof._validate_sealed_document(
        manifest, proof.PROJECTION_SCHEMA, "repository projection"
    )
    assert manifest["toolchain"] == proof._expected_toolchain_json()
    expected_paths = [
        relative.as_posix() for relative in proof._expected_bound_source_paths(ROOT)
    ]
    assert [entry["path"] for entry in manifest["source_files"]] == expected_paths
    for entry in manifest["source_files"]:
        raw = (ROOT / entry["path"]).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == entry["sha256"]
        assert len(raw) == entry["size_bytes"]


def test_editor_visible_proof_components_have_explicit_uht_categories() -> None:
    header = (
        ROOT / "unreal_plugins/VistaPlayableHome/Source/VistaPlayableHomeEditor/"
        "Public/Tests/VistaR5MultiClientProofActors.h"
    ).read_text()
    assert header.count('UPROPERTY(VisibleAnywhere, Category = "VISTA|R5 Proof")') == 3
    assert "UPROPERTY(VisibleAnywhere)" not in header
