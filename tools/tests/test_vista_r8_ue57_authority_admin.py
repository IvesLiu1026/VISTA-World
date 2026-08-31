from __future__ import annotations

import contextlib
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess

import pytest

from tools.admin import vista_r8_native_builder as native_builder
from tools.admin import vista_r8_ue57_authority_admin as admin


def test_native_builder_source_contract_uses_fresh_r2_checkout() -> None:
    expected = Path("/home/yhliu/VISTA-World-worktrees/vista-r8-fresh-namespace-r2")
    assert admin.CHECKOUT_ROOT == expected
    sources = {
        admin.REVIEW_HELPER_SOURCE,
        admin.STAGE_TRANSFER_LAUNCHER_SOURCE,
        admin.PARENT_SEAL_HELPER_SOURCE,
        admin.PARENT_SEAL_LAUNCHER_SOURCE,
        admin.INITIAL_BOOTSTRAP_HELPER_SOURCE,
        admin.INITIAL_BOOTSTRAP_LAUNCHER_SOURCE,
        admin.INITIAL_BOOTSTRAP_INSTALLER_SOURCE,
    }
    assert {
        source.relative_to(expected).as_posix() for source in sources
    } == set(native_builder.SOURCE_PATHS)
    assert all("vista-r9-six-room-finish-r1" not in str(source) for source in sources)


def _write(path: Path, raw: bytes, mode: int = 0o644) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(raw)
    path.chmod(mode)


