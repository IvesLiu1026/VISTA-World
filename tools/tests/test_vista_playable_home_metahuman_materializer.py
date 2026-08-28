from __future__ import annotations

import ast
import contextlib
import hashlib
import json
import os
import pathlib
import signal
import stat
import subprocess
from unittest import mock

import pytest

from tools.ue.vista_playable_home import materialize_metahuman_provider as materializer


REPOSITORY_ROOT = pathlib.Path(__file__).resolve().parents[2]


def _write(path: pathlib.Path, raw: bytes, mode: int = 0o600) -> pathlib.Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    path.chmod(mode)
    return path


class Fixture:
    def __init__(self, root: pathlib.Path) -> None:
        self.root = root.resolve()
        self.engine = self.root / "UE_5.7.3_prebuilt"
        self.run_root = self.root / "external-runs"
        self.run_root.mkdir()
        self.editor = _write(
            self.engine.joinpath(*materializer.EDITOR_RELATIVE.parts),
            b"#!/bin/sh\nexit 97\n",
            0o700,
        )
        _write(
            self.engine.joinpath(*materializer.BUILD_VERSION_RELATIVE.parts),
            b'{"fixture":"build"}\n',
        )
        _write(
            self.engine.joinpath(*materializer.PLUGIN_DESCRIPTOR_RELATIVE.parts),
            b'{"fixture":"plugin"}\n',
        )
        _write(
            self.engine.joinpath(*materializer.PRESET_RELATIVE.parts),
            b"fixture Vivian uasset",
        )
        _write(
            self.engine.joinpath(*materializer.PIPELINE_RELATIVE.parts),
            b"fixture Legacy High pipeline uasset",
        )

    def config(self, attempt_name: str = "attempt-vivian-test") -> materializer.MaterializationConfig:
        return materializer.MaterializationConfig(
            engine_root=self.engine,
            run_root=self.run_root,
            attempt_name=attempt_name,
        )

    def _fixture_sealer(self, path, **kwargs):
        candidate = pathlib.Path(path)
        try:
            candidate.relative_to(self.engine)
        except ValueError:
            return self.original_sealer(path, **kwargs)
        relaxed = dict(kwargs)
        relaxed.pop("expected_sha256", None)
        relaxed.pop("expected_size", None)
        return self.original_sealer(path, **relaxed)

    @contextlib.contextmanager
    def patched_inventory(self):
        self.original_sealer = materializer._seal_regular_file
        with (
            mock.patch.object(
                materializer.provider_contract,
                "build_inventory_report",
                return_value={"inventory_verified": True},
            ) as inventory,
            mock.patch.object(
                materializer,
                "_seal_regular_file",
                side_effect=self._fixture_sealer,
            ),
        ):
            yield inventory


def _success_result(plan: materializer.MaterializationPlan) -> dict:
    inventory = []
    for index in range(8):
        package = f"{materializer.ASSEMBLY_ROOT}/Vivian_VISTA/Asset{index}"
        inventory.append(
            {
                "class_path": "/Script/Engine.SkeletalMesh",
                "object_path": f"{package}.Asset{index}",
                "package_name": package,
            }
        )
    return {
        "schema_version": materializer.RESULT_SCHEMA,
        "provider_id": materializer.PROVIDER_ID,
        "provider_spec_content_digest": plan.provider["content_digest"],
        "accepted": False,
        "status": "assembled_candidate_requires_package_validation",
        "authoring_succeeded": True,
        "assembly_completed": True,
        "assembled_component_digests_complete": False,
        "entitlement_receipt_complete": False,
        "engine_version": materializer.PINNED_ENGINE_VERSION,
        "provider_spec_sha256": plan.provider_seal.sha256,
        "plugin_descriptor_sha256": materializer.PINNED_PLUGIN_DESCRIPTOR_SHA256,
        "preset_sha256": materializer.PINNED_PRESET_SHA256,
        "pipeline_sha256": materializer.PINNED_PIPELINE_SHA256,
        "source_object_path": materializer.SOURCE_OBJECT_PATH,
        "assembly_pipeline": "optimized",
        "assembly_quality": "high",
        "pipeline_object_path": materializer.PIPELINE_OBJECT_PATH,
        "rig_type": "joints_and_blend_shapes",
        "has_high_resolution_textures": True,
        "expected_blueprint": materializer.EXPECTED_BLUEPRINT,
        "expected_blueprint_class": materializer.EXPECTED_BLUEPRINT_CLASS,
        "asset_inventory": inventory,
        "account_tokens_recorded": False,
        "package_validation_complete": False,
        "runtime_visual_acceptance_complete": False,
    }


