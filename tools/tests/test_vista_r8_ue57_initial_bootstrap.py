from __future__ import annotations

import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import shutil
import stat
from typing import Any, Iterator

import pytest

from tools.admin import vista_r8_native_builder as native_builder
from tools.admin import vista_r8_ue57_initial_bootstrap as bootstrap


def _write(path: Path, raw: bytes, mode: int) -> dict[str, Any]:
    path.write_bytes(raw)
    path.chmod(mode)
    return {"sha256": hashlib.sha256(raw).hexdigest(), "size_bytes": len(raw)}


def _native_build_provenance(
    key: str,
    git: dict[str, Any],
    phase_a: dict[str, Any],
    output_pin: dict[str, Any],
    helper_pin: dict[str, Any],
    python_pin: dict[str, Any],
) -> dict[str, Any]:
    spec = bootstrap.NATIVE_JOB_SPECS[key]
    sources = {item["path"]: item["pin"] for item in git["sources"]}
    compiler = {
        "path": "/usr/bin/gcc-12",
        "canonical": "/usr/bin/x86_64-linux-gnu-gcc-12",
        "mode": "0755",
        "pin": {"sha256": "8" * 64, "size_bytes": 800},
    }
    readelf = {
        "path": "/usr/bin/readelf",
        "canonical": "/usr/bin/x86_64-linux-gnu-readelf",
        "mode": "0755",
        "pin": {"sha256": "9" * 64, "size_bytes": 900},
    }
    tracer = {
        "path": "/usr/bin/strace",
        "canonical": "/usr/bin/strace",
        "mode": "0755",
        "pin": {"sha256": "7" * 64, "size_bytes": 700},
    }
    tools = {
        "compiler": compiler,
        "readelf": readelf,
        "tracer": tracer,
        "toolchain": sorted(
            [
                compiler,
                readelf,
                tracer,
                {
                    "path": "/usr/lib/vista-r8-tool-a",
                    "canonical": "/usr/lib/vista-r8-tool-a",
                    "mode": "0444",
                    "pin": {"sha256": "a" * 64, "size_bytes": 1000},
                },
                {
                    "path": "/usr/lib/vista-r8-tool-b",
                    "canonical": "/usr/lib/vista-r8-tool-b",
                    "mode": "0755",
                    "pin": {"sha256": "b" * 64, "size_bytes": 1100},
                },
            ],
            key=lambda record: record["path"],
        ),
        "trace_contract": phase_a["trace_contract"],
    }
    job = bootstrap.seal_document(
        {
            "schema": bootstrap.NATIVE_BUILDER_JOB_SCHEMA,
            "status": "deterministic_static_native_closed",
            "accepted": False,
            "phase": "phase-a",
            "job_id": spec["job_id"],
            "source": {
                "git_bundle_pin": git["source_bundle"]["pin"],
                "commit": git["commit"],
                "git_path": spec["source_path"],
                "pin": sources[spec["source_path"]],
                "compiled_from_sealed_memfd": True,
            },
            "bindings": {"helper_pin": helper_pin, "python_pin": python_pin},
            "flags": bootstrap._native_job_flags(
                spec, helper_pin=helper_pin, python_pin=python_pin
            ),
            "environment": dict(bootstrap.BUILD_ENVIRONMENT),
            "tools": tools,
            "output": {
                "relative_path": f"artifacts/{spec['output_name']}",
                "mode": "0555",
                "pin": output_pin,
            },
            "determinism": {
                "build_count": 2,
                "byte_identical": True,
                "first_pin": output_pin,
                "second_pin": output_pin,
            },
            "static_elf": {
                "interpreter": None,
                "needed": [],
                "readelf_pin": tools["readelf"]["pin"],
            },
            "claims": {
                "builder_uid_gid": [
                    bootstrap.NATIVE_BUILDER_UID,
                    bootstrap.NATIVE_BUILDER_GID,
                ],
                "network_access": False,
                "worktree_input": False,
                "user_candidate_input": False,
            },
        }
    )
    return {
        "schema": bootstrap.NATIVE_BUILD_PROVENANCE_SCHEMA,
        "authority": {
            "root": str(bootstrap.NATIVE_BUILDER_PHASE_A_ROOT),
            "uid": bootstrap.NATIVE_BUILDER_UID,
            "gid": bootstrap.NATIVE_BUILDER_GID,
            "manifest_pin": phase_a["manifest_pin"],
            "manifest_content_digest": phase_a["manifest_content_digest"],
            "request_pin": phase_a["request_pin"],
            "source_bundle_pin": git["source_bundle"]["pin"],
            "builder_pin": phase_a["builder"]["pin"],
            "service_unit_pin": phase_a["builder"]["service_unit"]["pin"],
            "trace_contract": phase_a["trace_contract"],
        },
        "job": job,
        "job_manifest_pin": {
            "sha256": hashlib.sha256(bootstrap.canonical_json(job)).hexdigest(),
            "size_bytes": len(bootstrap.canonical_json(job)),
        },
    }