def _run_test_git(repository: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["/usr/bin/git", "-C", str(repository), *arguments],
        check=True,
        env={
            "PATH": "/usr/bin:/bin",
            "HOME": "/nonexistent",
            "LANG": "C",
            "LC_ALL": "C",
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_COUNT": "0",
            "GIT_NO_REPLACE_OBJECTS": "1",
            "GIT_TERMINAL_PROMPT": "0",
        },
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return result.stdout.strip()


def _native_trace_event(
    syscall: str,
    path: str,
    outcome: str,
    *,
    open_flags: list[str] | None = None,
) -> str:
    event: dict[str, object] = {
        "outcome": outcome,
        "paths": [path],
        "syscall": syscall,
    }
    if open_flags is not None:
        event["open_flags"] = open_flags
    return json.dumps(
        event,
        sort_keys=True,
        separators=(",", ":"),
    )


def _native_trace_contract(host: Path) -> dict[str, object]:
    raw = host.read_bytes()
    file_record = {
        "path": str(host),
        "canonical": str(host.resolve()),
        "mode": f"{stat.S_IMODE(host.stat().st_mode):04o}",
        "pin": {"sha256": hashlib.sha256(raw).hexdigest(), "size_bytes": len(raw)},
        "storage": "empty" if not raw else "regular",
        "component_chain": admin._native_builder_live_component_chain(
            host, "fixture host"
        ),
    }
    directory = host.parent
    directory_record = {
        "path": str(directory),
        "canonical": str(directory.resolve()),
        "component_chain": admin._native_builder_live_component_chain(
            directory, "fixture directory"
        ),
    }
    expected_tools = {
        invocation: tool
        for phase in ("phase-a", "phase-b")
        for invocation, tool in admin._native_builder_expected_trace_invocations(phase)
    }
    absent = str(directory / "vista-r8-absent")
    profiles = [
        {
            "id": invocation,
            "tool": tool,
            "event_multiset": [
                {
                    "line": _native_trace_event("access", absent, "ENOENT"),
                    "count": 1,
                }
            ],
            "host_files": [str(host)],
            "host_directories": [str(directory)],
            "search_state": [
                {
                    "syscall": "access",
                    "path": absent,
                    "errno": "ENOENT",
                    "count": 1,
                }
            ],
            "scratch_prestate": [],
        }
        for invocation, tool in sorted(expected_tools.items())
    ]
    return {
        "schema": admin.NATIVE_BUILDER_TRACE_CONTRACT_SCHEMA,
        "tracer_version": admin.NATIVE_BUILDER_STRACE_VERSION,
        "host_files": [file_record],
        "host_directories": [directory_record],
        "tracer_runtime_files": [str(host)],
        "builder_runtime_files": [str(host)],
        "path_aliases": [],
        "event_count_policies": admin._native_builder_trace_event_count_policies(),
        "profiles": profiles,
        "phase_invocations": {
            phase: [
                invocation
                for invocation, _tool in admin._native_builder_expected_trace_invocations(
                    phase
                )
            ]
            for phase in ("phase-a", "phase-b")
        },
    }


def _native_trace_contract_with_kernel_virtual() -> dict[str, object]:
    runtime_path = native_builder.PYTHON_PATH
    runtime = native_builder._planner_trace_file_record(str(runtime_path))
    special = native_builder._planner_trace_file_record(
        str(native_builder.KERNEL_VIRTUAL_SYSCTL_PATH)
    )
    root = native_builder._planner_trace_directory_record("/")
    expected_tools = {
        invocation: tool
        for phase in ("phase-a", "phase-b")
        for invocation, tool in admin._native_builder_expected_trace_invocations(phase)
    }
    profiles: list[dict[str, object]] = []
    for index, (invocation, tool) in enumerate(sorted(expected_tools.items())):
        host_files = [str(runtime_path)]
        events = [
            {
                "line": _native_trace_event("access", "/vista-r8-absent", "ENOENT"),
                "count": 1,
            }
        ]
        if index == 0:
            host_files.append(str(native_builder.KERNEL_VIRTUAL_SYSCTL_PATH))
            events.append(
                {
                    "line": _native_trace_event(
                        "openat",
                        str(native_builder.KERNEL_VIRTUAL_SYSCTL_PATH),
                        "OK",
                        open_flags=["O_RDONLY", "O_CLOEXEC"],
                    ),
                    "count": 1,
                }
            )
        profiles.append(
            {
                "id": invocation,
                "tool": tool,
                "event_multiset": sorted(events, key=lambda item: item["line"]),
                "host_files": sorted(host_files),
                "host_directories": ["/"],
                "search_state": [
                    {
                        "syscall": "access",
                        "path": "/vista-r8-absent",
                        "errno": "ENOENT",
                        "count": 1,
                    }
                ],
                "scratch_prestate": [],
            }
        )
    return {
        "schema": admin.NATIVE_BUILDER_TRACE_CONTRACT_SCHEMA,
        "tracer_version": admin.NATIVE_BUILDER_STRACE_VERSION,
        "host_files": sorted((runtime, special), key=lambda item: item["path"]),
        "host_directories": [root],
        "tracer_runtime_files": [str(runtime_path)],
        "builder_runtime_files": [str(runtime_path)],
        "path_aliases": [],
        "event_count_policies": admin._native_builder_trace_event_count_policies(),
        "profiles": profiles,
        "phase_invocations": {
            phase: [
                invocation
                for invocation, _tool in admin._native_builder_expected_trace_invocations(
                    phase
                )
            ]
            for phase in ("phase-a", "phase-b")
        },
    }


def _engine_source(root: Path) -> None:
    _write(root / "Engine/Binaries/Linux/UnrealEditor-Cmd", b"editor\0", 0o755)
    _write(root / "Engine/Binaries/Linux/UnrealEditor.modules", b"{}\n")
    _write(root / "Engine/Build/Build.version", b"{}\n")
    _write(root / "Content/readme.txt", b"payload\n", 0o600)


def _source_pin(snapshot: admin.TreeSnapshot) -> dict[str, object]:
    source_manifest = admin.canonical_json(admin.source_manifest(snapshot))
    python_raw = admin.PYTHON_PATH.read_bytes()
    return admin.seal_document(
        {
            "schema": admin.ENGINE_SOURCE_PIN_SCHEMA,
            "source_root": str(snapshot.root),
            "source_manifest_sha256": hashlib.sha256(source_manifest).hexdigest(),
            "source_manifest_size_bytes": len(source_manifest),
            "source_manifest_content_digest": admin.source_manifest(snapshot)[
                "content_digest"
            ],
            "tree_root_digest": snapshot.tree_digest,
            "projection": snapshot.projection(),
            "publisher_python_pin": {
                "sha256": hashlib.sha256(python_raw).hexdigest(),
                "size_bytes": len(python_raw),
            },
        }
    )


def _fake_noreplace(source: Path, destination: Path) -> None:
    if os.path.lexists(destination):
        raise admin.AuthorityError("FINAL_NOT_FRESH", str(destination))
    os.rename(source, destination)


def test_snapshot_is_complete_deterministic_and_projection_compatible(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    _engine_source(source)

    first = admin.snapshot_tree(source)
    second = admin.snapshot_tree(source)

    assert first.entries == second.entries
    assert first.tree_digest == second.tree_digest
    assert first.projection_sha256 == second.projection_sha256
    assert first.file_count == 4
    assert first.directory_count == 5
    assert first.total_bytes == sum(
        path.stat().st_size for path in source.rglob("*") if path.is_file()
    )
    assert first.projection()["directory_count"] == 6  # executor includes root "."
    assert all(item["uid"] == os.getuid() for item in first.entries)


def test_native_builder_trace_contract_is_independently_closed_and_projected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(admin, "ROOT_UID", os.getuid())
    monkeypatch.setattr(admin, "ROOT_GID", os.getgid())
    monkeypatch.setattr(
        admin,
        "_native_builder_component_chain_is_immutable_root_owned",
        lambda _chain: True,
    )
    host = tmp_path / "runtime"
    _write(host, b"runtime", 0o644)
    contract = _native_trace_contract(host)

    assert admin._native_builder_validate_trace_contract(contract) == contract
    assert admin._native_builder_trace_toolchain(contract) == [
        {
            key: contract["host_files"][0][key]  # type: ignore[index]
            for key in ("path", "canonical", "mode", "pin")
        }
    ]
    tools = {
        "compiler": {"pin": {"sha256": "1" * 64, "size_bytes": 1}},
        "readelf": {"pin": {"sha256": "2" * 64, "size_bytes": 2}},
        "tracer": {"pin": {"sha256": "3" * 64, "size_bytes": 3}},
        "toolchain": admin._native_builder_trace_toolchain(contract),
    }
    trace_raw = admin.canonical_json(contract)
    assert admin._native_builder_job_tools(tools, contract)["trace_contract"] == {
        "schema": admin.NATIVE_BUILDER_TRACE_CONTRACT_SCHEMA,
        "sha256": hashlib.sha256(trace_raw).hexdigest(),
        "size_bytes": len(trace_raw),
    }

    missing_profile = copy.deepcopy(contract)
    missing_profile["profiles"] = missing_profile["profiles"][:-1]  # type: ignore[index]
    with pytest.raises(admin.AuthorityError, match="TRACE_CONTRACT_INVALID"):
        admin._native_builder_validate_trace_contract(missing_profile)

    orphan = copy.deepcopy(contract)
    orphan["profiles"][0]["host_directories"] = []  # type: ignore[index]
    for profile in orphan["profiles"][1:]:  # type: ignore[index]
        profile["host_directories"] = []
    with pytest.raises(admin.AuthorityError, match="TRACE_CONTRACT_INVALID"):
        admin._native_builder_validate_trace_contract(orphan)

    invalid_scratch = copy.deepcopy(contract)
    invalid_scratch["profiles"][0]["scratch_prestate"] = [  # type: ignore[index]
        {
            "relative_path": "../escape",
            "kind": "directory",
            "mode": "0700",
        }
    ]
    with pytest.raises(admin.AuthorityError, match="TRACE_CONTRACT_INVALID"):
        admin._native_builder_validate_trace_contract(invalid_scratch)

    assert admin._native_builder_valid_trace_event(
        _native_trace_event("openat", "/dev/null", "OK", open_flags=["O_RDWR"])
    )
    assert not admin._native_builder_valid_trace_event(
        _native_trace_event("openat", "/dev/null", "OK", open_flags=["O_WRONLY"])
    )
    assert not admin._native_builder_valid_trace_event(
        _native_trace_event(
            "openat",
            "/dev/null",
            "OK",
            open_flags=["O_RDWR", "O_TRUNC"],
        )
    )


def test_native_builder_trace_inputs_hold_empty_bytes_and_reject_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(admin, "ROOT_UID", os.getuid())
    monkeypatch.setattr(admin, "ROOT_GID", os.getgid())
    monkeypatch.setattr(
        admin,
        "_native_builder_component_chain_is_immutable_root_owned",
        lambda _chain: True,
    )
    host = tmp_path / "empty-runtime.py"
    _write(host, b"", 0o644)
    contract = _native_trace_contract(host)
    admin._native_builder_validate_trace_contract(contract)
    authority = admin.HeldNativeBuilderPhase(
        contextlib.ExitStack(), {}, {}, {}, {}, {}, {}
    )
    try:
        admin._native_builder_hold_trace_inputs(authority, contract)
        authority.revalidate()
        _write(host, b"replacement", 0o644)
        with pytest.raises(
            admin.AuthorityError, match="NATIVE_BUILDER_(?:AUTHORITY|TRACE_INPUT)_DRIFT"
        ):
            authority.revalidate()
    finally:
        authority.close()


def test_native_builder_kernel_virtual_contract_mirror_and_held_revalidation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    contract = _native_trace_contract_with_kernel_virtual()
    assert admin._native_builder_validate_trace_contract(contract) == contract
    special = next(
        record
        for record in contract["host_files"]  # type: ignore[union-attr]
        if record["path"] == str(admin.NATIVE_BUILDER_KERNEL_VIRTUAL_SYSCTL_PATH)
    )
    assert admin.NATIVE_BUILDER_KERNEL_VIRTUAL_SYSCTL_PATH.stat().st_size == 0
    assert special["storage"] == "kernel_virtual"
    assert special["pin"]["size_bytes"] == 2
    assert special["pin"] in [
        pin.public() for pin in admin._native_builder_kernel_virtual_sysctl_pins()
    ]
    assert [item["path"] for item in special["component_chain"]] == list(
        admin.NATIVE_BUILDER_KERNEL_VIRTUAL_COMPONENT_PATHS
    )
    assert admin.NATIVE_BUILDER_TRACE_CONTRACT_SCHEMA.endswith("/v5")
    root, *proc_components = special["component_chain"]
    assert "metadata_policy" not in root
    assert all(
        field in root
        for field in admin.NATIVE_BUILDER_KERNEL_VIRTUAL_VOLATILE_METADATA_FIELDS
    )
    assert all(
        component["metadata_policy"]
        == admin.NATIVE_BUILDER_KERNEL_VIRTUAL_COMPONENT_POLICY
        and all(
            field not in component
            for field in admin.NATIVE_BUILDER_KERNEL_VIRTUAL_VOLATILE_METADATA_FIELDS
        )
        for component in proc_components
    )
    assert "nlink" not in proc_components[0]
    assert all("nlink" in component for component in proc_components[1:])

    authority = admin.HeldNativeBuilderPhase(
        contextlib.ExitStack(), {}, {}, {}, {}, {}, {}
    )
    admin._native_builder_hold_trace_inputs(authority, contract)
    try:
        authority.revalidate()
        original_lstat = os.lstat
        drift: dict[str, str | None] = {"nlink_path": None}

        def changing_proc_lstat(
            candidate: os.PathLike[str] | str, *args: object, **kwargs: object
        ) -> object:
            info = original_lstat(candidate, *args, **kwargs)
            candidate_text = os.fspath(candidate)
            if (
                candidate_text
                not in admin.NATIVE_BUILDER_KERNEL_VIRTUAL_METADATA_VOLATILE_PATHS
            ):
                return info
            return type(
                "ProcStat",
                (),
                {
                    "st_mode": info.st_mode,
                    "st_uid": info.st_uid,
                    "st_gid": info.st_gid,
                    "st_dev": info.st_dev + 211,
                    "st_ino": info.st_ino + 223,
                    "st_nlink": info.st_nlink
                    + (31 if candidate_text == "/proc" else 0)
                    + (1 if candidate_text == drift["nlink_path"] else 0),
                    "st_size": info.st_size,
                    "st_blocks": info.st_blocks,
                    "st_mtime_ns": info.st_mtime_ns + 227,
                    "st_ctime_ns": info.st_ctime_ns + 229,
                },
            )()

        monkeypatch.setattr(admin.os, "lstat", changing_proc_lstat)
        authority.revalidate()
        drift["nlink_path"] = "/proc/sys/vm"
        with pytest.raises(
            admin.AuthorityError, match="NATIVE_BUILDER_TRACE_INPUT_DRIFT"
        ):
            authority.revalidate()
        drift["nlink_path"] = None
        original_hash = admin._hash_kernel_virtual_sysctl_fd
        monkeypatch.setattr(
            admin,
            "_hash_kernel_virtual_sysctl_fd",
            lambda _descriptor: ("0" * 64, 2),
        )
        with pytest.raises(
            admin.AuthorityError, match="NATIVE_BUILDER_AUTHORITY_DRIFT"
        ):
            authority.revalidate()
        monkeypatch.setattr(admin, "_hash_kernel_virtual_sysctl_fd", original_hash)
    finally:
        authority.close()


def test_native_builder_kernel_virtual_reader_mirror_rejects_malformed_bytes(
    tmp_path: Path,
) -> None:
    target = tmp_path / "finite-sysctl"
    for raw in admin.NATIVE_BUILDER_KERNEL_VIRTUAL_SYSCTL_VALUES:
        _write(target, raw)
        descriptor = os.open(target, os.O_RDONLY | os.O_CLOEXEC)
        try:
            assert admin._hash_kernel_virtual_sysctl_fd(descriptor) == (
                hashlib.sha256(raw).hexdigest(),
                len(raw),
            )
        finally:
            os.close(descriptor)

    for malformed in (b"", b"1", b"3\n", b"1\nx"):
        _write(target, malformed)
        descriptor = os.open(target, os.O_RDONLY | os.O_CLOEXEC)
        try:
            with pytest.raises(
                admin.AuthorityError, match="NATIVE_BUILDER_TRACE_INPUT_DRIFT"
            ):
                admin._hash_kernel_virtual_sysctl_fd(descriptor)
        finally:
            os.close(descriptor)


def test_native_builder_kernel_virtual_contract_mirror_rejects_tampering() -> None:
    contract = _native_trace_contract_with_kernel_virtual()

    stale = copy.deepcopy(contract)
    stale["schema"] = "vista.r8-native-builder-trace-contract/v4"
    with pytest.raises(admin.AuthorityError, match="TRACE_CONTRACT_INVALID"):
        admin._native_builder_validate_trace_contract(stale)

    runtime_smuggle = copy.deepcopy(contract)
    runtime_smuggle["tracer_runtime_files"] = sorted(  # type: ignore[index]
        [
            *runtime_smuggle["tracer_runtime_files"],  # type: ignore[index]
            str(admin.NATIVE_BUILDER_KERNEL_VIRTUAL_SYSCTL_PATH),
        ]
    )
    with pytest.raises(admin.AuthorityError, match="TRACE_CONTRACT_INVALID"):
        admin._native_builder_validate_trace_contract(runtime_smuggle)

    orphan = copy.deepcopy(contract)
    first = orphan["profiles"][0]  # type: ignore[index]
    first["host_files"].remove(str(admin.NATIVE_BUILDER_KERNEL_VIRTUAL_SYSCTL_PATH))
    with pytest.raises(admin.AuthorityError, match="TRACE_CONTRACT_INVALID"):
        admin._native_builder_validate_trace_contract(orphan)

    missing_event = copy.deepcopy(contract)
    first = missing_event["profiles"][0]  # type: ignore[index]
    first["event_multiset"] = [
        item
        for item in first["event_multiset"]
        if str(admin.NATIVE_BUILDER_KERNEL_VIRTUAL_SYSCTL_PATH) not in item["line"]
    ]
    with pytest.raises(admin.AuthorityError, match="TRACE_CONTRACT_INVALID"):
        admin._native_builder_validate_trace_contract(missing_event)

    failed_write = copy.deepcopy(contract)
    first = failed_write["profiles"][0]  # type: ignore[index]
    first["event_multiset"] = sorted(
        [
            item
            for item in first["event_multiset"]
            if str(admin.NATIVE_BUILDER_KERNEL_VIRTUAL_SYSCTL_PATH) not in item["line"]
        ]
        + [
            {
                "line": _native_trace_event(
                    "openat",
                    str(admin.NATIVE_BUILDER_KERNEL_VIRTUAL_SYSCTL_PATH),
                    "EACCES",
                    open_flags=["O_WRONLY"],
                ),
                "count": 1,
            }
        ],
        key=lambda item: item["line"],
    )
    with pytest.raises(admin.AuthorityError, match="TRACE_CONTRACT_INVALID"):
        admin._native_builder_validate_trace_contract(failed_write)

    for field, value in (
        ("storage", "regular"),
        (
            "pin",
            {"sha256": hashlib.sha256(b"3\n").hexdigest(), "size_bytes": 2},
        ),
        ("mode", "0600"),
    ):
        changed = copy.deepcopy(contract)
        special = next(
            record
            for record in changed["host_files"]  # type: ignore[union-attr]
            if record["path"] == str(admin.NATIVE_BUILDER_KERNEL_VIRTUAL_SYSCTL_PATH)
        )
        special[field] = value
        with pytest.raises(admin.AuthorityError, match="TRACE_CONTRACT_INVALID"):
            admin._native_builder_validate_trace_contract(changed)

    for index, field in ((1, "device"), (2, "inode"), (-1, "ctime_ns")):
        changed = copy.deepcopy(contract)
        special = next(
            record
            for record in changed["host_files"]  # type: ignore[union-attr]
            if record["path"] == str(admin.NATIVE_BUILDER_KERNEL_VIRTUAL_SYSCTL_PATH)
        )
        special["component_chain"][index][field] = 1
        with pytest.raises(admin.AuthorityError, match="TRACE_CONTRACT_INVALID"):
            admin._native_builder_validate_trace_contract(changed)

    other_proc = copy.deepcopy(contract)
    special = next(
        record
        for record in other_proc["host_files"]  # type: ignore[union-attr]
        if record["path"] == str(admin.NATIVE_BUILDER_KERNEL_VIRTUAL_SYSCTL_PATH)
    )
    special["path"] = special["canonical"] = "/proc/sys/vm/swappiness"
    special["component_chain"][-1]["path"] = "/proc/sys/vm/swappiness"
    other_proc["host_files"] = sorted(  # type: ignore[index]
        other_proc["host_files"],
        key=lambda item: item["path"],  # type: ignore[index]
    )
    with pytest.raises(admin.AuthorityError, match="TRACE_CONTRACT_INVALID"):
        admin._native_builder_validate_trace_contract(other_proc)


def test_native_builder_kernel_virtual_hold_rejects_component_drift() -> None:
    contract = _native_trace_contract_with_kernel_virtual()
    for index, field, value in (
        (2, "device", 1),
        (2, "nlink", 1),
        (-1, "inode", 1),
        (-1, "mode", "0600"),
    ):
        changed = copy.deepcopy(contract)
        special = next(
            record
            for record in changed["host_files"]  # type: ignore[union-attr]
            if record["path"] == str(admin.NATIVE_BUILDER_KERNEL_VIRTUAL_SYSCTL_PATH)
        )
        if field == "nlink":
            special["component_chain"][index][field] += value
        elif field in admin.NATIVE_BUILDER_KERNEL_VIRTUAL_VOLATILE_METADATA_FIELDS:
            special["component_chain"][index][field] = value
        else:
            special["component_chain"][index][field] = value
        authority = admin.HeldNativeBuilderPhase(
            contextlib.ExitStack(), {}, {}, {}, {}, {}, {}
        )
        try:
            with pytest.raises(
                admin.AuthorityError, match="NATIVE_BUILDER_TRACE_INPUT_DRIFT"
            ):
                admin._native_builder_hold_trace_inputs(authority, changed)
        finally:
            authority.close()


def test_native_builder_trace_contract_rejects_unmodelled_symlink_alias(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(admin, "ROOT_UID", os.getuid())
    monkeypatch.setattr(admin, "ROOT_GID", os.getgid())
    host = tmp_path / "runtime"
    _write(host, b"runtime", 0o644)
    alias = tmp_path / "runtime-link"
    alias.symlink_to(host.name)
    contract = _native_trace_contract(host)
    alias_record = copy.deepcopy(contract["host_files"][0])  # type: ignore[index]
    alias_record["path"] = str(alias)
    alias_record["canonical"] = str(host)
    alias_record["component_chain"] = admin._native_builder_live_component_chain(
        alias, "alias"
    )
    contract["host_files"] = sorted(  # type: ignore[index]
        [contract["host_files"][0], alias_record],  # type: ignore[index]
        key=lambda item: item["path"],
    )
    for profile in contract["profiles"]:  # type: ignore[index]
        profile["host_files"] = sorted((str(host), str(alias)))
    contract["tracer_runtime_files"] = sorted((str(host), str(alias)))
    contract["builder_runtime_files"] = sorted((str(host), str(alias)))
    with pytest.raises(admin.AuthorityError, match="TRACE_CONTRACT_INVALID"):
        admin._native_builder_validate_trace_contract(contract)


def test_native_builder_flags_pin_active_input_macro_and_closed_compiler_mode() -> None:
    bindings = {
        "launcher_pin": {"sha256": "1" * 64, "size_bytes": 1},
        "helper_pin": {"sha256": "2" * 64, "size_bytes": 2},
        "input_pin": {"sha256": "3" * 64, "size_bytes": 3},
    }
    flags = admin._native_builder_expected_flags(
        "initial-bootstrap-installer", bindings
    )
    assert "-pipe" in flags
    assert "-fno-use-linker-plugin" in flags
    assert '-DEXPECTED_INPUT_PIN_SHA256="' + ("3" * 64) + '"' in flags
    assert not any(flag.startswith("-DEXPECTED_INPUT_SHA256=") for flag in flags)


def test_native_builder_independent_consumer_mirror_matches_producer_contract() -> None:
    assert admin.NATIVE_BUILDER_REQUEST_SCHEMA == native_builder.REQUEST_SCHEMA
    assert (
        admin.NATIVE_BUILDER_TRACE_CONTRACT_SCHEMA
        == native_builder.TRACE_CONTRACT_SCHEMA
    )
    assert admin.NATIVE_BUILDER_STRACE_VERSION == native_builder.STRACE_VERSION
    assert admin.NATIVE_BUILDER_CPU_ONLINE_PATH == native_builder.CPU_ONLINE_PATH
    assert (
        admin.NATIVE_BUILDER_CPU_ONLINE_READ_EVENT_LINE
        == native_builder.CPU_ONLINE_READ_EVENT_LINE
    )
    assert (
        admin.NATIVE_BUILDER_CPU_ONLINE_EVENT_COUNT_POLICY
        == native_builder.CPU_ONLINE_EVENT_COUNT_POLICY
    )
    assert (
        admin._native_builder_trace_event_count_policies()
        == native_builder._trace_event_count_policies()
    )
    assert admin.NATIVE_BUILDER_SOURCE_PATHS == native_builder.SOURCE_PATHS
    assert (
        admin.NATIVE_BUILDER_TRACE_FILE_SYSCALLS == native_builder.TRACE_FILE_SYSCALLS
    )
    assert (
        admin.NATIVE_BUILDER_TRACE_ALLOWED_ERRNOS == native_builder.TRACE_ALLOWED_ERRNOS
    )
    assert (
        admin.NATIVE_BUILDER_TRACE_OPEN_SYSCALLS == native_builder.TRACE_OPEN_SYSCALLS
    )
    assert (
        admin.NATIVE_BUILDER_TRACE_OPEN_ACCESS_MODES
        == native_builder.TRACE_OPEN_ACCESS_MODES
    )
    assert (
        admin.NATIVE_BUILDER_TRACE_OPEN_FLAG_TOKENS
        == native_builder.TRACE_OPEN_FLAG_TOKENS
    )
    assert (
        admin.NATIVE_BUILDER_TRACE_DEV_NULL_ALLOWED_NONMUTATING_FLAGS
        == native_builder.TRACE_DEV_NULL_ALLOWED_NONMUTATING_FLAGS
    )
    assert (
        admin.NATIVE_BUILDER_KERNEL_VIRTUAL_SYSCTL_PATH
        == native_builder.KERNEL_VIRTUAL_SYSCTL_PATH
    )
    assert (
        admin.NATIVE_BUILDER_KERNEL_VIRTUAL_COMPONENT_POLICY
        == native_builder.KERNEL_VIRTUAL_COMPONENT_POLICY
    )
    assert (
        admin.NATIVE_BUILDER_KERNEL_VIRTUAL_SYSCTL_VALUES
        == native_builder.KERNEL_VIRTUAL_SYSCTL_VALUES
    )
    assert (
        admin.NATIVE_BUILDER_KERNEL_VIRTUAL_COMPONENT_PATHS
        == native_builder.KERNEL_VIRTUAL_COMPONENT_PATHS
    )
    assert (
        admin.NATIVE_BUILDER_KERNEL_VIRTUAL_COMPONENT_KINDS
        == native_builder.KERNEL_VIRTUAL_COMPONENT_KINDS
    )
    assert (
        admin.NATIVE_BUILDER_KERNEL_VIRTUAL_METADATA_VOLATILE_PATHS
        == native_builder.KERNEL_VIRTUAL_METADATA_VOLATILE_PATHS
    )
    assert (
        admin.NATIVE_BUILDER_KERNEL_VIRTUAL_NLINK_VOLATILE_PATHS
        == native_builder.KERNEL_VIRTUAL_NLINK_VOLATILE_PATHS
    )
    assert (
        admin.NATIVE_BUILDER_KERNEL_VIRTUAL_VOLATILE_METADATA_FIELDS
        == native_builder.KERNEL_VIRTUAL_VOLATILE_METADATA_FIELDS
    )
    assert (
        admin.NATIVE_BUILDER_KERNEL_VIRTUAL_ALLOWED_OPEN_FLAGS
        == native_builder.KERNEL_VIRTUAL_ALLOWED_OPEN_FLAGS
    )
    assert (
        admin.NATIVE_BUILDER_KERNEL_VIRTUAL_READ_SYSCALLS
        == native_builder.KERNEL_VIRTUAL_READ_SYSCALLS
    )
    assert admin.NATIVE_BUILDER_BUILD_ENVIRONMENT == native_builder.BUILD_ENVIRONMENT
    for phase in ("phase-a", "phase-b"):
        assert admin._native_builder_expected_trace_invocations(
            phase
        ) == native_builder._expected_trace_invocations(phase)
    bindings = {
        "launcher_pin": {"sha256": "1" * 64, "size_bytes": 1},
        "helper_pin": {"sha256": "2" * 64, "size_bytes": 2},
        "input_pin": {"sha256": "3" * 64, "size_bytes": 3},
    }
    assert admin._native_builder_expected_flags(
        "initial-bootstrap-installer", bindings
    ) == native_builder.expected_job_flags("initial-bootstrap-installer", bindings)


def test_native_builder_independent_consumer_closes_cpu_online_read_count() -> None:
    event = {
        "line": admin.NATIVE_BUILDER_CPU_ONLINE_READ_EVENT_LINE,
        "count": 1,
    }
    assert admin._native_builder_validate_trace_events([event], "cpu-online") == [
        event
    ]
    invalid = {**event, "count": 2}
    with pytest.raises(admin.AuthorityError, match="TRACE_CONTRACT_INVALID"):
        admin._native_builder_validate_trace_events([invalid], "cpu-online")


def test_native_builder_cpu_online_policy_is_profile_and_host_bound() -> None:
    contract = _native_trace_contract_with_kernel_virtual()
    cpu_record = native_builder._planner_trace_file_record(
        native_builder.CPU_ONLINE_PATH
    )
    contract["host_files"] = sorted(  # type: ignore[index]
        [*contract["host_files"], cpu_record],  # type: ignore[index]
        key=lambda item: item["path"],
    )
    fetch = next(
        profile
        for profile in contract["profiles"]  # type: ignore[union-attr]
        if profile["id"] == "git:fetch"
    )
    fetch["host_files"] = sorted(  # type: ignore[index]
        [*fetch["host_files"], native_builder.CPU_ONLINE_PATH]  # type: ignore[index]
    )
    fetch["event_multiset"] = sorted(  # type: ignore[index]
        [
            *fetch["event_multiset"],  # type: ignore[index]
            {"line": native_builder.CPU_ONLINE_READ_EVENT_LINE, "count": 1},
        ],
        key=lambda item: item["line"],
    )
    assert admin._native_builder_validate_trace_contract(contract) == contract

    wrong_profile = copy.deepcopy(contract)
    wrong_fetch = next(
        profile
        for profile in wrong_profile["profiles"]  # type: ignore[union-attr]
        if profile["id"] == "git:fetch"
    )
    wrong_init = next(
        profile
        for profile in wrong_profile["profiles"]  # type: ignore[union-attr]
        if profile["id"] == "git:init"
    )
    wrong_fetch["host_files"].remove(native_builder.CPU_ONLINE_PATH)  # type: ignore[union-attr]
    wrong_fetch["event_multiset"] = [  # type: ignore[index]
        item
        for item in wrong_fetch["event_multiset"]  # type: ignore[union-attr]
        if item["line"] != native_builder.CPU_ONLINE_READ_EVENT_LINE
    ]
    wrong_init["host_files"] = sorted(  # type: ignore[index]
        [*wrong_init["host_files"], native_builder.CPU_ONLINE_PATH]  # type: ignore[index]
    )
    wrong_init["event_multiset"] = sorted(  # type: ignore[index]
        [
            *wrong_init["event_multiset"],  # type: ignore[index]
            {"line": native_builder.CPU_ONLINE_READ_EVENT_LINE, "count": 1},
        ],
        key=lambda item: item["line"],
    )
    with pytest.raises(admin.AuthorityError, match="cpu online event profile"):
        admin._native_builder_validate_trace_contract(wrong_profile)

    unbound_event = copy.deepcopy(contract)
    unbound_fetch = next(
        profile
        for profile in unbound_event["profiles"]  # type: ignore[union-attr]
        if profile["id"] == "git:fetch"
    )
    unbound_fetch["host_files"].remove(native_builder.CPU_ONLINE_PATH)  # type: ignore[union-attr]
    with pytest.raises(admin.AuthorityError, match="cpu online profile binding"):
        admin._native_builder_validate_trace_contract(unbound_event)

    runtime_smuggle = copy.deepcopy(contract)
    runtime_smuggle["builder_runtime_files"] = sorted(  # type: ignore[index]
        [
            *runtime_smuggle["builder_runtime_files"],  # type: ignore[index]
            native_builder.CPU_ONLINE_PATH,
        ]
    )
    with pytest.raises(admin.AuthorityError, match="builder_runtime_files"):
        admin._native_builder_validate_trace_contract(runtime_smuggle)

    policy_drift = copy.deepcopy(contract)
    policy_drift["event_count_policies"][0]["profile_id"] = "git:init"  # type: ignore[index]
    with pytest.raises(admin.AuthorityError, match="event count policies"):
        admin._native_builder_validate_trace_contract(policy_drift)
    for invalid_count in (True, 1.0):
        type_drift = copy.deepcopy(contract)
        type_drift["event_count_policies"][0]["canonical_count"] = invalid_count  # type: ignore[index]
        with pytest.raises(admin.AuthorityError, match="event count policies"):
            admin._native_builder_validate_trace_contract(type_drift)
    for policies in ([], admin._native_builder_trace_event_count_policies() * 2):
        cardinality_drift = copy.deepcopy(contract)
        cardinality_drift["event_count_policies"] = policies
        with pytest.raises(admin.AuthorityError, match="event count policies"):
            admin._native_builder_validate_trace_contract(cardinality_drift)


@pytest.mark.parametrize("replacement_kind", ["commit", "tree", "blob"])
def test_git_review_binding_ignores_replace_refs_and_hostile_global_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    replacement_kind: str,
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    source = repository / "reviewed.txt"
    _run_test_git(repository, "init", "-b", "main")
    _write(source, b"reviewed\n")
    _run_test_git(repository, "add", "--", source.name)
    _run_test_git(
        repository,
        "-c",
        "user.name=VISTA test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-m",
        "reviewed",
    )
    original_commit = _run_test_git(repository, "rev-parse", "HEAD")
    original_tree = _run_test_git(repository, "rev-parse", "HEAD^{tree}")
    original_blob = _run_test_git(repository, "rev-parse", "HEAD:reviewed.txt")

    _run_test_git(repository, "switch", "-c", "hostile")
    _write(source, b"hostile replacement\n")
    _run_test_git(repository, "add", "--", source.name)
    _run_test_git(
        repository,
        "-c",
        "user.name=VISTA test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-m",
        "hostile",
    )
    hostile_commit = _run_test_git(repository, "rev-parse", "HEAD")
    hostile_tree = _run_test_git(repository, "rev-parse", "HEAD^{tree}")
    hostile_blob = _run_test_git(repository, "rev-parse", "HEAD:reviewed.txt")
    _run_test_git(repository, "switch", "main")
    original, hostile = {
        "commit": (original_commit, hostile_commit),
        "tree": (original_tree, hostile_tree),
        "blob": (original_blob, hostile_blob),
    }[replacement_kind]
    _run_test_git(repository, "replace", original, hostile)

    hostile_home = tmp_path / "hostile-home"
    hostile_home.mkdir()
    hostile_config = hostile_home / ".gitconfig"
    _write(
        hostile_config,
        b"[core]\n\tworktree = /nonexistent-hostile-worktree\n"
        b"[alias]\n\tshow = !exit 97\n",
    )
    monkeypatch.setenv("HOME", str(hostile_home))
    monkeypatch.setenv("XDG_CONFIG_HOME", str(hostile_home))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(hostile_config))
    monkeypatch.setattr(admin, "CHECKOUT_ROOT", repository)
    monkeypatch.setattr(admin, "BUNDLE_SOURCE_PATHS", {"fixture": source})
    for name in (
        "LAUNCHER_SOURCE",
        "REVIEW_HELPER_SOURCE",
        "ADMIN_LAUNCHER_SOURCE",
        "STAGE_INSTALLER_SOURCE",
        "STAGE_TRANSFER_LAUNCHER_SOURCE",
        "ENGINE_WRAPPER_SOURCE",
        "BUILDPLUGIN_HELPER_SOURCE",
        "PARENT_SEAL_HELPER_SOURCE",
        "PARENT_SEAL_LAUNCHER_SOURCE",
        "INITIAL_BOOTSTRAP_HELPER_SOURCE",
        "INITIAL_BOOTSTRAP_INSTALLER_SOURCE",
        "INITIAL_BOOTSTRAP_LAUNCHER_SOURCE",
    ):
        monkeypatch.setattr(admin, name, source)
    monkeypatch.setattr(admin, "_reviewed_git_relative_paths", lambda: [source.name])

    binding, committed = admin._git_source_binding(return_committed_sources=True)

    assert binding["commit"] == original_commit
    assert committed == {source.name: b"reviewed\n"}
    assert source.read_bytes() == b"reviewed\n"


def test_git_review_binding_captures_commit_before_concurrent_ref_and_worktree_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    repository = tmp_path / "repository"
    repository.mkdir()
    source = repository / "reviewed.txt"
    _run_test_git(repository, "init", "-b", "main")
    _write(source, b"reviewed\n")
    _run_test_git(repository, "add", "--", source.name)
    _run_test_git(
        repository,
        "-c",
        "user.name=VISTA test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-m",
        "reviewed",
    )
    original_commit = _run_test_git(repository, "rev-parse", "HEAD")
    _run_test_git(repository, "switch", "-c", "hostile")
    _write(source, b"concurrent hostile replacement\n")
    _run_test_git(repository, "add", "--", source.name)
    _run_test_git(
        repository,
        "-c",
        "user.name=VISTA test",
        "-c",
        "user.email=test@example.invalid",
        "commit",
        "-m",
        "hostile",
    )
    _run_test_git(repository, "switch", "main")
    assert _run_test_git(repository, "rev-parse", "HEAD") == original_commit
    assert source.read_bytes() == b"reviewed\n"

    monkeypatch.setattr(admin, "CHECKOUT_ROOT", repository)
    monkeypatch.setattr(admin, "BUNDLE_SOURCE_PATHS", {"fixture": source})
    for name in (
        "LAUNCHER_SOURCE",
        "REVIEW_HELPER_SOURCE",
        "ADMIN_LAUNCHER_SOURCE",
        "STAGE_INSTALLER_SOURCE",
        "STAGE_TRANSFER_LAUNCHER_SOURCE",
        "ENGINE_WRAPPER_SOURCE",
        "BUILDPLUGIN_HELPER_SOURCE",
        "PARENT_SEAL_HELPER_SOURCE",
        "PARENT_SEAL_LAUNCHER_SOURCE",
        "INITIAL_BOOTSTRAP_HELPER_SOURCE",
        "INITIAL_BOOTSTRAP_INSTALLER_SOURCE",
        "INITIAL_BOOTSTRAP_LAUNCHER_SOURCE",
    ):
        monkeypatch.setattr(admin, name, source)
    monkeypatch.setattr(admin, "_reviewed_git_relative_paths", lambda: [source.name])

    real_run = subprocess.run
    switched = False

    def switch_after_commit_capture(
        command: list[str], *args: object, **kwargs: object
    ) -> subprocess.CompletedProcess[object]:
        nonlocal switched
        result = real_run(command, *args, **kwargs)
        if (
            not switched
            and "rev-parse" in command
            and any(argument.startswith("HEAD") for argument in command)
        ):
            switched = True
            real_run(
                ["/usr/bin/git", "-C", str(repository), "switch", "hostile"],
                check=True,
                env={
                    "PATH": "/usr/bin:/bin",
                    "HOME": "/nonexistent",
                    "LANG": "C",
                    "LC_ALL": "C",
                    "GIT_CONFIG_NOSYSTEM": "1",
                    "GIT_CONFIG_GLOBAL": "/dev/null",
                    "GIT_CONFIG_COUNT": "0",
                    "GIT_NO_REPLACE_OBJECTS": "1",
                    "GIT_TERMINAL_PROMPT": "0",
                },
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        return result

    monkeypatch.setattr(admin.subprocess, "run", switch_after_commit_capture)
    with pytest.raises(admin.AuthorityError, match="source differs from commit"):
        admin._git_source_binding(return_committed_sources=True)
    assert switched
    assert _run_test_git(repository, "rev-parse", "HEAD") != original_commit
    assert source.read_bytes() == b"concurrent hostile replacement\n"


def test_git_review_tree_parser_requires_exact_regular_blob_inventory() -> None:
    expected = ["a.txt", "dir/b.sh"]
    raw = (
        b"100644 blob " + (b"1" * 40) + b"\ta.txt\0"
        b"100755 blob " + (b"2" * 40) + b"\tdir/b.sh\0"
    )
    assert admin._parse_reviewed_git_tree(raw, expected) == {
        "a.txt": "1" * 40,
        "dir/b.sh": "2" * 40,
    }
    invalid = [
        b"120000 blob " + (b"1" * 40) + b"\ta.txt\0",
        b"100644 tree " + (b"1" * 40) + b"\ta.txt\0",
        b"100644 blob " + (b"z" * 40) + b"\ta.txt\0",
        raw + b"100644 blob " + (b"3" * 40) + b"\ta.txt\0",
        raw.removesuffix(b"\0"),
    ]
    for candidate in invalid:
        with pytest.raises(admin.AuthorityError, match="GIT_SOURCE_INVALID"):
            admin._parse_reviewed_git_tree(candidate, expected)


def _buildplugin_state_documents(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[dict[str, object], dict[str, object], admin.TreeSnapshot, admin.FilePin]:
    uid, gid = os.getuid(), os.getgid()
    authority = tmp_path / "buildplugin-authority"
    payload = authority / "payload"
    payload.mkdir(parents=True)
    payload.chmod(0o555)
    helper = tmp_path / "buildplugin-helper/vista_r8_buildplugin_authority.py"
    admin_root = tmp_path / "buildplugin-admin"
    admin_launcher = admin_root / "publish-reconcile-buildplugin"
    admin_receipt = admin_root / "receipt.json"
    python = tmp_path / "python3.10"
    monkeypatch.setattr(admin, "ROOT_UID", uid)
    monkeypatch.setattr(admin, "ROOT_GID", gid)
    monkeypatch.setattr(admin, "BUILDPLUGIN_AUTHORITY", authority)
    monkeypatch.setattr(admin, "BUILDPLUGIN_PAYLOAD", payload)
    monkeypatch.setattr(admin, "BUILDPLUGIN_HELPER_INSTALL_PATH", helper)
    monkeypatch.setattr(admin, "BUILDPLUGIN_ADMIN_INSTALL_ROOT", admin_root)
    monkeypatch.setattr(admin, "BUILDPLUGIN_ADMIN_INSTALL_PATH", admin_launcher)
    monkeypatch.setattr(admin, "BUILDPLUGIN_ADMIN_RECEIPT_PATH", admin_receipt)
    monkeypatch.setattr(admin, "PYTHON_PATH", python)
    monkeypatch.setattr(admin, "_require_parent", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        admin, "_require_exact_directory", lambda *_args, **_kwargs: None
    )
    monkeypatch.setattr(admin.os, "geteuid", lambda: uid + 1)
    snapshot = admin.TreeSnapshot(
        root=payload,
        root_device=os.lstat(payload).st_dev,
        entries=(),
        tree_digest="a" * 64,
        projection_sha256="b" * 64,
        file_count=0,
        directory_count=0,
        total_bytes=0,
    )
    monkeypatch.setattr(admin, "snapshot_tree", lambda _root: snapshot)
    manifest_pin = admin.FilePin("c" * 64, 101)
    manifest = {
        "schema_version": admin.BUILDPLUGIN_MANIFEST_SCHEMA,
        "source": {
            "path": str(tmp_path / "reviewed-source"),
            "projection_sha256": snapshot.projection_sha256,
            "inventory_sha256": "d" * 64,
            "file_count": 0,
            "directory_count": 1,
            "total_bytes": 0,
        },
        "authority": {
            "root": str(authority),
            "payload": str(payload),
            "directory_mode": "0555",
            "file_mode": "0444",
        },
        "critical_files": [],
        "entries": [
            {
                "kind": "directory",
                "path": ".",
                "source_mode": "0o755",
                "authority_mode": "0555",
            }
        ],
    }
    bootstrap = {
        "core_review_audit_pin": {"sha256": "e" * 64, "size_bytes": 102},
        "content_digest": "f" * 64,
    }
    receipt = admin.seal_document(
        {
            "schema_version": admin.BUILDPLUGIN_RECEIPT_SCHEMA,
            "accepted": True,
            "status": "root_published_immutable_buildplugin_authority",
            "source": manifest["source"],
            "authority": {
                "root": str(authority),
                "payload": str(payload),
                "payload_projection_sha256": snapshot.projection_sha256,
                "manifest": {
                    "path": "manifest.json",
                    "sha256": manifest_pin.sha256,
                    "size_bytes": manifest_pin.size_bytes,
                },
                "root_owned_nonwritable": True,
            },
            "publisher": {
                "helper": {
                    "path": str(helper),
                    "sha256": "1" * 64,
                    "size_bytes": 103,
                    "mode": "0500",
                },
                "interpreter": {
                    "path": str(python),
                    "sha256": "2" * 64,
                    "size_bytes": 104,
                    "mode": "0755",
                },
            },
            "admin_publication": {
                "authority_root": str(admin_root),
                "authority_mode": "0555",
                "launcher": {
                    "name": admin_launcher.name,
                    "path": str(admin_launcher),
                    "sha256": "3" * 64,
                    "size_bytes": 105,
                    "mode": "0500",
                },
                "receipt": {
                    "name": admin_receipt.name,
                    "path": str(admin_receipt),
                    "sha256": "4" * 64,
                    "size_bytes": 106,
                    "mode": "0444",
                    "schema": admin.BUILDPLUGIN_ADMIN_RECEIPT_SCHEMA,
                    "content_digest": "5" * 64,
                },
                "bootstrap_provenance": bootstrap,
                "admin_launcher_fd_required": True,
            },
            "policy": {
                "copy_from_held_source_descriptors_only": True,
                "all_source_file_descriptors_held": True,
                "source_namespace_revalidated_after_copy": True,
                "fresh_staging_only": True,
                "atomic_publish": "renameat2_noreplace",
                "output_directory_mode": "0555",
                "output_file_mode": "0444",
            },
            "claims": dict(admin._BUILDPLUGIN_NEGATIVE_CLAIMS),
        }
    )
    return manifest, receipt, snapshot, manifest_pin


def test_load_buildplugin_state_accepts_closed_v2_admin_lineage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest, receipt, snapshot, manifest_pin = _buildplugin_state_documents(
        tmp_path, monkeypatch
    )
    receipt_pin = admin.FilePin("6" * 64, 107)

    def root_file(path: Path, _label: str, _mode: int = 0o444):
        if path.name == "manifest.json":
            return admin.canonical_json(manifest), manifest_pin
        return admin.canonical_json(receipt), receipt_pin

    monkeypatch.setattr(admin, "_root_file", root_file)
    state = admin._load_buildplugin_state()
    assert state["snapshot"] == snapshot
    assert state["receipt"]["schema_version"] == admin.BUILDPLUGIN_RECEIPT_SCHEMA
    assert state["receipt"]["admin_publication"]["admin_launcher_fd_required"] is True


@pytest.mark.parametrize(
    "mutation",
    (
        "v1",
        "missing-admin",
        "extra-admin-key",
        "rebound-admin-root",
        "fd-false",
        "fd-integer",
        "unknown-top-key",
    ),
)
def test_load_buildplugin_state_rejects_downgraded_or_rebound_admin_lineage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, mutation: str
) -> None:
    manifest, original, _snapshot, manifest_pin = _buildplugin_state_documents(
        tmp_path, monkeypatch
    )
    receipt = copy.deepcopy(original)
    if mutation == "v1":
        receipt["schema_version"] = "vista.r8-buildplugin-authority-receipt/v1"
    elif mutation == "missing-admin":
        receipt.pop("admin_publication")
    elif mutation == "extra-admin-key":
        receipt["admin_publication"]["unexpected"] = True
    elif mutation == "rebound-admin-root":
        receipt["admin_publication"]["authority_root"] = "/root/rebound-admin"
    elif mutation == "fd-false":
        receipt["admin_publication"]["admin_launcher_fd_required"] = False
    elif mutation == "fd-integer":
        receipt["admin_publication"]["admin_launcher_fd_required"] = 1
    else:
        receipt["unexpected"] = True
    receipt["content_digest"] = admin.content_digest(receipt)

    def root_file(path: Path, _label: str, _mode: int = 0o444):
        if path.name == "manifest.json":
            return admin.canonical_json(manifest), manifest_pin
        return admin.canonical_json(receipt), admin.FilePin("6" * 64, 107)

    monkeypatch.setattr(admin, "_root_file", root_file)
    with pytest.raises(admin.AuthorityError, match="BUILDPLUGIN_AUTHORITY_INVALID"):
        admin._load_buildplugin_state()


def _live_buildplugin_publication_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[dict[str, object], dict[str, object], dict[str, Path]]:
    uid, gid = os.getuid(), os.getgid()
    helper_root = tmp_path / "buildplugin-helper"
    helper = helper_root / "vista_r8_buildplugin_authority.py"
    python = tmp_path / "python3.10"
    admin_root = tmp_path / "buildplugin-admin"
    launcher = admin_root / "publish-reconcile-buildplugin"
    receipt_path = admin_root / "receipt.json"
    _write(helper, b"reviewed BuildPlugin helper\n", 0o500)
    _write(python, b"#!/bin/sh\n", 0o755)
    _write(launcher, b"#!/bin/sh\n# reviewed admin\n", 0o500)
    helper_pin = admin._read_regular(helper, "helper", exact_mode=0o500)[1]
    python_pin = admin._read_regular(python, "python", exact_mode=0o755)[1]
    launcher_pin = admin._read_regular(launcher, "launcher", exact_mode=0o500)[1]
    publisher = {
        "helper": {
            "path": str(helper),
            "sha256": helper_pin.sha256,
            "size_bytes": helper_pin.size_bytes,
            "mode": "0500",
        },
        "interpreter": {
            "path": str(python),
            "sha256": python_pin.sha256,
            "size_bytes": python_pin.size_bytes,
            "mode": "0755",
        },
    }
    bootstrap = {
        "core_review_audit_pin": {"sha256": "a" * 64, "size_bytes": 101},
        "content_digest": "b" * 64,
    }
    admin_receipt = admin.seal_document(
        {
            "schema": admin.BUILDPLUGIN_ADMIN_RECEIPT_SCHEMA,
            "status": "root_installed_immutable_buildplugin_admin_authority",
            "accepted": True,
            "authority_root": str(admin_root),
            "launcher": {
                "path": str(launcher),
                "pin": launcher_pin.public(),
                "mode": "0500",
            },
            "helper": {
                "path": str(helper),
                "pin": helper_pin.public(),
                "mode": "0500",
            },
            "interpreter": {
                "path": str(python),
                "pin": python_pin.public(),
                "mode": "0755",
            },
            "bootstrap_provenance": bootstrap,
            "claims": {
                "fresh_no_replace": True,
                "downstream_live_fsync_required": True,
                "admin_launcher_fd_required": True,
                "launcher_receipt_live_bound": True,
            },
        }
    )
    _write(receipt_path, admin.canonical_json(admin_receipt), 0o444)
    receipt_pin = admin._read_regular(receipt_path, "admin receipt", exact_mode=0o444)[
        1
    ]
    helper_root.chmod(0o555)
    admin_root.chmod(0o555)
    publication = {
        "authority_root": str(admin_root),
        "authority_mode": "0555",
        "launcher": {
            "name": launcher.name,
            "path": str(launcher),
            "sha256": launcher_pin.sha256,
            "size_bytes": launcher_pin.size_bytes,
            "mode": "0500",
        },
        "receipt": {
            "name": receipt_path.name,
            "path": str(receipt_path),
            "sha256": receipt_pin.sha256,
            "size_bytes": receipt_pin.size_bytes,
            "mode": "0444",
            "schema": admin.BUILDPLUGIN_ADMIN_RECEIPT_SCHEMA,
            "content_digest": admin_receipt["content_digest"],
        },
        "bootstrap_provenance": bootstrap,
        "admin_launcher_fd_required": True,
    }
    monkeypatch.setattr(admin, "ROOT_UID", uid)
    monkeypatch.setattr(admin, "ROOT_GID", gid)
    monkeypatch.setattr(admin, "BUILDPLUGIN_HELPER_INSTALL_ROOT", helper_root)
    monkeypatch.setattr(admin, "BUILDPLUGIN_HELPER_INSTALL_PATH", helper)
    monkeypatch.setattr(admin, "PYTHON_PATH", python)
    monkeypatch.setattr(admin, "BUILDPLUGIN_ADMIN_INSTALL_ROOT", admin_root)
    monkeypatch.setattr(admin, "BUILDPLUGIN_ADMIN_INSTALL_PATH", launcher)
    monkeypatch.setattr(admin, "BUILDPLUGIN_ADMIN_RECEIPT_PATH", receipt_path)
    return (
        publication,
        publisher,
        {
            "helper_root": helper_root,
            "helper": helper,
            "python": python,
        },
    )


@pytest.mark.parametrize("hazard", ("missing", "extra", "mode", "hash"))
def test_live_buildplugin_state_rehashes_exact_publisher_helper_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, hazard: str
) -> None:
    publication, publisher, paths = _live_buildplugin_publication_fixture(
        tmp_path, monkeypatch
    )
    root = paths["helper_root"]
    helper = paths["helper"]
    root.chmod(0o755)
    if hazard == "missing":
        helper.unlink()
    elif hazard == "extra":
        _write(root / "unexpected", b"extra", 0o444)
    elif hazard == "mode":
        helper.chmod(0o400)
    else:
        helper.chmod(0o600)
        helper.write_bytes(b"tampered helper\n")
        helper.chmod(0o500)
    root.chmod(0o555)
    with pytest.raises(admin.AuthorityError, match="publisher helper"):
        admin._validate_buildplugin_admin_publication(publication, publisher, live=True)


def test_live_buildplugin_state_rehashes_publisher_python(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    publication, publisher, paths = _live_buildplugin_publication_fixture(
        tmp_path, monkeypatch
    )
    python = paths["python"]
    python.chmod(0o700)
    python.write_bytes(b"tampered interpreter\n")
    python.chmod(0o755)
    with pytest.raises(admin.AuthorityError, match="publisher helper or interpreter"):
        admin._validate_buildplugin_admin_publication(publication, publisher, live=True)


def test_checkout_engine_source_audit_derives_full_zero_write_pin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source"
    _engine_source(source)
    monkeypatch.setattr(admin, "ENGINE_SOURCE", source)
    before = sorted(path.relative_to(source).as_posix() for path in source.rglob("*"))

    report = admin.audit_engine_source()

    after = sorted(path.relative_to(source).as_posix() for path in source.rglob("*"))
    assert before == after
    assert report["publication_performed"] is False
    assert report["source_manifest"]["content_digest"] == admin.content_digest(
        report["source_manifest"]
    )
    pin = report["derived_engine_source_pin"]
    assert (
        pin["source_manifest_content_digest"]
        == report["source_manifest"]["content_digest"]
    )
    admin.validate_engine_source_pin(admin.snapshot_tree(source), pin)


@pytest.mark.parametrize("hazard", ["symlink", "hardlink", "fifo", "casefold"])
def test_snapshot_rejects_link_special_and_casefold_hazards(
    tmp_path: Path, hazard: str
) -> None:
    source = tmp_path / "source"
    source.mkdir()
    _write(source / "file", b"x")
    if hazard == "symlink":
        (source / "link").symlink_to("file")
        expected = "TREE_SPECIAL_NODE"
    elif hazard == "hardlink":
        os.link(source / "file", source / "alias")
        expected = "TREE_HARDLINK_ALIAS"
    elif hazard == "fifo":
        os.mkfifo(source / "fifo")
        expected = "TREE_SPECIAL_NODE"
    else:
        _write(source / "FILE", b"y")
        expected = "TREE_NAMESPACE_INVALID"

    with pytest.raises(admin.AuthorityError, match=expected):
        admin.snapshot_tree(source)


def test_engine_publication_requires_external_reviewed_pin_and_is_no_replace(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parent = tmp_path / "authorities"
    parent.mkdir(mode=0o755)
    source = tmp_path / "source"
    _engine_source(source)
    snapshot = admin.snapshot_tree(source)
    final = parent / "engine-authority"
    monkeypatch.setattr(admin, "ENGINE_SOURCE", source)
    monkeypatch.setattr(admin, "ENGINE_ROOT", final / "engine")
    monkeypatch.setattr(admin, "_require_parent", lambda *_args, **_kwargs: None)

    wrong = _source_pin(snapshot)
    wrong["source_manifest_sha256"] = "0" * 64
    wrong["content_digest"] = admin.content_digest(wrong)
    with pytest.raises(
        admin.AuthorityError, match="ENGINE_SOURCE_REVIEWED_PIN_MISMATCH"
    ):
        admin.publish_engine_from_snapshot(
            snapshot,
            wrong,
            final=final,
            owner=(os.getuid(), os.getgid()),
            rename=_fake_noreplace,
        )

    result = admin.publish_engine_from_snapshot(
        snapshot,
        _source_pin(snapshot),
        final=final,
        owner=(os.getuid(), os.getgid()),
        rename=_fake_noreplace,
    )
    assert result["status"] == "published_immutable_ue57_engine_authority"
    assert result["accepted"] is True
    assert stat.S_IMODE(final.stat().st_mode) == 0o555
    manifest_raw = (final / "engine-full-tree-manifest.json").read_bytes()
    manifest = json.loads(manifest_raw)
    assert manifest["schema"] == admin.ENGINE_MANIFEST_SCHEMA
    assert manifest["engine_root"] == str(final / "engine")
    assert manifest["content_digest"] == admin.content_digest(manifest)
    assert manifest["tree_root_digest"] == snapshot.tree_digest
    receipt = json.loads((final / "receipt.json").read_bytes())
    assert set(receipt) == {
        "schema",
        "status",
        "accepted",
        "authority_root",
        "manifest",
        "reviewed_source_manifest",
        "source_projections",
        "final_projection",
        "critical_engine_files",
        "publisher",
        "publication_policy",
        "claims",
        "content_digest",
    }
    assert receipt["accepted"] is True
    assert receipt["source_projections"]["pre"] == receipt["source_projections"]["post"]
    for path in final.rglob("*"):
        mode = stat.S_IMODE(path.stat().st_mode)
        if path.is_dir():
            assert mode == 0o555
        elif path.name == "UnrealEditor-Cmd":
            assert mode == 0o555
        else:
            assert mode == 0o444
        assert not path.is_symlink()

    with pytest.raises(admin.AuthorityError, match="FINAL_NOT_FRESH"):
        admin.publish_engine_from_snapshot(
            snapshot,
            _source_pin(snapshot),
            final=final,
            owner=(os.getuid(), os.getgid()),
            rename=_fake_noreplace,
        )


def test_existing_engine_reconcile_reaudits_and_fsyncs_without_republication(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    uid, gid = os.getuid(), os.getgid()
    parent = tmp_path / "authorities"
    parent.mkdir(mode=0o755)
    source = tmp_path / "source"
    _engine_source(source)
    final = parent / "ue-5.7.3-r1"
    helper = tmp_path / "bootstrap/vista_r8_ue57_authority_admin.py"
    _write(helper, b"reviewed helper\n", 0o500)
    source_pin_path = tmp_path / "bootstrap/engine-source-pin.json"
    monkeypatch.setattr(admin, "ROOT_UID", uid)
    monkeypatch.setattr(admin, "ROOT_GID", gid)
    monkeypatch.setattr(admin, "AUTHORITY_PARENT", parent)
    monkeypatch.setattr(admin, "ENGINE_SOURCE", source)
    monkeypatch.setattr(admin, "ENGINE_AUTHORITY", final)
    monkeypatch.setattr(admin, "ENGINE_ROOT", final / "engine")
    monkeypatch.setattr(
        admin, "ENGINE_MANIFEST", final / "engine-full-tree-manifest.json"
    )
    monkeypatch.setattr(admin, "ENGINE_SOURCE_PIN_PATH", source_pin_path)
    monkeypatch.setattr(admin, "INSTALLED_HELPER", helper)
    snapshot = admin.snapshot_tree(source)
    source_pin = _source_pin(snapshot)
    _write(source_pin_path, admin.canonical_json(source_pin), 0o444)
    live_python = admin._require_live_python(source_pin["publisher_python_pin"])
    helper_pin = admin._read_regular(helper, "helper", exact_mode=0o500)[1]
    monkeypatch.setattr(admin, "_require_parent", lambda *_args, **_kwargs: None)
    admin.publish_engine_from_snapshot(
        snapshot,
        source_pin,
        final=final,
        owner=(uid, gid),
        rename=_fake_noreplace,
        publisher_pins={"helper": helper_pin, "interpreter": live_python},
    )
    monkeypatch.undo()

    # Reapply the fixed fake authority identities after undoing only the
    # publication bypass; reconciliation itself must enforce the 0555 parent.
    monkeypatch.setattr(admin, "ROOT_UID", uid)
    monkeypatch.setattr(admin, "ROOT_GID", gid)
    monkeypatch.setattr(admin, "AUTHORITY_PARENT", parent)
    monkeypatch.setattr(admin, "ENGINE_SOURCE", source)
    monkeypatch.setattr(admin, "ENGINE_AUTHORITY", final)
    monkeypatch.setattr(admin, "ENGINE_ROOT", final / "engine")
    monkeypatch.setattr(
        admin, "ENGINE_MANIFEST", final / "engine-full-tree-manifest.json"
    )
    monkeypatch.setattr(admin, "ENGINE_SOURCE_PIN_PATH", source_pin_path)
    monkeypatch.setattr(admin, "INSTALLED_HELPER", helper)
    parent.chmod(0o555)
    before = sorted(path.relative_to(final).as_posix() for path in final.rglob("*"))

    result = admin.audit_existing_engine_authority(fsync=True)

    after = sorted(path.relative_to(final).as_posix() for path in final.rglob("*"))
    assert before == after
    assert result["status"] == "existing_engine_authority_durability_reconciled"
    assert result["publication_performed"] is False
    assert result["deletion_performed"] is False


def test_safe_copy_does_not_inherit_xattrs_or_source_writability(
    tmp_path: Path,
) -> None:
    source = tmp_path / "source"
    _write(source / "bin/tool", b"tool", 0o777)
    try:
        os.setxattr(source / "bin/tool", "user.vista-test", b"secret-metadata")
    except OSError:
        pytest.skip("user xattrs unavailable on this filesystem")
    snapshot = admin.snapshot_tree(source)
    destination = tmp_path / "destination"

    admin.copy_tree_from_snapshot(
        snapshot, destination, owner=(os.getuid(), os.getgid())
    )

    assert stat.S_IMODE((destination / "bin/tool").stat().st_mode) == 0o555
    assert os.listxattr(destination / "bin/tool") == []


def test_runtime_copy_uses_component_held_sources_and_executable_pins(
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "sources"
    executable = source_root / "real/python3.10"
    regular = source_root / "real/os.py"
    _write(executable, b"python-elf", 0o755)
    _write(regular, b"stdlib", 0o644)
    (source_root / "alias").symlink_to("real", target_is_directory=True)
    payload = tmp_path / "payload"
    payload.mkdir()
    executable_raw = executable.read_bytes()
    selected = {
        Path("usr/bin/python3.10"): source_root / "alias/python3.10",
        Path("usr/lib/python3.10/os.py"): regular,
    }

    inventory = admin.copy_selected_regular_files(
        selected,
        payload,
        owner=(os.getuid(), os.getgid()),
        executable_pins={
            Path("usr/bin/python3.10"): admin.FilePin(
                hashlib.sha256(executable_raw).hexdigest(), len(executable_raw), True
            )
        },
    )

    assert stat.S_IMODE((payload / "usr/bin/python3.10").stat().st_mode) == 0o555
    assert stat.S_IMODE((payload / "usr/lib/python3.10/os.py").stat().st_mode) == 0o444
    assert inventory[0]["symlink_resolutions"]
    assert inventory[0]["source_canonical"] == str(executable)
    with pytest.raises(admin.AuthorityError, match="RUNTIME_EXECUTABLE_PIN_MISMATCH"):
        other_payload = tmp_path / "other-payload"
        other_payload.mkdir()
        admin.copy_selected_regular_files(
            {Path("usr/bin/python3.10"): executable},
            other_payload,
            owner=(os.getuid(), os.getgid()),
            executable_pins={
                Path("usr/bin/python3.10"): admin.FilePin("0" * 64, 1, True)
            },
        )


def test_component_swap_between_lstat_and_open_is_rejected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "source/file"
    replacement = tmp_path / "replacement"
    _write(source, b"first")
    _write(replacement, b"second")
    real_stat = admin.os.stat
    swapped = False

    def swapping_stat(
        path: os.PathLike[str] | str,
        *args: object,
        **kwargs: object,
    ) -> os.stat_result:
        nonlocal swapped
        result = real_stat(path, *args, **kwargs)
        if path == "file" and kwargs.get("follow_symlinks") is False and not swapped:
            swapped = True
            source.unlink()
            replacement.rename(source)
        return result

    monkeypatch.setattr(admin.os, "stat", swapping_stat)
    with pytest.raises(admin.AuthorityError, match="RUNTIME_SOURCE_COMPONENT_DRIFT"):
        with admin.hold_source_file_components(source):
            pass


def test_parent_is_never_chmodded_and_requires_exact_0555(
    tmp_path: Path,
) -> None:
    parent = tmp_path / "parent"
    parent.mkdir(mode=0o755)
    with pytest.raises(admin.AuthorityError, match="AUTHORITY_PARENT_INVALID"):
        admin._require_parent(parent, owner=(os.getuid(), os.getgid()))
    assert stat.S_IMODE(parent.stat().st_mode) == 0o755


def test_readelf_parser_and_dependency_closure_are_nonexecuting_and_closed(
    tmp_path: Path,
) -> None:
    root = tmp_path / "root.elf"
    loader = tmp_path / "ld.so"
    libc = tmp_path / "libc.so.6"
    for path in (root, loader, libc):
        _write(path, b"\x7fELFfake")
    metadata = admin.parse_readelf_output(
        "[Requesting program interpreter: /lib64/ld-linux-x86-64.so.2]\n"
        " 0x1 (NEEDED) Shared library: [libc.so.6]\n"
    )
    assert metadata == admin.ElfMetadata("/lib64/ld-linux-x86-64.so.2", ("libc.so.6",))
    rich = admin.parse_readelf_output(
        " 0x1 (SONAME) Library soname: [libfake.so.1]\n"
        " 0x1 (RPATH) Library rpath: [$ORIGIN/../lib:/fixed/lib]\n"
        " 0x1 (RUNPATH) Library runpath: [$ORIGIN/lib:/run/lib]\n"
    )
    assert rich.soname == "libfake.so.1"
    assert rich.rpath == ("$ORIGIN/../lib", "/fixed/lib")
    assert rich.runpath == ("$ORIGIN/lib", "/run/lib")
    assert admin.dynamic_search_paths(
        rich, origin=Path("/authority/bin"), defaults=(Path("/default"),)
    ) == (Path("/authority/bin/lib"), Path("/run/lib"), Path("/default"))

    def inspect(path: Path) -> admin.ElfMetadata:
        if path == root.resolve():
            return admin.ElfMetadata(str(loader), ("libc.so.6",))
        return admin.ElfMetadata(None, ())

    closure = admin.resolve_elf_closure(
        [root], inspect=inspect, soname_map={"libc.so.6": [libc]}
    )
    assert closure == tuple(
        sorted((root.resolve(), loader.resolve(), libc.resolve()), key=str)
    )

    with pytest.raises(admin.AuthorityError, match="ELF_DEPENDENCY_MISSING"):
        admin.resolve_elf_closure([root], inspect=inspect, soname_map={})
    other = tmp_path / "other/libc.so.6"
    _write(other, b"\x7fELFother")
    with pytest.raises(admin.AuthorityError, match="ELF_DEPENDENCY_AMBIGUOUS"):
        admin.resolve_elf_closure(
            [root], inspect=inspect, soname_map={"libc.so.6": [libc, other]}
        )


def _fake_tree_snapshot(root: Path) -> admin.TreeSnapshot:
    root.mkdir(parents=True, exist_ok=True)
    _write(root / "etc/passwd", b"nobody:x:65534:65534::/:/usr/sbin/nologin\n")
    return admin.snapshot_tree(root)


def test_runtime_manifest_receipt_shapes_are_fixed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    authority = tmp_path / "runtime"
    payload = authority / "payload"
    snapshot = _fake_tree_snapshot(payload)
    monkeypatch.setattr(admin, "HOST_RUNTIME_AUTHORITY", authority)
    monkeypatch.setattr(admin, "HOST_RUNTIME_PAYLOAD", payload)
    manifest = admin.runtime_manifest(snapshot)
    manifest_pin = admin.FilePin("a" * 64, 123)
    reviewed_publication = {
        "input_pin": {
            "pin": {"sha256": "6" * 64, "size_bytes": 6},
            "content_digest": "7" * 64,
        },
        "reviewed_plan_pin": {
            "pin": {"sha256": "8" * 64, "size_bytes": 8},
            "content_digest": "9" * 64,
        },
        "audit_plan": {
            "sha256": "a" * 64,
            "size_bytes": 10,
            "content_digest": "b" * 64,
        },
    }
    publisher = {
        "helper_pin": {"sha256": "c" * 64, "size_bytes": 11},
        "runtime_admin_launcher_pin": {
            "sha256": "d" * 64,
            "size_bytes": 12,
        },
        "interpreter_pin": {"sha256": "e" * 64, "size_bytes": 13},
    }
    receipt = admin.runtime_receipt(
        snapshot,
        manifest_pin,
        manifest["content_digest"],
        {
            "engine_manifest_pin": {"sha256": "1" * 64, "size_bytes": 1},
            "buildplugin_manifest_pin": {"sha256": "2" * 64, "size_bytes": 2},
            "buildplugin_receipt_pin": {"sha256": "3" * 64, "size_bytes": 3},
            "python_pin": {"sha256": "4" * 64, "size_bytes": 4},
            "readelf_pin": {"sha256": "5" * 64, "size_bytes": 5},
        },
        reviewed_publication=reviewed_publication,
        publisher=publisher,
    )
    assert set(manifest) == {
        "schema",
        "authority_root",
        "payload_root",
        "entries",
        "projection",
        "content_digest",
    }
    assert receipt["schema"] == admin.HOST_RUNTIME_RECEIPT_SCHEMA
    assert receipt["status"] == "root_published_immutable_host_runtime_authority"
    assert receipt["accepted"] is True
    assert receipt["payload"] == snapshot.projection()
    assert receipt["reviewed_publication"] == reviewed_publication
    assert receipt["publisher"] == publisher
    assert receipt["content_digest"] == admin.content_digest(receipt)
    assert receipt["claims"] == {
        "allowlisted_runtime_closure_only": True,
        "ldd_executed": False,
        "final_contains_symlinks": False,
        "secrets_copied": False,
        "gpu_runtime_included": False,
    }


def test_bundle_launcher_and_v3_policy_bind_four_files_and_all_authorities(
    tmp_path: Path,
) -> None:
    launcher_text = (
        Path(admin.__file__)
        .with_name("vista_r8_ue57_launcher.c")
        .read_text(encoding="utf-8")
    )
    assert "SYS_execveat" in launcher_text
    assert "AT_EMPTY_PATH" in launcher_text
    assert "O_NOFOLLOW" in launcher_text
    assert '"-I", "-B"' in launcher_text
    assert "PYTHONHOME=" not in launcher_text
    assert "argc!=2" in launcher_text
    assert '"--audit-authorities"' in launcher_text
    assert '"--execute"' in launcher_text
    assert '"--reconcile-durability"' in launcher_text
    assert '"--argv0", REVIEWED_PYTHON_PATH' in launcher_text
    assert launcher_text.count('"--attempt-name", REVIEWED_ATTEMPT_NAME') == 3
    bundle_pins = {
        "makehuman_cc0_animation_runtime_executor.py": admin.FilePin("1" * 64, 1, True),
        "makehuman_cc0_animation_runtime_sandbox_wrapper.py": admin.FilePin(
            "2" * 64, 2
        ),
        "makehuman_cc0_animation_runtime_commandlet.py": admin.FilePin("3" * 64, 3),
        admin.LAUNCHER_NAME: admin.FilePin("4" * 64, 4, True),
    }
    bundle = admin.bundle_manifest(bundle_pins)
    assert bundle["schema"] == admin.BUNDLE_MANIFEST_SCHEMA
    assert len(bundle["files"]) == 4

    engine_entries = [
        {
            "path": relative,
            "type": "file",
            "mode": 0o555 if relative.endswith("Cmd") else 0o444,
            "uid": 0,
            "gid": 0,
            "size_bytes": index + 1,
            "sha256": str(index + 1) * 64,
        }
        for index, relative in enumerate(admin.CRITICAL_ENGINE_FILES)
    ]
    runtime_projection = {
        "tree_digest": "6" * 64,
        "file_count": 6,
        "directory_count": 6,
        "total_bytes": 6,
    }
    buildplugin_projection = {
        "projection_sha256": "7" * 64,
        "file_count": 7,
        "directory_count": 7,
        "total_bytes": 7,
    }
    publication_provenance = {
        "bundle_input_pin": {
            "pin": {"sha256": "7" * 64, "size_bytes": 17},
            "content_digest": "8" * 64,
        },
        "reviewed_plan_pin": {
            "pin": {"sha256": "9" * 64, "size_bytes": 18},
            "content_digest": "a" * 64,
        },
        "audit_plan": {
            "sha256": "b" * 64,
            "size_bytes": 19,
            "content_digest": "c" * 64,
        },
        "publisher": {
            "helper_pin": {"sha256": "d" * 64, "size_bytes": 20},
            "bundle_admin_launcher_pin": {
                "sha256": "e" * 64,
                "size_bytes": 21,
            },
            "interpreter_pin": {"sha256": "f" * 64, "size_bytes": 22},
        },
        "launcher_build": {
            "source_pin": {"sha256": "0" * 64, "size_bytes": 23},
            "compiler_driver_pin": {"sha256": "1" * 64, "size_bytes": 24},
            "toolchain_artifact_ledger_digest": "2" * 64,
            "output_pin": {"sha256": "3" * 64, "size_bytes": 25},
        },
    }
    policy = admin.build_root_policy(
        publication_provenance=publication_provenance,
        bundle_pins=bundle_pins,
        bundle_manifest_pin=admin.FilePin("5" * 64, 5),
        bundle_manifest_content_digest="8" * 64,
        input_pin={
            "python_pin": {"sha256": "9" * 64, "size_bytes": 9},
            "bwrap_pin": {"sha256": "a" * 64, "size_bytes": 10},
            "r3": {
                "receipt_pin": {},
                "receipt_content_digest": "b" * 64,
                "project": {},
            },
            "r8": {
                "attempt_name": "fresh",
                "receipt_pin": {},
                "receipt_content_digest": "c" * 64,
            },
        },
        engine_document={
            "entries": engine_entries,
            "content_digest": "d" * 64,
            "tree_root_digest": "e" * 64,
        },
        engine_pin=admin.FilePin("f" * 64, 11),
        engine_receipt_document={"content_digest": "a" * 64},
        engine_receipt_pin=admin.FilePin("b" * 64, 16),
        runtime_document={
            "projection": runtime_projection,
            "content_digest": "0" * 64,
        },
        runtime_manifest_pin=admin.FilePin("1" * 64, 12),
        runtime_receipt_document={"content_digest": "2" * 64},
        runtime_receipt_pin=admin.FilePin("3" * 64, 13),
        buildplugin_document={"source": buildplugin_projection},
        buildplugin_manifest_pin=admin.FilePin("4" * 64, 14),
        buildplugin_receipt_document={"content_digest": "5" * 64},
        buildplugin_receipt_pin=admin.FilePin("6" * 64, 15),
    )
    assert policy["schema"] == admin.ROOT_POLICY_SCHEMA
    assert policy["publication_provenance"] == publication_provenance
    assert "launcher_pin" in policy
    assert "live_python_pin" in policy
    assert "wrapper_python_pin" not in policy
    assert policy["approved_attempt_name"] == admin.APPROVED_ATTEMPT_NAME
    assert policy["invocation_ledger_path"] == str(admin.INVOCATION_LEDGER_PATH)
    assert policy["operation_lock_path"] == str(admin.OPERATION_LOCKS["executor"])
    assert policy["engine"]["receipt_pin"] == {"sha256": "b" * 64, "size_bytes": 16}
    assert policy["engine"]["receipt_content_digest"] == "a" * 64
    assert set(policy["host_runtime"]) == {
        "manifest_pin",
        "manifest_content_digest",
        "receipt_pin",
        "receipt_content_digest",
        "payload",
    }
    assert policy["buildplugin"]["manifest_content_digest"] == "4" * 64
    assert policy["content_digest"] == admin.content_digest(policy)


def test_native_launcher_template_compiles_as_static_elf_with_reviewed_literals(
    tmp_path: Path,
) -> None:
    compiler = shutil.which("gcc")
    if compiler is None:
        pytest.skip("gcc unavailable")
    source = Path(admin.__file__).with_name("vista_r8_ue57_launcher.c")
    output = tmp_path / "launcher"
    command = [
        compiler,
        "-std=c11",
        "-O2",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-static",
        "-s",
        "-Wl,--build-id=none",
        '-DREVIEWED_LOADER_PATH="/runtime/lib64/ld-linux.so.2"',
        f'-DREVIEWED_LOADER_SHA256="{"a" * 64}"',
        "-DREVIEWED_LOADER_BYTES=1",
        '-DREVIEWED_PYTHON_PATH="/runtime/usr/bin/python3.10"',
        f'-DREVIEWED_PYTHON_SHA256="{"b" * 64}"',
        "-DREVIEWED_PYTHON_BYTES=2",
        '-DREVIEWED_LIBRARY_PATH="/runtime/lib:/runtime/usr/lib"',
        f'-DREVIEWED_ATTEMPT_NAME="{admin.APPROVED_ATTEMPT_NAME}"',
        str(source),
        "-o",
        str(output),
    ]
    result = subprocess.run(
        command,
        check=False,
        cwd="/",
        env={"PATH": "/usr/bin:/bin"},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stderr
    raw = output.read_bytes()
    assert raw.startswith(b"\x7fELF")
    assert b"#!/bin/sh" not in raw


def test_runtime_and_bundle_plans_require_literal_reviewed_digest() -> None:
    runtime = admin.runtime_audit_plan(
        input_pin={
            "path": str(admin.RUNTIME_INPUT_PIN_PATH),
            "pin": {"sha256": "0" * 64, "size_bytes": 1},
            "content_digest": "1" * 64,
        },
        authority_pins={"engine": {}, "buildplugin": {}},
        inventory=[{"destination": "usr/lib/libc.so.6", "sha256": "a" * 64}],
        symlink_resolutions=[
            {"source": "/lib/libc.so.6", "target": "/usr/lib/libc.so.6"}
        ],
        elf_seeds=[],
        elf_graph=[{"source": "python", "needed": ["libc.so.6"]}],
        generated_etc={"etc/passwd": "nobody:x:65534:65534::/:/usr/sbin/nologin\n"},
        data_allowlist=["usr/share/zoneinfo/UTC"],
        tool_pins={"readelf": {"sha256": "b" * 64, "size_bytes": 1}},
        executable_destinations=["usr/bin/python3.10"],
        final_projection={
            "tree_digest": "c" * 64,
            "file_count": 1,
            "directory_count": 2,
            "total_bytes": 3,
        },
    )
    admin_launcher_pin = admin.FilePin("2" * 64, 2, True)
    pin = admin.reviewed_plan_pin(runtime, admin_launcher_pin)
    admin.validate_reviewed_plan(runtime, pin, admin_launcher_pin)
    tampered = dict(runtime)
    tampered["publication_performed"] = True
    with pytest.raises(admin.AuthorityError, match="REVIEWED_AUDIT_PLAN_PIN_MISMATCH"):
        admin.validate_reviewed_plan(tampered, pin, admin_launcher_pin)

    bundle = admin.bundle_audit_plan(
        input_pin={
            "path": str(admin.BUNDLE_INPUT_PIN_PATH),
            "pin": {"sha256": "c" * 64, "size_bytes": 1},
            "content_digest": "d" * 64,
        },
        source_pins={"executor": {"sha256": "d" * 64, "size_bytes": 1}},
        launcher_build={"compiler_driver_pin": {"sha256": "e" * 64, "size_bytes": 2}},
        launcher_binary_pin={"sha256": "f" * 64, "size_bytes": 3},
        authority_pins={"engine": {}},
        bundle_manifest_document=admin.seal_document(
            {"schema": admin.BUNDLE_MANIFEST_SCHEMA, "files": []}
        ),
        policy_core_document=admin.seal_document(
            {"schema": admin.ROOT_POLICY_CORE_SCHEMA}
        ),
    )
    assert bundle["root_layout"] == {
        "authority": str(admin.ROOT_EXECUTION_AUTHORITY),
        "bundle": str(admin.ROOT_BUNDLE),
        "policy": str(admin.ROOT_POLICY),
        "single_atomic_rename": True,
    }
    bundle_admin_launcher_pin = admin.FilePin("3" * 64, 3, True)
    admin.validate_reviewed_plan(
        bundle,
        admin.reviewed_plan_pin(bundle, bundle_admin_launcher_pin),
        bundle_admin_launcher_pin,
    )


def test_production_runtime_bundle_commands_fail_closed_until_reviewed_pins() -> None:
    assert (
        admin.main(
            [
                "reconcile-engine",
                "--acknowledgement",
                "wrong acknowledgement",
            ]
        )
        == 2
    )
    assert admin.main(["audit-host-runtime-plan"]) == 2
    assert admin.main(["audit-executor-bundle-plan"]) == 2
    assert (
        admin.main(
            [
                "publish-host-runtime",
                "--acknowledgement",
                admin.HOST_RUNTIME_ACKNOWLEDGEMENT,
            ]
        )
        == 2
    )
    assert (
        admin.main(
            [
                "publish-executor-bundle",
                "--acknowledgement",
                admin.BUNDLE_ACKNOWLEDGEMENT,
            ]
        )
        == 2
    )


def test_engine_shell_and_native_admin_launchers_have_closed_entrypoints() -> None:
    root = Path(__file__).resolve().parents[2]
    engine_wrapper = (root / "tools/admin/provision_vista_r8_ue57_engine.sh").read_text(
        encoding="utf-8"
    )
    assert "/root/vista-r8-ue57-authority-r2/" in engine_wrapper
    assert "PATH=/usr/sbin:/usr/bin:/sbin:/bin" in engine_wrapper
    assert (
        "unset ENV BASH_ENV CDPATH GLOBIGNORE PYTHONHOME PYTHONPATH" in engine_wrapper
    )
    assert "/usr/bin/id -u" in engine_wrapper
    assert "/usr/bin/sha256sum" in engine_wrapper
    assert "/usr/bin/stat -Lc" in engine_wrapper
    assert "/usr/bin/cut" in engine_wrapper
    assert (
        re.search(r"(?<!/usr/bin/)\b(?:id|stat|sha256sum|cut)\s", engine_wrapper)
        is None
    )
    assert "REQUIRED" not in engine_wrapper
    assert "env -i" in engine_wrapper
    assert "sudo" not in engine_wrapper
    assert 'exec 9<"$PYTHON"' in engine_wrapper
    assert "/proc/self/fd/9 -I -B" in engine_wrapper
    assert "reconcile-engine" in engine_wrapper
    assert ".engine.lock" in engine_wrapper
    bindings = admin._engine_wrapper_review_bindings(
        engine_wrapper.encode("utf-8"),
        helper_pin=admin.FilePin(
            "f9fd20d802a85bb3a57955edcd994644f64b34bb3fa7b8078cab0fcc0b1d7ce1",
            512_140,
        ),
        source_pin=admin.FilePin(
            "7b30cd3b5628a21579efc19013a1d13e9557684c6b8ab3b6495eb42544e4b3d9",
            786,
        ),
        python_pin=admin.FilePin(
            "7d51cd6b48b521277f5caa4610a82126e315fa2be4df069823a8b1eeb5bd4a86",
            5_917_224,
        ),
    )
    assert bindings["EXPECTED_HELPER_BYTES"] == "512140"
    assert bindings["EXPECTED_SOURCE_PIN_BYTES"] == "786"
    assert bindings["EXPECTED_PYTHON_BYTES"] == "5917224"
    admin_launcher = (root / "tools/admin/vista_r8_ue57_admin_launcher.c").read_text(
        encoding="utf-8"
    )
    assert "VISTA_R8_ADMIN_STAGE_RUNTIME" in admin_launcher
    assert "VISTA_R8_ADMIN_STAGE_BUNDLE" in admin_launcher
    assert '"/proc/self/exe"' in admin_launcher
    assert "SYS_execveat" in admin_launcher
    assert "AT_EMPTY_PATH" in admin_launcher
    assert "O_NOFOLLOW" in admin_launcher
    assert "sudo" not in admin_launcher
    assert not (root / "tools/admin/provision_vista_r8_ue57_runtime_bundle.sh").exists()


def _pin_for(path: Path, *, executable: bool = False) -> admin.FilePin:
    raw = path.read_bytes()
    return admin.FilePin(hashlib.sha256(raw).hexdigest(), len(raw), executable)


def _bomb_root_access(monkeypatch: pytest.MonkeyPatch) -> None:
    original_lstat = admin.os.lstat
    original_open = admin.os.open

    def bomb_lstat(path: object, *args: object, **kwargs: object):
        if os.fsdecode(os.fspath(path)).startswith("/root/"):
            raise AssertionError("unprivileged builder touched /root")
        return original_lstat(path, *args, **kwargs)

    def bomb_open(path: object, *args: object, **kwargs: object):
        if isinstance(path, (str, bytes, os.PathLike)) and os.fsdecode(
            os.fspath(path)
        ).startswith("/root/"):
            raise AssertionError("unprivileged builder opened /root")
        return original_open(path, *args, **kwargs)

    monkeypatch.setattr(admin.os, "lstat", bomb_lstat)
    monkeypatch.setattr(admin.os, "open", bomb_open)


def _stage_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path, Path]:
    uid, gid = os.getuid(), os.getgid()
    stage_parent = tmp_path / "root"
    stage_parent.mkdir(mode=0o700)
    candidate = tmp_path / "runtime-input-candidate"
    candidate.mkdir(mode=0o700)
    input_path = candidate / "input-pin.json"
    _write(input_path, b'{"candidate":true}\n', 0o444)
    candidate.chmod(0o555)
    final = stage_parent / "runtime-input"
    monkeypatch.setattr(admin, "ROOT_UID", uid)
    monkeypatch.setattr(admin, "ROOT_GID", gid)
    monkeypatch.setattr(admin, "REVIEW_UID", uid)
    monkeypatch.setattr(admin, "REVIEW_GID", gid)
    monkeypatch.setattr(admin, "RUNTIME_INPUT_REVIEW_CANDIDATE", input_path)
    monkeypatch.setattr(admin, "RUNTIME_INPUT_AUTHORITY", final)
    monkeypatch.setattr(admin, "RUNTIME_INPUT_PIN_PATH", final / "input-pin.json")
    monkeypatch.setattr(admin, "_require_core_installed", lambda: None)
    monkeypatch.setattr(
        admin,
        "_require_stage_installer_invocation",
        lambda _stage, *, plan, descriptor: {"plan": plan, "fd": descriptor},
    )
    monkeypatch.setattr(admin, "_core_authority_identity", lambda: (("core",),))
    monkeypatch.setattr(
        admin,
        "_stage_installer_authority_identity",
        lambda key: (("installer", key),),
    )
    monkeypatch.setattr(
        admin,
        "operation_lock",
        lambda _name: contextlib.nullcontext(),
    )
    monkeypatch.setattr(
        admin,
        "_parse_candidate_document",
        lambda _raw, _schema, _label: {
            "tool_pins": {"python": {"pin": {"sha256": "a" * 64, "size_bytes": 1}}}
        },
    )
    monkeypatch.setattr(admin, "validate_runtime_input_pin", lambda _document: None)
    monkeypatch.setattr(
        admin, "_validate_runtime_input_against_live", lambda _document: {}
    )
    monkeypatch.setattr(
        admin,
        "_require_live_python",
        lambda _pin: admin.FilePin("a" * 64, 1, True),
    )
    return candidate, input_path, final


def test_bootstrap_input_stage_is_external_pin_no_replace_and_reconcile_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _candidate, input_path, final = _stage_fixture(tmp_path, monkeypatch)
    expected = _pin_for(input_path)
    monkeypatch.setattr(
        admin.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("root stage operation ran subprocess")
        ),
    )

    result = admin.install_stage_input_authority(
        "runtime", expected.public(), stage_installer_fd=9
    )

    assert result["publication_performed"] is True
    assert result["reviewed_input_pin"] == expected.public()
    assert not final.is_symlink()
    assert stat.S_IMODE(final.stat().st_mode) == 0o555
    assert stat.S_IMODE((final / "input-pin.json").stat().st_mode) == 0o444
    assert (final / "input-pin.json").read_bytes() == input_path.read_bytes()
    with pytest.raises(admin.AuthorityError, match="FINAL_NOT_FRESH"):
        admin.install_stage_input_authority(
            "runtime", expected.public(), stage_installer_fd=9
        )

    monkeypatch.setattr(
        admin,
        "_installed_stage_input_and_plan",
        lambda _stage: ({}, expected, {"content_digest": "b" * 64}),
    )
    reconciled = admin.reconcile_stage_authority(
        "runtime",
        plan=False,
        reviewed_primary_pin=expected.public(),
        stage_installer_fd=9,
    )
    assert reconciled["publication_performed"] is False
    assert reconciled["deletion_performed"] is False
    assert (final / "input-pin.json").read_bytes() == input_path.read_bytes()


def test_bootstrap_input_stage_rejects_unreviewed_pin_and_special_candidate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate, input_path, _final = _stage_fixture(tmp_path, monkeypatch)
    with pytest.raises(
        admin.AuthorityError, match="STAGE_EXTERNAL_REVIEW_PIN_MISMATCH"
    ):
        admin.install_stage_input_authority(
            "runtime",
            {"sha256": "0" * 64, "size_bytes": input_path.stat().st_size},
            stage_installer_fd=9,
        )
    candidate.chmod(0o755)
    (candidate / "extra").symlink_to("input-pin.json")
    candidate.chmod(0o555)
    with pytest.raises(admin.AuthorityError, match="IMMUTABLE_AUTHORITY_INVALID"):
        admin.install_stage_input_authority(
            "runtime", _pin_for(input_path).public(), stage_installer_fd=9
        )


def test_bootstrap_plan_stage_binds_v2_pin_native_binary_and_earlier_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _candidate, input_path, input_final = _stage_fixture(tmp_path, monkeypatch)
    input_pin = _pin_for(input_path)
    admin.install_stage_input_authority(
        "runtime", input_pin.public(), stage_installer_fd=9
    )
    before = admin._flat_stage_identity("runtime", plan=False)

    helper = tmp_path / "installed-helper.py"
    _write(helper, b"reviewed helper\n", 0o500)
    helper_pin = _pin_for(helper)
    python_pin = admin.FilePin("c" * 64, 17, True)
    plan = admin.seal_document(
        {"schema": admin.RUNTIME_AUDIT_PLAN_SCHEMA, "publication_performed": False}
    )
    plan_candidate = tmp_path / "runtime-plan-candidate"
    plan_candidate.mkdir(mode=0o700)
    admin_binary = plan_candidate / admin.ADMIN_LAUNCHER_NAME
    admin_raw = (
        b"\x7fELFfixture\0"
        + helper_pin.sha256.encode("ascii")
        + b"\0"
        + python_pin.sha256.encode("ascii")
    )
    _write(admin_binary, admin_raw, 0o555)
    admin_pin = _pin_for(admin_binary, executable=True)
    reviewed_document = admin.reviewed_plan_pin(plan, admin_pin)
    reviewed_path = plan_candidate / "reviewed-plan-pin.json"
    _write(reviewed_path, admin.canonical_json(reviewed_document), 0o444)
    plan_candidate.chmod(0o555)
    plan_final = input_final.parent / "runtime-plan"
    monkeypatch.setattr(admin, "INSTALLED_HELPER", helper)
    monkeypatch.setattr(admin, "RUNTIME_PLAN_REVIEW_CANDIDATE_ROOT", plan_candidate)
    monkeypatch.setattr(admin, "RUNTIME_REVIEWED_PLAN_CANDIDATE", reviewed_path)
    monkeypatch.setattr(admin, "RUNTIME_ADMIN_LAUNCHER_CANDIDATE", admin_binary)
    monkeypatch.setattr(admin, "RUNTIME_PLAN_AUTHORITY", plan_final)
    monkeypatch.setattr(
        admin, "RUNTIME_REVIEWED_PLAN_PIN_PATH", plan_final / "reviewed-plan-pin.json"
    )
    monkeypatch.setattr(
        admin, "RUNTIME_ADMIN_LAUNCHER", plan_final / admin.ADMIN_LAUNCHER_NAME
    )
    monkeypatch.setattr(
        admin,
        "_installed_stage_input_and_plan",
        lambda _stage: (
            {"tool_pins": {"python": {"pin": python_pin.public()}}},
            input_pin,
            plan,
        ),
    )
    monkeypatch.setattr(admin, "_require_live_python", lambda _pin: python_pin)
    monkeypatch.setattr(
        admin,
        "_parse_candidate_document",
        lambda raw, schema, label: (
            admin.strict_json(raw, label)
            if schema == admin.REVIEWED_PLAN_PIN_SCHEMA
            else {"tool_pins": {"python": {"pin": python_pin.public()}}}
        ),
    )
    monkeypatch.setattr(
        admin.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("root stage publisher ran subprocess")
        ),
    )

    result = admin.install_stage_plan_authority(
        "runtime",
        _pin_for(reviewed_path).public(),
        admin_pin.public(),
        stage_installer_fd=9,
    )

    assert result["publication_performed"] is True
    assert stat.S_IMODE(plan_final.stat().st_mode) == 0o555
    assert (
        stat.S_IMODE((plan_final / admin.ADMIN_LAUNCHER_NAME).stat().st_mode) == 0o555
    )
    assert admin._flat_stage_identity("runtime", plan=False) == before
    reconciled = admin.reconcile_stage_authority(
        "runtime",
        plan=True,
        reviewed_primary_pin=_pin_for(reviewed_path).public(),
        reviewed_admin_launcher_pin=admin_pin.public(),
        stage_installer_fd=9,
    )
    assert reconciled["publication_performed"] is False
    assert admin._flat_stage_identity("runtime", plan=False) == before


def test_root_bundle_validation_never_rehashes_compiler_or_toolchain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    expected = {
        "source_pins": {
            admin.LAUNCHER_SOURCE.name: {"pin": {"sha256": "1" * 64, "size_bytes": 1}}
        },
        "launcher_build": {"source_pin": {"sha256": "1" * 64, "size_bytes": 1}},
        "runtime_executables": {},
        "launcher_binary_pin": {"sha256": "2" * 64, "size_bytes": 2},
        "engine": {},
        "host_runtime": {},
        "buildplugin": {},
        "r3": {},
        "r8": {},
    }
    monkeypatch.setattr(admin.os, "geteuid", lambda: admin.ROOT_UID)
    monkeypatch.setattr(admin, "validate_bundle_input_pin", lambda _value: None)
    monkeypatch.setattr(admin, "_load_engine_state", lambda: {})
    monkeypatch.setattr(admin, "_load_runtime_state", lambda: {})
    monkeypatch.setattr(admin, "_load_buildplugin_state", lambda: {})
    monkeypatch.setattr(admin, "_source_pins", lambda: expected["source_pins"])
    monkeypatch.setattr(admin, "_runtime_executable_binding", lambda: {})
    monkeypatch.setattr(
        admin,
        "_validate_launcher_build_spec",
        lambda _value: expected["launcher_build"],
    )
    monkeypatch.setattr(
        admin,
        "_launcher_build_spec",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("root rehashed compiler/toolchain")
        ),
    )
    monkeypatch.setattr(
        admin,
        "_authority_binding",
        lambda state, *, buildplugin: state,
    )
    monkeypatch.setattr(admin, "_load_r3_binding", lambda: {})
    monkeypatch.setattr(admin, "_load_r8_binding", lambda: {})

    assert (
        admin._validate_bundle_input_against_live(
            expected,
            reviewed_launcher_pin=admin.FilePin("2" * 64, 2, True),
        )
        == expected
    )


def test_runtime_plan_local_native_build_is_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        admin,
        "_compile_admin_launcher",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("local compiler must not run")
        ),
    )
    with pytest.raises(
        admin.AuthorityError, match="DEDICATED_BUILDER_AUTHORITY_REQUIRED"
    ):
        admin.build_runtime_plan_review_candidate()
    assert not (tmp_path / "plan-candidate").exists()


def test_admin_launcher_compiles_exact_head_blob_memfd_not_reopened_checkout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    compiler = tmp_path / "compiler"
    output = tmp_path / "admin-launcher"
    _write(compiler, b"compiler-driver", 0o755)
    committed = b"/* exact git show HEAD blob */\nint main(void){return 0;}\n"
    mutable_checkout = tmp_path / "mutable-admin-launcher.c"
    _write(mutable_checkout, b"malicious replacement\n")
    monkeypatch.setattr(admin, "COMPILER_PATH", compiler)
    monkeypatch.setattr(admin, "ADMIN_LAUNCHER_SOURCE", mutable_checkout)
    monkeypatch.setattr(admin, "CHECKOUT_ROOT", tmp_path)
    monkeypatch.setattr(admin, "_review_toolchain_artifact_pins", lambda: [])
    original_hold = admin.hold_source_file_components

    @contextlib.contextmanager
    def reject_checkout_source(path: Path):
        if path == mutable_checkout:
            raise AssertionError("compile reopened mutable checkout source")
        with original_hold(path) as held:
            yield held

    def fake_compile(
        command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        source_argument = next(
            item for item in command if item.startswith("/proc/self/fd/")
        )
        assert command[command.index("-x") + 1] == "c"
        assert command.index("-x") < command.index(source_argument)
        descriptor = int(source_argument.rsplit("/", 1)[1])
        os.lseek(descriptor, 0, os.SEEK_SET)
        assert os.read(descriptor, len(committed) + 1) == committed
        _write(output, b"\x7fELFcompiled", 0o755)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(admin, "hold_source_file_components", reject_checkout_source)
    monkeypatch.setattr(admin.subprocess, "run", fake_compile)

    built, provenance = admin._compile_admin_launcher(
        "runtime",
        committed_source=committed,
        python_pin={"sha256": "1" * 64, "size_bytes": 1},
        helper_pin={"sha256": "2" * 64, "size_bytes": 2},
        output=output,
    )

    assert built == _pin_for(output, executable=True)
    assert provenance["source"]["pin"] == {
        "sha256": hashlib.sha256(committed).hexdigest(),
        "size_bytes": len(committed),
    }
    assert provenance["source"]["compiled_from_sealed_memfd"] is True


def test_stage_installer_compiles_exact_head_blob_memfd_and_candidate_pins(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    compiler = tmp_path / "compiler"
    output = tmp_path / "stage-installer"
    _write(compiler, b"compiler-driver", 0o755)
    committed = b"/* exact Git stage-installer blob */\nint main(void){return 0;}\n"
    mutable_checkout = tmp_path / "mutable-stage-installer.c"
    _write(mutable_checkout, b"malicious replacement\n")
    monkeypatch.setattr(admin, "ROOT_UID", -1)
    monkeypatch.setattr(admin, "COMPILER_PATH", compiler)
    monkeypatch.setattr(admin, "STAGE_INSTALLER_SOURCE", mutable_checkout)
    monkeypatch.setattr(admin, "CHECKOUT_ROOT", tmp_path)
    monkeypatch.setattr(admin, "_review_toolchain_artifact_pins", lambda: [])
    original_hold = admin.hold_source_file_components

    @contextlib.contextmanager
    def reject_checkout_source(path: Path):
        if path == mutable_checkout:
            raise AssertionError("compile reopened mutable stage-installer source")
        with original_hold(path) as held:
            yield held

    def fake_compile(
        command: list[str], **kwargs: object
    ) -> subprocess.CompletedProcess[str]:
        source_argument = next(
            item for item in command if item.startswith("/proc/self/fd/")
        )
        assert command[command.index("-x") + 1] == "c"
        assert command.index("-x") < command.index(source_argument)
        descriptor = int(source_argument.rsplit("/", 1)[1])
        os.lseek(descriptor, 0, os.SEEK_SET)
        assert os.read(descriptor, len(committed) + 1) == committed
        assert "-DVISTA_R8_STAGE_RUNTIME_PLAN" in command
        assert f'-DEXPECTED_REVIEWED_PLAN_PIN_SHA256="{"3" * 64}"' in command
        assert f'-DEXPECTED_ADMIN_LAUNCHER_SHA256="{"4" * 64}"' in command
        _write(output, b"\x7fELFcompiled-stage-installer", 0o755)
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(admin, "hold_source_file_components", reject_checkout_source)
    monkeypatch.setattr(admin.subprocess, "run", fake_compile)

    built, provenance = admin._compile_stage_installer(
        "runtime-plan",
        committed_source=committed,
        python_pin={"sha256": "1" * 64, "size_bytes": 11},
        helper_pin={"sha256": "2" * 64, "size_bytes": 22},
        primary_pin={"sha256": "3" * 64, "size_bytes": 33},
        secondary_pin={"sha256": "4" * 64, "size_bytes": 44},
        output=output,
    )

    assert built == _pin_for(output, executable=True)
    assert provenance["source"]["pin"] == {
        "sha256": hashlib.sha256(committed).hexdigest(),
        "size_bytes": len(committed),
    }
    assert provenance["source"]["compiled_from_sealed_memfd"] is True
    assert provenance["primary_pin"] == {"sha256": "3" * 64, "size_bytes": 33}
    assert provenance["secondary_pin"] == {"sha256": "4" * 64, "size_bytes": 44}


def test_all_stage_installer_local_native_builds_are_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        admin,
        "_compile_stage_installer",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("local compiler must not run")
        ),
    )
    for key in admin.STAGE_KEYS:
        with pytest.raises(
            admin.AuthorityError, match="DEDICATED_BUILDER_AUTHORITY_REQUIRED"
        ):
            admin.build_stage_installer_review_candidate(key)
    assert not any(tmp_path.iterdir())


def test_stage_transfer_local_native_build_is_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        admin,
        "_compile_stage_transfer_launcher",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("local compiler must not run")
        ),
    )
    with pytest.raises(
        admin.AuthorityError, match="DEDICATED_BUILDER_AUTHORITY_REQUIRED"
    ):
        admin.build_stage_transfer_launcher_review_candidate()
    assert not any(tmp_path.iterdir())