def _exclusive_result(environment: dict[str, str], result: dict) -> None:
    path = pathlib.Path(environment[materializer.RESULT_ENV])
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        sealed = dict(result)
        sealed["content_digest"] = materializer._content_digest(sealed)
        raw = materializer.canonical_json(sealed, newline=True)
        os.write(descriptor, raw)
    finally:
        os.close(descriptor)


class _ImmediateProcess:
    def __init__(self, return_code: int) -> None:
        self.pid = 999_999_937
        self.returncode = return_code

    def poll(self) -> int:
        return self.returncode

    def wait(self, timeout=None) -> int:
        return self.returncode


def _popen_factory(
    *,
    observed: dict[str, object],
    result: dict,
    return_code: int,
):
    def fake_popen(command, **kwargs):
        observed["command"] = command
        observed["kwargs"] = kwargs
        _exclusive_result(kwargs["env"], result)
        return _ImmediateProcess(return_code)

    return fake_popen


def test_dry_run_is_zero_write_fixed_and_non_promoting(tmp_path: pathlib.Path) -> None:
    fixture = Fixture(tmp_path)
    config = fixture.config()
    before = sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*"))

    with fixture.patched_inventory() as inventory:
        first = materializer.plan_materialization(config)
        second = materializer.plan_materialization(config)

    assert inventory.call_count == 2
    assert first.report == second.report
    assert first.input_fingerprint == second.input_fingerprint
    assert first.report["mode"] == "dry_run"
    assert first.report["will_write"] is False
    assert first.report["will_execute_unreal"] is False
    assert not config.attempt_root.exists()
    assert sorted(path.relative_to(tmp_path) for path in tmp_path.rglob("*")) == before
    assert first.provider["provider_id"] == materializer.PROVIDER_ID
    assert first.request["provider_spec_path"] == str(
        config.attempt_root / materializer.PROVIDER_COPY_NAME
    )
    assert first.request["provider_spec_sha256"] == first.provider_seal.sha256
    assert first.request["provider_spec_content_digest"] == first.provider["content_digest"]
    assert first.request["pipeline_sha256"] == materializer.PINNED_PIPELINE_SHA256
    assert first.report["fixed_sources"]["pipeline"] == {
        "object_path": materializer.PIPELINE_OBJECT_PATH,
        "relative_path": materializer.PIPELINE_RELATIVE.as_posix(),
        "sha256": materializer.PINNED_PIPELINE_SHA256,
        "size_bytes": materializer.PINNED_PIPELINE_SIZE_BYTES,
    }
    assert first.request["authorization"] == {
        "cloud_requests_authorized": True,
        "interactive_epic_sign_in_allowed": True,
        "store_account_tokens_in_receipt": False,
    }
    assert first.report["gates"] == {
        "source_inventory_verified": True,
        "assembled_candidate": False,
        "package_validation_complete": False,
        "runtime_visual_acceptance_complete": False,
        "photoreal_character_accepted": False,
    }


def test_request_matches_commandlet_newline_digest_contract(tmp_path: pathlib.Path) -> None:
    fixture = Fixture(tmp_path)
    with fixture.patched_inventory():
        plan = materializer.plan_materialization(fixture.config())

    body = dict(plan.request)
    observed = body.pop("content_digest")
    expected = hashlib.sha256(
        materializer.canonical_json(body, newline=True)
    ).hexdigest()
    assert observed == expected
    assert plan.request_raw == materializer.canonical_json(plan.request, newline=True)


def test_cli_accepts_no_provider_script_asset_class_or_environment_override() -> None:
    parser = materializer._parser()
    destinations = {action.dest for action in parser._actions}
    assert destinations == {
        "help",
        "engine_root",
        "run_root",
        "attempt_name",
        "apply",
    }
    for forbidden in (
        "provider",
        "script",
        "asset",
        "object_path",
        "class_path",
        "command",
        "env",
        "token",
    ):
        assert forbidden not in destinations