def test_root_consumer_mirror_matches_trace_v5_producer_contract() -> None:
    assert bootstrap.NATIVE_BUILDER_TRACE_CONTRACT_SCHEMA == (
        native_builder.TRACE_CONTRACT_SCHEMA
    )
    assert bootstrap.COMMON_NATIVE_FLAGS == native_builder.COMMON_FLAGS
    assert bootstrap.BUILD_ENVIRONMENT == native_builder.BUILD_ENVIRONMENT
    helper_pin = {"sha256": "1" * 64, "size_bytes": 11}
    python_pin = {"sha256": "2" * 64, "size_bytes": 22}
    for spec in bootstrap.NATIVE_JOB_SPECS.values():
        bindings = {"helper_pin": helper_pin, "python_pin": python_pin}
        assert bootstrap._native_job_flags(
            spec, helper_pin=helper_pin, python_pin=python_pin
        ) == native_builder.expected_job_flags(spec["job_id"], bindings)


class Fixture:
    def __init__(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        uid, gid = os.getuid(), os.getgid()
        self.root_parent = tmp_path / "root"
        self.review_parent = tmp_path / "review"
        self.root_parent.mkdir(mode=0o700)
        self.review_parent.mkdir(mode=0o700)
        monkeypatch.setattr(bootstrap, "ROOT_UID", uid)
        monkeypatch.setattr(bootstrap, "ROOT_GID", gid)
        monkeypatch.setattr(bootstrap, "REVIEW_UID", uid)
        monkeypatch.setattr(bootstrap, "REVIEW_GID", gid)
        monkeypatch.setattr(bootstrap, "NATIVE_BUILDER_UID", uid)
        monkeypatch.setattr(bootstrap, "NATIVE_BUILDER_GID", gid)
        monkeypatch.setattr(bootstrap, "ROOT_PARENT", self.root_parent)
        monkeypatch.setattr(bootstrap, "INSTALLED_ROOT", self.root_parent / "initial")
        monkeypatch.setattr(
            bootstrap,
            "INSTALLED_LAUNCHER",
            bootstrap.INSTALLED_ROOT / bootstrap.LAUNCHER_NAME,
        )
        monkeypatch.setattr(
            bootstrap,
            "INSTALLED_HELPER",
            bootstrap.INSTALLED_ROOT / bootstrap.HELPER_NAME,
        )
        monkeypatch.setattr(
            bootstrap,
            "INSTALLED_INPUT_PIN",
            bootstrap.INSTALLED_ROOT / bootstrap.INPUT_PIN_NAME,
        )
        monkeypatch.setattr(
            bootstrap, "INSTALLED_LOCK", bootstrap.INSTALLED_ROOT / bootstrap.LOCK_NAME
        )
        monkeypatch.setattr(bootstrap, "CORE_CANDIDATE", self.review_parent / "core")
        monkeypatch.setattr(
            bootstrap, "PARENT_CANDIDATE", self.review_parent / "parent"
        )
        monkeypatch.setattr(
            bootstrap, "BUILDPLUGIN_CANDIDATE", self.review_parent / "bp"
        )
        monkeypatch.setattr(bootstrap, "CORE_FINAL", self.root_parent / "core-final")
        monkeypatch.setattr(
            bootstrap, "PARENT_FINAL", self.root_parent / "parent-final"
        )
        monkeypatch.setattr(
            bootstrap, "BUILDPLUGIN_HELPER_FINAL", self.root_parent / "bp-helper-final"
        )
        monkeypatch.setattr(
            bootstrap, "BUILDPLUGIN_ADMIN_FINAL", self.root_parent / "bp-admin-final"
        )
        self.python = tmp_path / "python3.10"
        self.python_pin = _write(self.python, b"fixed-python", 0o755)
        monkeypatch.setattr(bootstrap, "PYTHON_PATH", self.python)
        self.launcher_pin = {
            "sha256": hashlib.sha256(b"fixed-launcher").hexdigest(),
            "size_bytes": len(b"fixed-launcher"),
        }
        self.helper_pin = {
            "sha256": hashlib.sha256(b"fixed-helper").hexdigest(),
            "size_bytes": len(b"fixed-helper"),
        }
        self.document = self._make_document()

    def _make_document(self) -> dict[str, Any]:
        templates = bootstrap._candidate_templates()
        raw_by_source = {
            "vista_r8_ue57_authority_admin.py": b"core-helper",
            "provision_vista_r8_ue57_engine.sh": b"engine-wrapper",
            "transfer-r8-ue57-stage-installer": b"static-transfer",
            "engine-source-pin.json": b'{"engine":"pin"}\n',
            "vista_authority_parent_seal.py": b"parent-helper",
            "launch-vista-authority-parent-seal": b"static-parent",
            "vista_r8_buildplugin_authority.py": b"buildplugin-helper",
            "publish-reconcile-buildplugin.sh": b"buildplugin-shell",
        }
        candidate_records: list[list[dict[str, Any]]] = []
        roots_done: set[str] = set()
        for template in templates:
            root = Path(template["candidate_root"])
            if str(root) not in roots_done:
                root.mkdir(mode=0o700)
                roots_done.add(str(root))
            records: list[dict[str, Any]] = []
            for source, destination, source_mode, final_mode in template["files"]:
                path = root / source
                if not path.exists():
                    pin = _write(path, raw_by_source[source], int(source_mode, 8))
                else:
                    raw = path.read_bytes()
                    pin = {
                        "sha256": hashlib.sha256(raw).hexdigest(),
                        "size_bytes": len(raw),
                    }
                records.append(
                    {
                        "source_name": source,
                        "destination_name": destination,
                        "source_mode": source_mode,
                        "final_mode": final_mode,
                        "pin": pin,
                    }
                )
            candidate_records.append(records)
        for root in roots_done:
            Path(root).chmod(0o555)

        source_pins = {
            path: {"sha256": "c" * 64, "size_bytes": 1200 + index}
            for index, path in enumerate(bootstrap.NATIVE_BUILDER_SOURCE_PATHS)
        }
        source_pins["tools/admin/vista_r8_ue57_authority_admin.py"] = candidate_records[
            0
        ][0]["pin"]
        source_pins["tools/admin/vista_authority_parent_seal.py"] = candidate_records[
            1
        ][0]["pin"]
        source_pins["tools/admin/vista_r8_ue57_initial_bootstrap.py"] = self.helper_pin
        git = {
            "commit": "a" * 40,
            "source_bundle": {
                "path": str(bootstrap.NATIVE_BUILDER_SOURCE_BUNDLE),
                "mode": "0444",
                "uid": bootstrap.ROOT_UID,
                "gid": bootstrap.ROOT_GID,
                "pin": {"sha256": "d" * 64, "size_bytes": 1300},
            },
            "sources": [
                {"path": path, "pin": source_pins[path]}
                for path in bootstrap.NATIVE_BUILDER_SOURCE_PATHS
            ],
        }
        phase_a = {
            "root": str(bootstrap.NATIVE_BUILDER_PHASE_A_ROOT),
            "manifest_pin": {"sha256": "e" * 64, "size_bytes": 1400},
            "manifest_content_digest": "f" * 64,
            "request_pin": {"sha256": "0" * 64, "size_bytes": 1500},
            "request_content_digest": "1" * 64,
            "source_bundle": git["source_bundle"],
            "source_commit": git["commit"],
            "sources": git["sources"],
            "builder": {
                "path": str(bootstrap.NATIVE_BUILDER_HELPER),
                "mode": "0444",
                "uid": bootstrap.ROOT_UID,
                "gid": bootstrap.ROOT_GID,
                "pin": {"sha256": "2" * 64, "size_bytes": 1600},
                "service_unit": {
                    "path": str(bootstrap.NATIVE_BUILDER_PHASE_A_UNIT),
                    "mode": "0644",
                    "uid": bootstrap.ROOT_UID,
                    "gid": bootstrap.ROOT_GID,
                    "pin": {"sha256": "3" * 64, "size_bytes": 1700},
                },
            },
            "trace_contract": {
                "schema": bootstrap.NATIVE_BUILDER_TRACE_CONTRACT_SCHEMA,
                "sha256": "4" * 64,
                "size_bytes": 1800,
            },
        }
        bp_binding = {
            "helper_pin": candidate_records[2][0]["pin"],
            "admin_script_pin": candidate_records[3][0]["pin"],
        }
        bindings = [
            {
                "root": templates[0]["candidate_root"],
                "files": {
                    record["source_name"]: record["pin"]
                    for record in candidate_records[0]
                },
            },
            {
                "candidate_root": templates[1]["candidate_root"],
                "helper_pin": candidate_records[1][0]["pin"],
                "launcher_pin": candidate_records[1][1]["pin"],
            },
            bp_binding,
            bp_binding,
        ]
        sequence: list[dict[str, Any]] = []
        for index, (template, records, binding) in enumerate(
            zip(templates, candidate_records, bindings, strict=True)
        ):
            generated = []
            for name, mode, size in template["generated_files"]:
                item: dict[str, Any] = {"name": name, "mode": mode}
                if size is not None:
                    item["size_bytes"] = size
                generated.append(item)
            sequence.append(
                {
                    "key": template["key"],
                    "candidate_root": template["candidate_root"],
                    "candidate_root_mode": "0555",
                    "candidate_files": records,
                    "final_root": template["final_root"],
                    "final_root_mode": "0555",
                    "generated_files": generated,
                    "native_build_provenance": (
                        _native_build_provenance(
                            template["key"],
                            git,
                            phase_a,
                            records[2]["pin"] if index == 0 else records[1]["pin"],
                            records[0]["pin"],
                            self.python_pin,
                        )
                        if index < 2
                        else None
                    ),
                    "review_provenance": {
                        "source": template["provenance_source"],
                        "binding": binding,
                        "git_commit": git["commit"],
                    },
                }
            )
        return bootstrap.seal_document(
            {
                "schema": bootstrap.INPUT_PIN_SCHEMA,
                "status": "dedicated_builder_initial_bootstrap_inputs_frozen",
                "accepted": False,
                "git": git,
                "native_builder_phase_a": phase_a,
                "components": {
                    "installed_root": {
                        "path": str(bootstrap.INSTALLED_ROOT),
                        "mode": "0555",
                    },
                    "launcher": {
                        "path": str(bootstrap.INSTALLED_LAUNCHER),
                        "mode": "0500",
                        "pin": self.launcher_pin,
                        "build_provenance": _native_build_provenance(
                            "initial-bootstrap",
                            git,
                            phase_a,
                            self.launcher_pin,
                            self.helper_pin,
                            self.python_pin,
                        ),
                    },
                    "helper": {
                        "path": str(bootstrap.INSTALLED_HELPER),
                        "mode": "0500",
                        "pin": self.helper_pin,
                    },
                    "input_pin": {
                        "path": str(bootstrap.INSTALLED_INPUT_PIN),
                        "mode": "0444",
                    },
                    "lock": {
                        "path": str(bootstrap.INSTALLED_LOCK),
                        "mode": "0600",
                        "size_bytes": 0,
                    },
                    "python": {
                        "path": str(bootstrap.PYTHON_PATH),
                        "mode": "0755",
                        "pin": self.python_pin,
                    },
                },
                "core_review_audit": {
                    "schema": bootstrap.CORE_AUDIT_SCHEMA,
                    "pin": {"sha256": "5" * 64, "size_bytes": 500},
                    "content_digest": "6" * 64,
                },
                "sequence": sequence,
                "operations": {
                    "publish": {
                        "operation": bootstrap.PUBLISH_OPERATION,
                        "acknowledgement": bootstrap.PUBLISH_ACKNOWLEDGEMENT,
                    },
                    "reconcile": {
                        "operation": bootstrap.RECONCILE_OPERATION,
                        "acknowledgement": bootstrap.RECONCILE_ACKNOWLEDGEMENT,
                    },
                    "resume": {
                        "operation": bootstrap.RESUME_OPERATION,
                        "acknowledgement": bootstrap.RESUME_ACKNOWLEDGEMENT,
                    },
                },
                "claims": {
                    "append_only_prefix_order": True,
                    "candidate_free_reconcile": True,
                    "fresh_no_replace": True,
                    "no_delete_no_repair_no_rollback": True,
                    "root_compiler_or_subprocess_execution": False,
                    "root_network_access": False,
                    "durability_unknown_reconcile_only": True,
                    "admin_launcher_fd_required": True,
                    "launcher_receipt_live_bound": True,
                    "dedicated_native_builder_required": True,
                },
            }
        )

    def root_fd(self) -> int:
        return os.open(self.root_parent, os.O_RDONLY | os.O_DIRECTORY)

    def publish(self) -> dict[str, Any]:
        descriptor = self.root_fd()
        try:
            return bootstrap._publish_or_resume(
                bootstrap.PUBLISH_OPERATION, self.document, descriptor
            )
        finally:
            os.close(descriptor)


@pytest.fixture
def fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Fixture]:
    value = Fixture(tmp_path, monkeypatch)
    bootstrap.validate_input_document(
        value.document,
        launcher_pin=value.launcher_pin,
        helper_pin=value.helper_pin,
        python_pin=value.python_pin,
    )
    yield value


