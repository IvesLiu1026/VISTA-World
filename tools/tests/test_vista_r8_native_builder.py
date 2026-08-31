from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from tools.admin import vista_r8_native_builder as builder


def _pin(raw: bytes) -> dict[str, object]:
    return {"sha256": hashlib.sha256(raw).hexdigest(), "size_bytes": len(raw)}


def _trace_event(
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


def _tool(path: str, marker: str, mode: str = "0755") -> dict[str, object]:
    return {
        "path": path,
        "canonical": path,
        "mode": mode,
        "pin": _pin(marker.encode()),
    }


def _trace_host_file(path: Path) -> dict[str, object]:
    raw = path.read_bytes()
    return {
        "path": str(path),
        "canonical": str(path.resolve()),
        "mode": f"{path.stat().st_mode & 0o7777:04o}",
        "pin": _pin(raw),
        "storage": "regular",
        "component_chain": builder._path_component_chain(path),
    }


def _trace_host_directory(path: Path) -> dict[str, object]:
    return {
        "path": str(path),
        "canonical": str(path.resolve()),
        "component_chain": builder._path_component_chain(path),
    }


def _trace_contract(tmp_path: Path) -> dict[str, object]:
    host_file = tmp_path / "host-runtime.bin"
    host_file.write_bytes(b"host runtime")
    host_file.chmod(0o644)
    expected_tools = {
        invocation: tool
        for phase in ("phase-a", "phase-b")
        for invocation, tool in builder._expected_trace_invocations(phase)
    }
    absent = str(tmp_path / "vista-r8-absent")
    profiles = []
    for profile_id, tool in sorted(expected_tools.items()):
        profiles.append(
            {
                "id": profile_id,
                "tool": tool,
                "event_multiset": [
                    {
                        "line": _trace_event("access", absent, "ENOENT"),
                        "count": 1,
                    }
                ],
                "host_files": [str(host_file)],
                "host_directories": [str(tmp_path)],
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
        )
    return {
        "schema": builder.TRACE_CONTRACT_SCHEMA,
        "tracer_version": builder.STRACE_VERSION,
        "host_files": [_trace_host_file(host_file)],
        "host_directories": [_trace_host_directory(tmp_path)],
        "tracer_runtime_files": [str(host_file)],
        "builder_runtime_files": [str(host_file)],
        "path_aliases": [],
        "event_count_policies": builder._trace_event_count_policies(),
        "profiles": profiles,
        "phase_invocations": {
            phase: [
                invocation
                for invocation, _tool_name in builder._expected_trace_invocations(phase)
            ]
            for phase in ("phase-a", "phase-b")
        },
    }


def _request_trace_contract() -> dict[str, object]:
    python_pin = {
        "sha256": builder.PINNED_PYTHON_SHA256,
        "size_bytes": builder.PINNED_PYTHON_SIZE,
    }
    tracer_pin = _pin(b"strace")

    def record(path: str, pin: dict[str, object], inode: int) -> dict[str, object]:
        return {
            "path": path,
            "canonical": path,
            "mode": "0755",
            "pin": pin,
            "storage": "regular",
            "component_chain": [
                {
                    "path": "/",
                    "kind": "directory",
                    "mode": "0755",
                    "uid": 0,
                    "gid": 0,
                    "device": 1,
                    "inode": 2,
                    "nlink": 1,
                    "mtime_ns": 1,
                    "ctime_ns": 1,
                },
                {
                    "path": path,
                    "kind": "regular",
                    "mode": "0755",
                    "uid": 0,
                    "gid": 0,
                    "device": 1,
                    "inode": inode,
                    "nlink": 1,
                    "mtime_ns": 1,
                    "ctime_ns": 1,
                },
            ],
        }

    files = sorted(
        [
            record(str(builder.PYTHON_PATH), python_pin, 101),
            record(str(builder.STRACE_PATH), tracer_pin, 102),
        ],
        key=lambda item: item["path"],
    )
    root_directory = {
        "path": "/",
        "canonical": "/",
        "component_chain": [dict(files[0]["component_chain"][0])],
    }
    expected_tools = {
        invocation: tool
        for phase in ("phase-a", "phase-b")
        for invocation, tool in builder._expected_trace_invocations(phase)
    }
    profiles = [
        {
            "id": profile_id,
            "tool": tool,
            "event_multiset": [
                {
                    "line": _trace_event("access", "/vista-r8-absent", "ENOENT"),
                    "count": 1,
                }
            ],
            "host_files": [item["path"] for item in files],
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
        for profile_id, tool in sorted(expected_tools.items())
    ]
    return {
        "schema": builder.TRACE_CONTRACT_SCHEMA,
        "tracer_version": builder.STRACE_VERSION,
        "host_files": files,
        "host_directories": [root_directory],
        "tracer_runtime_files": [str(builder.STRACE_PATH)],
        "builder_runtime_files": [str(builder.PYTHON_PATH)],
        "path_aliases": [],
        "event_count_policies": builder._trace_event_count_policies(),
        "profiles": profiles,
        "phase_invocations": {
            phase: [
                invocation
                for invocation, _tool_name in builder._expected_trace_invocations(phase)
            ]
            for phase in ("phase-a", "phase-b")
        },
    }


def _request_trace_contract_with_kernel_virtual() -> dict[str, object]:
    contract = _request_trace_contract()
    special = builder._planner_trace_file_record(
        str(builder.KERNEL_VIRTUAL_SYSCTL_PATH)
    )
    contract["host_files"] = sorted(  # type: ignore[index]
        [*contract["host_files"], special],  # type: ignore[index]
        key=lambda item: item["path"],
    )
    profile = contract["profiles"][0]  # type: ignore[index]
    profile["host_files"] = sorted(  # type: ignore[index]
        [*profile["host_files"], str(builder.KERNEL_VIRTUAL_SYSCTL_PATH)]
    )
    profile["event_multiset"] = sorted(  # type: ignore[index]
        [
            *profile["event_multiset"],
            {
                "line": _trace_event(
                    "openat",
                    str(builder.KERNEL_VIRTUAL_SYSCTL_PATH),
                    "OK",
                    open_flags=["O_RDONLY"],
                ),
                "count": 1,
            },
        ],
        key=lambda item: item["line"],
    )
    return contract


def _source_pins() -> dict[str, dict[str, object]]:
    return {path: _pin(f"source:{path}".encode()) for path in builder.SOURCE_PATHS}


def _phase_a_request() -> dict[str, object]:
    source_pins = _source_pins()
    trace_contract = _request_trace_contract()
    python_pin = {
        "sha256": builder.PINNED_PYTHON_SHA256,
        "size_bytes": builder.PINNED_PYTHON_SIZE,
    }
    jobs: list[dict[str, object]] = []
    for job_id in builder.PHASE_A_JOB_IDS:
        spec = builder.JOB_SPECS[job_id]
        bindings = {
            "helper_pin": source_pins[spec["helper_source_path"]],
            "python_pin": python_pin,
        }
        jobs.append(
            {
                "id": job_id,
                "source_path": spec["source_path"],
                "output_name": spec["output_name"],
                "output_mode": "0555",
                "bindings": bindings,
                "flags": builder.expected_job_flags(job_id, bindings),
            }
        )
    return builder.seal_document(
        {
            "schema": builder.REQUEST_SCHEMA,
            "phase": "phase-a",
            "status": "reviewed_native_build_request",
            "accepted": False,
            "builder": {
                "path": str(builder.INSTALLED_BUILDER),
                "mode": "0444",
                "uid": 0,
                "gid": 0,
                "pin": _pin(b"builder"),
                "service_unit": {
                    "path": str(builder.UNIT_PATHS["phase-a"]),
                    "mode": "0644",
                    "uid": 0,
                    "gid": 0,
                    "pin": _pin(b"phase-a-unit"),
                },
            },
            "source_bundle": {
                "path": str(builder.SOURCE_BUNDLE),
                "mode": "0444",
                "uid": 0,
                "gid": 0,
                "pin": _pin(b"bundle"),
            },
            "source_commit": "a" * 40,
            "sources": [
                {"path": path, "pin": source_pins[path]}
                for path in sorted(builder.SOURCE_PATHS)
            ],
            "tools": {
                "python": {
                    "path": str(builder.PYTHON_PATH),
                    "canonical": str(builder.PYTHON_PATH),
                    "mode": "0755",
                    "pin": python_pin,
                },
                "git": _tool(str(builder.GIT_PATH), "git"),
                "compiler": _tool(str(builder.COMPILER_PATH), "compiler"),
                "readelf": _tool(str(builder.READELF_PATH), "readelf"),
                "tracer": _tool(str(builder.STRACE_PATH), "strace"),
                "toolchain": [
                    {key: record[key] for key in ("path", "canonical", "mode", "pin")}
                    for record in trace_contract["host_files"]  # type: ignore[index]
                ],
            },
            "trace_contract": trace_contract,
            "jobs": jobs,
            "phase_inputs": {},
            "claims": {
                "dedicated_builder_uid_gid": [997, 997],
                "network_access": False,
                "double_build_required": True,
                "worktree_or_user_candidate_input": False,
                "write_root": str(builder.STATE_ROOT),
                "observation_only": True,
                "production_native_output": False,
            },
        }
    )


def _job_manifest(
    request: dict[str, object], job: dict[str, object], marker: bytes
) -> dict[str, object]:
    pin = _pin(marker)
    sources = request["sources"]
    tools = request["tools"]
    source_pin = next(
        item["pin"]
        for item in sources  # type: ignore[union-attr]
        if item["path"] == job["source_path"]
    )
    return builder.seal_document(
        {
            "schema": builder.JOB_MANIFEST_SCHEMA,
            "status": "deterministic_static_native_closed",
            "accepted": False,
            "phase": request["phase"],
            "job_id": job["id"],
            "source": {
                "git_bundle_pin": request["source_bundle"]["pin"],  # type: ignore[index]
                "commit": request["source_commit"],
                "git_path": job["source_path"],
                "pin": source_pin,
                "compiled_from_sealed_memfd": True,
            },
            "bindings": job["bindings"],
            "flags": job["flags"],
            "environment": builder.BUILD_ENVIRONMENT,
            "tools": {
                "compiler": tools["compiler"],  # type: ignore[index]
                "readelf": tools["readelf"],  # type: ignore[index]
                "toolchain": tools["toolchain"],  # type: ignore[index]
            },
            "output": {
                "relative_path": f"artifacts/{job['output_name']}",
                "mode": "0555",
                "pin": pin,
            },
            "determinism": {
                "build_count": 2,
                "byte_identical": True,
                "first_pin": pin,
                "second_pin": pin,
            },
            "static_elf": {
                "interpreter": None,
                "needed": [],
                "readelf_pin": tools["readelf"]["pin"],  # type: ignore[index]
            },
            "claims": {
                "builder_uid_gid": [997, 997],
                "network_access": False,
                "worktree_input": False,
                "user_candidate_input": False,
            },
        }
    )


def _phase_a_manifest(request: dict[str, object]) -> dict[str, object]:
    jobs = [
        _job_manifest(request, job, f"elf:{job['id']}".encode())
        for job in request["jobs"]  # type: ignore[union-attr]
    ]
    parent_job = next(job for job in jobs if job["job_id"] == "parent-seal-launcher")
    return builder.seal_document(
        {
            "schema": builder.PHASE_A_MANIFEST_SCHEMA,
            "status": "dedicated_builder_phase_closed",
            "accepted": False,
            "phase": "phase-a",
            "request_pin": builder._document_pin(request).public(),
            "source_commit": request["source_commit"],
            "source_bundle_pin": request["source_bundle"]["pin"],  # type: ignore[index]
            "jobs": jobs,
            "inventory": {
                "root_entries": [
                    "artifacts",
                    "manifest.json",
                    "manifests",
                    builder.PARENT_SEAL_CANDIDATE_RELATIVE,
                ],
                "artifacts": [],
                "manifests": [],
                "parent_seal_candidate": {
                    "relative_path": builder.PARENT_SEAL_CANDIDATE_RELATIVE,
                    "files": [
                        {
                            "name": builder.PARENT_SEAL_HELPER_NAME,
                            "mode": "0444",
                            "pin": parent_job["bindings"]["helper_pin"],
                            "git_path": builder.JOB_SPECS["parent-seal-launcher"][
                                "helper_source_path"
                            ],
                        },
                        {
                            "name": builder.PARENT_SEAL_LAUNCHER_NAME,
                            "mode": "0555",
                            "pin": parent_job["output"]["pin"],
                            "job_id": "parent-seal-launcher",
                        },
                    ],
                },
            },
            "claims": {
                "builder_uid_gid": [997, 997],
                "network_access": False,
                "double_build_verified": True,
                "worktree_or_user_candidate_input": False,
                "closed": True,
            },
        }
    )


def test_fixed_identity_paths_phases_and_recipes() -> None:
    assert (builder.BUILDER_UID, builder.BUILDER_GID) == (997, 997)
    assert builder.INSTALLED_BUILDER == Path(
        "/usr/local/libexec/vista-r8-native-builder-r1/vista_r8_native_builder.py"
    )
    assert builder.INPUT_ROOT == Path("/etc/vista-r8-native-builder-r1")
    assert builder.PHASE_ROOTS == {
        "phase-a": Path("/var/lib/vista-r8-native-builder-r1/phase-a-slot/published"),
        "phase-b": Path("/var/lib/vista-r8-native-builder-r1/phase-b-slot/published"),
    }
    assert builder.PHASE_A_JOB_IDS == (
        "stage-transfer-launcher",
        "parent-seal-launcher",
        "initial-bootstrap-launcher",
    )
    assert builder.PHASE_B_JOB_IDS == ("initial-bootstrap-installer",)


def test_git_environment_closes_host_config_replace_refs_and_prompts() -> None:
    assert builder.GIT_ENVIRONMENT == {
        **builder.BUILD_ENVIRONMENT,
        "HOME": "/nonexistent",
        "XDG_CONFIG_HOME": "/nonexistent",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_COUNT": "0",
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_ATTR_NOSYSTEM": "1",
        "GIT_CEILING_DIRECTORIES": "$SCRATCH",
        "GIT_DISCOVERY_ACROSS_FILESYSTEM": "0",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_PAGER": "cat",
    }


def test_builder_runtime_identity_uses_only_kernel_and_proc_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in ("getuid", "geteuid", "getgid", "getegid"):
        monkeypatch.setattr(builder.os, name, lambda: 997)
    monkeypatch.setattr(builder.os, "getresuid", lambda: (997, 997, 997))
    monkeypatch.setattr(builder.os, "getresgid", lambda: (997, 997, 997))
    monkeypatch.setattr(builder.os, "getgroups", lambda: [997])
    monkeypatch.setattr(
        builder,
        "_read_proc_self_status",
        lambda: (
            b"Name:\tpython3.10\n"
            b"Uid:\t997\t997\t997\t997\n"
            b"Gid:\t997\t997\t997\t997\n"
            b"Groups:\t997\n"
        ),
    )
    builder._require_builder_identity()

    monkeypatch.setattr(
        builder,
        "_read_proc_self_status",
        lambda: b"Uid:\t997\t997\t997\t998\nGid:\t997\t997\t997\t997\nGroups:\t997\n",
    )
    with pytest.raises(builder.BuilderError, match="BUILDER_IDENTITY_REQUIRED"):
        builder._require_builder_identity()


def test_json_is_strict_canonical_and_rejects_duplicate_or_nan() -> None:
    assert builder.strict_json(b'{"a":1}\n', "valid") == {"a": 1}
    with pytest.raises(builder.BuilderError, match="JSON_INVALID"):
        builder.strict_json(b'{"a":1,"a":2}\n', "duplicate")
    with pytest.raises(builder.BuilderError, match="JSON_INVALID"):
        builder.strict_json(b'{"a":NaN}\n', "nan")
    with pytest.raises(builder.BuilderError, match="JSON_INVALID"):
        builder.strict_json(b'{"b":1, "a":2}\n', "not canonical")


def test_trace_parser_normalizes_only_reviewed_volatile_fields(tmp_path: Path) -> None:
    scratch = tmp_path / "phase-a.staging" / ".git-scratch"
    cwd = scratch / "source.git"
    line = (
        f'openat(AT_FDCWD<{cwd}>, "{scratch}/objects/ab/cd", '
        "O_RDONLY|O_CLOEXEC) = 17<"
        f"{scratch}/objects/ab/cd>"
    )
    event = builder._parse_trace_line(line, cwd=cwd, scratch=scratch)
    assert event["open_flags"] == ["O_RDONLY", "O_CLOEXEC"]
    assert {key: event[key] for key in ("syscall", "outcome", "paths", "line")} == {
        "syscall": "openat",
        "outcome": "OK",
        "paths": ["$SCRATCH/objects/ab/cd"],
        "line": _trace_event(
            "openat",
            "$SCRATCH/objects/ab/cd",
            "OK",
            open_flags=["O_RDONLY", "O_CLOEXEC"],
        ),
    }

    exec_event = builder._parse_trace_line(
        'execve("/proc/self/fd/14", ["/usr/bin/git", "--version"], '
        "0x7ffc0abc1234 /* 9 vars */) = 0",
        cwd=cwd,
        scratch=scratch,
    )
    assert exec_event["paths"] == ["$PROC_FD"]
    assert exec_event["line"] == _trace_event("execve", "$PROC_FD", "OK")
    assert "0x7ffc0abc1234" not in exec_event["line"]

    parent_event = builder._parse_trace_line(
        f'newfstatat(AT_FDCWD, "{tmp_path}", {{st_mode=S_IFDIR|0700}}, 0) = 0',
        cwd=cwd,
        scratch=scratch,
    )
    assert parent_event["paths"] == ["$SCRATCH_ANCESTOR"]

    pipe_event = builder._parse_trace_line(
        'newfstatat(1<pipe:[12345]>, "", {st_mode=S_IFIFO|0600}, AT_EMPTY_PATH) = 0',
        cwd=cwd,
        scratch=scratch,
    )
    assert pipe_event["paths"] == ["$FD_SPECIAL"]

    proc_event = builder._parse_trace_line(
        'readlink("/proc/self", "12345", 1024) = 5',
        cwd=cwd,
        scratch=scratch,
    )
    assert proc_event["paths"] == ["$PROC_SELF"]

    proc_root = builder._parse_trace_line(
        'readlink("/proc", 0x1234, 1024) = -1 EINVAL (Invalid argument)',
        cwd=cwd,
        scratch=scratch,
    )
    assert proc_root["paths"] == ["$PROC_ROOT"]

    proc_fd_directory = builder._parse_trace_line(
        'readlink("/proc/12345/fd", 0x1234, 1024) = -1 EINVAL (Invalid argument)',
        cwd=cwd,
        scratch=scratch,
        emitting_pid=12345,
        trace_pids=frozenset({12345}),
    )
    assert proc_fd_directory["paths"] == ["$PROC_FD_DIR"]

    pyvenv_probe = builder._parse_trace_line(
        'newfstatat(AT_FDCWD, "/proc/self/fd/pyvenv.cfg", '
        "0x7fff0000, 0) = -1 ENOENT (No such file or directory)",
        cwd=cwd,
        scratch=scratch,
    )
    assert pyvenv_probe["paths"] == ["$PROC_FD_PYVENV"]

    proc_self_pyvenv_probe = builder._parse_trace_line(
        'newfstatat(AT_FDCWD, "/proc/12345/pyvenv.cfg", '
        "0x7fff0000, 0) = -1 ENOENT (No such file or directory)",
        cwd=cwd,
        scratch=scratch,
        emitting_pid=12345,
        trace_pids=frozenset({12345}),
    )
    assert proc_self_pyvenv_probe["paths"] == ["$PROC_SELF_PYVENV"]

    fixed_source_gch = builder._parse_trace_line(
        f'access("/proc/12345/fd/{builder.FIXED_COMPILER_SOURCE_FD}.gch", F_OK) '
        "= -1 ENOENT (No such file or directory)",
        cwd=cwd,
        scratch=scratch,
        emitting_pid=12345,
        trace_pids=frozenset({12345}),
    )
    assert fixed_source_gch["paths"] == ["$PROC_FIXED_SOURCE_GCH"]

    with pytest.raises(builder.BuilderError, match="TRACE_PROC_PID_UNBOUND"):
        builder._parse_trace_line(
            'readlink("/proc/54321/fd", 0x1234, 1024) = -1 EINVAL (Invalid argument)',
            cwd=cwd,
            scratch=scratch,
            emitting_pid=12345,
            trace_pids=frozenset({12345}),
        )


def test_trace_parser_resolves_relative_dirfd_and_closes_negative_search_state(
    tmp_path: Path,
) -> None:
    scratch = tmp_path / "scratch"
    cwd = scratch / "cwd"
    event = builder._parse_trace_line(
        'openat(8</usr/lib/gcc/x86_64-linux-gnu/12>, "include/stddef.h", '
        "O_RDONLY|O_CLOEXEC) = -1 ENOENT (No such file or directory)",
        cwd=cwd,
        scratch=scratch,
    )
    assert event["outcome"] == "ENOENT"
    assert event["paths"] == ["/usr/lib/gcc/x86_64-linux-gnu/12/include/stddef.h"]

    empty_path = builder._parse_trace_line(
        'newfstatat(3</etc/ld.so.cache>, "", '
        "{st_mode=S_IFREG|0644, st_size=1, ...}, AT_EMPTY_PATH) = 0",
        cwd=cwd,
        scratch=scratch,
    )
    assert empty_path["paths"] == ["/etc/ld.so.cache"]


@pytest.mark.parametrize(
    "line,code",
    [
        (
            'openat(AT_FDCWD, "x", O_RDONLY <unfinished ...>',
            "TRACE_UNFINISHED",
        ),
        (
            "<... openat resumed>) = 3</tmp/x>",
            "TRACE_UNFINISHED",
        ),
        ('future_file_call("/etc/input") = 0', "TRACE_SYSCALL_UNKNOWN"),
        (
            'openat(AT_FDCWD, "x", O_RDONLY) = -1 EIO (I/O error)',
            "TRACE_RESULT_UNKNOWN",
        ),
        ('openat(AT_FDCWD, "x", O_RDONLY) = ? ERESTARTSYS', "TRACE_RESULT_UNKNOWN"),
        ('openat(AT_FDCWD, "x", O_RDONLY) = -512', "TRACE_RESULT_UNKNOWN"),
        ('openat(AT_FDCWD, "x", O_RDONLY) = 0x1234', "TRACE_RESULT_UNKNOWN"),
        ('openat(AT_FDCWD, "x", O_MYSTERY) = 3', "TRACE_OPEN_FLAGS_UNKNOWN"),
        ('chdir("/tmp") = 0', "TRACE_STATE_MUTATION"),
        ("fchdir(3</tmp>) = 0", "TRACE_STATE_MUTATION"),
        ('openat(AT_FDCWD, "unterminated, O_RDONLY) = 3', "TRACE_INVALID"),
    ],
)
def test_trace_parser_rejects_unknown_unfinished_or_malformed_lines(
    tmp_path: Path, line: str, code: str
) -> None:
    with pytest.raises(builder.BuilderError, match=code):
        builder._parse_trace_line(line, cwd=tmp_path, scratch=tmp_path)


def test_trace_multiset_is_exact_sorted_and_counted(tmp_path: Path) -> None:
    lines = [
        'access("/etc/missing", R_OK) = -1 ENOENT (No such file or directory)',
        'stat("/etc/ld.so.cache", {st_mode=S_IFREG|0644, st_size=1, ...}) = 0',
        'access("/etc/missing", R_OK) = -1 ENOENT (No such file or directory)',
    ]
    multiset, events = builder._trace_event_multiset(
        lines, cwd=tmp_path, scratch=tmp_path
    )
    assert len(events) == 3
    assert multiset == [
        {
            "line": _trace_event("access", "/etc/missing", "ENOENT"),
            "count": 2,
        },
        {
            "line": _trace_event("stat", "/etc/ld.so.cache", "OK"),
            "count": 1,
        },
    ]


def test_trace_multiset_collapses_only_exact_cpu_online_read_multiplicity(
    tmp_path: Path,
) -> None:
    cpu_online = "/sys/devices/system/cpu/online"
    cpu_possible = "/sys/devices/system/cpu/possible"
    cpu_line = (
        f'openat(AT_FDCWD, "{cpu_online}", O_RDONLY|O_CLOEXEC) = '
        f'3<{cpu_online}>'
    )
    possible_line = (
        f'openat(AT_FDCWD, "{cpu_possible}", O_RDONLY|O_CLOEXEC) = '
        f'3<{cpu_possible}>'
    )
    no_cloexec_line = (
        f'openat(AT_FDCWD, "{cpu_online}", O_RDONLY) = 3<{cpu_online}>'
    )
    denied_line = (
        f'openat(AT_FDCWD, "{cpu_online}", O_RDONLY|O_CLOEXEC) = '
        "-1 EACCES (Permission denied)"
    )
    stat_line = (
        f'newfstatat(AT_FDCWD, "{cpu_online}", '
        "{st_mode=S_IFREG|0444, st_size=4096, ...}, 0) = 0"
    )
    multiset, events = builder._trace_event_multiset(
        [
            cpu_line,
            cpu_line,
            cpu_line,
            possible_line,
            possible_line,
            no_cloexec_line,
            no_cloexec_line,
            denied_line,
            denied_line,
            stat_line,
            stat_line,
        ],
        cwd=tmp_path,
        scratch=tmp_path,
    )
    assert len(events) == 11
    assert {item["line"]: item["count"] for item in multiset} == {
        builder.CPU_ONLINE_READ_EVENT_LINE: 1,
        _trace_event(
            "openat",
            cpu_possible,
            "OK",
            open_flags=["O_RDONLY", "O_CLOEXEC"],
        ): 2,
        _trace_event(
            "openat", cpu_online, "OK", open_flags=["O_RDONLY"]
        ): 2,
        _trace_event(
            "openat",
            cpu_online,
            "EACCES",
            open_flags=["O_RDONLY", "O_CLOEXEC"],
        ): 2,
        _trace_event("newfstatat", cpu_online, "OK"): 2,
    }
    assert builder._validate_trace_event_multiset(
        [{"line": builder.CPU_ONLINE_READ_EVENT_LINE, "count": 1}],
        "cpu-online",
    ) == [{"line": builder.CPU_ONLINE_READ_EVENT_LINE, "count": 1}]
    with pytest.raises(builder.BuilderError, match="REQUEST_INVALID"):
        builder._validate_trace_event_multiset(
            [{"line": builder.CPU_ONLINE_READ_EVENT_LINE, "count": 2}],
            "cpu-online",
        )


def test_trace_multiset_collapses_only_held_workspace_ancestor_depth(
    tmp_path: Path,
) -> None:
    scratch = tmp_path / "private" / "staging"
    lines = [
        f'newfstatat(AT_FDCWD, "{tmp_path}", {{st_mode=S_IFDIR|0700}}, 0) = 0',
        f'newfstatat(AT_FDCWD, "{tmp_path / "private"}", '
        "{st_mode=S_IFDIR|0700}, 0) = 0",
    ]
    multiset, _events = builder._trace_event_multiset(
        lines, cwd=scratch, scratch=scratch
    )
    assert multiset == [
        {
            "line": _trace_event("newfstatat", "$SCRATCH_ANCESTOR", "OK"),
            "count": 1,
        }
    ]


def test_scratch_validation_rejects_symlink_and_two_path_escape(
    tmp_path: Path,
) -> None:
    scratch = tmp_path / "scratch"
    scratch.mkdir(mode=0o700)
    external = tmp_path / "external"
    external.write_bytes(b"external")
    (scratch / "link").symlink_to(external)
    escaped = builder._parse_trace_line(
        f'openat(AT_FDCWD, "{scratch / "link"}", O_RDONLY|O_CLOEXEC) = 3',
        cwd=scratch,
        scratch=scratch,
    )
    with pytest.raises(builder.BuilderError, match="TRACE_SCRATCH_SYMLINK"):
        builder._validate_scratch_lifecycle(
            [escaped], root=scratch, before=[], after=[]
        )

    (scratch / "link").unlink()
    linked = builder._parse_trace_line(
        f'link("{external}", "{scratch / "linked"}") = 0',
        cwd=scratch,
        scratch=scratch,
    )
    with pytest.raises(builder.BuilderError, match="TRACE_HOST_MUTATION"):
        builder._validate_scratch_lifecycle([linked], root=scratch, before=[], after=[])

    symlink_call = builder._parse_trace_line(
        f'symlink("{external}", "{scratch / "transient"}") = 0',
        cwd=scratch,
        scratch=scratch,
    )
    with pytest.raises(builder.BuilderError, match="TRACE_SCRATCH_SYMLINK"):
        builder._validate_scratch_lifecycle(
            [symlink_call], root=scratch, before=[], after=[]
        )

    safe_link = scratch / "safe-link"
    safe_symlink = builder._parse_trace_line(
        f'symlink("testing", "{safe_link}") = 0',
        cwd=scratch,
        scratch=scratch,
    )
    assert safe_symlink["resolved_paths"] == [
        str(scratch / "testing"),
        str(safe_link),
    ]
    safe_unlink = builder._parse_trace_line(
        f'unlink("{safe_link}") = 0', cwd=scratch, scratch=scratch
    )
    builder._validate_scratch_lifecycle(
        [safe_symlink, safe_unlink], root=scratch, before=[], after=[]
    )


def test_trace_rejects_parent_components_before_symlink_normalization(
    tmp_path: Path,
) -> None:
    scratch = tmp_path / "scratch"
    scratch.mkdir(mode=0o700)
    transient = scratch / "d"
    created = builder._parse_trace_line(
        f'symlink(".", "{transient}") = 0', cwd=scratch, scratch=scratch
    )
    assert created["resolved_paths"] == [str(scratch), str(transient)]
    with pytest.raises(builder.BuilderError, match="TRACE_PATH_TRAVERSAL"):
        builder._parse_trace_line(
            f'openat(AT_FDCWD, "{transient}/a/b/../../../outside", O_RDONLY) = 3',
            cwd=scratch,
            scratch=scratch,
        )
    deleted = builder._parse_trace_line(
        f'unlink("{transient}") = 0', cwd=scratch, scratch=scratch
    )
    builder._validate_scratch_lifecycle(
        [created, deleted], root=scratch, before=[], after=[]
    )


def test_trace_accepts_pinned_immutable_gcc_host_parent_paths(tmp_path: Path) -> None:
    scratch = tmp_path / "scratch"
    scratch.mkdir(mode=0o700)
    requested = "/usr/lib/gcc/x86_64-linux-gnu/12/../../../x86_64-linux-gnu/crt1.o"
    canonical = os.path.realpath(requested)
    assert canonical == "/usr/lib/x86_64-linux-gnu/crt1.o"
    event = builder._parse_trace_line(
        f'openat(AT_FDCWD, "{requested}", O_RDONLY) = 3<{canonical}>',
        cwd=scratch,
        scratch=scratch,
    )
    assert event["paths"] == [requested]
    assert event["open_flags"] == ["O_RDONLY"]
    record = builder._planner_trace_file_record(requested)
    assert record["canonical"] == canonical
    assert any(
        ".." in Path(component["path"]).parts for component in record["component_chain"]
    )
    assert builder._component_chain_is_immutable_root_owned(record["component_chain"])

    directory = builder._planner_trace_directory_record("/lib/../lib/.")
    assert directory["path"] == "/lib/../lib/."
    assert directory["canonical"] == "/usr/lib"
    assert (
        builder._validate_trace_host_record(
            directory, "GCC lexical directory", expected_kind="directory"
        )
        == directory
    )


def test_scratch_lifecycle_allows_only_dev_null_as_external_mutating_open(
    tmp_path: Path,
) -> None:
    scratch = tmp_path / "scratch"
    scratch.mkdir(mode=0o700)
    null_open = builder._parse_trace_line(
        'openat(AT_FDCWD, "/dev/null", O_RDWR|O_CLOEXEC) = 3',
        cwd=scratch,
        scratch=scratch,
    )
    builder._validate_scratch_lifecycle([null_open], root=scratch, before=[], after=[])

    for flags in (
        "O_WRONLY",
        "O_RDWR|O_TRUNC",
        "O_RDWR|O_CREAT",
        "O_RDWR|O_TMPFILE",
    ):
        rejected = builder._parse_trace_line(
            f'openat(AT_FDCWD, "/dev/null", {flags}) = 3',
            cwd=scratch,
            scratch=scratch,
        )
        with pytest.raises(builder.BuilderError, match="TRACE_HOST_MUTATION"):
            builder._validate_scratch_lifecycle(
                [rejected], root=scratch, before=[], after=[]
            )

    external = tmp_path / "external"
    external.write_bytes(b"unchanged")
    external_open = builder._parse_trace_line(
        f'openat(AT_FDCWD, "{external}", O_RDWR|O_CLOEXEC) = 3',
        cwd=scratch,
        scratch=scratch,
    )
    with pytest.raises(builder.BuilderError, match="TRACE_HOST_MUTATION"):
        builder._validate_scratch_lifecycle(
            [external_open], root=scratch, before=[], after=[]
        )


def test_vanished_scratch_leaf_requires_create_delete_lifecycle(
    tmp_path: Path,
) -> None:
    scratch = tmp_path / "scratch"
    scratch.mkdir(mode=0o700)
    leaf = scratch / "temporary"
    created = builder._parse_trace_line(
        f'openat(AT_FDCWD, "{leaf}", O_WRONLY|O_CREAT|O_EXCL, 0600) = 3',
        cwd=scratch,
        scratch=scratch,
    )
    observed = builder._parse_trace_line(
        f'newfstatat(AT_FDCWD, "{leaf}", {{st_mode=S_IFREG|0600}}, 0) = 0',
        cwd=scratch,
        scratch=scratch,
    )
    deleted = builder._parse_trace_line(
        f'unlink("{leaf}") = 0', cwd=scratch, scratch=scratch
    )
    builder._validate_scratch_lifecycle(
        [created, observed, deleted], root=scratch, before=[], after=[]
    )
    with pytest.raises(builder.BuilderError, match="TRACE_SCRATCH_LIFECYCLE_INVALID"):
        builder._validate_scratch_lifecycle(
            [observed, deleted], root=scratch, before=[], after=[]
        )

    spoofed_leaf = scratch / "O_CREAT-marker"
    spoofed_open = builder._parse_trace_line(
        f'openat(AT_FDCWD, "{spoofed_leaf}", O_RDWR) = 3',
        cwd=scratch,
        scratch=scratch,
    )
    spoofed_delete = builder._parse_trace_line(
        f'unlink("{spoofed_leaf}") = 0', cwd=scratch, scratch=scratch
    )
    assert spoofed_open["open_flags"] == ["O_RDWR"]
    with pytest.raises(builder.BuilderError, match="TRACE_SCRATCH_LIFECYCLE_INVALID"):
        builder._validate_scratch_lifecycle(
            [spoofed_open, spoofed_delete], root=scratch, before=[], after=[]
        )


def test_scratch_root_observation_is_not_a_vanished_leaf(tmp_path: Path) -> None:
    scratch = tmp_path / "scratch"
    scratch.mkdir(mode=0o700)
    observed = builder._parse_trace_line(
        f'newfstatat(AT_FDCWD, "{scratch}", {{st_mode=S_IFDIR|0700}}, 0) = 0',
        cwd=scratch,
        scratch=scratch,
    )
    builder._validate_scratch_lifecycle([observed], root=scratch, before=[], after=[])


def test_scratch_prestate_is_exact_pinned_tree_without_aliases(tmp_path: Path) -> None:
    scratch = tmp_path / "scratch"
    scratch.mkdir(mode=0o700)
    child = scratch / "child"
    child.write_bytes(b"pinned")
    child.chmod(0o600)
    first = builder._scratch_tree_snapshot(scratch)
    assert first == [
        {
            "relative_path": "child",
            "kind": "regular",
            "mode": "0600",
            "pin": _pin(b"pinned"),
        }
    ]
    assert builder._validate_scratch_prestate(first, "scratch") == first
    child.write_bytes(b"drift")
    assert builder._scratch_tree_snapshot(scratch) != first


def test_runtime_map_parser_binds_path_device_inode_and_rejects_deleted(
    tmp_path: Path,
) -> None:
    mapped = tmp_path / "mapped"
    mapped.write_bytes(b"mapped")
    info = mapped.stat()
    line = (
        "00000000-00001000 r--p 00000000 "
        f"{os.major(info.st_dev):02x}:{os.minor(info.st_dev):02x} "
        f"{info.st_ino} {mapped}"
    )
    assert builder._parse_runtime_map_lines([line]) == [
        {
            "canonical": str(mapped),
            "device": info.st_dev,
            "inode": info.st_ino,
        }
    ]

    wrong_inode = line.replace(f" {info.st_ino} ", f" {info.st_ino + 1} ")
    with pytest.raises(builder.BuilderError, match="TRACE_RUNTIME_MAP_INVALID"):
        builder._parse_runtime_map_lines([wrong_inode])
    with pytest.raises(builder.BuilderError, match="TRACE_RUNTIME_MAP_INVALID"):
        builder._parse_runtime_map_lines([line + " (deleted)"])


def test_trace_invocation_scratch_token_is_independent_of_workspace_layout(
    tmp_path: Path,
) -> None:
    observed_cwd = tmp_path / "observe-git"
    replay_cwd = tmp_path / "verify" / "git"
    observed, _ = builder._trace_event_multiset(
        [f'mkdir("{observed_cwd / "source.git"}", 0777) = -1 EEXIST (File exists)'],
        cwd=observed_cwd,
        scratch=observed_cwd,
    )
    replayed, _ = builder._trace_event_multiset(
        [f'mkdir("{replay_cwd / "source.git"}", 0777) = -1 EEXIST (File exists)'],
        cwd=replay_cwd,
        scratch=replay_cwd,
    )
    assert (
        observed
        == replayed
        == [
            {
                "line": _trace_event("mkdir", "$SCRATCH/source.git", "EEXIST"),
                "count": 1,
            }
        ]
    )

    first_random = builder._parse_trace_line(
        f'newfstatat(AT_FDCWD, "{observed_cwd / "source.git" / "tA1b2C3"}", '
        "{st_mode=S_IFREG|0600}, 0) = 0",
        cwd=observed_cwd,
        scratch=observed_cwd,
    )
    second_random = builder._parse_trace_line(
        f'newfstatat(AT_FDCWD, "{replay_cwd / "source.git" / "tz9Y8x7"}", '
        "{st_mode=S_IFREG|0600}, 0) = 0",
        cwd=replay_cwd,
        scratch=replay_cwd,
    )
    assert {
        key: first_random[key] for key in ("syscall", "outcome", "paths", "line")
    } == {key: second_random[key] for key in ("syscall", "outcome", "paths", "line")}
    assert first_random["paths"] == ["$SCRATCH/source.git/$GIT_INIT_TMP"]

    near_match = builder._parse_trace_line(
        f'newfstatat(AT_FDCWD, "{observed_cwd / "source.git" / "tA1b2C34"}", '
        "{st_mode=S_IFREG|0600}, 0) = 0",
        cwd=observed_cwd,
        scratch=observed_cwd,
    )
    assert near_match["paths"] == ["$SCRATCH/source.git/tA1b2C34"]

    for prefix, token in (("tmp_idx", "$TMP_IDX"), ("tmp_pack", "$TMP_PACK")):
        event = builder._parse_trace_line(
            f'openat(AT_FDCWD, "source.git/objects/pack/{prefix}_A1b2C3", '
            "O_RDWR|O_CREAT|O_EXCL, 0600) = 4",
            cwd=observed_cwd,
            scratch=observed_cwd,
        )
        assert event["paths"] == [f"$SCRATCH/source.git/objects/pack/{token}"]

    for basename, token in (
        ("ccA1b2C3.o", "$GCC_OBJECT"),
        ("ccA1b2C3.cdtor.c", "$GCC_CDTOR_C"),
        ("ccA1b2C3.cdtor.o", "$GCC_CDTOR_OBJECT"),
    ):
        event = builder._parse_trace_line(
            f'newfstatat(AT_FDCWD, "{observed_cwd / basename}", '
            "{st_mode=S_IFREG|0600}, 0) = 0",
            cwd=observed_cwd,
            scratch=observed_cwd,
        )
        assert event["paths"] == [f"$SCRATCH/{token}"]

    unrecognized_gcc_temp = builder._parse_trace_line(
        f'newfstatat(AT_FDCWD, "{observed_cwd / "ccA1b2C3.so"}", '
        "{st_mode=S_IFREG|0600}, 0) = 0",
        cwd=observed_cwd,
        scratch=observed_cwd,
    )
    assert unrecognized_gcc_temp["paths"] == ["$SCRATCH/ccA1b2C3.so"]


def test_trace_contract_closes_all_phase_invocations_and_host_inputs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(builder, "ROOT_UID", os.getuid())
    monkeypatch.setattr(builder, "ROOT_GID", os.getgid())
    monkeypatch.setattr(
        builder, "_component_chain_is_immutable_root_owned", lambda _chain: True
    )
    contract = _trace_contract(tmp_path)
    assert builder._validate_trace_contract(contract) == contract
    assert (  # type: ignore[index]
        contract["phase_invocations"]["phase-a"][0] == "python:builder-startup"
    )
    assert any(
        profile["id"].startswith("compiler:parent-seal-launcher:")
        for profile in contract["profiles"]  # type: ignore[union-attr]
    )

    missing_child = copy.deepcopy(contract)
    missing_child["profiles"] = [  # type: ignore[index]
        profile
        for profile in missing_child["profiles"]  # type: ignore[union-attr]
        if profile["id"] != "git:fetch"
    ]
    with pytest.raises(builder.BuilderError, match="trace profiles"):
        builder._validate_trace_contract(missing_child)


def test_kernel_virtual_sysctl_record_is_finite_stream_pinned_and_revalidated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = builder.KERNEL_VIRTUAL_SYSCTL_PATH
    record = builder._planner_trace_file_record(str(path))

    assert path.stat().st_size == 0
    assert record["path"] == record["canonical"] == str(path)
    assert record["storage"] == "kernel_virtual"
    assert record["mode"] == "0644"
    assert record["pin"] in [
        pin.public() for pin in builder._kernel_virtual_sysctl_pins()
    ]
    assert [item["path"] for item in record["component_chain"]] == list(
        builder.KERNEL_VIRTUAL_COMPONENT_PATHS
    )
    assert builder.TRACE_CONTRACT_SCHEMA.endswith("/v5")
    root, *proc_components = record["component_chain"]
    assert "metadata_policy" not in root
    assert all(
        field in root for field in builder.KERNEL_VIRTUAL_VOLATILE_METADATA_FIELDS
    )
    assert all(
        item["metadata_policy"] == builder.KERNEL_VIRTUAL_COMPONENT_POLICY
        and all(
            field not in item
            for field in builder.KERNEL_VIRTUAL_VOLATILE_METADATA_FIELDS
        )
        for item in proc_components
    )
    assert "nlink" not in proc_components[0]
    assert all("nlink" in item for item in proc_components[1:])
    assert (
        builder._validate_trace_host_record(
            record, "finite sysctl", expected_kind="regular"
        )
        == record
    )

    held = builder._open_trace_host_file(record, "finite sysctl")
    try:
        builder._revalidate_held(held, "finite sysctl", builder.MAX_NATIVE_BYTES)
        original_hash = builder._hash_kernel_virtual_sysctl_fd
        monkeypatch.setattr(
            builder,
            "_hash_kernel_virtual_sysctl_fd",
            lambda _descriptor: builder.FilePin("0" * 64, 2),
        )
        with pytest.raises(builder.BuilderError, match="FILE_DRIFT"):
            builder._revalidate_held(held, "finite sysctl", builder.MAX_NATIVE_BYTES)
        monkeypatch.setattr(builder, "_hash_kernel_virtual_sysctl_fd", original_hash)
    finally:
        held.close()

    original_lstat = os.lstat
    drift: dict[str, str | None] = {"nlink_path": None}

    def changing_proc_lstat(
        candidate: os.PathLike[str] | str, *args: object, **kwargs: object
    ) -> object:
        info = original_lstat(candidate, *args, **kwargs)
        candidate_text = os.fspath(candidate)
        if candidate_text not in builder.KERNEL_VIRTUAL_METADATA_VOLATILE_PATHS:
            return info
        return SimpleNamespace(
            st_mode=info.st_mode,
            st_uid=info.st_uid,
            st_gid=info.st_gid,
            st_dev=info.st_dev + 101,
            st_ino=info.st_ino + 103,
            st_nlink=info.st_nlink
            + (17 if candidate_text == "/proc" else 0)
            + (1 if candidate_text == drift["nlink_path"] else 0),
            st_size=info.st_size,
            st_blocks=info.st_blocks,
            st_mtime_ns=info.st_mtime_ns + 107,
            st_ctime_ns=info.st_ctime_ns + 109,
        )

    monkeypatch.setattr(builder.os, "lstat", changing_proc_lstat)
    builder._assert_component_chain_live(
        record["component_chain"], path, "namespace metadata"
    )
    drift["nlink_path"] = "/proc/sys"
    with pytest.raises(builder.BuilderError, match="TRACE_PATH_DRIFT"):
        builder._assert_component_chain_live(
            record["component_chain"], path, "stable descendant nlink"
        )


@pytest.mark.parametrize("raw", builder.KERNEL_VIRTUAL_SYSCTL_VALUES)
def test_kernel_virtual_sysctl_reader_accepts_only_exact_finite_values(
    tmp_path: Path, raw: bytes
) -> None:
    target = tmp_path / "finite-sysctl"
    target.write_bytes(raw)
    descriptor = os.open(target, os.O_RDONLY | os.O_CLOEXEC)
    try:
        assert builder._hash_kernel_virtual_sysctl_fd(descriptor).public() == _pin(raw)
    finally:
        os.close(descriptor)

    for malformed in (b"", b"1", b"3\n", b"1\nx"):
        target.write_bytes(malformed)
        descriptor = os.open(target, os.O_RDONLY | os.O_CLOEXEC)
        try:
            with pytest.raises(builder.BuilderError, match="TRACE_INPUT_DRIFT"):
                builder._hash_kernel_virtual_sysctl_fd(descriptor)
        finally:
            os.close(descriptor)


@pytest.mark.parametrize(
    "raw_path,cwd",
    [
        ("/proc/sys/vm/./overcommit_memory", Path("/")),
        ("/proc//sys/vm/overcommit_memory", Path("/")),
        ("/proc/sys/vm/../vm/overcommit_memory", Path("/")),
        ("overcommit_memory", Path("/proc/sys/vm")),
    ],
)
def test_kernel_virtual_sysctl_trace_rejects_nonliteral_spellings(
    tmp_path: Path, raw_path: str, cwd: Path
) -> None:
    with pytest.raises(builder.BuilderError, match="TRACE_KERNEL_VIRTUAL_PATH_INVALID"):
        builder._parse_trace_line(
            f'openat(AT_FDCWD, "{raw_path}", O_RDONLY|O_CLOEXEC) = 3',
            cwd=cwd,
            scratch=tmp_path,
        )


def test_kernel_virtual_sysctl_trace_accepts_only_readonly_exact_literal(
    tmp_path: Path,
) -> None:
    path = str(builder.KERNEL_VIRTUAL_SYSCTL_PATH)
    event = builder._parse_trace_line(
        f'openat(AT_FDCWD, "{path}", O_RDONLY|O_NOFOLLOW|O_CLOEXEC|O_NONBLOCK) = 3',
        cwd=tmp_path,
        scratch=tmp_path,
    )
    assert event["paths"] == [path]
    assert event["open_flags"] == [
        "O_RDONLY",
        "O_NOFOLLOW",
        "O_CLOEXEC",
        "O_NONBLOCK",
    ]

    alias = tmp_path / "overcommit-alias"
    alias.symlink_to(builder.KERNEL_VIRTUAL_SYSCTL_PATH)
    with pytest.raises(builder.BuilderError, match="TRACE_KERNEL_VIRTUAL_PATH_INVALID"):
        builder._parse_trace_line(
            f'openat(AT_FDCWD, "{alias}", O_RDONLY) = 3',
            cwd=tmp_path,
            scratch=tmp_path,
        )

    for flags, result in (
        ("O_WRONLY", "3"),
        ("O_RDONLY|O_CREAT", "-1 EACCES (Permission denied)"),
        ("O_RDWR", "-1 EACCES (Permission denied)"),
    ):
        with pytest.raises(
            builder.BuilderError, match="TRACE_KERNEL_VIRTUAL_PATH_INVALID"
        ):
            builder._parse_trace_line(
                f'openat(AT_FDCWD, "{path}", {flags}) = {result}',
                cwd=tmp_path,
                scratch=tmp_path,
            )


def test_kernel_virtual_sysctl_planner_rejects_aliases_and_other_proc_inputs(
    tmp_path: Path,
) -> None:
    alias = tmp_path / "overcommit-alias"
    alias.symlink_to(builder.KERNEL_VIRTUAL_SYSCTL_PATH)
    rejected_files = (
        "/proc/sys/vm/./overcommit_memory",
        "/proc//sys/vm/overcommit_memory",
        "/proc/sys/vm/../vm/overcommit_memory",
        "/proc/sys/vm/swappiness",
        str(alias),
    )
    for path in rejected_files:
        with pytest.raises(builder.BuilderError, match="TRACE_HOST_INPUT_UNTRUSTED"):
            builder._planner_trace_file_record(path)
    with pytest.raises(builder.BuilderError, match="TRACE_HOST_INPUT_UNTRUSTED"):
        builder._planner_trace_directory_record("/proc/sys/vm")


def test_kernel_virtual_sysctl_contract_requires_exact_profile_event_binding() -> None:
    contract = _request_trace_contract_with_kernel_virtual()
    assert builder._validate_trace_contract(contract) == contract

    stale_schema = copy.deepcopy(contract)
    stale_schema["schema"] = "vista.r8-native-builder-trace-contract/v4"
    with pytest.raises(builder.BuilderError, match="trace contract schema/version"):
        builder._validate_trace_contract(stale_schema)

    runtime_smuggle = copy.deepcopy(contract)
    runtime_smuggle["builder_runtime_files"] = sorted(  # type: ignore[index]
        [
            *runtime_smuggle["builder_runtime_files"],  # type: ignore[index]
            str(builder.KERNEL_VIRTUAL_SYSCTL_PATH),
        ]
    )
    with pytest.raises(builder.BuilderError, match="trace builder_runtime_files"):
        builder._validate_trace_contract(runtime_smuggle)

    orphan_event = copy.deepcopy(contract)
    first = orphan_event["profiles"][0]  # type: ignore[index]
    first["host_files"].remove(str(builder.KERNEL_VIRTUAL_SYSCTL_PATH))
    with pytest.raises(builder.BuilderError, match="orphan kernel virtual event"):
        builder._validate_trace_contract(orphan_event)

    missing_event = copy.deepcopy(contract)
    first = missing_event["profiles"][0]  # type: ignore[index]
    first["event_multiset"] = [
        item
        for item in first["event_multiset"]
        if str(builder.KERNEL_VIRTUAL_SYSCTL_PATH) not in item["line"]
    ]
    with pytest.raises(builder.BuilderError, match="kernel virtual profile binding"):
        builder._validate_trace_contract(missing_event)

    failed_write = copy.deepcopy(contract)
    first = failed_write["profiles"][0]  # type: ignore[index]
    first["event_multiset"] = sorted(
        [
            item
            for item in first["event_multiset"]
            if str(builder.KERNEL_VIRTUAL_SYSCTL_PATH) not in item["line"]
        ]
        + [
            {
                "line": _trace_event(
                    "openat",
                    str(builder.KERNEL_VIRTUAL_SYSCTL_PATH),
                    "EACCES",
                    open_flags=["O_WRONLY"],
                ),
                "count": 1,
            }
        ],
        key=lambda item: item["line"],
    )
    with pytest.raises(builder.BuilderError, match="kernel virtual open flags"):
        builder._validate_trace_contract(failed_write)


def test_cpu_online_count_policy_is_closed_to_git_fetch_and_held_host_file() -> None:
    contract = _request_trace_contract()
    cpu_record = builder._planner_trace_file_record(builder.CPU_ONLINE_PATH)
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
        [*fetch["host_files"], builder.CPU_ONLINE_PATH]  # type: ignore[index]
    )
    fetch["event_multiset"] = sorted(  # type: ignore[index]
        [
            *fetch["event_multiset"],  # type: ignore[index]
            {"line": builder.CPU_ONLINE_READ_EVENT_LINE, "count": 1},
        ],
        key=lambda item: item["line"],
    )
    assert builder._validate_trace_contract(contract) == contract

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
    wrong_fetch["host_files"].remove(builder.CPU_ONLINE_PATH)  # type: ignore[union-attr]
    wrong_fetch["event_multiset"] = [  # type: ignore[index]
        item
        for item in wrong_fetch["event_multiset"]  # type: ignore[union-attr]
        if item["line"] != builder.CPU_ONLINE_READ_EVENT_LINE
    ]
    wrong_init["host_files"] = sorted(  # type: ignore[index]
        [*wrong_init["host_files"], builder.CPU_ONLINE_PATH]  # type: ignore[index]
    )
    wrong_init["event_multiset"] = sorted(  # type: ignore[index]
        [
            *wrong_init["event_multiset"],  # type: ignore[index]
            {"line": builder.CPU_ONLINE_READ_EVENT_LINE, "count": 1},
        ],
        key=lambda item: item["line"],
    )
    with pytest.raises(builder.BuilderError, match="cpu online event profile"):
        builder._validate_trace_contract(wrong_profile)

    unbound_event = copy.deepcopy(contract)
    unbound_fetch = next(
        profile
        for profile in unbound_event["profiles"]  # type: ignore[union-attr]
        if profile["id"] == "git:fetch"
    )
    unbound_fetch["host_files"].remove(builder.CPU_ONLINE_PATH)  # type: ignore[union-attr]
    with pytest.raises(builder.BuilderError, match="cpu online profile binding"):
        builder._validate_trace_contract(unbound_event)

    runtime_smuggle = copy.deepcopy(contract)
    runtime_smuggle["builder_runtime_files"] = sorted(  # type: ignore[index]
        [
            *runtime_smuggle["builder_runtime_files"],  # type: ignore[index]
            builder.CPU_ONLINE_PATH,
        ]
    )
    with pytest.raises(builder.BuilderError, match="trace builder_runtime_files"):
        builder._validate_trace_contract(runtime_smuggle)

    policy_drift = copy.deepcopy(contract)
    policy_drift["event_count_policies"][0]["profile_id"] = "git:init"  # type: ignore[index]
    with pytest.raises(builder.BuilderError, match="event count policies"):
        builder._validate_trace_contract(policy_drift)
    for invalid_count in (True, 1.0):
        type_drift = copy.deepcopy(contract)
        type_drift["event_count_policies"][0]["canonical_count"] = invalid_count  # type: ignore[index]
        with pytest.raises(builder.BuilderError, match="event count policies"):
            builder._validate_trace_contract(type_drift)
    for policies in ([], builder._trace_event_count_policies() * 2):
        cardinality_drift = copy.deepcopy(contract)
        cardinality_drift["event_count_policies"] = policies
        with pytest.raises(builder.BuilderError, match="event count policies"):
            builder._validate_trace_contract(cardinality_drift)


def test_kernel_virtual_sysctl_contract_rejects_forged_record_fields() -> None:
    contract = _request_trace_contract_with_kernel_virtual()
    special = next(
        record
        for record in contract["host_files"]  # type: ignore[union-attr]
        if record["path"] == str(builder.KERNEL_VIRTUAL_SYSCTL_PATH)
    )

    mutations: list[tuple[str, object]] = [
        ("storage", "regular"),
        ("pin", _pin(b"3\n")),
        ("mode", "0600"),
    ]
    for field, value in mutations:
        changed = copy.deepcopy(contract)
        target = next(
            record
            for record in changed["host_files"]  # type: ignore[union-attr]
            if record["path"] == str(builder.KERNEL_VIRTUAL_SYSCTL_PATH)
        )
        target[field] = value
        with pytest.raises(builder.BuilderError, match="REQUEST_INVALID"):
            builder._validate_trace_contract(changed)

    changed = copy.deepcopy(contract)
    target = next(
        record
        for record in changed["host_files"]  # type: ignore[union-attr]
        if record["path"] == str(builder.KERNEL_VIRTUAL_SYSCTL_PATH)
    )
    target["component_chain"][1]["metadata_policy"] = "request-selected"
    with pytest.raises(builder.BuilderError, match="REQUEST_INVALID"):
        builder._validate_trace_contract(changed)

    for index, field in ((1, "device"), (2, "inode"), (-1, "mtime_ns")):
        changed = copy.deepcopy(contract)
        target = next(
            record
            for record in changed["host_files"]  # type: ignore[union-attr]
            if record["path"] == str(builder.KERNEL_VIRTUAL_SYSCTL_PATH)
        )
        target["component_chain"][index][field] = 1
        with pytest.raises(builder.BuilderError, match="REQUEST_INVALID"):
            builder._validate_trace_contract(changed)

    for index, field, value in (
        (2, "nlink", 1),
        (-1, "nlink", 1),
        (-1, "mode", "0600"),
    ):
        changed = copy.deepcopy(contract)
        target = next(
            record
            for record in changed["host_files"]  # type: ignore[union-attr]
            if record["path"] == str(builder.KERNEL_VIRTUAL_SYSCTL_PATH)
        )
        if field == "nlink":
            target["component_chain"][index][field] += value
        else:
            target["component_chain"][index][field] = value
        assert target != special
        with pytest.raises(builder.BuilderError, match="TRACE_PATH_DRIFT"):
            builder._open_trace_host_file(target, "forged component")


def test_trace_host_inventory_accepts_and_revalidates_empty_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(builder, "ROOT_UID", os.getuid())
    monkeypatch.setattr(builder, "ROOT_GID", os.getgid())
    monkeypatch.setattr(
        builder, "_component_chain_is_immutable_root_owned", lambda _chain: True
    )
    target = tmp_path / "empty-runtime.py"
    target.write_bytes(b"")
    target.chmod(0o644)

    record = builder._planner_trace_file_record(str(target))
    assert record["storage"] == "empty"
    assert record["pin"] == _pin(b"")
    assert (
        builder._validate_trace_host_record(
            record, "empty runtime", expected_kind="regular"
        )
        == record
    )

    held = builder._open_trace_host_file(record, "empty runtime")
    try:
        builder._revalidate_held(held, "empty runtime", builder.MAX_NATIVE_BYTES)
    finally:
        held.close()


def test_trace_host_inventory_streams_sparse_file_and_rejects_storage_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(builder, "ROOT_UID", os.getuid())
    monkeypatch.setattr(builder, "ROOT_GID", os.getgid())
    monkeypatch.setattr(
        builder, "_component_chain_is_immutable_root_owned", lambda _chain: True
    )
    target = tmp_path / "sparse-runtime.bin"
    with target.open("wb") as stream:
        stream.seek(1024 * 1024)
        stream.write(b"x")
    target.chmod(0o644)
    if target.stat().st_blocks * 512 >= target.stat().st_size:
        pytest.skip("test filesystem does not preserve sparse allocation")

    record = builder._planner_trace_file_record(str(target))
    assert record["storage"] == "sparse"
    assert record["pin"] == _pin((b"\0" * (1024 * 1024)) + b"x")
    held = builder._open_trace_host_file(record, "sparse runtime")
    held.close()

    changed = copy.deepcopy(record)
    changed["storage"] = "empty"
    with pytest.raises(builder.BuilderError, match="TRACE_INPUT_DRIFT"):
        builder._open_trace_host_file(changed, "sparse runtime")


def test_trace_host_record_rejects_virtual_storage_outside_sysfs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(builder, "ROOT_UID", os.getuid())
    monkeypatch.setattr(builder, "ROOT_GID", os.getgid())
    target = tmp_path / "runtime"
    target.write_bytes(b"runtime")
    target.chmod(0o644)
    record = _trace_host_file(target)
    record["storage"] = "virtual"
    with pytest.raises(builder.BuilderError, match="REQUEST_INVALID"):
        builder._validate_trace_host_record(
            record, "virtual runtime", expected_kind="regular"
        )


def test_observed_contract_assembly_explicitly_models_symlink_path_aliases(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(builder, "ROOT_UID", os.getuid())
    monkeypatch.setattr(builder, "ROOT_GID", os.getgid())
    monkeypatch.setattr(
        builder, "_component_chain_is_immutable_root_owned", lambda _chain: True
    )
    seed = _trace_contract(tmp_path)
    profiles = {profile["id"]: profile for profile in seed["profiles"]}  # type: ignore[index]
    host = tmp_path / "host-runtime.bin"
    assembled = builder._assemble_observed_trace_contract(
        profiles,
        tracer_runtime_canonicals=[str(host.resolve())],
        builder_runtime_canonicals=[str(host.resolve())],
    )
    assert builder._validate_trace_contract(assembled) == assembled

    alias = tmp_path / "host-runtime-link"
    alias.symlink_to(host.name)
    changed = copy.deepcopy(profiles)
    changed["git:init"]["host_files"].append(str(alias))
    changed["git:init"]["host_files"].sort()
    aliased = builder._assemble_observed_trace_contract(
        changed,
        tracer_runtime_canonicals=[str(host.resolve())],
        builder_runtime_canonicals=[str(host.resolve())],
    )
    assert aliased["path_aliases"] == [
        {
            "kind": "regular",
            "canonical": str(host.resolve()),
            "paths": sorted((str(host), str(alias))),
        }
    ]


def test_trace_contract_rejects_implicit_symlink_or_hardlink_aliases(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(builder, "ROOT_UID", os.getuid())
    monkeypatch.setattr(builder, "ROOT_GID", os.getgid())
    monkeypatch.setattr(
        builder, "_component_chain_is_immutable_root_owned", lambda _chain: True
    )
    contract = _trace_contract(tmp_path)
    host = tmp_path / "host-runtime.bin"

    symlink = tmp_path / "host-runtime-link"
    symlink.symlink_to(host.name)
    symlink_alias = copy.deepcopy(contract)
    symlink_alias["host_files"].append(_trace_host_file(symlink))  # type: ignore[union-attr]
    symlink_alias["host_files"] = sorted(  # type: ignore[index]
        symlink_alias["host_files"],
        key=lambda item: item["path"],  # type: ignore[index]
    )
    with pytest.raises(builder.BuilderError, match="trace path alias projection"):
        builder._validate_trace_contract(symlink_alias)

    hardlink_alias = copy.deepcopy(contract)
    duplicate_inode = copy.deepcopy(hardlink_alias["host_files"][0])  # type: ignore[index]
    duplicate_inode["path"] = str(tmp_path / "host-runtime-hardlink")
    duplicate_inode["canonical"] = duplicate_inode["path"]
    duplicate_inode["component_chain"][-1]["path"] = duplicate_inode["path"]
    hardlink_alias["host_files"].append(duplicate_inode)  # type: ignore[union-attr]
    hardlink_alias["host_files"] = sorted(  # type: ignore[index]
        hardlink_alias["host_files"],
        key=lambda item: item["path"],  # type: ignore[index]
    )
    with pytest.raises(builder.BuilderError, match="implicit hardlink or bind alias"):
        builder._validate_trace_contract(hardlink_alias)


def test_trace_component_chain_detects_alias_or_parent_rebind(tmp_path: Path) -> None:
    target = tmp_path / "runtime"
    target.write_bytes(b"runtime")
    target.chmod(0o644)
    record = _trace_host_file(target)
    builder._assert_component_chain_live(
        record["component_chain"],
        target,
        "runtime",  # type: ignore[arg-type]
    )

    target.rename(tmp_path / "displaced")
    target.write_bytes(b"runtime")
    target.chmod(0o644)
    with pytest.raises(builder.BuilderError, match="TRACE_PATH_DRIFT"):
        builder._assert_component_chain_live(
            record["component_chain"],
            target,
            "runtime",  # type: ignore[arg-type]
        )


def test_phase_a_request_is_closed_and_cross_binds_helper_python_and_flags() -> None:
    request = _phase_a_request()
    assert builder._validate_request(request, "phase-a") == request

    changed = copy.deepcopy(request)
    changed["jobs"][0]["bindings"]["helper_pin"] = _pin(b"wrong")  # type: ignore[index]
    changed["jobs"][0]["flags"] = builder.expected_job_flags(  # type: ignore[index]
        "stage-transfer-launcher",
        changed["jobs"][0]["bindings"],  # type: ignore[index]
    )
    changed["content_digest"] = builder.content_digest(changed)
    with pytest.raises(
        builder.BuilderError, match="job stage-transfer-launcher helper"
    ):
        builder._validate_request(changed, "phase-a")

    extra = copy.deepcopy(request)
    extra["caller_path"] = "/tmp/hostile"
    extra["content_digest"] = builder.content_digest(extra)
    with pytest.raises(builder.BuilderError, match="top-level fields"):
        builder._validate_request(extra, "phase-a")

    incomplete_toolchain = copy.deepcopy(request)
    incomplete_toolchain["tools"]["toolchain"] = []  # type: ignore[index]
    incomplete_toolchain["content_digest"] = builder.content_digest(
        incomplete_toolchain
    )
    with pytest.raises(builder.BuilderError, match="toolchain"):
        builder._validate_request(incomplete_toolchain, "phase-a")


def test_parent_seal_uses_exact_active_macro_flags_not_source_substrings() -> None:
    request = _phase_a_request()
    parent = next(
        job
        for job in request["jobs"]  # type: ignore[union-attr]
        if job["id"] == "parent-seal-launcher"
    )
    bindings = parent["bindings"]
    assert parent["flags"] == [
        *builder.COMMON_FLAGS,
        *builder._define_flags(bindings, "python_pin", "helper_pin"),
    ]
    assert "-pipe" in parent["flags"]
    assert "-fno-use-linker-plugin" in parent["flags"]

    decoy = copy.deepcopy(request)
    decoy_parent = next(
        job
        for job in decoy["jobs"]  # type: ignore[union-attr]
        if job["id"] == "parent-seal-launcher"
    )
    decoy_parent["flags"] = [*builder.COMMON_FLAGS]
    decoy["content_digest"] = builder.content_digest(decoy)
    with pytest.raises(builder.BuilderError, match="job parent-seal-launcher flags"):
        builder._validate_request(decoy, "phase-a")


def test_installer_input_pin_flag_preserves_active_c_macro_name() -> None:
    bindings = {
        "launcher_pin": _pin(b"launcher"),
        "helper_pin": _pin(b"helper"),
        "input_pin": _pin(b"input"),
    }
    flags = builder.expected_job_flags("initial-bootstrap-installer", bindings)
    assert f'-DEXPECTED_INPUT_PIN_SHA256="{bindings["input_pin"]["sha256"]}"' in flags
    assert f'-DEXPECTED_INPUT_SHA256="{bindings["input_pin"]["sha256"]}"' not in flags


def test_compiler_source_memfd_uses_fixed_collision_checked_descriptor() -> None:
    with builder._fixed_compiler_source_memfd(b"source", "test source") as descriptor:
        assert descriptor == builder.FIXED_COMPILER_SOURCE_FD
        assert os.pread(descriptor, 6, 0) == b"source"
    with pytest.raises(OSError):
        os.fstat(builder.FIXED_COMPILER_SOURCE_FD)

    occupied = os.open("/dev/null", os.O_RDONLY | os.O_CLOEXEC)
    try:
        os.dup2(occupied, builder.FIXED_COMPILER_SOURCE_FD, inheritable=False)
        with pytest.raises(builder.BuilderError, match="FIXED_SOURCE_FD_COLLISION"):
            with builder._fixed_compiler_source_memfd(b"source", "test source"):
                raise AssertionError("unreachable")
    finally:
        os.close(builder.FIXED_COMPILER_SOURCE_FD)
        os.close(occupied)


def test_tool_symlink_is_resolved_then_held_and_pinned(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    uid, gid = os.getuid(), os.getgid()
    canonical = tmp_path / "compiler-real"
    canonical.write_bytes(b"compiler")
    canonical.chmod(0o755)
    link = tmp_path / "compiler"
    link.symlink_to(canonical.name)
    monkeypatch.setattr(builder, "ROOT_UID", uid)
    monkeypatch.setattr(builder, "ROOT_GID", gid)
    record = {
        "path": str(link),
        "canonical": str(canonical),
        "mode": "0755",
        "pin": _pin(b"compiler"),
    }
    held = builder._open_held_tool(link, record, "compiler")
    try:
        assert held.path == canonical
        assert held.pin.public() == _pin(b"compiler")
    finally:
        held.close()


def test_request_open_failure_closes_every_prior_held_descriptor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closed: list[str] = []
    calls = 0

    class FakeHeld:
        def __init__(self, label: str) -> None:
            self.label = label

        def close(self) -> None:
            closed.append(self.label)

    def fake_open(*_args: object, **_kwargs: object) -> FakeHeld:
        nonlocal calls
        calls += 1
        if calls == 3:
            raise builder.BuilderError("FILE_INVALID", "installed builder")
        return FakeHeld(f"held-{calls}")

    monkeypatch.setattr(builder, "_open_held_regular", fake_open)
    with pytest.raises(builder.BuilderError, match="FILE_INVALID"):
        builder._load_request("phase-a")
    assert closed == ["held-2", "held-1"]


def test_tool_open_failure_closes_every_prior_held_descriptor(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    closed: list[str] = []
    calls = 0

    class FakeHeld:
        def __init__(self, label: str) -> None:
            self.label = label

        def close(self) -> None:
            closed.append(self.label)

    def fake_open(*_args: object, **_kwargs: object) -> FakeHeld:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise builder.BuilderError("FILE_INVALID", "Git")
        return FakeHeld(f"held-{calls}")

    monkeypatch.setattr(builder, "_open_held_tool", fake_open)
    with pytest.raises(builder.BuilderError, match="FILE_INVALID"):
        with builder._held_tools(_phase_a_request()):
            raise AssertionError("unreachable")
    assert closed == ["held-1"]


def test_double_build_rejects_nondeterministic_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    request = _phase_a_request()
    job = request["jobs"][0]  # type: ignore[index]
    calls = 0

    def fake_build_once(
        _job: object,
        _source: bytes,
        _tools: object,
        destination: Path,
        *,
        cwd: Path,
        build_index: int,
        trace: object,
    ) -> tuple[builder.FilePin, dict[str, object]]:
        nonlocal calls
        assert build_index == calls + 1
        assert trace is not None
        assert cwd.parent == tmp_path
        assert cwd.name == f"{job['id']}.build-{calls + 1}-root"
        assert destination == cwd / "output"
        calls += 1
        raw = f"elf-{calls}".encode()
        destination.write_bytes(raw)
        pin = _pin(raw)
        return builder.FilePin(pin["sha256"], len(raw)), {  # type: ignore[arg-type]
            "interpreter": None,
            "needed": [],
            "readelf_pin": _pin(b"readelf"),
        }

    monkeypatch.setattr(builder, "_build_once", fake_build_once)
    monkeypatch.setattr(builder, "_snapshot_tools", lambda _tools: {})
    monkeypatch.setattr(builder, "_revalidate_tools", lambda _tools, _before: None)
    monkeypatch.setattr(builder, "BUILDER_UID", os.getuid())
    monkeypatch.setattr(builder, "BUILDER_GID", os.getgid())
    with pytest.raises(builder.BuilderError, match="NONDETERMINISTIC_BUILD"):
        builder._build_job_twice(
            job,
            b"source",
            request,
            {"compiler": object(), "readelf": object()},  # type: ignore[dict-item]
            tmp_path,
            tmp_path / "published",
            output_relative="artifacts/output",
            trace=builder.TraceAuthority({}, {}, {}, tmp_path),
        )


def test_phase_a_manifest_requires_two_identical_builds() -> None:
    request = _phase_a_request()
    manifest = _phase_a_manifest(request)
    builder._validate_phase_a_manifest(manifest)
    changed = copy.deepcopy(manifest)
    changed["jobs"][1]["determinism"]["second_pin"] = _pin(b"different")  # type: ignore[index]
    changed["jobs"][1]["content_digest"] = builder.content_digest(  # type: ignore[index]
        changed["jobs"][1]  # type: ignore[index]
    )
    changed["content_digest"] = builder.content_digest(changed)
    with pytest.raises(builder.BuilderError, match="job parent-seal-launcher"):
        builder._validate_phase_a_manifest(changed)


def test_phase_a_manifest_closes_builder_owned_parent_candidate() -> None:
    request = _phase_a_request()
    manifest = _phase_a_manifest(request)
    builder._validate_phase_a_manifest(manifest)

    changed = copy.deepcopy(manifest)
    changed["inventory"]["parent_seal_candidate"]["files"][0]["pin"] = _pin(  # type: ignore[index]
        b"untrusted helper"
    )
    changed["content_digest"] = builder.content_digest(changed)
    with pytest.raises(builder.BuilderError, match="parent seal candidate inventory"):
        builder._validate_phase_a_manifest(changed)


def test_rename_noreplace_never_replaces_existing_final(tmp_path: Path) -> None:
    source = tmp_path / "source"
    destination = tmp_path / "destination"
    source.mkdir()
    destination.mkdir()
    marker = destination / "keep"
    marker.write_text("keep")
    with pytest.raises(builder.BuilderError, match="PHASE_ALREADY_PUBLISHED"):
        builder._rename_noreplace(source, destination)
    assert marker.read_text() == "keep"
    assert source.is_dir()


def test_closed_staging_is_safely_reopened_and_removed_after_collision(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    slot, final, _lock = _temporary_phase_slot(tmp_path, monkeypatch)
    staging = slot / ".phase-a.staging-collision"
    staging.mkdir(mode=0o700)
    child = staging / "manifest.json"
    child.write_bytes(b"closed\n")
    child.chmod(0o444)
    staging.chmod(0o555)
    final.mkdir(mode=0o555)

    with pytest.raises(builder.BuilderError, match="PHASE_ALREADY_PUBLISHED"):
        builder._rename_noreplace(staging, final)
    builder._safe_remove_staging(staging)

    assert not staging.exists()
    assert final.is_dir()


def test_publish_parent_fsync_failure_preserves_closed_final_for_reconcile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    slot, final, _lock = _temporary_phase_slot(tmp_path, monkeypatch)
    staging = slot / ".phase-a.staging-fsync"
    staging.mkdir(mode=0o700)
    marker = staging / "manifest.json"
    marker.write_bytes(b"closed\n")
    monkeypatch.setattr(builder, "_close_tree", lambda path: path.chmod(0o555))
    monkeypatch.setattr(
        builder,
        "_rename_noreplace",
        lambda source, destination: source.rename(destination),
    )
    monkeypatch.setattr(
        builder.os,
        "fsync",
        lambda _descriptor: (_ for _ in ()).throw(OSError("injected parent fsync")),
    )

    with pytest.raises(builder.BuilderError, match="PUBLISH_DURABILITY_UNCERTAIN"):
        builder._publish(staging, final)

    assert not staging.exists()
    assert final.is_dir()
    assert (final / "manifest.json").read_bytes() == b"closed\n"


def _temporary_phase_slot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path, Path]:
    state = tmp_path / "state"
    slot = state / "phase-a-slot"
    final = slot / "published"
    lock = slot / ".build.lock"
    state.mkdir(mode=0o755)
    slot.mkdir(mode=0o711)
    lock.touch(mode=0o600)
    lock.chmod(0o600)
    state.chmod(0o555)
    monkeypatch.setattr(builder, "ROOT_UID", os.getuid())
    monkeypatch.setattr(builder, "ROOT_GID", os.getgid())
    monkeypatch.setattr(builder, "BUILDER_UID", os.getuid())
    monkeypatch.setattr(builder, "BUILDER_GID", os.getgid())
    monkeypatch.setattr(builder, "STATE_ROOT", state)
    monkeypatch.setattr(builder, "PHASE_SLOTS", {"phase-a": slot})
    monkeypatch.setattr(builder, "PHASE_ROOTS", {"phase-a": final})
    monkeypatch.setattr(builder, "LOCK_PATHS", {"phase-a": lock})
    return slot, final, lock


def test_workspace_chain_is_held_and_detects_rebind(tmp_path: Path) -> None:
    private = tmp_path / "private"
    private.mkdir(mode=0o700)
    authority = builder._open_workspace_chain(private, allowed_uids={0, os.geteuid()})
    authority.revalidate()
    displaced = tmp_path / "displaced"
    private.rename(displaced)
    private.mkdir(mode=0o700)
    try:
        with pytest.raises(builder.BuilderError, match="WORKSPACE_ANCESTOR_DRIFT"):
            authority.revalidate()
    finally:
        authority.close()


def test_phase_lock_allows_expected_publish_directory_timestamp_change(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    slot, final, _lock = _temporary_phase_slot(tmp_path, monkeypatch)

    with builder._phase_lock("phase-a"):
        staging = slot / ".phase-a.staging-test"
        staging.mkdir()
        staging.chmod(0o555)
        staging.rename(final)

    assert final.is_dir()
    assert set(path.name for path in slot.iterdir()) == {".build.lock", "published"}


def test_phase_lock_rejects_slot_path_rebind(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    slot, final, _lock = _temporary_phase_slot(tmp_path, monkeypatch)

    with pytest.raises(builder.BuilderError, match="PHASE_SLOT_DRIFT"):
        with builder._phase_lock("phase-a"):
            displaced = slot.with_name("phase-a-slot-displaced")
            slot.parent.chmod(0o755)
            slot.rename(displaced)
            slot.mkdir(mode=0o711)
            (slot / ".build.lock").touch(mode=0o600)
            final.mkdir(mode=0o555)
            slot.parent.chmod(0o555)


def test_phase_lock_rejects_slot_metadata_drift(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    slot, final, _lock = _temporary_phase_slot(tmp_path, monkeypatch)

    with pytest.raises(builder.BuilderError, match="PHASE_SLOT_DRIFT"):
        with builder._phase_lock("phase-a"):
            final.mkdir(mode=0o555)
            slot.chmod(0o700)


def test_phase_lock_rejects_unexpected_final_inventory(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    slot, final, _lock = _temporary_phase_slot(tmp_path, monkeypatch)

    with pytest.raises(builder.BuilderError, match="PHASE_SLOT_DRIFT"):
        with builder._phase_lock("phase-a"):
            final.mkdir(mode=0o555)
            (slot / "unexpected").write_bytes(b"drift")


def test_source_contains_no_yhliu_compile_or_mutable_candidate_fallback() -> None:
    raw = Path(builder.__file__).read_text()
    assert "/home/yhliu" not in raw
    assert "review-candidate-20260830a" not in raw
    assert "newuidmap" not in raw
    assert "newgidmap" not in raw
    assert "subuid" not in raw
    assert "subgid" not in raw
    assert 'parser.add_argument("--phase"' in raw
    assert 'choices=("phase-a", "phase-b")' in raw


def test_cli_rejects_unknown_phase_without_work(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit):
        builder.main(["--phase", "phase-c"])
    assert "invalid choice" in capsys.readouterr().err


def test_phase_a_planner_cli_requires_every_external_pin(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit):
        builder.main(["--plan-phase-a-request"])
    assert "all phase A planner inputs are required" in capsys.readouterr().err


def test_builder_claims_remain_negative() -> None:
    request = _phase_a_request()
    assert request["accepted"] is False
    assert request["claims"] == {
        "dedicated_builder_uid_gid": [997, 997],
        "network_access": False,
        "double_build_required": True,
        "worktree_or_user_candidate_input": False,
        "write_root": "/var/lib/vista-r8-native-builder-r1",
        "observation_only": True,
        "production_native_output": False,
    }
    assert json.loads(builder.canonical_json(request))["accepted"] is False