def test_apply_writes_private_attempt_and_uses_safe_fixed_subprocess(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture = Fixture(tmp_path)
    config = fixture.config()
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-reach-unreal")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "must-not-reach-unreal")
    observed: dict[str, object] = {}

    with fixture.patched_inventory():
        plan = materializer.plan_materialization(config)

        fake_popen = _popen_factory(
            observed=observed,
            result=_success_result(plan),
            return_code=0,
        )
        with mock.patch.object(materializer.subprocess, "Popen", side_effect=fake_popen):
            report = materializer.apply_materialization(plan)

    attempt = config.attempt_root
    assert report["assembled_candidate"] is True
    assert report["package_validation_complete"] is False
    assert report["runtime_visual_acceptance_complete"] is False
    assert report["photoreal_character_accepted"] is False
    assert report["device_authorization_handoff_exists"] is False
    assert report["device_authorization_handoff_sha256"] is None
    assert stat.S_IMODE(attempt.stat().st_mode) == 0o700
    assert stat.S_IMODE((attempt / "project").stat().st_mode) == 0o700
    for path in attempt.rglob("*"):
        if path.is_file():
            assert stat.S_IMODE(path.stat().st_mode) == 0o600

    provider_copy = attempt / materializer.PROVIDER_COPY_NAME
    assert provider_copy.read_bytes() == materializer.PROVIDER_PATH.read_bytes()
    request_raw = (attempt / materializer.REQUEST_NAME).read_bytes()
    request = json.loads(request_raw)
    assert request_raw == materializer.canonical_json(request, newline=True)
    assert pathlib.Path(request["provider_spec_path"]).parent == attempt
    assert pathlib.Path(request["provider_spec_path"]).name == materializer.PROVIDER_COPY_NAME
    assert pathlib.Path(request["attempt_root"]) == attempt
    assert pathlib.Path(request["project_file"]).parent == attempt / "project"
    assert hashlib.sha256(provider_copy.read_bytes()).hexdigest() == request[
        "provider_spec_sha256"
    ]

    project = json.loads((attempt / "project" / materializer.PROJECT_NAME).read_bytes())
    enabled = {
        item["Name"] for item in project["Plugins"] if item["Enabled"] is True
    }
    assert enabled == set(materializer.PROJECT_PLUGINS)
    assert {"Name": "AndroidFileServer", "Enabled": False} in project["Plugins"]

    command = observed["command"]
    kwargs = observed["kwargs"]
    assert isinstance(command, list)
    assert command[0] == str(fixture.editor)
    assert command[1] == str(attempt / "project" / materializer.PROJECT_NAME)
    assert command[2:] == [
        "-run=pythonscript",
        f"-script={attempt / materializer.AUTHOR_SCRIPT_NAME}",
        "-unattended",
        "-nop4",
        "-nosplash",
        "-vulkan",
        "-RenderOffscreen",
        "-graphicsadapter=0",
        "-stdout",
        "-FullStdOutLogOutput",
    ]
    assert kwargs["shell"] is False
    assert kwargs["start_new_session"] is True
    assert kwargs["close_fds"] is True
    assert kwargs["stdin"] is subprocess.DEVNULL
    environment = kwargs["env"]
    assert "OPENAI_API_KEY" not in environment
    assert "ANTHROPIC_AUTH_TOKEN" not in environment
    assert environment[materializer.REQUEST_ENV] == str(
        attempt / materializer.REQUEST_NAME
    )
    assert environment[materializer.RESULT_ENV] == str(
        attempt / materializer.RESULT_NAME
    )
    assert all("must-not-reach-unreal" not in value for value in environment.values())


def test_apply_detects_source_drift_before_creating_attempt(tmp_path: pathlib.Path) -> None:
    fixture = Fixture(tmp_path)
    config = fixture.config()
    with fixture.patched_inventory():
        plan = materializer.plan_materialization(config)
        fixture.editor.write_bytes(b"#!/bin/sh\nexit 96\n")
        fixture.editor.chmod(0o700)
        with pytest.raises(materializer.MetaHumanMaterializerError) as caught:
            materializer.apply_materialization(plan)

    assert caught.value.code in {"PLAN_DRIFT", "SOURCE_CHANGED"}
    assert not config.attempt_root.exists()


def test_existing_attempt_is_rejected_without_modification(tmp_path: pathlib.Path) -> None:
    fixture = Fixture(tmp_path)
    config = fixture.config()
    config.attempt_root.mkdir()
    marker = _write(config.attempt_root / "keep.txt", b"keep")
    before = marker.read_bytes()
    with fixture.patched_inventory():
        with pytest.raises(materializer.MetaHumanMaterializerError) as caught:
            materializer.plan_materialization(config)
    assert caught.value.code == "ATTEMPT_EXISTS"
    assert marker.read_bytes() == before


def test_destination_inside_normal_git_repository_is_rejected_before_write(
    tmp_path: pathlib.Path,
) -> None:
    fixture_root = tmp_path / "fixture"
    fixture_root.mkdir()
    fixture = Fixture(fixture_root)
    repository = tmp_path / "normal-repository"
    (repository / ".git").mkdir(parents=True)
    run_root = repository / "external-looking-runs"
    run_root.mkdir()
    config = materializer.MaterializationConfig(
        engine_root=fixture.engine,
        run_root=run_root,
        attempt_name="attempt-must-not-exist",
    )

    with fixture.patched_inventory():
        with pytest.raises(materializer.MetaHumanMaterializerError) as caught:
            materializer.plan_materialization(config)
    assert caught.value.code == "DESTINATION_IN_GIT"
    assert not config.attempt_root.exists()
    assert (repository / ".git").is_dir()


def test_destination_inside_linked_worktree_git_file_is_rejected_before_write(
    tmp_path: pathlib.Path,
) -> None:
    fixture_root = tmp_path / "fixture"
    fixture_root.mkdir()
    fixture = Fixture(fixture_root)
    worktree = tmp_path / "linked-worktree"
    worktree.mkdir()
    git_marker = _write(
        worktree / ".git",
        b"gitdir: /srv/repository/.git/worktrees/linked-worktree\n",
    )
    run_root = worktree / "runs"
    run_root.mkdir()
    config = materializer.MaterializationConfig(
        engine_root=fixture.engine,
        run_root=run_root,
        attempt_name="attempt-must-not-exist",
    )
    before = git_marker.read_bytes()

    with fixture.patched_inventory():
        with pytest.raises(materializer.MetaHumanMaterializerError) as caught:
            materializer.plan_materialization(config)
    assert caught.value.code == "DESTINATION_IN_GIT"
    assert not config.attempt_root.exists()
    assert git_marker.read_bytes() == before


def test_destination_inside_pinned_engine_tree_is_rejected_before_write(
    tmp_path: pathlib.Path,
) -> None:
    fixture = Fixture(tmp_path)
    run_root = fixture.engine / "generated-runs"
    run_root.mkdir()
    config = materializer.MaterializationConfig(
        engine_root=fixture.engine,
        run_root=run_root,
        attempt_name="attempt-must-not-exist",
    )

    with fixture.patched_inventory():
        with pytest.raises(materializer.MetaHumanMaterializerError) as caught:
            materializer.plan_materialization(config)
    assert caught.value.code == "DESTINATION_IN_ENGINE"
    assert not config.attempt_root.exists()


def test_result_with_credential_field_is_rejected_and_attempt_retained(
    tmp_path: pathlib.Path,
) -> None:
    fixture = Fixture(tmp_path)
    config = fixture.config()
    with fixture.patched_inventory():
        plan = materializer.plan_materialization(config)
        result = _success_result(plan)
        result["access_token"] = "not-a-real-token-value-1234567890"

        observed: dict[str, object] = {}
        fake_popen = _popen_factory(
            observed=observed,
            result=result,
            return_code=0,
        )
        with (
            mock.patch.object(materializer.subprocess, "Popen", side_effect=fake_popen),
            pytest.raises(materializer.MetaHumanMaterializerError) as caught,
        ):
            materializer.apply_materialization(plan)

    assert caught.value.code == "RESULT_CONTAINS_CREDENTIAL"
    assert config.attempt_root.is_dir()
    assert (config.attempt_root / materializer.RESULT_NAME).is_file()


def test_rejected_commandlet_never_promotes_and_retains_receipt(tmp_path: pathlib.Path) -> None:
    fixture = Fixture(tmp_path)
    config = fixture.config()
    with fixture.patched_inventory():
        plan = materializer.plan_materialization(config)
        result = {
            "schema_version": materializer.RESULT_SCHEMA,
            "provider_id": materializer.PROVIDER_ID,
            "provider_spec_content_digest": plan.provider["content_digest"],
            "accepted": False,
            "status": "authoring_failed",
            "authoring_succeeded": False,
            "assembly_completed": False,
            "assembled_component_digests_complete": False,
            "entitlement_receipt_complete": False,
            "failed_stage": "auto_rig",
            "error_type": "RuntimeError",
            "error_message_sha256": hashlib.sha256(
                b"device authorization unavailable"
            ).hexdigest(),
            "account_tokens_recorded": False,
            "package_validation_complete": False,
            "runtime_visual_acceptance_complete": False,
        }

        observed: dict[str, object] = {}
        fake_popen = _popen_factory(
            observed=observed,
            result=result,
            return_code=1,
        )
        with (
            mock.patch.object(materializer.subprocess, "Popen", side_effect=fake_popen),
            pytest.raises(materializer.MetaHumanMaterializerError) as caught,
        ):
            materializer.apply_materialization(plan)

    assert caught.value.code == "AUTHORING_FAILED"
    retained = json.loads((config.attempt_root / materializer.RESULT_NAME).read_bytes())
    assert retained["accepted"] is False
    assert retained["package_validation_complete"] is False
    assert retained["runtime_visual_acceptance_complete"] is False


def _proc_stat(pid: int, parent_pid: int, start_ticks: int) -> bytes:
    fields = ["S", str(parent_pid), *(["0"] * 17), str(start_ticks)]
    return f"{pid} (fixture process) {' '.join(fields)}\n".encode("ascii")


def _fake_proc_process(
    proc_root: pathlib.Path,
    *,
    pid: int,
    parent_pid: int,
    start_ticks: int,
    children: tuple[int, ...] = (),
    argv: tuple[str, ...] | None = None,
) -> None:
    process_root = proc_root / str(pid)
    _write(process_root / "stat", _proc_stat(pid, parent_pid, start_ticks))
    _write(
        process_root / "task" / str(pid) / "children",
        (" ".join(str(child) for child in children) + "\n").encode("ascii"),
    )
    if argv is not None:
        _write(
            process_root / "cmdline",
            b"\0".join(value.encode("utf-8") for value in argv) + b"\0",
        )


def test_proc_monitor_reads_cmdline_only_for_owned_same_uid_descendants(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proc_root = tmp_path / "proc"
    official = "https://www.epicgames.com/activate?userCode=AB12CD34"
    _fake_proc_process(
        proc_root,
        pid=100,
        parent_pid=1,
        start_ticks=10_000,
        children=(101,),
    )
    _fake_proc_process(
        proc_root,
        pid=101,
        parent_pid=100,
        start_ticks=10_001,
        argv=("/usr/bin/xdg-open", "https://example.com/not-epic"),
    )
    # This process has a valid-looking URL but is not in the owned tree.
    _fake_proc_process(
        proc_root,
        pid=999,
        parent_pid=1,
        start_ticks=10_002,
        argv=("/usr/bin/xdg-open", official),
    )
    root = materializer.ProcessIdentity(100, 1, 10_000)
    expected_uid = os.geteuid()
    original_reader = materializer._read_stable_process_cmdline
    read_pids: list[int] = []

    def tracking_reader(identity, *, proc_root):
        read_pids.append(identity.pid)
        return original_reader(identity, proc_root=proc_root)

    monkeypatch.setattr(materializer, "_read_stable_process_cmdline", tracking_reader)
    assert (
        materializer._scan_owned_device_authorization(
            root,
            expected_uid=expected_uid,
            proc_root=proc_root,
        )
        is None
    )
    assert read_pids == [101]
    assert 999 not in read_pids

    _write(
        proc_root / "101" / "cmdline",
        b"/usr/bin/xdg-open\0" + official.encode("ascii") + b"\0",
    )
    assert materializer._scan_owned_device_authorization(
        root,
        expected_uid=expected_uid,
        proc_root=proc_root,
    ) == (official, "AB12CD34")


def test_proc_monitor_excludes_descendant_with_different_uid(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proc_root = tmp_path / "proc"
    _fake_proc_process(
        proc_root,
        pid=200,
        parent_pid=1,
        start_ticks=20_000,
        children=(201,),
    )
    _fake_proc_process(
        proc_root,
        pid=201,
        parent_pid=200,
        start_ticks=20_001,
        argv=(
            "/usr/bin/xdg-open",
            "https://www.epicgames.com/activate?userCode=ZX90CV12",
        ),
    )
    expected_uid = os.geteuid()

    def fake_uid(pid, *, proc_root):
        return expected_uid if pid == 200 else expected_uid + 1

    monkeypatch.setattr(materializer, "_process_uid", fake_uid)
    descendants = materializer._owned_descendant_processes(
        materializer.ProcessIdentity(200, 1, 20_000),
        expected_uid=expected_uid,
        proc_root=proc_root,
    )
    assert descendants == ()


@pytest.mark.parametrize(
    "argv",
    [
        ("/usr/bin/xdg-open", "http://www.epicgames.com/activate?userCode=AB12CD34"),
        ("/usr/bin/xdg-open", "https://epicgames.com/activate?userCode=AB12CD34"),
        ("/usr/bin/xdg-open", "https://www.epicgames.com/activate?userCode=too-short"),
        ("/usr/bin/xdg-open", "https://www.epicgames.com/activate?x=1&userCode=AB12CD34"),
        ("xdg-open", "https://www.epicgames.com/activate?userCode=AB12CD34"),
        (
            "/usr/bin/xdg-open",
            "https://www.epicgames.com/activate?userCode=AB12CD34",
            "extra",
        ),
    ],
)
def test_device_authorization_url_contract_rejects_every_non_exact_argv(
    argv: tuple[str, ...],
) -> None:
    assert materializer._match_device_authorization_argv(argv) is None


@pytest.mark.parametrize(
    "argv",
    [
        (
            "/usr/bin/xdg-open",
            "https://www.epicgames.com/activate?userCode=AB12CD34",
        ),
        (
            "/bin/sh",
            "/usr/bin/xdg-open",
            "https://www.epicgames.com/activate?userCode=AB12CD34",
        ),
    ],
)
def test_device_authorization_url_contract_accepts_only_pinned_xdg_forms(
    argv: tuple[str, ...],
) -> None:
    assert materializer._match_device_authorization_argv(argv) == (
        "https://www.epicgames.com/activate?userCode=AB12CD34",
        "AB12CD34",
    )


def test_apply_publishes_private_device_handoff_without_leaking_it_into_report(
    tmp_path: pathlib.Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fixture = Fixture(tmp_path)
    config = fixture.config()
    observed: dict[str, object] = {}
    url = "https://www.epicgames.com/activate?userCode=QW12ER34"
    with fixture.patched_inventory():
        plan = materializer.plan_materialization(config)
        fake_popen = _popen_factory(
            observed=observed,
            result=_success_result(plan),
            return_code=0,
        )

        def fake_monitor(process, *, attempt_root, log_path, timeout_seconds):
            assert timeout_seconds == materializer.AUTHORING_TIMEOUT_SECONDS
            assert log_path == attempt_root / materializer.LOG_NAME
            digest = materializer._publish_device_authorization(
                attempt_root,
                url=url,
                user_code="QW12ER34",
            )
            return 0, digest

        with (
            mock.patch.object(materializer.subprocess, "Popen", side_effect=fake_popen),
            mock.patch.object(
                materializer,
                "_monitor_authoring_process",
                side_effect=fake_monitor,
            ),
        ):
            report = materializer.apply_materialization(plan)

    receipt_path = config.attempt_root / materializer.DEVICE_AUTHORIZATION_NAME
    raw = receipt_path.read_bytes()
    receipt = json.loads(raw)
    assert raw == materializer.canonical_json(receipt, newline=True)
    assert stat.S_IMODE(receipt_path.stat().st_mode) == 0o600
    assert receipt == {
        "schema_version": materializer.DEVICE_AUTHORIZATION_SCHEMA,
        "url": url,
        "user_code": "QW12ER34",
        "contains_credentials": False,
        "user_action_required": True,
    }
    assert report["device_authorization_handoff_exists"] is True
    assert report["device_authorization_handoff_sha256"] == hashlib.sha256(raw).hexdigest()
    serialized_report = json.dumps(report, sort_keys=True)
    assert url not in serialized_report
    assert "QW12ER34" not in serialized_report
    assert "token" not in raw.decode("utf-8").lower()
    assert url in capsys.readouterr().err

    before = receipt_path.read_bytes()
    with pytest.raises(materializer.MetaHumanMaterializerError) as caught:
        materializer._publish_device_authorization(
            config.attempt_root,
            url=url,
            user_code="QW12ER34",
        )
    assert caught.value.code == "WRITE_FAILED"
    assert receipt_path.read_bytes() == before


def test_monitor_timeout_terminates_owned_process_group(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    class HangingProcess:
        pid = 424_242

        def __init__(self) -> None:
            self.wait_calls = 0

        def poll(self):
            return None

        def wait(self, timeout=None):
            self.wait_calls += 1
            if self.wait_calls == 1:
                raise subprocess.TimeoutExpired(cmd="fixture", timeout=timeout)
            return -signal.SIGKILL

        def terminate(self):
            raise AssertionError("killpg should own the session")

        def kill(self):
            raise AssertionError("killpg should own the session")

    process = HangingProcess()
    identity = materializer.ProcessIdentity(process.pid, 1, 30_000)
    signals: list[tuple[int, signal.Signals]] = []
    monotonic = iter((0.0, 1.0))
    monkeypatch.setattr(materializer, "_read_process_identity", lambda pid: identity)
    monkeypatch.setattr(materializer, "_process_uid", lambda pid: os.geteuid())
    monkeypatch.setattr(
        materializer,
        "_scan_owned_device_authorization",
        lambda root, *, expected_uid: None,
    )
    monkeypatch.setattr(materializer.time, "monotonic", lambda: next(monotonic))
    monkeypatch.setattr(
        materializer.os,
        "killpg",
        lambda pid, sent_signal: signals.append((pid, sent_signal)),
    )

    with pytest.raises(materializer.MetaHumanMaterializerError) as caught:
        materializer._monitor_authoring_process(
            process,
            attempt_root=tmp_path,
            log_path=_write(tmp_path / materializer.LOG_NAME, b""),
            timeout_seconds=0.5,
        )
    assert caught.value.code == "AUTHORING_TIMEOUT"
    assert signals == [
        (process.pid, signal.SIGTERM),
        (process.pid, signal.SIGKILL),
    ]
    assert process.wait_calls == 2


def _xdg_failure_line(user_code: str = "CCFFQJTB") -> bytes:
    return (
        "xdg-open: no method available for opening '"
        "https://www.epicgames.com/activate?userCode="
        f"{user_code}'\n"
    ).encode("ascii")


def test_short_lived_detached_xdg_is_recovered_from_only_owned_log(
    tmp_path: pathlib.Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    fixture = Fixture(tmp_path)
    config = fixture.config()
    observed: dict[str, object] = {}
    with fixture.patched_inventory():
        plan = materializer.plan_materialization(config)

        def fake_popen(command, **kwargs):
            observed["command"] = command
            observed["kwargs"] = kwargs
            kwargs["stdout"].write(_xdg_failure_line())
            kwargs["stdout"].flush()
            _exclusive_result(kwargs["env"], _success_result(plan))
            # This PID never exists in /proc, reproducing the detached-child
            # race while the fixed owned log remains available.
            return _ImmediateProcess(0)

        with mock.patch.object(materializer.subprocess, "Popen", side_effect=fake_popen):
            report = materializer.apply_materialization(plan)

    receipt_path = config.attempt_root / materializer.DEVICE_AUTHORIZATION_NAME
    receipt = json.loads(receipt_path.read_bytes())
    assert receipt["user_code"] == "CCFFQJTB"
    assert report["device_authorization_handoff_exists"] is True
    assert report["device_authorization_handoff_sha256"] == hashlib.sha256(
        receipt_path.read_bytes()
    ).hexdigest()
    assert "CCFFQJTB" in capsys.readouterr().err
    assert "CCFFQJTB" not in json.dumps(report, sort_keys=True)


def test_process_exit_race_performs_final_log_read_before_pending_finalize(
    tmp_path: pathlib.Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    log_path = _write(tmp_path / materializer.LOG_NAME, b"")

    class ExitRaceProcess:
        pid = 999_999_929

        def poll(self):
            # The first monitor scan has already observed EOF.  Reproduce the
            # real race by publishing stderr immediately before exit becomes
            # visible to poll().
            with log_path.open("ab") as handle:
                handle.write(_xdg_failure_line("RT12YU34"))
                handle.flush()
                os.fsync(handle.fileno())
            return 0

    return_code, handoff_sha256 = materializer._monitor_authoring_process(
        ExitRaceProcess(),
        attempt_root=tmp_path,
        log_path=log_path,
        timeout_seconds=1.0,
    )
    receipt_path = tmp_path / materializer.DEVICE_AUTHORIZATION_NAME
    assert return_code == 0
    assert handoff_sha256 == hashlib.sha256(receipt_path.read_bytes()).hexdigest()
    assert json.loads(receipt_path.read_bytes())["user_code"] == "RT12YU34"
    assert "RT12YU34" in capsys.readouterr().err


def test_incremental_owned_log_match_survives_every_chunk_boundary(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    log_path = _write(tmp_path / materializer.LOG_NAME, _xdg_failure_line("AS12DF34"))
    state = materializer._new_authoring_log_scan_state(log_path)
    monkeypatch.setattr(materializer, "AUTHORING_LOG_SCAN_CHUNK_BYTES", 7)

    assert materializer._scan_authoring_log_device_authorization(
        log_path,
        state,
    ) == (
        "https://www.epicgames.com/activate?userCode=AS12DF34",
        "AS12DF34",
    )


def test_duplicate_owned_log_handoff_is_consumed_once(tmp_path: pathlib.Path) -> None:
    line = _xdg_failure_line("GH12JK34")
    log_path = _write(tmp_path / materializer.LOG_NAME, line + line)
    state = materializer._new_authoring_log_scan_state(log_path)

    assert materializer._scan_authoring_log_device_authorization(
        log_path,
        state,
    ) == (
        "https://www.epicgames.com/activate?userCode=GH12JK34",
        "GH12JK34",
    )
    assert materializer._scan_authoring_log_device_authorization(log_path, state) is None


def test_owned_log_rejects_generic_urls_invalid_urls_credentials_and_oversize_lines(
    tmp_path: pathlib.Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    valid_url = "https://www.epicgames.com/activate?userCode=ZX12CV34"
    raw = b"".join(
        (
            f"LogEOS: browser target {valid_url}\n".encode("ascii"),
            (
                "xdg-open: no method available for opening '"
                "https://example.com/activate?userCode=ZX12CV34'\n"
            ).encode("ascii"),
            (
                "xdg-open: no method available for opening '"
                f"{valid_url}' access_token=credential-material-must-not-print\n"
            ).encode("ascii"),
            b"x" * 2048 + valid_url.encode("ascii") + b"\n",
        )
    )
    log_path = _write(tmp_path / materializer.LOG_NAME, raw)
    state = materializer._new_authoring_log_scan_state(log_path)
    monkeypatch.setattr(materializer, "AUTHORING_LOG_SCAN_MAX_LINE_BYTES", 256)

    assert materializer._scan_authoring_log_device_authorization(log_path, state) is None
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_owned_log_total_byte_bound_refuses_late_url(
    tmp_path: pathlib.Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    raw = b"x" * 128 + b"\n" + _xdg_failure_line("BN12MM34")
    log_path = _write(tmp_path / materializer.LOG_NAME, raw)
    state = materializer._new_authoring_log_scan_state(log_path)
    monkeypatch.setattr(materializer, "AUTHORING_LOG_SCAN_CHUNK_BYTES", 16)
    monkeypatch.setattr(materializer, "AUTHORING_LOG_SCAN_MAX_BYTES", 64)

    assert materializer._scan_authoring_log_device_authorization(log_path, state) is None
    assert state.exhausted is True
    assert state.offset == 64


def test_file_pin_mismatch_fails_closed(tmp_path: pathlib.Path) -> None:
    source = _write(tmp_path / "source.bin", b"source")
    with pytest.raises(materializer.MetaHumanMaterializerError) as caught:
        materializer._seal_regular_file(
            source,
            label="fixture",
            expected_sha256="0" * 64,
        )
    assert caught.value.code == "SOURCE_PIN_MISMATCH"


def test_source_has_no_shell_or_generic_execution_escape_hatch() -> None:
    source_path = pathlib.Path(materializer.__file__).resolve()
    source = source_path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    assert "os.system" not in source
    assert "shell=True" not in source
    assert "eval(" not in source
    assert "exec(" not in source
    popen_calls = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "subprocess"
        and node.func.attr == "Popen"
    ]
    assert len(popen_calls) == 1
    keywords = {keyword.arg: keyword.value for keyword in popen_calls[0].keywords}
    assert isinstance(keywords["shell"], ast.Constant)
    assert keywords["shell"].value is False
    assert isinstance(keywords["start_new_session"], ast.Constant)
    assert keywords["start_new_session"].value is True