def test_v2_uses_fixed_native_builder_paths_and_parent_candidate() -> None:
    assert bootstrap.INPUT_PIN_SCHEMA.endswith("/v2")
    assert bootstrap.CORE_AUDIT_SCHEMA.endswith("/v2")
    assert (bootstrap.NATIVE_BUILDER_UID, bootstrap.NATIVE_BUILDER_GID) == (997, 997)
    assert bootstrap.PARENT_CANDIDATE == Path(
        "/var/lib/vista-r8-native-builder-r1/phase-a-slot/published/"
        "parent-seal-candidate"
    )


def test_publish_all_four_roots_exact_and_receipt_reference(fixture: Fixture) -> None:
    result = fixture.publish()
    assert result["accepted"] is True
    assert result["prefix_length"] == 4
    for item in fixture.document["sequence"]:
        root = Path(item["final_root"])
        assert stat.S_IMODE(root.stat().st_mode) == 0o555
        assert root.stat().st_nlink == 2
        expected = {
            record["destination_name"] for record in item["candidate_files"]
        } | {record["name"] for record in item["generated_files"]}
        assert {path.name for path in root.iterdir()} == expected
    receipt = bootstrap.strict_json(
        (bootstrap.BUILDPLUGIN_ADMIN_FINAL / "receipt.json").read_bytes(),
        "admin receipt",
    )
    assert receipt == bootstrap._admin_receipt(fixture.document)
    assert receipt["claims"]["admin_launcher_fd_required"] is True
    assert receipt["claims"]["launcher_receipt_live_bound"] is True