def test_parent_seal_local_native_build_is_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        admin,
        "_compile_parent_seal_launcher",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("local compiler must not run")
        ),
    )
    with pytest.raises(
        admin.AuthorityError, match="DEDICATED_BUILDER_AUTHORITY_REQUIRED"
    ):
        admin.build_parent_seal_review_candidate()
    assert not any(tmp_path.iterdir())


def test_buildplugin_admin_candidate_is_exact_closed_shell_and_root_path_free(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    uid, gid = os.getuid(), os.getgid()
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    helper = checkout / "vista_r8_buildplugin_authority.py"
    python = tmp_path / "python3.10"
    _write(helper, b"reviewed BuildPlugin helper", 0o644)
    _write(python, b"reviewed python", 0o755)
    final = tmp_path / "buildplugin-admin-review"
    monkeypatch.setattr(admin, "REVIEW_UID", uid)
    monkeypatch.setattr(admin, "REVIEW_GID", gid)
    monkeypatch.setattr(admin, "CHECKOUT_ROOT", checkout)
    monkeypatch.setattr(admin, "BUILDPLUGIN_HELPER_SOURCE", helper)
    monkeypatch.setattr(admin, "BUILDPLUGIN_ADMIN_REVIEW_CANDIDATE_ROOT", final)
    monkeypatch.setattr(admin, "PYTHON_PATH", python)
    monkeypatch.setattr(
        admin,
        "_require_unprivileged_review_helper",
        lambda: {helper.name: helper.read_bytes()},
    )
    _bomb_root_access(monkeypatch)

    result = admin.build_buildplugin_admin_review_candidate()

    assert result["accepted"] is False
    assert set(path.name for path in final.iterdir()) == {
        helper.name,
        admin.BUILDPLUGIN_ADMIN_SCRIPT_NAME,
    }
    assert all(stat.S_IMODE(path.stat().st_mode) == 0o444 for path in final.iterdir())
    script = (final / admin.BUILDPLUGIN_ADMIN_SCRIPT_NAME).read_text()
    assert "/usr/bin/id" in script
    assert "/usr/bin/stat" in script
    assert "/usr/bin/sha256sum" in script
    assert "/usr/bin/env -i PATH=/usr/bin:/bin" in script
    assert "publish-buildplugin" in script
    assert "reconcile-buildplugin" in script
    assert "--admin-launcher-fd 8" in script
    assert "BASH_ENV" not in script


def test_core_candidate_generation_refuses_pending_engine_wrapper(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    uid, gid = os.getuid(), os.getgid()
    final = tmp_path / "core-review"
    monkeypatch.setattr(admin, "REVIEW_UID", uid)
    monkeypatch.setattr(admin, "REVIEW_GID", gid)
    monkeypatch.setattr(admin, "CORE_BOOTSTRAP_REVIEW_CANDIDATE_ROOT", final)
    pending = b"EXPECTED_HELPER_SHA256=REVIEWED_HELPER_SHA256_REQUIRED\n"
    monkeypatch.setattr(
        admin,
        "_require_unprivileged_review_helper",
        lambda: {"wrapper": pending},
    )

    def pending_materials(
        committed: dict[str, bytes], *, require_core_candidate: bool
    ) -> dict[str, object]:
        assert require_core_candidate is False
        admin._engine_wrapper_review_bindings(
            committed["wrapper"],
            helper_pin=admin.FilePin("1" * 64, 1),
            source_pin=admin.FilePin("2" * 64, 2),
            python_pin=admin.FilePin("3" * 64, 3),
        )
        raise AssertionError("unreachable")

    monkeypatch.setattr(admin, "_core_bootstrap_review_materials", pending_materials)

    with pytest.raises(admin.AuthorityError, match="CORE_BOOTSTRAP_REVIEW_PENDING"):
        admin.build_core_bootstrap_review_candidate()

    assert not final.exists()


def test_core_bootstrap_audit_is_user_only_canonical_and_zero_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    uid, gid = os.geteuid(), os.getegid()
    monkeypatch.setattr(admin, "REVIEW_UID", uid)
    monkeypatch.setattr(admin, "REVIEW_GID", gid)
    monkeypatch.setattr(
        admin,
        "_require_unprivileged_review_binding",
        lambda: (
            {"commit": "a" * 40, "tracked_paths": ["reviewed"]},
            {"reviewed": b"bytes"},
        ),
    )
    monkeypatch.setattr(
        admin,
        "_core_bootstrap_review_materials",
        lambda _sources, *, require_core_candidate: {
            "core_candidate": {"validated": require_core_candidate}
        },
    )
    monkeypatch.setattr(
        admin.tempfile,
        "mkdtemp",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("zero-write audit created staging")
        ),
    )
    monkeypatch.setattr(
        admin,
        "_write_new",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("zero-write audit wrote output")
        ),
    )

    result = admin.audit_core_bootstrap_review_inputs()

    assert result["schema"] == admin.CORE_BOOTSTRAP_REVIEW_AUDIT_SCHEMA
    assert result["claims"]["persistent_authority_write_performed"] is False
    assert result["claims"]["ephemeral_review_build_performed"] is False
    assert result["claims"]["dedicated_builder_phase_a_validated"] is True
    assert result["claims"]["local_user_native_compile_performed"] is False
    assert result["content_digest"] == admin.content_digest(result)

    monkeypatch.setattr(admin.os, "geteuid", lambda: admin.ROOT_UID)
    with pytest.raises(admin.AuthorityError, match="UNPRIVILEGED_REVIEW_REQUIRED"):
        admin.audit_core_bootstrap_review_inputs()


def _fake_static_pin(path: Path, _label: str) -> admin.FilePin:
    raw = path.read_bytes()
    return admin.FilePin(hashlib.sha256(raw).hexdigest(), len(raw), True)


def _fake_static_fd(descriptor: int, label: str) -> admin.FilePin:
    return admin._read_sealed_native_output(descriptor, label)[1]


def test_stdlib_static_elf_audit_rejects_malformed_stage_artifact() -> None:
    with pytest.raises(admin.AuthorityError, match="NATIVE_BUILDER_ARTIFACT_INVALID"):
        admin._stdlib_require_static_elf(b"\\x7fELFmalformed", "stage transfer")


def test_stdlib_static_elf_audit_rejects_dynamic_parent_artifact() -> None:
    with pytest.raises(admin.AuthorityError, match="NATIVE_BUILDER_ARTIFACT_INVALID"):
        admin._stdlib_require_static_elf(Path("/bin/true").read_bytes(), "parent seal")


def test_core_native_local_rebuild_entrypoints_are_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        admin,
        "_compile_core_native_isolated",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("legacy bwrap rebuild must not run")
        ),
    )
    for operation in (
        admin.build_stage_transfer_launcher_review_candidate,
        admin.build_parent_seal_review_candidate,
    ):
        with pytest.raises(
            admin.AuthorityError, match="DEDICATED_BUILDER_AUTHORITY_REQUIRED"
        ):
            operation()