def test_successful_promotion_preserves_the_opened_staging_inode(
    fixture: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    opened_inode: tuple[int, int] | None = None

    def observe(label: str) -> None:
        nonlocal opened_inode
        if label == "after_staging_open:core":
            names = [
                path
                for path in fixture.root_parent.iterdir()
                if path.name.startswith(".core-final.staging-")
            ]
            assert len(names) == 1
            info = names[0].stat(follow_symlinks=False)
            opened_inode = (info.st_dev, info.st_ino)

    monkeypatch.setattr(bootstrap, "_failure_point", observe)
    fixture.publish()
    final_info = bootstrap.CORE_FINAL.stat(follow_symlinks=False)
    assert opened_inode == (final_info.st_dev, final_info.st_ino)


def test_staging_swap_between_mkdir_and_open_is_never_cleaned(
    fixture: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    replacement: Path | None = None
    displaced: Path | None = None

    def swap(label: str) -> None:
        nonlocal replacement, displaced
        if label == "after_staging_mkdir:core":
            staging = next(
                path
                for path in fixture.root_parent.iterdir()
                if path.name.startswith(".core-final.staging-")
            )
            displaced = fixture.root_parent / ".displaced-created-staging"
            staging.rename(displaced)
            staging.mkdir(mode=0o700)
            (staging / "replacement-marker").write_bytes(b"do-not-remove")
            replacement = staging

    monkeypatch.setattr(bootstrap, "_failure_point", swap)
    with pytest.raises(
        bootstrap.BootstrapError, match="STAGING_STATE_RECONCILE_REQUIRED"
    ):
        fixture.publish()
    assert replacement is not None
    assert (replacement / "replacement-marker").read_bytes() == b"do-not-remove"
    assert displaced is not None and displaced.is_dir()
    assert not bootstrap.CORE_FINAL.exists()


def test_cleanup_refuses_a_replacement_of_the_held_staging_name(
    fixture: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    replacement: Path | None = None
    displaced: Path | None = None

    def swap_then_fail(label: str) -> None:
        nonlocal replacement, displaced
        if label == "before_rename:core":
            raise OSError("force cleanup")
        if label == "before_cleanup:core":
            staging = next(
                path
                for path in fixture.root_parent.iterdir()
                if path.name.startswith(".core-final.staging-")
            )
            displaced = fixture.root_parent / ".displaced-sealed-staging"
            staging.rename(displaced)
            staging.mkdir(mode=0o700)
            (staging / "replacement-marker").write_bytes(b"do-not-remove")
            replacement = staging

    monkeypatch.setattr(bootstrap, "_failure_point", swap_then_fail)
    with pytest.raises(
        bootstrap.BootstrapError, match="STAGING_CLEANUP_RECONCILE_REQUIRED"
    ):
        fixture.publish()
    assert replacement is not None
    assert (replacement / "replacement-marker").read_bytes() == b"do-not-remove"
    assert displaced is not None and any(displaced.iterdir())
    assert not bootstrap.CORE_FINAL.exists()


def test_rename_success_followed_by_exception_is_reconcile_only(
    fixture: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = bootstrap._rename_noreplace

    def rename_then_raise(parent_fd: int, source: str, destination: str) -> None:
        original(parent_fd, source, destination)
        raise OSError("exception after successful rename")

    monkeypatch.setattr(bootstrap, "_rename_noreplace", rename_then_raise)
    with pytest.raises(
        bootstrap.BootstrapError, match="DURABILITY_UNKNOWN_RECONCILE_REQUIRED"
    ):
        fixture.publish()
    assert bootstrap._prefix_state(fixture.document)[0] == 1


def test_rename_success_moved_back_to_source_is_not_misclassified_for_cleanup(
    fixture: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    original = bootstrap._rename_noreplace

    def rename_move_back_then_raise(
        parent_fd: int, source: str, destination: str
    ) -> None:
        original(parent_fd, source, destination)
        os.rename(
            destination,
            source,
            src_dir_fd=parent_fd,
            dst_dir_fd=parent_fd,
        )
        raise OSError("exception after successful rename and external move")

    monkeypatch.setattr(bootstrap, "_rename_noreplace", rename_move_back_then_raise)
    with pytest.raises(
        bootstrap.BootstrapError, match="DURABILITY_UNKNOWN_RECONCILE_REQUIRED"
    ):
        fixture.publish()
    staging = [
        path
        for path in fixture.root_parent.iterdir()
        if path.name.startswith(".core-final.staging-")
    ]
    assert len(staging) == 1 and any(staging[0].iterdir())
    assert not bootstrap.CORE_FINAL.exists()


def test_final_reopen_swap_is_reconcile_only_and_preserves_replacement(
    fixture: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    replacement: Path | None = None
    displaced: Path | None = None

    def swap(label: str) -> None:
        nonlocal replacement, displaced
        if label == "after_reopen:core":
            displaced = fixture.root_parent / ".displaced-promoted-final"
            bootstrap.CORE_FINAL.rename(displaced)
            bootstrap.CORE_FINAL.mkdir(mode=0o555)
            replacement = bootstrap.CORE_FINAL

    monkeypatch.setattr(bootstrap, "_failure_point", swap)
    with pytest.raises(
        bootstrap.BootstrapError, match="DURABILITY_UNKNOWN_RECONCILE_REQUIRED"
    ):
        fixture.publish()
    assert replacement is not None and replacement.is_dir()
    assert displaced is not None and any(displaced.iterdir())


def test_all_five_prefix_states_and_resume_are_byte_identical(
    fixture: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert bootstrap._prefix_state(fixture.document)[0] == 0
    snapshots: dict[int, dict[str, bytes]] = {}
    for stop_after in range(1, 5):

        def stop(label: str, *, stop_after: int = stop_after) -> None:
            if (
                label
                == f"after_reopen:{fixture.document['sequence'][stop_after - 1]['key']}"
                and stop_after < 4
            ):
                raise bootstrap.BootstrapError("TEST_STOP", label)

        monkeypatch.setattr(bootstrap, "_failure_point", stop)
        if stop_after == 1:
            with pytest.raises(bootstrap.BootstrapError):
                fixture.publish()
        elif stop_after < 4:
            descriptor = fixture.root_fd()
            try:
                with pytest.raises(bootstrap.BootstrapError):
                    bootstrap._publish_or_resume(
                        bootstrap.RESUME_OPERATION, fixture.document, descriptor
                    )
            finally:
                os.close(descriptor)
        else:
            descriptor = fixture.root_fd()
            try:
                bootstrap._publish_or_resume(
                    bootstrap.RESUME_OPERATION, fixture.document, descriptor
                )
            finally:
                os.close(descriptor)
        assert bootstrap._prefix_state(fixture.document)[0] == stop_after
        snapshots[stop_after] = {
            str(path): path.read_bytes()
            for item in fixture.document["sequence"][:stop_after]
            for path in Path(item["final_root"]).iterdir()
        }
    assert bootstrap._prefix_state(fixture.document)[0] == 4
    assert snapshots[4].items() >= snapshots[1].items()


def test_candidate_free_partial_and_full_reconcile(
    fixture: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    def stop(label: str) -> None:
        if label == "after_reopen:parent-seal":
            raise bootstrap.BootstrapError("TEST_STOP", label)

    monkeypatch.setattr(bootstrap, "_failure_point", stop)
    with pytest.raises(bootstrap.BootstrapError):
        fixture.publish()
    monkeypatch.setattr(
        bootstrap,
        "_open_all_candidates",
        lambda _sequence: (_ for _ in ()).throw(
            AssertionError("reconcile opened a reviewed candidate")
        ),
    )
    descriptor = fixture.root_fd()
    try:
        result = bootstrap._reconcile_prefix(fixture.document, descriptor)
    finally:
        os.close(descriptor)
    assert result["prefix_length"] == 2
    assert result["candidate_access_performed"] is False


def test_candidate_free_full_reconcile(
    fixture: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    fixture.publish()
    monkeypatch.setattr(
        bootstrap,
        "_open_all_candidates",
        lambda _sequence: (_ for _ in ()).throw(
            AssertionError("full reconcile opened a reviewed candidate")
        ),
    )
    descriptor = fixture.root_fd()
    try:
        result = bootstrap._reconcile_prefix(fixture.document, descriptor)
    finally:
        os.close(descriptor)
    assert result["prefix_length"] == 4
    assert result["complete"] is True
    assert result["candidate_access_performed"] is False


@pytest.mark.parametrize("stage_index", range(4))
def test_no_replace_collision_at_each_target_preserves_earlier_roots(
    fixture: Fixture,
    monkeypatch: pytest.MonkeyPatch,
    stage_index: int,
) -> None:
    original = bootstrap._rename_noreplace
    target_name = Path(fixture.document["sequence"][stage_index]["final_root"]).name

    def collide(parent_fd: int, source: str, destination: str) -> None:
        if destination == target_name:
            os.mkdir(destination, 0o555, dir_fd=parent_fd)
        original(parent_fd, source, destination)

    monkeypatch.setattr(bootstrap, "_rename_noreplace", collide)
    with pytest.raises(
        bootstrap.BootstrapError, match="FINAL_COLLISION_RECONCILE_REQUIRED"
    ):
        fixture.publish()
    for item in fixture.document["sequence"][:stage_index]:
        bootstrap._audit_final(item, fixture.document, fsync=False)
    assert Path(fixture.document["sequence"][stage_index]["final_root"]).is_dir()
    for item in fixture.document["sequence"][stage_index + 1 :]:
        assert not Path(item["final_root"]).exists()


@pytest.mark.parametrize(
    "phase",
    [
        "before_rename",
        "after_rename",
        "before_final_fsync",
        "after_final_fsync",
        "before_parent_fsync",
        "after_parent_fsync",
        "before_reopen",
        "after_reopen",
    ],
)
@pytest.mark.parametrize("stage_index", range(4))
def test_injected_failures_preserve_only_valid_prefix(
    fixture: Fixture,
    monkeypatch: pytest.MonkeyPatch,
    phase: str,
    stage_index: int,
) -> None:
    key = fixture.document["sequence"][stage_index]["key"]

    def injected(label: str) -> None:
        if label == f"{phase}:{key}":
            raise OSError("injected")

    monkeypatch.setattr(bootstrap, "_failure_point", injected)
    with pytest.raises((bootstrap.BootstrapError, OSError)):
        fixture.publish()
    expected = stage_index if phase == "before_rename" else stage_index + 1
    assert bootstrap._prefix_state(fixture.document)[0] == expected
    for item in fixture.document["sequence"][expected:]:
        assert not Path(item["final_root"]).exists()


def test_mutation_between_stages_stops_at_checkpoint(
    fixture: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = bootstrap.BUILDPLUGIN_CANDIDATE / "publish-reconcile-buildplugin.sh"

    def mutate(label: str) -> None:
        if label == "after_reopen:core":
            bootstrap.BUILDPLUGIN_CANDIDATE.chmod(0o755)
            target.chmod(0o644)
            target.write_bytes(b"mutated")
            target.chmod(0o444)
            bootstrap.BUILDPLUGIN_CANDIDATE.chmod(0o555)

    monkeypatch.setattr(bootstrap, "_failure_point", mutate)
    with pytest.raises(bootstrap.BootstrapError, match="CANDIDATE_DRIFT"):
        fixture.publish()
    assert bootstrap._prefix_state(fixture.document)[0] == 1


def test_prefix_gap_and_tamper_are_rejected(fixture: Fixture) -> None:
    fixture.publish()
    middle = Path(fixture.document["sequence"][1]["final_root"])
    middle.chmod(0o755)
    shutil.rmtree(middle)
    with pytest.raises(bootstrap.BootstrapError, match="PREFIX_GAP"):
        bootstrap._prefix_state(fixture.document)


def test_final_receipt_field_tamper_is_rejected(fixture: Fixture) -> None:
    fixture.publish()
    receipt = bootstrap.BUILDPLUGIN_ADMIN_FINAL / "receipt.json"
    bootstrap.BUILDPLUGIN_ADMIN_FINAL.chmod(0o755)
    receipt.chmod(0o644)
    document = json.loads(receipt.read_text())
    document["claims"]["admin_launcher_fd_required"] = False
    document["content_digest"] = bootstrap.content_digest(document)
    receipt.write_bytes(bootstrap.canonical_json(document))
    receipt.chmod(0o444)
    bootstrap.BUILDPLUGIN_ADMIN_FINAL.chmod(0o555)
    with pytest.raises(bootstrap.BootstrapError, match="FILE_INVALID|FINAL_TAMPERED"):
        bootstrap._prefix_state(fixture.document)


@pytest.mark.parametrize(
    "mutation",
    [
        "mode",
        "hardlink",
        "symlink",
        "fifo",
        "missing",
        "extra",
        "owner",
        "oversize",
        "sparse",
    ],
)
def test_candidate_namespace_and_metadata_attacks_fail_closed(
    fixture: Fixture, monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    root = bootstrap.CORE_CANDIDATE
    target = root / "engine-source-pin.json"
    root.chmod(0o755)
    if mutation == "mode":
        target.chmod(0o644)
    elif mutation == "hardlink":
        os.link(target, root / "alias")
    elif mutation == "symlink":
        target.unlink()
        target.symlink_to("vista_r8_ue57_authority_admin.py")
    elif mutation == "fifo":
        target.unlink()
        os.mkfifo(target, 0o444)
    elif mutation == "missing":
        target.unlink()
    elif mutation == "extra":
        _write(root / "extra", b"extra", 0o444)
    elif mutation == "owner":
        monkeypatch.setattr(bootstrap, "REVIEW_UID", os.getuid() + 1)
    elif mutation == "oversize":
        monkeypatch.setattr(bootstrap, "MAX_CANDIDATE_BYTES", 4)
    else:
        target.unlink()
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT, 0o444)
        try:
            os.lseek(descriptor, 1024 * 1024, os.SEEK_SET)
            os.write(descriptor, b"x")
        finally:
            os.close(descriptor)
    root.chmod(0o555)
    with pytest.raises((bootstrap.BootstrapError, OSError)):
        bootstrap._open_all_candidates(fixture.document["sequence"])


def test_shared_buildplugin_candidate_is_revalidated_for_both_roots(
    fixture: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    opened = bootstrap._open_all_candidates(fixture.document["sequence"])
    try:
        assert set(opened) == {
            str(bootstrap.CORE_CANDIDATE),
            str(bootstrap.PARENT_CANDIDATE),
            str(bootstrap.BUILDPLUGIN_CANDIDATE),
        }
        calls = 0
        original = opened[str(bootstrap.BUILDPLUGIN_CANDIDATE)].revalidate

        def counted() -> None:
            nonlocal calls
            calls += 1
            original()

        monkeypatch.setattr(
            opened[str(bootstrap.BUILDPLUGIN_CANDIDATE)], "revalidate", counted
        )
        bootstrap._revalidate_candidates(opened)
        bootstrap._revalidate_candidates(opened)
        assert calls == 2
    finally:
        for candidate in opened.values():
            candidate.close()


def test_parent_candidate_uses_dedicated_builder_owner(
    fixture: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(bootstrap, "NATIVE_BUILDER_UID", os.getuid() + 1)
    with pytest.raises(bootstrap.BootstrapError, match="DIRECTORY_INVALID"):
        bootstrap._open_all_candidates(fixture.document["sequence"])


def test_input_schema_rejects_omission_unknown_tamper_and_rebind(
    fixture: Fixture,
) -> None:
    mutations: list[dict[str, Any]] = []
    omitted = copy.deepcopy(fixture.document)
    del omitted["claims"]
    mutations.append(omitted)
    unknown = copy.deepcopy(fixture.document)
    unknown["unknown"] = True
    mutations.append(unknown)
    wrong_order = copy.deepcopy(fixture.document)
    wrong_order["sequence"] = list(reversed(wrong_order["sequence"]))
    mutations.append(wrong_order)
    rebound = copy.deepcopy(fixture.document)
    rebound["components"]["launcher"]["pin"] = {"sha256": "f" * 64, "size_bytes": 1}
    mutations.append(rebound)
    native_helper_rebound = copy.deepcopy(fixture.document)
    native_helper_job = native_helper_rebound["sequence"][0]["native_build_provenance"][
        "job"
    ]
    native_helper_job["bindings"]["helper_pin"] = {
        "sha256": "e" * 64,
        "size_bytes": 1,
    }
    native_helper_job["content_digest"] = bootstrap.content_digest(native_helper_job)
    mutations.append(native_helper_rebound)
    native_source_rebound = copy.deepcopy(fixture.document)
    native_source_job = native_source_rebound["sequence"][1]["native_build_provenance"][
        "job"
    ]
    native_source_job["source"]["git_path"] = "tools/admin/not-the-parent-launcher.c"
    native_source_job["content_digest"] = bootstrap.content_digest(native_source_job)
    mutations.append(native_source_rebound)
    native_determinism_rebound = copy.deepcopy(fixture.document)
    native_determinism_job = native_determinism_rebound["sequence"][0][
        "native_build_provenance"
    ]["job"]
    native_determinism_job["determinism"]["byte_identical"] = False
    native_determinism_job["content_digest"] = bootstrap.content_digest(
        native_determinism_job
    )
    native_determinism_rebound["sequence"][0]["native_build_provenance"][
        "job_manifest_pin"
    ] = {
        "sha256": hashlib.sha256(
            bootstrap.canonical_json(native_determinism_job)
        ).hexdigest(),
        "size_bytes": len(bootstrap.canonical_json(native_determinism_job)),
    }
    mutations.append(native_determinism_rebound)
    native_toolchain_rebound = copy.deepcopy(fixture.document)
    native_toolchain_job = native_toolchain_rebound["sequence"][1][
        "native_build_provenance"
    ]["job"]
    native_toolchain_job["tools"]["toolchain"][0]["path"] = "/tmp/fake-cc1"
    native_toolchain_job["content_digest"] = bootstrap.content_digest(
        native_toolchain_job
    )
    mutations.append(native_toolchain_rebound)
    native_static_rebound = copy.deepcopy(fixture.document)
    native_static_provenance = native_static_rebound["components"]["launcher"][
        "build_provenance"
    ]
    native_static_job = native_static_provenance["job"]
    native_static_job["static_elf"]["needed"] = ["libc.so.6"]
    native_static_job["content_digest"] = bootstrap.content_digest(native_static_job)
    native_static_raw = bootstrap.canonical_json(native_static_job)
    native_static_provenance["job_manifest_pin"] = {
        "sha256": hashlib.sha256(native_static_raw).hexdigest(),
        "size_bytes": len(native_static_raw),
    }
    mutations.append(native_static_rebound)
    native_claim_rebound = copy.deepcopy(fixture.document)
    native_claim_provenance = native_claim_rebound["sequence"][1][
        "native_build_provenance"
    ]
    native_claim_job = native_claim_provenance["job"]
    native_claim_job["claims"]["network_access"] = True
    native_claim_job["content_digest"] = bootstrap.content_digest(native_claim_job)
    native_claim_raw = bootstrap.canonical_json(native_claim_job)
    native_claim_provenance["job_manifest_pin"] = {
        "sha256": hashlib.sha256(native_claim_raw).hexdigest(),
        "size_bytes": len(native_claim_raw),
    }
    mutations.append(native_claim_rebound)
    phase_a_rebound = copy.deepcopy(fixture.document)
    phase_a_rebound["native_builder_phase_a"]["manifest_pin"] = {
        "sha256": "4" * 64,
        "size_bytes": 1,
    }
    mutations.append(phase_a_rebound)
    source_bundle_rebound = copy.deepcopy(fixture.document)
    source_bundle_rebound["git"]["source_bundle"]["path"] = "/tmp/source.bundle"
    source_bundle_rebound["native_builder_phase_a"]["source_bundle"] = (
        source_bundle_rebound["git"]["source_bundle"]
    )
    mutations.append(source_bundle_rebound)
    for document in mutations:
        document["content_digest"] = bootstrap.content_digest(document)
        with pytest.raises(bootstrap.BootstrapError, match="INPUT_PIN_INVALID"):
            bootstrap.validate_input_document(
                document,
                launcher_pin=fixture.launcher_pin,
                helper_pin=fixture.helper_pin,
                python_pin=fixture.python_pin,
            )


def test_empty_reconcile_and_invalid_publish_resume_states_fail(
    fixture: Fixture,
) -> None:
    descriptor = fixture.root_fd()
    try:
        with pytest.raises(bootstrap.BootstrapError, match="NONEMPTY_PREFIX_REQUIRED"):
            bootstrap._reconcile_prefix(fixture.document, descriptor)
        with pytest.raises(
            bootstrap.BootstrapError, match="INCOMPLETE_PREFIX_REQUIRED"
        ):
            bootstrap._publish_or_resume(
                bootstrap.RESUME_OPERATION, fixture.document, descriptor
            )
    finally:
        os.close(descriptor)
    fixture.publish()
    descriptor = fixture.root_fd()
    try:
        with pytest.raises(bootstrap.BootstrapError, match="EMPTY_PREFIX_REQUIRED"):
            bootstrap._publish_or_resume(
                bootstrap.PUBLISH_OPERATION, fixture.document, descriptor
            )
        with pytest.raises(
            bootstrap.BootstrapError, match="INCOMPLETE_PREFIX_REQUIRED"
        ):
            bootstrap._publish_or_resume(
                bootstrap.RESUME_OPERATION, fixture.document, descriptor
            )
    finally:
        os.close(descriptor)


def test_root_helper_has_no_subprocess_network_or_toolchain_execution() -> None:
    source = Path(bootstrap.__file__).read_text()
    assert "import subprocess" not in source
    assert "import socket" not in source
    assert "os.system" not in source
    assert "execv" not in source
    assert "subprocess.run" not in source
    assert "same_uid_procfs_guard" not in source
    assert "PR_SET_DUMPABLE" not in source
    assert "NATIVE_REBUILD_BWRAP_PREFIX" not in source
    assert "reviewed_initial_bootstrap_inputs_frozen" not in source


def test_parser_is_closed_and_acknowledgements_are_literal() -> None:
    parser = bootstrap._parser()
    with pytest.raises(SystemExit):
        parser.parse_args([])
    with pytest.raises(SystemExit):
        parser.parse_args([bootstrap.PUBLISH_OPERATION, "extra"])
    args = parser.parse_args(
        [
            bootstrap.PUBLISH_OPERATION,
            "--launcher-fd",
            "3",
            "--helper-fd",
            "4",
            "--input-pin-fd",
            "5",
            "--python-fd",
            "6",
            "--lock-fd",
            "7",
            "--acknowledgement",
            bootstrap.PUBLISH_ACKNOWLEDGEMENT,
        ]
    )
    assert args.operation == bootstrap.PUBLISH_OPERATION


def test_lock_is_nonblocking(fixture: Fixture) -> None:
    lock = fixture.root_parent / "test.lock"
    lock.touch(mode=0o600)
    first = os.open(lock, os.O_RDONLY)
    second = os.open(lock, os.O_RDONLY)
    try:
        fcntl.flock(first, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(BlockingIOError):
            fcntl.flock(second, fcntl.LOCK_EX | fcntl.LOCK_NB)
    finally:
        os.close(second)
        os.close(first)