def test_one_shot_installer_transfer_is_pinned_immutable_and_fd_bound(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    uid, gid = os.getuid(), os.getgid()
    root_parent = tmp_path / "root"
    root_parent.mkdir(mode=0o700)
    installer_parent = root_parent / "stage-installers"
    review_root = tmp_path / "runtime-input-installer-candidate"
    review_root.mkdir(mode=0o700)
    review_binary = review_root / admin.STAGE_INSTALLER_NAME
    _write(review_binary, b"\x7fELFone-shot-installer", 0o555)
    review_root.chmod(0o555)
    authority = installer_parent / "runtime-input"
    helper_pin = admin.FilePin("1" * 64, 11)
    python_pin = admin.FilePin("2" * 64, 22, True)
    transfer_pin = admin.FilePin("3" * 64, 33, True)
    monkeypatch.setattr(admin, "ROOT_UID", uid)
    monkeypatch.setattr(admin, "ROOT_GID", gid)
    monkeypatch.setattr(admin, "REVIEW_UID", uid)
    monkeypatch.setattr(admin, "REVIEW_GID", gid)
    monkeypatch.setattr(admin, "STAGE_INSTALLER_AUTHORITY_PARENT", installer_parent)
    monkeypatch.setattr(
        admin,
        "STAGE_INSTALLER_AUTHORITIES",
        {**admin.STAGE_INSTALLER_AUTHORITIES, "runtime-input": authority},
    )
    monkeypatch.setattr(
        admin,
        "STAGE_INSTALLER_REVIEW_ROOTS",
        {**admin.STAGE_INSTALLER_REVIEW_ROOTS, "runtime-input": review_root},
    )
    monkeypatch.setattr(admin, "_require_core_installed", lambda: None)
    monkeypatch.setattr(admin, "_core_authority_identity", lambda: (("core",),))
    monkeypatch.setattr(
        admin,
        "_core_publisher_pins",
        lambda: (helper_pin, python_pin, transfer_pin),
    )
    monkeypatch.setattr(
        admin,
        "_require_stage_transfer_invocation",
        lambda _descriptor: transfer_pin,
    )
    monkeypatch.setattr(
        admin,
        "operation_lock",
        lambda _stage: contextlib.nullcontext(),
    )
    monkeypatch.setattr(
        admin.subprocess,
        "run",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("installer transfer ran subprocess")
        ),
    )
    reviewed = _pin_for(review_binary, executable=True)

    result = admin.install_stage_installer_authority(
        "runtime",
        plan=False,
        reviewed_installer_pin=reviewed.public(),
        stage_transfer_launcher_fd=8,
    )

    assert result["publication_performed"] is True
    assert set(path.name for path in authority.iterdir()) == {
        admin.STAGE_INSTALLER_NAME,
        "receipt.json",
    }
    assert stat.S_IMODE(authority.stat().st_mode) == 0o555
    assert (
        stat.S_IMODE((authority / admin.STAGE_INSTALLER_NAME).stat().st_mode) == 0o555
    )
    assert stat.S_IMODE((authority / "receipt.json").stat().st_mode) == 0o444
    with pytest.raises(admin.AuthorityError, match="FINAL_NOT_FRESH"):
        admin.install_stage_installer_authority(
            "runtime",
            plan=False,
            reviewed_installer_pin=reviewed.public(),
            stage_transfer_launcher_fd=8,
        )
    reconciled = admin.reconcile_stage_installer_authority(
        "runtime",
        plan=False,
        reviewed_installer_pin=reviewed.public(),
        stage_transfer_launcher_fd=8,
    )
    assert reconciled["publication_performed"] is False
    installed = authority / admin.STAGE_INSTALLER_NAME
    descriptor = os.open(installed, os.O_RDONLY | os.O_CLOEXEC)
    wrong = os.open(authority / "receipt.json", os.O_RDONLY | os.O_CLOEXEC)
    try:
        receipt = admin._require_stage_installer_invocation(
            "runtime", plan=False, descriptor=descriptor
        )
        assert receipt["installer"]["pin"] == reviewed.public()
        with pytest.raises(
            admin.AuthorityError, match="STAGE_INSTALLER_INVOCATION_INVALID"
        ):
            admin._require_stage_installer_invocation(
                "runtime", plan=False, descriptor=wrong
            )
    finally:
        os.close(wrong)
        os.close(descriptor)


def test_core_live_fsync_covers_exact_root_and_fails_closed_on_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    uid, gid = os.getuid(), os.getgid()
    parent = tmp_path / "root"
    parent.mkdir(mode=0o700)
    root = parent / "vista-r8-ue57-authority-r2"
    root.mkdir(mode=0o700)
    paths = {
        "vista_r8_ue57_authority_admin.py": 0o500,
        "provision_vista_r8_ue57_engine.sh": 0o500,
        "transfer-r8-ue57-stage-installer": 0o555,
        "engine-source-pin.json": 0o444,
        ".engine.lock": 0o600,
        ".runtime.lock": 0o600,
        ".bundle.lock": 0o600,
        ".executor.lock": 0o600,
    }
    for name, mode in paths.items():
        _write(root / name, b"" if name.startswith(".") else name.encode(), mode)
    root.chmod(0o555)
    monkeypatch.setattr(admin, "ROOT_UID", uid)
    monkeypatch.setattr(admin, "ROOT_GID", gid)
    monkeypatch.setattr(admin, "INSTALLED_ROOT", root)
    monkeypatch.setattr(
        admin, "INSTALLED_HELPER", root / "vista_r8_ue57_authority_admin.py"
    )
    monkeypatch.setattr(
        admin,
        "INSTALLED_ENGINE_WRAPPER",
        root / "provision_vista_r8_ue57_engine.sh",
    )
    monkeypatch.setattr(
        admin,
        "INSTALLED_STAGE_TRANSFER_LAUNCHER",
        root / "transfer-r8-ue57-stage-installer",
    )
    monkeypatch.setattr(
        admin, "ENGINE_SOURCE_PIN_PATH", root / "engine-source-pin.json"
    )
    monkeypatch.setattr(
        admin,
        "OPERATION_LOCKS",
        {
            "engine": root / ".engine.lock",
            "runtime": root / ".runtime.lock",
            "bundle": root / ".bundle.lock",
            "executor": root / ".executor.lock",
        },
    )
    monkeypatch.setattr(admin, "_require_core_installed", lambda: None)
    expected = {path.stat().st_ino for path in (parent, root, *root.iterdir())}
    observed: set[int] = set()
    real_fsync = os.fsync

    def record_fsync(descriptor: int) -> None:
        observed.add(os.fstat(descriptor).st_ino)
        real_fsync(descriptor)

    monkeypatch.setattr(admin.os, "fsync", record_fsync)
    admin._live_fsync_core_authority()
    assert expected <= observed

    monkeypatch.setattr(
        admin.os,
        "fsync",
        lambda _descriptor: (_ for _ in ()).throw(OSError("injected fsync")),
    )
    with pytest.raises(
        admin.AuthorityError, match="CORE_AUTHORITY_LIVE_FSYNC_REQUIRED"
    ):
        admin._live_fsync_core_authority()

    helper = admin.INSTALLED_HELPER
    mutated = False

    def mutate_during_fsync(descriptor: int) -> None:
        nonlocal mutated
        real_fsync(descriptor)
        if not mutated:
            mutated = True
            helper.chmod(0o700)
            helper.write_bytes(b"mutated core helper")
            helper.chmod(0o500)

    monkeypatch.setattr(admin.os, "fsync", mutate_during_fsync)
    with pytest.raises(
        admin.AuthorityError, match="CORE_AUTHORITY_LIVE_FSYNC_REQUIRED"
    ):
        admin._live_fsync_core_authority()


def test_one_shot_installer_transfer_rejects_wrong_external_pin(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    uid, gid = os.getuid(), os.getgid()
    root_parent = tmp_path / "root"
    root_parent.mkdir(mode=0o700)
    review_root = tmp_path / "candidate"
    review_root.mkdir()
    binary = review_root / admin.STAGE_INSTALLER_NAME
    _write(binary, b"\x7fELFcandidate", 0o555)
    review_root.chmod(0o555)
    monkeypatch.setattr(admin, "ROOT_UID", uid)
    monkeypatch.setattr(admin, "ROOT_GID", gid)
    monkeypatch.setattr(admin, "REVIEW_UID", uid)
    monkeypatch.setattr(admin, "REVIEW_GID", gid)
    monkeypatch.setattr(
        admin, "STAGE_INSTALLER_AUTHORITY_PARENT", root_parent / "installers"
    )
    monkeypatch.setattr(
        admin,
        "STAGE_INSTALLER_AUTHORITIES",
        {
            **admin.STAGE_INSTALLER_AUTHORITIES,
            "runtime-input": root_parent / "installers/runtime-input",
        },
    )
    monkeypatch.setattr(
        admin,
        "STAGE_INSTALLER_REVIEW_ROOTS",
        {**admin.STAGE_INSTALLER_REVIEW_ROOTS, "runtime-input": review_root},
    )
    monkeypatch.setattr(admin, "_require_core_installed", lambda: None)
    monkeypatch.setattr(admin, "_core_authority_identity", lambda: (("core",),))
    monkeypatch.setattr(
        admin,
        "operation_lock",
        lambda _stage: contextlib.nullcontext(),
    )
    monkeypatch.setattr(
        admin,
        "_require_stage_transfer_invocation",
        lambda _descriptor: admin.FilePin("3" * 64, 33, True),
    )

    with pytest.raises(
        admin.AuthorityError, match="STAGE_EXTERNAL_REVIEW_PIN_MISMATCH"
    ):
        admin.install_stage_installer_authority(
            "runtime",
            plan=False,
            reviewed_installer_pin={
                "sha256": "0" * 64,
                "size_bytes": binary.stat().st_size,
            },
            stage_transfer_launcher_fd=8,
        )


def test_stage_installer_parent_requires_exact_append_only_prefix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    parent = tmp_path / "stage-installers"
    parent.mkdir(mode=0o700)
    monkeypatch.setattr(admin, "ROOT_UID", os.getuid())
    monkeypatch.setattr(admin, "ROOT_GID", os.getgid())
    monkeypatch.setattr(admin, "STAGE_INSTALLER_AUTHORITY_PARENT", parent)

    (parent / "runtime-plan").mkdir(mode=0o555)
    with pytest.raises(admin.AuthorityError, match="STAGE_INSTALLER_SEQUENCE_INVALID"):
        admin._require_stage_installer_sequence("runtime-input", include_current=False)

    (parent / "runtime-plan").rmdir()
    (parent / "runtime-input").mkdir(mode=0o555)
    admin._require_stage_installer_sequence("runtime-plan", include_current=False)
    with pytest.raises(admin.AuthorityError, match="STAGE_INSTALLER_SEQUENCE_INVALID"):
        admin._require_stage_installer_sequence("runtime-plan", include_current=True)


def test_stage_installer_transfer_detects_and_preserves_earlier_child_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    uid, gid = os.getuid(), os.getgid()
    root_parent = tmp_path / "root"
    root_parent.mkdir(mode=0o700)
    installer_parent = root_parent / "stage-installers"
    installer_parent.mkdir(mode=0o700)
    earlier = installer_parent / "runtime-input"
    earlier.mkdir(mode=0o755)
    earlier_marker = earlier / "marker"
    _write(earlier_marker, b"reviewed-earlier-authority", 0o444)
    earlier.chmod(0o555)
    review_root = tmp_path / "runtime-plan-installer-candidate"
    review_root.mkdir(mode=0o700)
    review_binary = review_root / admin.STAGE_INSTALLER_NAME
    _write(review_binary, b"\x7fELFruntime-plan-installer", 0o555)
    review_root.chmod(0o555)
    authority = installer_parent / "runtime-plan"
    helper_pin = admin.FilePin("1" * 64, 11)
    python_pin = admin.FilePin("2" * 64, 22, True)
    transfer_pin = admin.FilePin("3" * 64, 33, True)
    monkeypatch.setattr(admin, "ROOT_UID", uid)
    monkeypatch.setattr(admin, "ROOT_GID", gid)
    monkeypatch.setattr(admin, "REVIEW_UID", uid)
    monkeypatch.setattr(admin, "REVIEW_GID", gid)
    monkeypatch.setattr(admin, "STAGE_INSTALLER_AUTHORITY_PARENT", installer_parent)
    monkeypatch.setattr(
        admin,
        "STAGE_INSTALLER_AUTHORITIES",
        {**admin.STAGE_INSTALLER_AUTHORITIES, "runtime-plan": authority},
    )
    monkeypatch.setattr(
        admin,
        "STAGE_INSTALLER_REVIEW_ROOTS",
        {**admin.STAGE_INSTALLER_REVIEW_ROOTS, "runtime-plan": review_root},
    )
    monkeypatch.setattr(admin, "_require_core_installed", lambda: None)
    monkeypatch.setattr(admin, "_core_authority_identity", lambda: (("core",),))
    monkeypatch.setattr(
        admin,
        "_core_publisher_pins",
        lambda: (helper_pin, python_pin, transfer_pin),
    )
    monkeypatch.setattr(
        admin,
        "_require_stage_transfer_invocation",
        lambda _descriptor: transfer_pin,
    )
    monkeypatch.setattr(
        admin, "operation_lock", lambda _stage: contextlib.nullcontext()
    )
    monkeypatch.setattr(
        admin,
        "_previous_stage_installer_identities",
        lambda _key: {
            "runtime-input": (
                hashlib.sha256(earlier_marker.read_bytes()).hexdigest(),
                stat.S_IMODE(earlier_marker.stat().st_mode),
            )
        },
    )
    original_publish = admin.publish_staging

    def publish_then_mutate_earlier(staging: Path, final: Path) -> None:
        original_publish(staging, final)
        earlier_marker.chmod(0o644)
        earlier_marker.write_bytes(b"mutated-after-later-publication")
        earlier_marker.chmod(0o444)

    monkeypatch.setattr(admin, "publish_staging", publish_then_mutate_earlier)
    reviewed = _pin_for(review_binary, executable=True)

    with pytest.raises(admin.AuthorityError, match="EARLIER_STAGE_AUTHORITY_DRIFT"):
        admin.install_stage_installer_authority(
            "runtime",
            plan=True,
            reviewed_installer_pin=reviewed.public(),
            stage_transfer_launcher_fd=8,
        )

    assert authority.is_dir()
    assert (
        authority / admin.STAGE_INSTALLER_NAME
    ).read_bytes() == review_binary.read_bytes()
    assert earlier_marker.read_bytes() == b"mutated-after-later-publication"


def test_candidate_size_mismatch_rejects_before_hash_or_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    candidate = tmp_path / "candidate"
    _write(candidate, b"x" * 4096, 0o555)
    monkeypatch.setattr(admin, "REVIEW_UID", os.getuid())
    monkeypatch.setattr(admin, "REVIEW_GID", os.getgid())
    with admin.hold_source_file_components(candidate) as held:
        monkeypatch.setattr(
            admin,
            "_hash_fd",
            lambda _descriptor: (_ for _ in ()).throw(
                AssertionError("size mismatch reached hashing")
            ),
        )
        with pytest.raises(
            admin.AuthorityError, match="STAGE_EXTERNAL_REVIEW_PIN_MISMATCH"
        ):
            admin._read_held_bytes(
                held,
                admin.FilePin("0" * 64, 1),
                "oversized candidate",
            )


def test_initial_bootstrap_phase_b_request_derivation_is_zero_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = admin.seal_document(
        {
            "schema": admin.NATIVE_BUILDER_REQUEST_SCHEMA,
            "phase": "phase-b",
            "accepted": False,
        }
    )
    initial = admin.seal_document(
        {"schema": admin.INITIAL_BOOTSTRAP_INPUT_PIN_SCHEMA, "accepted": False}
    )
    audit = admin.seal_document(
        {"schema": admin.CORE_BOOTSTRAP_REVIEW_AUDIT_SCHEMA, "accepted": False}
    )
    monkeypatch.setattr(
        admin,
        "_derive_native_builder_phase_b_request",
        lambda _pin: (request, initial, audit),
    )
    result = admin.build_initial_bootstrap_review_candidate(
        {"sha256": "1" * 64, "size_bytes": 1}
    )
    assert result["status"] == "native_builder_phase_b_request_derived_zero_write"
    assert result["request_document"] == request
    assert result["candidate_publication_performed"] is False
    assert not any(tmp_path.iterdir())


def _phase_b_cross_binding_documents(
    host: Path,
) -> tuple[
    dict[str, object],
    admin.FilePin,
    dict[str, object],
    admin.FilePin,
    dict[str, object],
]:
    trace_contract = _native_trace_contract(host)
    source_pin = {"sha256": "1" * 64, "size_bytes": 11}
    builder_pin = {"sha256": "2" * 64, "size_bytes": 22}
    bundle_pin = {"sha256": "3" * 64, "size_bytes": 33}
    common_builder = {
        "path": str(admin.NATIVE_BUILDER_HELPER),
        "mode": "0444",
        "uid": admin.ROOT_UID,
        "gid": admin.ROOT_GID,
        "pin": builder_pin,
    }
    tools = {
        "python": {"pin": {"sha256": "4" * 64, "size_bytes": 44}},
        "git": {"pin": {"sha256": "5" * 64, "size_bytes": 55}},
        "compiler": {"pin": {"sha256": "6" * 64, "size_bytes": 66}},
        "readelf": {"pin": {"sha256": "7" * 64, "size_bytes": 77}},
        "tracer": {"pin": {"sha256": "8" * 64, "size_bytes": 88}},
        "toolchain": admin._native_builder_trace_toolchain(trace_contract),
    }
    phase_a_request = admin.seal_document(
        {
            "schema": admin.NATIVE_BUILDER_REQUEST_SCHEMA,
            "phase": "phase-a",
            "status": "reviewed_native_build_request",
            "accepted": False,
            "builder": {
                **common_builder,
                "service_unit": {"path": "phase-a.service"},
            },
            "source_bundle": {"path": "source.bundle", "pin": bundle_pin},
            "source_commit": "a" * 40,
            "sources": [{"path": "source.c", "pin": source_pin}],
            "tools": tools,
            "trace_contract": trace_contract,
            "jobs": [],
            "phase_inputs": {},
            "claims": {"accepted": False},
        }
    )
    phase_a_raw = admin.canonical_json(phase_a_request)
    phase_a_request_pin = admin.FilePin(
        hashlib.sha256(phase_a_raw).hexdigest(), len(phase_a_raw)
    )
    phase_a_manifest = admin.seal_document(
        {
            "schema": admin.NATIVE_BUILDER_PHASE_A_SCHEMA,
            "status": "dedicated_builder_phase_closed",
            "accepted": False,
            "phase": "phase-a",
            "request_pin": phase_a_request_pin.public(),
            "source_commit": phase_a_request["source_commit"],
            "source_bundle_pin": bundle_pin,
            "jobs": [],
            "inventory": {},
            "claims": {"closed": True},
        }
    )
    phase_a_manifest_raw = admin.canonical_json(phase_a_manifest)
    phase_a_manifest_pin = admin.FilePin(
        hashlib.sha256(phase_a_manifest_raw).hexdigest(),
        len(phase_a_manifest_raw),
    )
    phase_b_request = admin.seal_document(
        {
            "schema": admin.NATIVE_BUILDER_REQUEST_SCHEMA,
            "phase": "phase-b",
            "status": "reviewed_native_build_request",
            "accepted": False,
            "builder": {
                **common_builder,
                "service_unit": {"path": "phase-b.service"},
            },
            "source_bundle": phase_a_request["source_bundle"],
            "source_commit": phase_a_request["source_commit"],
            "sources": phase_a_request["sources"],
            "tools": phase_a_request["tools"],
            "trace_contract": phase_a_request["trace_contract"],
            "jobs": [],
            "phase_inputs": {
                "phase_a": {
                    "root": str(admin.NATIVE_BUILDER_PHASE_A_ROOT),
                    "manifest_pin": phase_a_manifest_pin.public(),
                    "content_digest": phase_a_manifest["content_digest"],
                },
                "core_review_audit": {},
                "initial_input": {},
            },
            "claims": {"accepted": False},
        }
    )
    return (
        phase_a_request,
        phase_a_request_pin,
        phase_a_manifest,
        phase_a_manifest_pin,
        phase_b_request,
    )


def test_phase_b_job_rejects_coherently_resealed_extra_top_level_key(
    tmp_path: Path,
) -> None:
    host = tmp_path / "runtime"
    _write(host, b"runtime", 0o644)
    *_phase_a, request = _phase_b_cross_binding_documents(host)
    request = copy.deepcopy(request)
    source_pin = {"sha256": "9" * 64, "size_bytes": 99}
    installer_pin = admin.FilePin("a" * 64, 111)
    expected_job = {
        "id": "initial-bootstrap-installer",
        "source_path": "tools/admin/vista_r8_ue57_initial_bootstrap_installer.c",
        "output_name": admin.INITIAL_BOOTSTRAP_INSTALLER_NAME,
        "output_mode": "0555",
        "bindings": {"input_pin": {"sha256": "b" * 64, "size_bytes": 12}},
        "flags": ["-closed-test-flag"],
    }
    request["sources"] = [{"path": expected_job["source_path"], "pin": source_pin}]
    request["jobs"] = [expected_job]
    job = admin.seal_document(
        {
            "schema": admin.NATIVE_BUILDER_JOB_SCHEMA,
            "status": "deterministic_static_native_closed",
            "accepted": False,
            "phase": "phase-b",
            "job_id": "initial-bootstrap-installer",
            "source": {
                "git_bundle_pin": request["source_bundle"]["pin"],
                "commit": request["source_commit"],
                "git_path": expected_job["source_path"],
                "pin": source_pin,
                "compiled_from_sealed_memfd": True,
            },
            "bindings": expected_job["bindings"],
            "flags": expected_job["flags"],
            "environment": admin.NATIVE_BUILDER_BUILD_ENVIRONMENT,
            "tools": admin._native_builder_job_tools(
                request["tools"], request["trace_contract"]
            ),
            "output": {
                "relative_path": (
                    "initial-bootstrap-installer/"
                    + admin.INITIAL_BOOTSTRAP_INSTALLER_NAME
                ),
                "mode": "0555",
                "pin": installer_pin.public(),
            },
            "determinism": {
                "build_count": 2,
                "byte_identical": True,
                "first_pin": installer_pin.public(),
                "second_pin": installer_pin.public(),
            },
            "static_elf": {
                "interpreter": None,
                "needed": [],
                "readelf_pin": request["tools"]["readelf"]["pin"],
            },
            "claims": {
                "builder_uid_gid": [
                    admin.NATIVE_BUILDER_UID,
                    admin.NATIVE_BUILDER_GID,
                ],
                "network_access": False,
                "worktree_input": False,
                "user_candidate_input": False,
            },
        }
    )
    assert (
        admin._native_builder_validate_phase_b_job(
            job,
            expected_request=request,
            installer_source_pin=source_pin,
            installer_pin=installer_pin,
        )
        == job
    )

    resealed = copy.deepcopy(job)
    resealed["unexpected"] = {"aggregate_manifest_also_updated": True}
    resealed.pop("content_digest")
    resealed = admin.seal_document(resealed)
    with pytest.raises(admin.AuthorityError, match="phase B installer job"):
        admin._native_builder_validate_phase_b_job(
            resealed,
            expected_request=request,
            installer_source_pin=source_pin,
            installer_pin=installer_pin,
        )


@pytest.mark.parametrize(
    "tamper",
    [
        "bundle",
        "commit",
        "sources",
        "builder",
        "tools",
        "runtime_trace",
        "phase_a_request_pin",
        "phase_a_manifest_pin",
        "phase_a_binding",
    ],
)
def test_phase_b_cross_binding_is_exact_and_rejects_each_lineage_break(
    tmp_path: Path,
    tamper: str,
) -> None:
    host = tmp_path / "runtime"
    _write(host, b"runtime", 0o644)
    (
        phase_a_request,
        phase_a_request_pin,
        phase_a_manifest,
        phase_a_manifest_pin,
        phase_b_request,
    ) = _phase_b_cross_binding_documents(host)
    admin._native_builder_validate_phase_b_cross_binding(
        phase_b_request=phase_b_request,
        phase_a_request=phase_a_request,
        phase_a_request_pin=phase_a_request_pin,
        phase_a_manifest=phase_a_manifest,
        phase_a_manifest_pin=phase_a_manifest_pin,
    )

    broken_request = copy.deepcopy(phase_b_request)
    broken_request_pin = phase_a_request_pin
    broken_manifest_pin = phase_a_manifest_pin
    if tamper == "bundle":
        broken_request["source_bundle"]["pin"]["sha256"] = "9" * 64  # type: ignore[index]
    elif tamper == "commit":
        broken_request["source_commit"] = "b" * 40
    elif tamper == "sources":
        broken_request["sources"][0]["pin"]["sha256"] = "9" * 64  # type: ignore[index]
    elif tamper == "builder":
        broken_request["builder"]["pin"]["sha256"] = "9" * 64  # type: ignore[index]
    elif tamper == "tools":
        broken_request["tools"]["tracer"]["pin"]["sha256"] = "9" * 64  # type: ignore[index]
    elif tamper == "runtime_trace":
        broken_request["trace_contract"]["builder_runtime_files"] = []  # type: ignore[index]
    elif tamper == "phase_a_request_pin":
        broken_request_pin = admin.FilePin("9" * 64, phase_a_request_pin.size_bytes)
    elif tamper == "phase_a_manifest_pin":
        broken_manifest_pin = admin.FilePin("9" * 64, phase_a_manifest_pin.size_bytes)
    else:
        broken_request["phase_inputs"]["phase_a"]["root"] = "/wrong"  # type: ignore[index]
    if tamper not in {"phase_a_request_pin", "phase_a_manifest_pin"}:
        broken_request.pop("content_digest")
        broken_request = admin.seal_document(broken_request)

    with pytest.raises(
        admin.AuthorityError, match="NATIVE_BUILDER_PHASE_B_LINEAGE_INVALID"
    ):
        admin._native_builder_validate_phase_b_cross_binding(
            phase_b_request=broken_request,
            phase_a_request=phase_a_request,
            phase_a_request_pin=broken_request_pin,
            phase_a_manifest=phase_a_manifest,
            phase_a_manifest_pin=broken_manifest_pin,
        )


def test_phase_b_cross_binding_runs_at_derivation_and_held_audit_boundaries() -> None:
    source = Path(admin.__file__).read_text()
    assert source.count("_native_builder_validate_phase_b_cross_binding(") == 3


def test_initial_bootstrap_candidate_rejects_root_and_external_pin_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(admin.os, "geteuid", lambda: admin.ROOT_UID)
    with pytest.raises(admin.AuthorityError, match="UNPRIVILEGED_REVIEW_REQUIRED"):
        admin.build_initial_bootstrap_review_candidate(
            {"sha256": "0" * 64, "size_bytes": 1}
        )


def test_initial_bootstrap_installer_consumes_only_phase_b_authority(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(admin, "NATIVE_BUILDER_PHASE_B_REQUEST", tmp_path / "absent")
    monkeypatch.setattr(
        admin,
        "_compile_initial_bootstrap_installer",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("local compiler must not run")
        ),
    )
    with pytest.raises(admin.AuthorityError, match="FILE_INVALID"):
        admin.build_initial_bootstrap_installer_review_candidate()
    assert not any(tmp_path.iterdir())


def test_initial_bootstrap_installer_candidate_rejects_root(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(admin.os, "geteuid", lambda: admin.ROOT_UID)
    with pytest.raises(admin.AuthorityError, match="UNPRIVILEGED_REVIEW_REQUIRED"):
        admin.build_initial_bootstrap_installer_review_candidate()


def test_initial_bootstrap_candidate_rejects_external_pin_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(admin.os, "geteuid", lambda: admin.REVIEW_UID)
    monkeypatch.setattr(admin.os, "getegid", lambda: admin.REVIEW_GID)
    git = {"commit": "a" * 40}
    audit = admin.seal_document(
        {
            "schema": admin.CORE_BOOTSTRAP_REVIEW_AUDIT_SCHEMA,
            "git": git,
            "reviewed_inputs": {},
        }
    )
    monkeypatch.setattr(
        admin,
        "_require_unprivileged_review_binding",
        lambda: (git, {}),
    )
    monkeypatch.setattr(admin, "audit_core_bootstrap_review_inputs", lambda: audit)
    monkeypatch.setattr(
        admin.tempfile,
        "mkdtemp",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("pin mismatch reached staging")
        ),
    )
    with pytest.raises(
        admin.AuthorityError, match="INITIAL_BOOTSTRAP_AUDIT_PIN_MISMATCH"
    ):
        admin.build_initial_bootstrap_review_candidate(
            {"sha256": "0" * 64, "size_bytes": 1}
        )


def test_all_unfrozen_native_recipe_entrypoints_are_fail_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        admin,
        "_compile_admin_launcher",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(
            AssertionError("local compiler must not run")
        ),
    )
    for operation in (
        admin.build_runtime_plan_review_candidate,
        admin.build_bundle_plan_review_candidate,
        admin.build_bundle_input_review_candidate,
        admin.build_stage_transfer_launcher_review_candidate,
        admin.build_parent_seal_review_candidate,
    ):
        with pytest.raises(
            admin.AuthorityError, match="DEDICATED_BUILDER_AUTHORITY_REQUIRED"
        ):
            operation()
    for key in admin.STAGE_KEYS:
        with pytest.raises(
            admin.AuthorityError, match="DEDICATED_BUILDER_AUTHORITY_REQUIRED"
        ):
            admin.build_stage_installer_review_candidate(key)
