#!/usr/bin/env python3
"""Fail-closed publishers for the VISTA R8 UE 5.7 execution authorities.

This module is deliberately standard-library only.  The production entry point
must be installed at :data:`INSTALLED_HELPER` and invoked by one of the two
reviewed root-owned native administrator launchers.  A checkout copy is useful
only for CPU fixture tests and zero-write inspection.

The engine source contract is *not* learned at publication time.  A separate,
root-owned reviewed pin document must bind the complete pre-copy source
manifest digest, projection, counts, and bytes.  Likewise, runtime and bundle
inputs come from fixed reviewed pin documents; no production CLI accepts a
path, hash, soname, asset list, or authority root.
"""

from __future__ import annotations

import argparse
import array
import contextlib
import ctypes
import dataclasses
import errno
import fcntl
import grp
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import pwd
import re
import socket
import stat
import struct
import subprocess
import sys
import tempfile
from typing import Any, Callable, Iterable, Mapping, Sequence
import unicodedata


ENGINE_MANIFEST_SCHEMA = "vista.r5-immutable-engine-tree/v1"
ENGINE_SOURCE_PIN_SCHEMA = "vista.r8-ue57-engine-source-pin/v1"
ENGINE_RECEIPT_SCHEMA = "vista.r8-ue57-engine-authority-receipt/v1"
HOST_RUNTIME_MANIFEST_SCHEMA = "vista.r8-ue57-host-runtime-authority-manifest/v1"
HOST_RUNTIME_RECEIPT_SCHEMA = "vista.r8-ue57-host-runtime-authority-receipt/v2"
RUNTIME_INPUT_PIN_SCHEMA = "vista.r8-ue57-host-runtime-input-pin/v1"
BUNDLE_INPUT_PIN_SCHEMA = "vista.r8-ue57-executor-bundle-input-pin/v1"
RUNTIME_AUDIT_PLAN_SCHEMA = "vista.r8-ue57-host-runtime-audit-plan/v1"
BUNDLE_AUDIT_PLAN_SCHEMA = "vista.r8-ue57-executor-bundle-audit-plan/v1"
REVIEWED_PLAN_PIN_SCHEMA = "vista.r8-ue57-reviewed-audit-plan-pin/v2"
STAGE_INSTALLER_RECEIPT_SCHEMA = "vista.r8-ue57-stage-installer-transfer-receipt/v1"
BUNDLE_MANIFEST_SCHEMA = "vista.r8-sealed-ue57-executor-bundle/v2"
ROOT_POLICY_SCHEMA = "vista.r8-sealed-ue57-executor-root-policy/v3"
ROOT_POLICY_CORE_SCHEMA = "vista.r8-sealed-ue57-executor-root-policy-core/v1"
CORE_BOOTSTRAP_REVIEW_AUDIT_SCHEMA = "vista.r8-ue57-core-bootstrap-review-audit/v2"
INITIAL_BOOTSTRAP_INPUT_PIN_SCHEMA = "vista.r8-ue57-initial-bootstrap-input-pin/v2"
BUILDPLUGIN_MANIFEST_SCHEMA = "vista.r8-buildplugin-authority-manifest/v1"
BUILDPLUGIN_RECEIPT_SCHEMA = "vista.r8-buildplugin-authority-receipt/v2"
BUILDPLUGIN_ADMIN_RECEIPT_SCHEMA = "vista.r8-buildplugin-admin-install-receipt/v1"

ROOT_UID = 0
ROOT_GID = 0
REVIEW_UID = 1000021
REVIEW_GID = 1000001
INSTALLED_ROOT = Path("/root/vista-r8-ue57-authority-r2")
INSTALLED_HELPER = INSTALLED_ROOT / "vista_r8_ue57_authority_admin.py"
INSTALLED_ENGINE_WRAPPER = INSTALLED_ROOT / "provision_vista_r8_ue57_engine.sh"
INSTALLED_STAGE_TRANSFER_LAUNCHER = INSTALLED_ROOT / "transfer-r8-ue57-stage-installer"
ENGINE_SOURCE_PIN_PATH = INSTALLED_ROOT / "engine-source-pin.json"

# These are intentionally separate, fresh root authorities.  The core helper
# is sealed before the engine is copied, while runtime inputs do not exist
# until the engine and BuildPlugin authorities are sealed, and bundle inputs do
# not exist until the runtime is sealed.  Appending later pins below
# ``INSTALLED_ROOT`` would create a sequential-sealing cycle.
RUNTIME_INPUT_AUTHORITY = Path("/root/vista-r8-ue57-runtime-input-r1")
RUNTIME_INPUT_PIN_PATH = RUNTIME_INPUT_AUTHORITY / "input-pin.json"
RUNTIME_INPUT_REVIEW_CANDIDATE = Path(
    "/data/sysx/vista-world/runs/vista-action-world-r1/"
    "vista-r8-ue57-runtime-input-review-candidate-20260830a/input-pin.json"
)
RUNTIME_PLAN_AUTHORITY = Path("/root/vista-r8-ue57-runtime-plan-r1")
RUNTIME_REVIEWED_PLAN_PIN_PATH = RUNTIME_PLAN_AUTHORITY / "reviewed-plan-pin.json"
ADMIN_LAUNCHER_NAME = "publish-reconcile-r8-ue57"
RUNTIME_ADMIN_LAUNCHER = RUNTIME_PLAN_AUTHORITY / ADMIN_LAUNCHER_NAME
RUNTIME_PLAN_REVIEW_CANDIDATE_ROOT = Path(
    "/data/sysx/vista-world/runs/vista-action-world-r1/"
    "vista-r8-ue57-runtime-plan-review-candidate-20260830a"
)
RUNTIME_REVIEWED_PLAN_CANDIDATE = (
    RUNTIME_PLAN_REVIEW_CANDIDATE_ROOT / "reviewed-plan-pin.json"
)
RUNTIME_ADMIN_LAUNCHER_CANDIDATE = (
    RUNTIME_PLAN_REVIEW_CANDIDATE_ROOT / ADMIN_LAUNCHER_NAME
)
BUNDLE_INPUT_AUTHORITY = Path("/root/vista-r8-ue57-bundle-input-r1")
BUNDLE_INPUT_PIN_PATH = BUNDLE_INPUT_AUTHORITY / "input-pin.json"
BUNDLE_PLAN_AUTHORITY = Path("/root/vista-r8-ue57-bundle-plan-r1")
BUNDLE_REVIEWED_PLAN_PIN_PATH = BUNDLE_PLAN_AUTHORITY / "reviewed-plan-pin.json"
BUNDLE_ADMIN_LAUNCHER = BUNDLE_PLAN_AUTHORITY / ADMIN_LAUNCHER_NAME
BUNDLE_PLAN_REVIEW_CANDIDATE_ROOT = Path(
    "/data/sysx/vista-world/runs/vista-action-world-r1/"
    "vista-r8-ue57-bundle-plan-review-candidate-20260830a"
)
BUNDLE_REVIEWED_PLAN_CANDIDATE = (
    BUNDLE_PLAN_REVIEW_CANDIDATE_ROOT / "reviewed-plan-pin.json"
)
BUNDLE_ADMIN_LAUNCHER_CANDIDATE = (
    BUNDLE_PLAN_REVIEW_CANDIDATE_ROOT / ADMIN_LAUNCHER_NAME
)
STAGE_INSTALLER_NAME = "install-reconcile-r8-ue57-stage"
STAGE_INSTALLER_AUTHORITY_PARENT = Path("/root/vista-r8-ue57-stage-installers-r1")
STAGE_INSTALLER_REVIEW_PARENT = Path(
    "/data/sysx/vista-world/runs/vista-action-world-r1"
)
STAGE_KEYS = ("runtime-input", "runtime-plan", "bundle-input", "bundle-plan")
STAGE_INSTALLER_REVIEW_ROOTS = {
    stage: STAGE_INSTALLER_REVIEW_PARENT
    / f"vista-r8-ue57-{stage}-stage-installer-review-candidate-20260830a"
    for stage in STAGE_KEYS
}
STAGE_INSTALLER_AUTHORITIES = {
    stage: STAGE_INSTALLER_AUTHORITY_PARENT / stage for stage in STAGE_KEYS
}

AUTHORITY_PARENT = Path("/data/vista-authorities")
ENGINE_SOURCE = Path("/mnt/NAS2/yhliu/UE_5.7.3_prebuilt")
ENGINE_AUTHORITY = AUTHORITY_PARENT / "ue-5.7.3-r1"
ENGINE_ROOT = ENGINE_AUTHORITY / "engine"
ENGINE_MANIFEST = ENGINE_AUTHORITY / "engine-full-tree-manifest.json"
HOST_RUNTIME_AUTHORITY = AUTHORITY_PARENT / "vista-r8-ue57-host-runtime-r1"
HOST_RUNTIME_PAYLOAD = HOST_RUNTIME_AUTHORITY / "payload"
BUILDPLUGIN_AUTHORITY = AUTHORITY_PARENT / "vista-r8-ue-animation-buildplugin-r1"
BUILDPLUGIN_PAYLOAD = BUILDPLUGIN_AUTHORITY / "payload"

ROOT_EXECUTION_AUTHORITY = Path("/root/vista-r8-ue57-executor-r2")
ROOT_BUNDLE = ROOT_EXECUTION_AUTHORITY / "bundle"
ROOT_POLICY = ROOT_EXECUTION_AUTHORITY / "policy.json"
CHECKOUT_ROOT = Path("/home/yhliu/VISTA-World-worktrees/vista-r8-fresh-namespace-r2")
BUNDLE_SOURCE_PATHS = {
    "makehuman_cc0_animation_runtime_executor.py": (
        CHECKOUT_ROOT / "tools/ue/vista_playable_home/"
        "makehuman_cc0_animation_runtime_executor.py"
    ),
    "makehuman_cc0_animation_runtime_sandbox_wrapper.py": (
        CHECKOUT_ROOT / "tools/ue/vista_playable_home/"
        "makehuman_cc0_animation_runtime_sandbox_wrapper.py"
    ),
    "makehuman_cc0_animation_runtime_commandlet.py": (
        CHECKOUT_ROOT / "tools/ue/vista_playable_home/"
        "makehuman_cc0_animation_runtime_commandlet.py"
    ),
}
LAUNCHER_NAME = "launch-r8-ue57"
LAUNCHER_SOURCE = CHECKOUT_ROOT / "tools/admin/vista_r8_ue57_launcher.c"
REVIEW_HELPER_SOURCE = CHECKOUT_ROOT / "tools/admin/vista_r8_ue57_authority_admin.py"
ADMIN_LAUNCHER_SOURCE = CHECKOUT_ROOT / "tools/admin/vista_r8_ue57_admin_launcher.c"
STAGE_INSTALLER_SOURCE = CHECKOUT_ROOT / "tools/admin/vista_r8_ue57_stage_installer.c"
STAGE_TRANSFER_LAUNCHER_SOURCE = (
    CHECKOUT_ROOT / "tools/admin/vista_r8_ue57_stage_transfer_launcher.c"
)
ENGINE_WRAPPER_SOURCE = CHECKOUT_ROOT / "tools/admin/provision_vista_r8_ue57_engine.sh"
BUILDPLUGIN_HELPER_SOURCE = (
    CHECKOUT_ROOT / "tools/admin/vista_r8_buildplugin_authority.py"
)
PARENT_SEAL_HELPER_SOURCE = CHECKOUT_ROOT / "tools/admin/vista_authority_parent_seal.py"
PARENT_SEAL_LAUNCHER_SOURCE = (
    CHECKOUT_ROOT / "tools/admin/vista_authority_parent_seal_launcher.c"
)
INITIAL_BOOTSTRAP_HELPER_SOURCE = (
    CHECKOUT_ROOT / "tools/admin/vista_r8_ue57_initial_bootstrap.py"
)
INITIAL_BOOTSTRAP_LAUNCHER_SOURCE = (
    CHECKOUT_ROOT / "tools/admin/vista_r8_ue57_initial_bootstrap_launcher.c"
)
INITIAL_BOOTSTRAP_INSTALLER_SOURCE = (
    CHECKOUT_ROOT / "tools/admin/vista_r8_ue57_initial_bootstrap_installer.c"
)
INITIAL_BOOTSTRAP_LAUNCHER_NAME = "bootstrap-r8-ue57-initial-authorities"
INITIAL_BOOTSTRAP_INSTALLER_NAME = "install-reconcile-r8-ue57-initial-bootstrap"
INITIAL_BOOTSTRAP_INPUT_NAME = "input-pin.json"
INITIAL_BOOTSTRAP_REVIEW_CANDIDATE_ROOT = Path(
    "/var/lib/vista-r8-native-builder-r2/phase-b-slot/published/"
    "initial-bootstrap-candidate"
)
INITIAL_BOOTSTRAP_INSTALL_ROOT = Path("/root/vista-r8-ue57-initial-bootstrap-r2")
INITIAL_BOOTSTRAP_INSTALLER_REVIEW_CANDIDATE_ROOT = Path(
    "/var/lib/vista-r8-native-builder-r2/phase-b-slot/published/"
    "initial-bootstrap-installer"
)
INITIAL_BOOTSTRAP_INSTALLER_INSTALL_ROOT = Path(
    "/root/vista-r8-ue57-initial-bootstrap-installer-r2"
)
NATIVE_BUILDER_UID = 997
NATIVE_BUILDER_GID = 997
NATIVE_BUILDER_NAME = "vista-r8-builder"
NATIVE_BUILDER_ACCOUNT_HOME = Path("/nonexistent")
NATIVE_BUILDER_HOME = Path("/var/lib/vista-r8-native-builder-r2")
NATIVE_BUILDER_INPUT_ROOT = Path("/etc/vista-r8-native-builder-r2")
NATIVE_BUILDER_BUNDLE = NATIVE_BUILDER_INPUT_ROOT / "source.bundle"
NATIVE_BUILDER_PHASE_A_REQUEST = NATIVE_BUILDER_INPUT_ROOT / "phase-a-request.json"
NATIVE_BUILDER_PHASE_B_REQUEST = NATIVE_BUILDER_INPUT_ROOT / "phase-b-request.json"
NATIVE_BUILDER_PHASE_A_ROOT = NATIVE_BUILDER_HOME / "phase-a-slot/published"
NATIVE_BUILDER_PHASE_B_ROOT = NATIVE_BUILDER_HOME / "phase-b-slot/published"
NATIVE_BUILDER_PHASE_A_PARENT_SEAL_ROOT = (
    NATIVE_BUILDER_PHASE_A_ROOT / "parent-seal-candidate"
)
NATIVE_BUILDER_HELPER = Path(
    "/usr/local/libexec/vista-r8-native-builder-r2/vista_r8_native_builder.py"
)
NATIVE_BUILDER_PHASE_A_UNIT = Path(
    "/etc/systemd/system/vista-r8-native-builder-r2-phase-a.service"
)
NATIVE_BUILDER_PHASE_B_UNIT = Path(
    "/etc/systemd/system/vista-r8-native-builder-r2-phase-b.service"
)
NATIVE_BUILDER_PHASE_A_SCHEMA = "vista.r8-native-builder-phase-a-manifest/v1"
NATIVE_BUILDER_PHASE_B_SCHEMA = "vista.r8-native-builder-phase-b-manifest/v1"
NATIVE_BUILDER_REQUEST_SCHEMA = "vista.r8-native-builder-request/v2"
NATIVE_BUILDER_TRACE_CONTRACT_SCHEMA = "vista.r8-native-builder-trace-contract/v5"
NATIVE_BUILDER_JOB_SCHEMA = "vista.r8-native-builder-job-manifest/v1"
NATIVE_BUILDER_KERNEL_VIRTUAL_SYSCTL_PATH = Path("/proc/sys/vm/overcommit_memory")
NATIVE_BUILDER_KERNEL_VIRTUAL_COMPONENT_POLICY = "proc-chain-mount-metadata-volatile-v2"
NATIVE_BUILDER_KERNEL_VIRTUAL_SYSCTL_VALUES = (b"0\n", b"1\n", b"2\n")
NATIVE_BUILDER_KERNEL_VIRTUAL_COMPONENT_PATHS = (
    "/",
    "/proc",
    "/proc/sys",
    "/proc/sys/vm",
    "/proc/sys/vm/overcommit_memory",
)
NATIVE_BUILDER_KERNEL_VIRTUAL_COMPONENT_KINDS = (
    "directory",
    "directory",
    "directory",
    "directory",
    "regular",
)
NATIVE_BUILDER_KERNEL_VIRTUAL_METADATA_VOLATILE_PATHS = (
    NATIVE_BUILDER_KERNEL_VIRTUAL_COMPONENT_PATHS[1:]
)
NATIVE_BUILDER_KERNEL_VIRTUAL_NLINK_VOLATILE_PATHS = ("/proc",)
NATIVE_BUILDER_KERNEL_VIRTUAL_VOLATILE_METADATA_FIELDS = (
    "device",
    "inode",
    "mtime_ns",
    "ctime_ns",
)
NATIVE_BUILDER_CPU_ONLINE_PATH = "/sys/devices/system/cpu/online"
NATIVE_BUILDER_CPU_ONLINE_READ_EVENT_LINE = (
    '{"open_flags":["O_RDONLY","O_CLOEXEC"],"outcome":"OK",'
    f'"paths":["{NATIVE_BUILDER_CPU_ONLINE_PATH}"],"syscall":"openat"}}'
)
NATIVE_BUILDER_CPU_ONLINE_EVENT_COUNT_POLICY = "positive-presence-v1"


def _native_builder_trace_event_count_policies() -> list[dict[str, Any]]:
    return [
        {
            "canonical_count": 1,
            "event_line": NATIVE_BUILDER_CPU_ONLINE_READ_EVENT_LINE,
            "policy": NATIVE_BUILDER_CPU_ONLINE_EVENT_COUNT_POLICY,
            "profile_id": "git:fetch",
        }
    ]


def _native_builder_validate_trace_event_count_policies(
    value: Any,
) -> list[dict[str, Any]]:
    expected = _native_builder_trace_event_count_policies()
    if type(value) is not list or len(value) != 1:
        _fail("NATIVE_BUILDER_TRACE_CONTRACT_INVALID", "event count policies")
    item = value[0]
    if (
        type(item) is not dict
        or set(item) != {"canonical_count", "event_line", "policy", "profile_id"}
        or type(item.get("canonical_count")) is not int
        or type(item.get("event_line")) is not str
        or type(item.get("policy")) is not str
        or type(item.get("profile_id")) is not str
        or item != expected[0]
    ):
        _fail("NATIVE_BUILDER_TRACE_CONTRACT_INVALID", "event count policies")
    return [dict(item)]


MAX_NATIVE_BUILDER_BUNDLE_BYTES = 512 * 1024 * 1024
MAX_NATIVE_BUILDER_TRACE_FILE_BYTES = 64 * 1024 * 1024
MAX_NATIVE_BUILDER_TRACE_LINES = 1_000_000
ENGINE_SOURCE_PIN_REVIEW_CANDIDATE = Path(
    "/data/sysx/vista-world/runs/vista-action-world-r1/"
    "vista-r8-ue57-engine-source-pin-review-candidate-20260830a/"
    "engine-source-pin.json"
)
CORE_BOOTSTRAP_REVIEW_CANDIDATE_ROOT = Path(
    "/data/sysx/vista-world/runs/vista-action-world-r1/"
    "vista-r8-ue57-core-bootstrap-review-candidate-20260830a"
)
PARENT_SEAL_LAUNCHER_NAME = "launch-vista-authority-parent-seal"
BUILDPLUGIN_ADMIN_REVIEW_CANDIDATE_ROOT = Path(
    "/data/sysx/vista-world/runs/vista-action-world-r1/"
    "vista-r8-buildplugin-admin-review-candidate-20260830a"
)
BUILDPLUGIN_ADMIN_SCRIPT_NAME = "publish-reconcile-buildplugin.sh"
BUILDPLUGIN_HELPER_INSTALL_ROOT = Path("/root/vista-r8-buildplugin-authority-r1")
BUILDPLUGIN_HELPER_INSTALL_PATH = (
    BUILDPLUGIN_HELPER_INSTALL_ROOT / "vista_r8_buildplugin_authority.py"
)
BUILDPLUGIN_ADMIN_INSTALL_ROOT = Path("/root/vista-r8-buildplugin-admin-r1")
BUILDPLUGIN_ADMIN_INSTALL_PATH = (
    BUILDPLUGIN_ADMIN_INSTALL_ROOT / "publish-reconcile-buildplugin"
)
BUILDPLUGIN_ADMIN_RECEIPT_PATH = BUILDPLUGIN_ADMIN_INSTALL_ROOT / "receipt.json"
BUNDLE_INPUT_LAUNCHER = BUNDLE_INPUT_AUTHORITY / LAUNCHER_NAME
BUNDLE_LAUNCHER_REVIEW_CANDIDATE = Path(
    "/data/sysx/vista-world/runs/vista-action-world-r1/"
    "vista-r8-ue57-launcher-review-candidate-20260830a/launch-r8-ue57"
)
BUNDLE_INPUT_REVIEW_CANDIDATE = (
    BUNDLE_LAUNCHER_REVIEW_CANDIDATE.parent / "input-pin.json"
)
APPROVED_ATTEMPT_NAME = "makehuman-cc0-animation-ue57-r1-20260830a"
INVOCATION_LEDGER_PATH = Path(
    "/data/vista-published/vista-action-world-r1/"
    ".makehuman-cc0-animation-ue57-r1-20260830a.invocation.json"
)

PYTHON_PATH = Path("/usr/bin/python3.10")
READELF_PATH = Path("/usr/bin/readelf")
STRACE_PATH = Path("/usr/bin/strace")
NATIVE_BUILDER_STRACE_VERSION = "strace -- version 5.16"
BWRAP_PATH = Path("/usr/bin/bwrap")
COMPILER_PATH = Path("/usr/bin/gcc-12")
NEWUIDMAP_PATH = Path("/usr/bin/newuidmap")
NEWGIDMAP_PATH = Path("/usr/bin/newgidmap")
SUBUID_PATH = Path("/etc/subuid")
SUBGID_PATH = Path("/etc/subgid")
REVIEW_USERNAME = "yhliu"
NATIVE_BUILD_SUBUID = 165536
NATIVE_BUILD_SUBGID = 165536
NATIVE_BUILD_SUBID_RANGE = 65536
COMPILER_TOOLCHAIN_ARTIFACTS = (
    Path("/usr/lib/gcc/x86_64-linux-gnu/12/cc1"),
    Path("/usr/lib/gcc/x86_64-linux-gnu/12/collect2"),
    Path("/usr/bin/as"),
    Path("/usr/bin/ld"),
    Path("/usr/lib/gcc/x86_64-linux-gnu/12/crtbeginT.o"),
    Path("/usr/lib/gcc/x86_64-linux-gnu/12/crtend.o"),
    Path("/usr/lib/x86_64-linux-gnu/crt1.o"),
    Path("/usr/lib/x86_64-linux-gnu/crti.o"),
    Path("/usr/lib/x86_64-linux-gnu/crtn.o"),
    Path("/usr/lib/x86_64-linux-gnu/libc.a"),
    Path("/usr/lib/x86_64-linux-gnu/libc_nonshared.a"),
    Path("/usr/lib/gcc/x86_64-linux-gnu/12/libgcc.a"),
    Path("/usr/lib/gcc/x86_64-linux-gnu/12/libgcc_eh.a"),
)
NATIVE_BUILDER_SOURCE_PATHS = (
    "tools/admin/vista_r8_ue57_authority_admin.py",
    "tools/admin/vista_r8_ue57_stage_transfer_launcher.c",
    "tools/admin/vista_authority_parent_seal.py",
    "tools/admin/vista_authority_parent_seal_launcher.c",
    "tools/admin/vista_r8_ue57_initial_bootstrap.py",
    "tools/admin/vista_r8_ue57_initial_bootstrap_launcher.c",
    "tools/admin/vista_r8_ue57_initial_bootstrap_installer.c",
)
NATIVE_BUILDER_PHASE_A_JOB_IDS = (
    "stage-transfer-launcher",
    "parent-seal-launcher",
    "initial-bootstrap-launcher",
)
NATIVE_BUILDER_PHASE_B_JOB_IDS = ("initial-bootstrap-installer",)
NATIVE_BUILDER_TRACE_FILE_SYSCALLS = frozenset(
    {
        "access",
        "chdir",
        "chmod",
        "chown",
        "creat",
        "execve",
        "execveat",
        "fchdir",
        "faccessat",
        "faccessat2",
        "fchmodat",
        "fchownat",
        "getcwd",
        "link",
        "linkat",
        "lstat",
        "mkdir",
        "mkdirat",
        "mknod",
        "mknodat",
        "newfstatat",
        "open",
        "openat",
        "openat2",
        "quotactl",
        "readlink",
        "readlinkat",
        "rename",
        "renameat",
        "renameat2",
        "rmdir",
        "stat",
        "statfs",
        "statx",
        "symlink",
        "symlinkat",
        "truncate",
        "unlink",
        "unlinkat",
        "utime",
        "utimensat",
        "utimes",
    }
)
NATIVE_BUILDER_TRACE_ALLOWED_ERRNOS = frozenset(
    {"EACCES", "EEXIST", "EINVAL", "ELOOP", "ENOENT", "ENOTDIR", "EPERM"}
)
NATIVE_BUILDER_TRACE_OPEN_SYSCALLS = frozenset({"open", "openat", "openat2"})
NATIVE_BUILDER_TRACE_OPEN_ACCESS_MODES = frozenset({"O_RDONLY", "O_WRONLY", "O_RDWR"})
NATIVE_BUILDER_TRACE_OPEN_FLAG_TOKENS = frozenset(
    {
        "O_RDONLY",
        "O_WRONLY",
        "O_RDWR",
        "O_APPEND",
        "O_ASYNC",
        "O_CLOEXEC",
        "O_CREAT",
        "O_DIRECT",
        "O_DIRECTORY",
        "O_DSYNC",
        "O_EXCL",
        "O_LARGEFILE",
        "O_NOATIME",
        "O_NOCTTY",
        "O_NOFOLLOW",
        "O_NONBLOCK",
        "O_PATH",
        "O_SYNC",
        "O_TMPFILE",
        "O_TRUNC",
    }
)
NATIVE_BUILDER_TRACE_DEV_NULL_ALLOWED_NONMUTATING_FLAGS = frozenset({"O_CLOEXEC"})
NATIVE_BUILDER_KERNEL_VIRTUAL_ALLOWED_OPEN_FLAGS = frozenset(
    {"O_CLOEXEC", "O_LARGEFILE", "O_NOFOLLOW", "O_NONBLOCK"}
)
NATIVE_BUILDER_KERNEL_VIRTUAL_READ_SYSCALLS = frozenset(
    {
        "access",
        "faccessat",
        "faccessat2",
        "lstat",
        "newfstatat",
        "open",
        "openat",
        "openat2",
        "stat",
        "statfs",
        "statx",
    }
)
NATIVE_BUILDER_BUILD_ENVIRONMENT = {
    "PATH": "/usr/bin:/bin",
    "LANG": "C",
    "LC_ALL": "C",
    "SOURCE_DATE_EPOCH": "0",
    "TMPDIR": "$SCRATCH",
}
PYTHON_STDLIB = Path("/usr/lib/python3.10")
SYSTEM_LIBRARY_DIRECTORIES = (
    Path("/lib/x86_64-linux-gnu"),
    Path("/usr/lib/x86_64-linux-gnu"),
    Path("/lib64"),
    Path("/usr/lib64"),
)
HOST_LIBRARY_RELATIVE_PATHS = (
    "lib/x86_64-linux-gnu",
    "usr/lib/x86_64-linux-gnu",
    "lib64",
    "usr/lib64",
)
RUNTIME_DATA_ALLOWLIST = (
    Path("/usr/share/zoneinfo/UTC"),
    Path("/usr/lib/locale/C.utf8"),
    Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
)
GENERATED_ETC = {
    "etc/group": "root:x:0:\nnogroup:x:65534:\n",
    "etc/hosts": "127.0.0.1 localhost\n::1 localhost\n",
    "etc/nsswitch.conf": "passwd: files\ngroup: files\nhosts: files\n",
    "etc/passwd": (
        "root:x:0:0:root:/root:/usr/sbin/nologin\n"
        "nobody:x:65534:65534:nobody:/nonexistent:/usr/sbin/nologin\n"
    ),
}
FORBIDDEN_RUNTIME_SOURCE_PREFIXES = (
    Path("/home"),
    Path("/root"),
    Path("/run"),
    Path("/proc"),
    Path("/sys"),
    Path("/dev"),
    Path("/etc/ssh"),
)
FORBIDDEN_RUNTIME_SOURCE_FILES = frozenset(
    {Path("/etc/shadow"), Path("/etc/gshadow"), Path("/etc/sudoers")}
)
CRITICAL_ENGINE_FILES = (
    "Engine/Binaries/Linux/UnrealEditor-Cmd",
    "Engine/Binaries/Linux/UnrealEditor.modules",
    "Engine/Build/Build.version",
)
R3_RUN_ROOT = Path(
    "/data/sysx/vista-world/runs/vista-action-world-r1/"
    "makehuman-cc0-ue-import-r3-20260829"
)
R3_PROJECT_ROOT = R3_RUN_ROOT / "project"
R3_RECEIPT_PATH = R3_RUN_ROOT / "makehuman-cc0-import-host-receipt.json"
R8_PUBLISHED_PARENT = Path("/data/vista-published/vista-action-world-r1")
R8_ATTEMPT_NAME = "makehuman-cc0-animation-r8-20260830a"
R8_AUTHORITY = R8_PUBLISHED_PARENT / R8_ATTEMPT_NAME
R8_RECEIPT_PATH = R8_AUTHORITY / "host-receipt.json"
R8_FBX_RELATIVE_PATHS = (
    "fbx/AS_VistaCC0Idle.fbx",
    "fbx/AS_VistaCC0MugPickupCountertop.fbx",
    "fbx/AS_VistaCC0MugPlaceCountertop.fbx",
    "fbx/AS_VistaCC0Run.fbx",
    "fbx/AS_VistaCC0Walk.fbx",
)

ENGINE_ACKNOWLEDGEMENT = (
    "I acknowledge one fresh publication of the reviewed VISTA R8 UE 5.7 "
    "engine authority."
)
STAGE_ACKNOWLEDGEMENTS = {
    ("runtime", False, "install"): (
        "I acknowledge one fresh publication of the externally reviewed "
        "VISTA R8 UE 5.7 runtime input authority."
    ),
    ("runtime", False, "reconcile"): (
        "I acknowledge reconciliation of the externally reviewed VISTA R8 "
        "UE 5.7 runtime input authority without republishing or deleting it."
    ),
    ("runtime", True, "install"): (
        "I acknowledge one fresh publication of the externally reviewed "
        "VISTA R8 UE 5.7 runtime plan authority."
    ),
    ("runtime", True, "reconcile"): (
        "I acknowledge reconciliation of the externally reviewed VISTA R8 "
        "UE 5.7 runtime plan authority without republishing or deleting it."
    ),
    ("bundle", False, "install"): (
        "I acknowledge one fresh publication of the externally reviewed "
        "VISTA R8 UE 5.7 bundle input authority."
    ),
    ("bundle", False, "reconcile"): (
        "I acknowledge reconciliation of the externally reviewed VISTA R8 "
        "UE 5.7 bundle input authority without republishing or deleting it."
    ),
    ("bundle", True, "install"): (
        "I acknowledge one fresh publication of the externally reviewed "
        "VISTA R8 UE 5.7 bundle plan authority."
    ),
    ("bundle", True, "reconcile"): (
        "I acknowledge reconciliation of the externally reviewed VISTA R8 "
        "UE 5.7 bundle plan authority without republishing or deleting it."
    ),
}
STAGE_INSTALLER_TRANSFER_ACKNOWLEDGEMENTS = {
    (stage, "install"): (
        "I acknowledge one fresh root transfer of the externally reviewed "
        f"VISTA R8 UE 5.7 {stage} one-shot stage installer."
    )
    for stage in STAGE_KEYS
}
STAGE_INSTALLER_TRANSFER_ACKNOWLEDGEMENTS.update(
    {
        (stage, "reconcile"): (
            "I acknowledge reconciliation of the externally reviewed VISTA R8 "
            f"UE 5.7 {stage} one-shot stage installer without republishing or "
            "deleting it."
        )
        for stage in STAGE_KEYS
    }
)
HOST_RUNTIME_ACKNOWLEDGEMENT = (
    "I acknowledge one fresh publication of the reviewed VISTA R8 UE 5.7 "
    "host-runtime authority."
)
BUNDLE_ACKNOWLEDGEMENT = (
    "I acknowledge one fresh publication of the reviewed VISTA R8 UE 5.7 "
    "R2 executor bundle."
)
HOST_RUNTIME_RECONCILIATION_ACKNOWLEDGEMENT = (
    "I acknowledge reconciliation of the existing reviewed VISTA R8 UE 5.7 "
    "host-runtime authority without republishing or deleting it."
)
BUNDLE_RECONCILIATION_ACKNOWLEDGEMENT = (
    "I acknowledge reconciliation of the existing reviewed VISTA R8 UE 5.7 "
    "R2 executor bundle without republishing or deleting it."
)
ENGINE_RECONCILIATION_ACKNOWLEDGEMENT = (
    "I acknowledge reconciliation of the existing reviewed VISTA R8 UE 5.7 "
    "engine authority without republishing or deleting it."
)
INITIAL_BOOTSTRAP_PUBLISH_ACKNOWLEDGEMENT = (
    "I acknowledge one irreversible append-only publication of the four "
    "externally reviewed VISTA R8 UE 5.7 initial authorities from an empty prefix."
)
INITIAL_BOOTSTRAP_RECONCILE_ACKNOWLEDGEMENT = (
    "I acknowledge candidate-free audit and fsync reconciliation of the existing "
    "VISTA R8 UE 5.7 initial-authority prefix without creating, deleting, or "
    "repairing any root."
)
INITIAL_BOOTSTRAP_RESUME_ACKNOWLEDGEMENT = (
    "I acknowledge candidate-free reconciliation followed by append-only resume "
    "of the externally reviewed VISTA R8 UE 5.7 initial-authority prefix."
)
INITIAL_BOOTSTRAP_INSTALL_ACKNOWLEDGEMENT = (
    "I acknowledge one fresh no-replace installation of the externally "
    "reviewed VISTA R8 UE 5.7 initial bootstrap authority."
)
INITIAL_BOOTSTRAP_INSTALL_RECONCILE_ACKNOWLEDGEMENT = (
    "I acknowledge candidate-free fsync reconciliation of the existing VISTA "
    "R8 UE 5.7 initial bootstrap authority without creating, deleting, "
    "renaming, chmodding, or repairing it."
)

SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
SONAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9.+_-]{0,254}$")
NEEDED_RE = re.compile(r"\(NEEDED\).*\[([^\]]+)\]")
INTERP_RE = re.compile(r"Requesting program interpreter:\s*([^\]]+)\]")
SONAME_FIELD_RE = re.compile(r"\(SONAME\).*\[([^\]]+)\]")
RPATH_RE = re.compile(r"\(RPATH\).*\[([^\]]*)\]")
RUNPATH_RE = re.compile(r"\(RUNPATH\).*\[([^\]]*)\]")
RENAME_NOREPLACE = 1
AT_FDCWD = -100
CHUNK_BYTES = 4 * 1024 * 1024
# The sealed UE engine manifest is intentionally a complete file-by-file
# authority inventory and is currently larger than 16 MiB.  Keep one closed,
# finite ceiling that accommodates that reviewed document without silently
# weakening JSON limits for unbounded input.
MAX_JSON_BYTES = 128 * 1024 * 1024
OPERATION_LOCKS = {
    "engine": INSTALLED_ROOT / ".engine.lock",
    "runtime": INSTALLED_ROOT / ".runtime.lock",
    "bundle": INSTALLED_ROOT / ".bundle.lock",
    "executor": INSTALLED_ROOT / ".executor.lock",
}


class AuthorityError(RuntimeError):
    """A closed authority or publication invariant failed."""

    def __init__(self, code: str, message: str) -> None:
        super().__init__(f"{code}: {message}")
        self.code = code


def _fail(code: str, message: str) -> None:
    raise AuthorityError(code, message)


def canonical_json(value: Any) -> bytes:
    try:
        return (
            json.dumps(
                value,
                allow_nan=False,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            )
            + "\n"
        ).encode("utf-8", "strict")
    except (TypeError, ValueError, UnicodeError) as exc:
        raise AuthorityError("CANONICAL_JSON_INVALID", "value differs") from exc


def content_digest(value: Mapping[str, Any]) -> str:
    body = dict(value)
    body.pop("content_digest", None)
    return hashlib.sha256(canonical_json(body)).hexdigest()


def seal_document(value: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(value)
    if "content_digest" in result:
        _fail("DOCUMENT_ALREADY_SEALED", "content_digest is already present")
    result["content_digest"] = content_digest(result)
    return result


def _pairs(items: Sequence[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, item in items:
        if key in value:
            raise ValueError(f"duplicate key: {key}")
        value[key] = item
    return value


def strict_json(raw: bytes, label: str) -> dict[str, Any]:
    if len(raw) > MAX_JSON_BYTES:
        _fail("JSON_INVALID", f"{label} exceeds limit")
    try:
        value = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=_pairs,
            parse_constant=lambda token: (_ for _ in ()).throw(
                ValueError(f"nonfinite: {token}")
            ),
        )
    except (UnicodeError, ValueError, TypeError) as exc:
        raise AuthorityError("JSON_INVALID", label) from exc
    if type(value) is not dict or canonical_json(value) != raw:
        _fail("JSON_INVALID", f"{label} is not one canonical object")
    return value


def _safe_relative(value: str) -> bool:
    pure = PurePosixPath(value)
    return (
        bool(value)
        and not pure.is_absolute()
        and pure.as_posix() == value
        and all(part not in ("", ".", "..") for part in pure.parts)
        and unicodedata.normalize("NFC", value) == value
    )


def _identity(info: os.stat_result) -> tuple[int, ...]:
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_nlink,
        info.st_uid,
        info.st_gid,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _file_flags() -> int:
    required = ("O_NOFOLLOW", "O_CLOEXEC")
    if any(not hasattr(os, name) for name in required):
        _fail("PLATFORM_UNSUPPORTED", "O_NOFOLLOW/O_CLOEXEC required")
    return os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK


def _directory_flags() -> int:
    if not hasattr(os, "O_DIRECTORY"):
        _fail("PLATFORM_UNSUPPORTED", "O_DIRECTORY required")
    return _file_flags() | os.O_DIRECTORY


def _hash_fd(descriptor: int) -> tuple[str, int]:
    digest = hashlib.sha256()
    size = 0
    os.lseek(descriptor, 0, os.SEEK_SET)
    while block := os.read(descriptor, CHUNK_BYTES):
        digest.update(block)
        size += len(block)
    os.lseek(descriptor, 0, os.SEEK_SET)
    return digest.hexdigest(), size


def _hash_kernel_virtual_sysctl_fd(descriptor: int) -> tuple[str, int]:
    maximum = max(map(len, NATIVE_BUILDER_KERNEL_VIRTUAL_SYSCTL_VALUES))
    os.lseek(descriptor, 0, os.SEEK_SET)
    raw = os.read(descriptor, maximum + 1)
    if raw not in NATIVE_BUILDER_KERNEL_VIRTUAL_SYSCTL_VALUES or os.read(descriptor, 1):
        _fail(
            "NATIVE_BUILDER_TRACE_INPUT_DRIFT",
            str(NATIVE_BUILDER_KERNEL_VIRTUAL_SYSCTL_PATH),
        )
    os.lseek(descriptor, 0, os.SEEK_SET)
    return hashlib.sha256(raw).hexdigest(), len(raw)


@dataclasses.dataclass(frozen=True)
class FilePin:
    sha256: str
    size_bytes: int
    executable: bool = False

    def public(self, *, executable: bool | None = None) -> dict[str, Any]:
        value: dict[str, Any] = {
            "sha256": self.sha256,
            "size_bytes": self.size_bytes,
        }
        if executable is not None:
            value["executable"] = executable
        return value


def _native_builder_kernel_virtual_sysctl_pins() -> frozenset[FilePin]:
    return frozenset(
        FilePin(hashlib.sha256(raw).hexdigest(), len(raw))
        for raw in NATIVE_BUILDER_KERNEL_VIRTUAL_SYSCTL_VALUES
    )


def _native_builder_path_is_procfs(value: str | Path) -> bool:
    return PurePosixPath(str(value)).parts[:2] == ("/", "proc")


def _native_builder_is_kernel_virtual_sysctl_target(
    requested: str | Path, canonical: str | Path
) -> bool:
    expected = str(NATIVE_BUILDER_KERNEL_VIRTUAL_SYSCTL_PATH)
    return str(requested) == expected and str(canonical) == expected


def _native_builder_kernel_virtual_component_chain_is_exact(
    chain: Sequence[Mapping[str, Any]],
) -> bool:
    return (
        tuple(item.get("path") for item in chain)
        == NATIVE_BUILDER_KERNEL_VIRTUAL_COMPONENT_PATHS
        and tuple(item.get("kind") for item in chain)
        == NATIVE_BUILDER_KERNEL_VIRTUAL_COMPONENT_KINDS
        and "metadata_policy" not in chain[0]
        and all(
            item.get("metadata_policy")
            == NATIVE_BUILDER_KERNEL_VIRTUAL_COMPONENT_POLICY
            and all(
                field not in item
                for field in NATIVE_BUILDER_KERNEL_VIRTUAL_VOLATILE_METADATA_FIELDS
            )
            for item in chain[1:]
        )
        and "nlink" not in chain[1]
        and all(type(item.get("nlink")) is int for item in chain[2:])
        and all(item.get("kind") != "symlink" for item in chain)
    )


@dataclasses.dataclass(frozen=True)
class TreeSnapshot:
    root: Path
    root_device: int
    entries: tuple[dict[str, Any], ...]
    tree_digest: str
    projection_sha256: str
    file_count: int
    directory_count: int
    total_bytes: int

    def projection(self) -> dict[str, Any]:
        return {
            "tree_digest": self.projection_sha256,
            "file_count": self.file_count,
            "directory_count": self.directory_count + 1,
            "total_bytes": self.total_bytes,
        }


def _projection_digest(entries: Sequence[Mapping[str, Any]]) -> str:
    records: list[dict[str, Any]] = [{"kind": "directory", "path": "."}]
    for entry in entries:
        if entry["type"] == "directory":
            records.append({"kind": "directory", "path": entry["path"]})
        else:
            records.append(
                {
                    "kind": "file",
                    "path": entry["path"],
                    "sha256": entry["sha256"],
                    "size_bytes": entry["size_bytes"],
                }
            )
    digest = hashlib.sha256()
    for record in sorted(records, key=lambda item: (item["path"], item["kind"])):
        raw = canonical_json(record).rstrip(b"\n")
        digest.update(len(raw).to_bytes(8, "big"))
        digest.update(raw)
    return digest.hexdigest()


def _engine_tree_digest(entries: Sequence[Mapping[str, Any]]) -> str:
    content = [
        {
            "path": item["path"],
            "type": item["type"],
            "size_bytes": item["size_bytes"],
            "sha256": item["sha256"],
        }
        for item in entries
    ]
    return hashlib.sha256(canonical_json({"entries": content})).hexdigest()


def snapshot_tree(
    root: Path, *, require_single_link_files: bool = True
) -> TreeSnapshot:
    """Fully hash a tree using openat/O_NOFOLLOW and reject namespace hazards."""

    if not root.is_absolute():
        _fail("TREE_ROOT_INVALID", str(root))
    try:
        root_lstat = os.lstat(root)
        root_fd = os.open(root, _directory_flags())
    except OSError as exc:
        raise AuthorityError("TREE_ROOT_INVALID", str(root)) from exc
    try:
        opened_root = os.fstat(root_fd)
        if not stat.S_ISDIR(opened_root.st_mode) or _identity(opened_root) != _identity(
            root_lstat
        ):
            _fail("TREE_ROOT_INVALID", str(root))
        root_device = opened_root.st_dev
        entries: list[dict[str, Any]] = []
        folded: set[str] = set()

        def visit(directory_fd: int, prefix: str) -> None:
            try:
                names = sorted(os.listdir(directory_fd))
            except OSError as exc:
                raise AuthorityError("TREE_SCAN_FAILED", prefix or ".") from exc
            local_folded: set[str] = set()
            for name in names:
                if (
                    not name
                    or "/" in name
                    or name in (".", "..")
                    or unicodedata.normalize("NFC", name) != name
                    or name.casefold() in local_folded
                ):
                    _fail("TREE_NAMESPACE_INVALID", f"{prefix}/{name}")
                local_folded.add(name.casefold())
                relative = f"{prefix}/{name}" if prefix else name
                if not _safe_relative(relative) or relative.casefold() in folded:
                    _fail("TREE_NAMESPACE_INVALID", relative)
                folded.add(relative.casefold())
                try:
                    before = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                except OSError as exc:
                    raise AuthorityError("TREE_SCAN_FAILED", relative) from exc
                if before.st_dev != root_device:
                    _fail("TREE_MOUNT_DRIFT", relative)
                mode = stat.S_IMODE(before.st_mode)
                if stat.S_ISDIR(before.st_mode):
                    try:
                        child_fd = os.open(
                            name, _directory_flags(), dir_fd=directory_fd
                        )
                    except OSError as exc:
                        raise AuthorityError(
                            "TREE_DIRECTORY_INVALID", relative
                        ) from exc
                    try:
                        opened = os.fstat(child_fd)
                        if _identity(opened) != _identity(before):
                            _fail("TREE_NAMESPACE_DRIFT", relative)
                        entries.append(
                            {
                                "path": relative,
                                "type": "directory",
                                "mode": mode,
                                "uid": before.st_uid,
                                "gid": before.st_gid,
                                "size_bytes": 0,
                                "sha256": "",
                            }
                        )
                        visit(child_fd, relative)
                        if _identity(os.fstat(child_fd)) != _identity(opened):
                            _fail("TREE_NAMESPACE_DRIFT", relative)
                    finally:
                        os.close(child_fd)
                elif stat.S_ISREG(before.st_mode):
                    if require_single_link_files and before.st_nlink != 1:
                        _fail("TREE_HARDLINK_ALIAS", relative)
                    try:
                        descriptor = os.open(name, _file_flags(), dir_fd=directory_fd)
                    except OSError as exc:
                        raise AuthorityError("TREE_FILE_INVALID", relative) from exc
                    try:
                        opened = os.fstat(descriptor)
                        if (
                            _identity(opened) != _identity(before)
                            or not stat.S_ISREG(opened.st_mode)
                            or (require_single_link_files and opened.st_nlink != 1)
                        ):
                            _fail("TREE_NAMESPACE_DRIFT", relative)
                        digest, size = _hash_fd(descriptor)
                        if size != before.st_size or _identity(
                            os.fstat(descriptor)
                        ) != _identity(opened):
                            _fail("TREE_NAMESPACE_DRIFT", relative)
                        entries.append(
                            {
                                "path": relative,
                                "type": "file",
                                "mode": mode,
                                "uid": before.st_uid,
                                "gid": before.st_gid,
                                "size_bytes": size,
                                "sha256": digest,
                            }
                        )
                    finally:
                        os.close(descriptor)
                else:
                    _fail("TREE_SPECIAL_NODE", relative)

        visit(root_fd, "")
        entries.sort(key=lambda item: item["path"])
        file_count = sum(item["type"] == "file" for item in entries)
        directory_count = sum(item["type"] == "directory" for item in entries)
        total_bytes = sum(
            item["size_bytes"] for item in entries if item["type"] == "file"
        )
        return TreeSnapshot(
            root=root,
            root_device=root_device,
            entries=tuple(entries),
            tree_digest=_engine_tree_digest(entries),
            projection_sha256=_projection_digest(entries),
            file_count=file_count,
            directory_count=directory_count,
            total_bytes=total_bytes,
        )
    finally:
        os.close(root_fd)


def source_manifest(snapshot: TreeSnapshot) -> dict[str, Any]:
    return seal_document(
        {
            "schema": "vista.r8-ue57-engine-source-manifest/v1",
            "source_root": str(snapshot.root),
            "entries": list(snapshot.entries),
            "tree_root_digest": snapshot.tree_digest,
            "projection": snapshot.projection(),
        }
    )


def _parse_pin(value: Any, label: str) -> FilePin:
    if (
        type(value) is not dict
        or set(value) != {"sha256", "size_bytes"}
        or type(value.get("sha256")) is not str
        or SHA256_RE.fullmatch(value["sha256"]) is None
        or type(value.get("size_bytes")) is not int
        or value["size_bytes"] < 0
    ):
        _fail("PIN_INVALID", label)
    return FilePin(value["sha256"], value["size_bytes"])


def _read_regular(
    path: Path, label: str, *, exact_mode: int | None = None
) -> tuple[bytes, FilePin]:
    try:
        before = os.lstat(path)
        descriptor = os.open(path, _file_flags())
    except OSError as exc:
        raise AuthorityError("FILE_INVALID", label) from exc
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or _identity(opened) != _identity(before)
            or (exact_mode is not None and stat.S_IMODE(opened.st_mode) != exact_mode)
        ):
            _fail("FILE_INVALID", label)
        digest, size = _hash_fd(descriptor)
        if _identity(os.fstat(descriptor)) != _identity(opened):
            _fail("FILE_DRIFT", label)
        os.lseek(descriptor, 0, os.SEEK_SET)
        raw = bytearray()
        while block := os.read(descriptor, CHUNK_BYTES):
            raw.extend(block)
        return bytes(raw), FilePin(digest, size, bool(opened.st_mode & 0o111))
    finally:
        os.close(descriptor)


def load_sealed_document(
    path: Path, schema: str, label: str
) -> tuple[dict[str, Any], FilePin]:
    raw, pin = _read_regular(path, label)
    document = strict_json(raw, label)
    if document.get("schema") != schema or document.get(
        "content_digest"
    ) != content_digest(document):
        _fail("DOCUMENT_INVALID", label)
    return document, pin


def validate_engine_source_pin(
    snapshot: TreeSnapshot, pin_document: Mapping[str, Any]
) -> None:
    manifest = source_manifest(snapshot)
    manifest_raw = canonical_json(manifest)
    expected_keys = {
        "schema",
        "source_root",
        "source_manifest_sha256",
        "source_manifest_size_bytes",
        "source_manifest_content_digest",
        "tree_root_digest",
        "projection",
        "publisher_python_pin",
        "content_digest",
    }
    if (
        set(pin_document) != expected_keys
        or pin_document.get("schema") != ENGINE_SOURCE_PIN_SCHEMA
        or pin_document.get("source_root") != str(ENGINE_SOURCE)
        or pin_document.get("content_digest") != content_digest(pin_document)
        or pin_document.get("source_manifest_sha256")
        != hashlib.sha256(manifest_raw).hexdigest()
        or pin_document.get("source_manifest_size_bytes") != len(manifest_raw)
        or pin_document.get("source_manifest_content_digest")
        != manifest["content_digest"]
        or pin_document.get("tree_root_digest") != snapshot.tree_digest
        or pin_document.get("projection") != snapshot.projection()
    ):
        _fail("ENGINE_SOURCE_REVIEWED_PIN_MISMATCH", str(snapshot.root))
    _pin_path(
        PYTHON_PATH,
        pin_document.get("publisher_python_pin"),
        "publisher Python",
    )


def derive_engine_source_pin(snapshot: TreeSnapshot) -> dict[str, Any]:
    """Return a zero-write review candidate, never a production trust anchor."""

    manifest = source_manifest(snapshot)
    raw = canonical_json(manifest)
    _python_raw, python_pin = _read_regular(PYTHON_PATH, "publisher Python")
    return seal_document(
        {
            "schema": ENGINE_SOURCE_PIN_SCHEMA,
            "source_root": str(ENGINE_SOURCE),
            "source_manifest_sha256": hashlib.sha256(raw).hexdigest(),
            "source_manifest_size_bytes": len(raw),
            "source_manifest_content_digest": manifest["content_digest"],
            "tree_root_digest": snapshot.tree_digest,
            "projection": snapshot.projection(),
            "publisher_python_pin": python_pin.public(),
        }
    )


def _copy_file_fd(source_fd: int, destination_fd: int) -> FilePin:
    digest = hashlib.sha256()
    size = 0
    os.lseek(source_fd, 0, os.SEEK_SET)
    while block := os.read(source_fd, CHUNK_BYTES):
        view = memoryview(block)
        while view:
            written = os.write(destination_fd, view)
            if written <= 0:
                _fail("COPY_FAILED", "short write")
            view = view[written:]
        digest.update(block)
        size += len(block)
    os.fsync(destination_fd)
    return FilePin(digest.hexdigest(), size)


def copy_tree_from_snapshot(
    snapshot: TreeSnapshot,
    destination: Path,
    *,
    owner: tuple[int, int] = (ROOT_UID, ROOT_GID),
) -> None:
    """Copy one already pinned tree without inheriting xattrs, ACLs, or caps."""

    destination.mkdir(mode=0o700)
    os.chown(destination, *owner, follow_symlinks=False)
    destination_fd = os.open(destination, _directory_flags())
    source_fd = os.open(snapshot.root, _directory_flags())
    try:
        destination_fds: dict[str, int] = {".": destination_fd}
        source_fds: dict[str, int] = {".": source_fd}
        try:
            for entry in sorted(
                (item for item in snapshot.entries if item["type"] == "directory"),
                key=lambda item: (len(PurePosixPath(item["path"]).parts), item["path"]),
            ):
                relative = str(entry["path"])
                pure = PurePosixPath(relative)
                parent = pure.parent.as_posix()
                parent = "." if parent == "." else parent
                source_parent = source_fds[parent]
                destination_parent = destination_fds[parent]
                source_child = os.open(
                    pure.name, _directory_flags(), dir_fd=source_parent
                )
                source_child_info = os.fstat(source_child)
                if (
                    source_child_info.st_dev != snapshot.root_device
                    or stat.S_IMODE(source_child_info.st_mode) != entry["mode"]
                    or source_child_info.st_uid != entry["uid"]
                    or source_child_info.st_gid != entry["gid"]
                ):
                    os.close(source_child)
                    _fail("TREE_SOURCE_DRIFT", relative)
                os.mkdir(pure.name, 0o700, dir_fd=destination_parent)
                destination_child = os.open(
                    pure.name, _directory_flags(), dir_fd=destination_parent
                )
                os.fchown(destination_child, *owner)
                source_fds[relative] = source_child
                destination_fds[relative] = destination_child
            for entry in (item for item in snapshot.entries if item["type"] == "file"):
                relative = str(entry["path"])
                pure = PurePosixPath(relative)
                parent = pure.parent.as_posix()
                parent = "." if parent == "." else parent
                source_parent = source_fds[parent]
                destination_parent = destination_fds[parent]
                source_file = os.open(pure.name, _file_flags(), dir_fd=source_parent)
                try:
                    source_info = os.fstat(source_file)
                    if (
                        source_info.st_nlink != 1
                        or source_info.st_dev != snapshot.root_device
                        or stat.S_IMODE(source_info.st_mode) != entry["mode"]
                        or source_info.st_uid != entry["uid"]
                        or source_info.st_gid != entry["gid"]
                        or source_info.st_size != entry["size_bytes"]
                    ):
                        _fail("TREE_SOURCE_DRIFT", relative)
                    destination_file = os.open(
                        pure.name,
                        os.O_WRONLY
                        | os.O_CREAT
                        | os.O_EXCL
                        | os.O_NOFOLLOW
                        | os.O_CLOEXEC,
                        0o600,
                        dir_fd=destination_parent,
                    )
                    try:
                        copied = _copy_file_fd(source_file, destination_file)
                        if (
                            copied.sha256 != entry["sha256"]
                            or copied.size_bytes != entry["size_bytes"]
                            or _identity(os.fstat(source_file))
                            != _identity(source_info)
                        ):
                            _fail("TREE_SOURCE_DRIFT", relative)
                        os.fchown(destination_file, *owner)
                        os.fchmod(
                            destination_file,
                            0o555 if int(entry["mode"]) & 0o111 else 0o444,
                        )
                        os.fsync(destination_file)
                    finally:
                        os.close(destination_file)
                finally:
                    os.close(source_file)
            for relative, descriptor in sorted(
                destination_fds.items(),
                key=lambda item: len(PurePosixPath(item[0]).parts),
                reverse=True,
            ):
                os.fchmod(descriptor, 0o555)
                os.fsync(descriptor)
        finally:
            for relative, descriptor in destination_fds.items():
                if relative != ".":
                    os.close(descriptor)
            for relative, descriptor in source_fds.items():
                if relative != ".":
                    os.close(descriptor)
    finally:
        os.close(source_fd)
        os.close(destination_fd)


def engine_manifest(snapshot: TreeSnapshot) -> dict[str, Any]:
    return seal_document(
        {
            "schema": ENGINE_MANIFEST_SCHEMA,
            "engine_root": str(ENGINE_ROOT),
            "entries": list(snapshot.entries),
            "tree_root_digest": snapshot.tree_digest,
        }
    )


def engine_receipt(
    source_pre: TreeSnapshot,
    source_post: TreeSnapshot,
    source_pin_document: Mapping[str, Any],
    copied: TreeSnapshot,
    manifest_pin: FilePin,
    manifest_content_digest: str,
    publisher_pins: Mapping[str, FilePin],
) -> dict[str, Any]:
    pre_manifest = source_manifest(source_pre)
    post_manifest = source_manifest(source_post)
    by_path = {item["path"]: item for item in copied.entries}
    critical_files: list[dict[str, Any]] = []
    for relative in CRITICAL_ENGINE_FILES:
        item = by_path.get(relative)
        if type(item) is not dict or item.get("type") != "file":
            _fail("ENGINE_CRITICAL_FILE_MISSING", relative)
        critical_files.append(
            {
                "relative_path": relative,
                "sha256": item["sha256"],
                "size_bytes": item["size_bytes"],
                "executable": bool(item["mode"] & 0o111),
            }
        )
    return seal_document(
        {
            "schema": ENGINE_RECEIPT_SCHEMA,
            "status": "root_published_immutable_ue57_engine_authority",
            "accepted": True,
            "authority_root": str(ENGINE_AUTHORITY),
            "manifest": {
                "pin": manifest_pin.public(),
                "content_digest": manifest_content_digest,
            },
            "reviewed_source_manifest": {
                "sha256": source_pin_document["source_manifest_sha256"],
                "size_bytes": source_pin_document["source_manifest_size_bytes"],
                "content_digest": source_pin_document["source_manifest_content_digest"],
                "tree_digest": source_pin_document["tree_root_digest"],
                "projection": source_pin_document["projection"],
            },
            "source_projections": {
                "pre": {
                    "projection": source_pre.projection(),
                    "manifest_sha256": hashlib.sha256(
                        canonical_json(pre_manifest)
                    ).hexdigest(),
                    "manifest_content_digest": pre_manifest["content_digest"],
                },
                "post": {
                    "projection": source_post.projection(),
                    "manifest_sha256": hashlib.sha256(
                        canonical_json(post_manifest)
                    ).hexdigest(),
                    "manifest_content_digest": post_manifest["content_digest"],
                },
            },
            "final_projection": copied.projection(),
            "critical_engine_files": critical_files,
            "publisher": {
                "helper_pin": publisher_pins["helper"].public(),
                "interpreter_pin": publisher_pins["interpreter"].public(),
            },
            "publication_policy": {
                "copy_from_nofollow_descriptors": True,
                "xattrs_acls_caps_inherited": False,
                "source_pre_post_full_projection_equal": True,
                "renameat2_noreplace": True,
                "final_and_parent_fsynced": True,
            },
            "claims": {
                "host_runtime_included": False,
                "buildplugin_included": False,
                "runtime_interaction_verified": False,
                "human_motion_quality_accepted": False,
                "gta_level_quality": False,
            },
        }
    )


def _write_new(path: Path, raw: bytes, mode: int, owner: tuple[int, int]) -> FilePin:
    descriptor = os.open(
        path,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
        0o600,
    )
    try:
        view = memoryview(raw)
        while view:
            written = os.write(descriptor, view)
            if written <= 0:
                _fail("WRITE_FAILED", str(path))
            view = view[written:]
        os.fsync(descriptor)
        os.fchown(descriptor, *owner)
        os.fchmod(descriptor, mode)
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    return FilePin(hashlib.sha256(raw).hexdigest(), len(raw), bool(mode & 0o111))


def rename_noreplace(source: Path, destination: Path) -> None:
    try:
        libc = ctypes.CDLL(None, use_errno=True)
        call = libc.renameat2
    except (AttributeError, OSError) as exc:
        raise AuthorityError("ATOMIC_PUBLISH_UNAVAILABLE", "renameat2") from exc
    call.argtypes = (
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_int,
        ctypes.c_char_p,
        ctypes.c_uint,
    )
    call.restype = ctypes.c_int
    result = call(
        AT_FDCWD,
        os.fsencode(source),
        AT_FDCWD,
        os.fsencode(destination),
        RENAME_NOREPLACE,
    )
    if result != 0:
        observed = ctypes.get_errno()
        code = (
            "FINAL_NOT_FRESH" if observed == errno.EEXIST else "ATOMIC_PUBLISH_FAILED"
        )
        _fail(code, f"renameat2 errno={observed}")


Rename = Callable[[Path, Path], None]


def publish_staging(
    staging: Path, final: Path, *, rename: Rename = rename_noreplace
) -> None:
    if os.path.lexists(final):
        _fail("FINAL_NOT_FRESH", str(final))
    renamed = False
    try:
        rename(staging, final)
        renamed = True
        final_fd = os.open(final, _directory_flags())
        parent_fd = os.open(final.parent, _directory_flags())
        try:
            os.fsync(final_fd)
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
            os.close(final_fd)
    except AuthorityError:
        raise
    except OSError as exc:
        if renamed:
            raise AuthorityError(
                "PUBLISHED_DURABILITY_UNKNOWN",
                f"{final}; audit without retry or deletion",
            ) from exc
        raise AuthorityError("ATOMIC_PUBLISH_FAILED", str(final)) from exc


def _remove_private_staging(path: Path) -> None:
    if not os.path.lexists(path):
        return
    for current, directories, files in os.walk(path, topdown=False, followlinks=False):
        for name in files:
            child = Path(current) / name
            metadata = os.lstat(child)
            if not stat.S_ISREG(metadata.st_mode):
                _fail("STAGING_CLEANUP_FAILED", str(child))
            os.chmod(child, 0o600, follow_symlinks=False)
            child.unlink()
        for name in directories:
            child = Path(current) / name
            metadata = os.lstat(child)
            if not stat.S_ISDIR(metadata.st_mode):
                _fail("STAGING_CLEANUP_FAILED", str(child))
            os.chmod(child, 0o700, follow_symlinks=False)
            child.rmdir()
    os.chmod(path, 0o700, follow_symlinks=False)
    path.rmdir()


def _require_parent(path: Path, *, owner: tuple[int, int] | None = None) -> None:
    owner = (ROOT_UID, ROOT_GID) if owner is None else owner
    metadata = os.lstat(path)
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != owner[0]
        or metadata.st_gid != owner[1]
        or stat.S_IMODE(metadata.st_mode) != 0o555
    ):
        _fail("AUTHORITY_PARENT_INVALID", str(path))


def publish_engine_from_snapshot(
    source: TreeSnapshot,
    source_pin: Mapping[str, Any],
    *,
    final: Path = ENGINE_AUTHORITY,
    owner: tuple[int, int] = (ROOT_UID, ROOT_GID),
    rename: Rename = rename_noreplace,
    publisher_pins: Mapping[str, FilePin] | None = None,
) -> dict[str, Any]:
    validate_engine_source_pin(source, source_pin)
    _require_parent(final.parent, owner=owner)
    if os.path.lexists(final):
        _fail("FINAL_NOT_FRESH", str(final))
    staging = Path(tempfile.mkdtemp(prefix=f".{final.name}.staging-", dir=final.parent))
    os.chown(staging, *owner, follow_symlinks=False)
    try:
        copied_root = staging / "engine"
        copy_tree_from_snapshot(source, copied_root, owner=owner)
        post_source = snapshot_tree(source.root)
        if canonical_json(source_manifest(post_source)) != canonical_json(
            source_manifest(source)
        ):
            _fail("ENGINE_SOURCE_DRIFT", str(source.root))
        copied = snapshot_tree(copied_root)
        if (
            copied.tree_digest != source.tree_digest
            or copied.file_count != source.file_count
            or copied.directory_count != source.directory_count
            or copied.total_bytes != source.total_bytes
        ):
            _fail("ENGINE_COPY_DIFFERS", str(copied_root))
        manifest_document = engine_manifest(copied)
        manifest_raw = canonical_json(manifest_document)
        manifest_pin = _write_new(
            staging / "engine-full-tree-manifest.json", manifest_raw, 0o444, owner
        )
        receipt_document = engine_receipt(
            source,
            post_source,
            source_pin,
            copied,
            manifest_pin,
            manifest_document["content_digest"],
            publisher_pins
            or {
                "helper": FilePin("0" * 64, 0),
                "interpreter": FilePin("0" * 64, 0),
            },
        )
        receipt_pin = _write_new(
            staging / "receipt.json",
            canonical_json(receipt_document),
            0o444,
            owner,
        )
        os.chmod(staging, 0o555, follow_symlinks=False)
        publish_staging(staging, final, rename=rename)
        return {
            "status": "published_immutable_ue57_engine_authority",
            "accepted": True,
            "authority_root": str(final),
            "manifest_pin": manifest_pin.public(),
            "manifest_content_digest": manifest_document["content_digest"],
            "receipt_pin": receipt_pin.public(),
            "receipt_content_digest": receipt_document["content_digest"],
            "tree_digest": copied.tree_digest,
            "source_manifest_sha256": hashlib.sha256(
                canonical_json(source_manifest(source))
            ).hexdigest(),
        }
    finally:
        if os.path.lexists(staging):
            _remove_private_staging(staging)


@dataclasses.dataclass(frozen=True)
class ElfMetadata:
    interpreter: str | None
    needed: tuple[str, ...]
    soname: str | None = None
    rpath: tuple[str, ...] = ()
    runpath: tuple[str, ...] = ()


def parse_readelf_output(raw: str) -> ElfMetadata:
    interpreters = INTERP_RE.findall(raw)
    if len(set(interpreters)) > 1:
        _fail("ELF_METADATA_INVALID", "multiple PT_INTERP values")
    needed = tuple(match.group(1) for match in NEEDED_RE.finditer(raw))
    if len(set(needed)) != len(needed) or any(
        SONAME_RE.fullmatch(item) is None for item in needed
    ):
        _fail("ELF_METADATA_INVALID", "duplicate or unsafe DT_NEEDED")
    interpreter = interpreters[0] if interpreters else None
    if interpreter is not None and (
        not interpreter.startswith("/") or ".." in PurePosixPath(interpreter).parts
    ):
        _fail("ELF_METADATA_INVALID", "unsafe PT_INTERP")
    sonames = SONAME_FIELD_RE.findall(raw)
    if len(set(sonames)) > 1 or any(
        SONAME_RE.fullmatch(item) is None for item in sonames
    ):
        _fail("ELF_METADATA_INVALID", "unsafe or multiple DT_SONAME")

    def dynamic_paths(pattern: re.Pattern[str], label: str) -> tuple[str, ...]:
        matches = pattern.findall(raw)
        if len(matches) > 1:
            _fail("ELF_METADATA_INVALID", f"multiple {label}")
        if not matches or matches == [""]:
            return ()
        values = tuple(matches[0].split(":"))
        if any(not value or "\x00" in value for value in values):
            _fail("ELF_METADATA_INVALID", f"unsafe {label}")
        return values

    return ElfMetadata(
        interpreter,
        needed,
        sonames[0] if sonames else None,
        dynamic_paths(RPATH_RE, "DT_RPATH"),
        dynamic_paths(RUNPATH_RE, "DT_RUNPATH"),
    )


def inspect_elf(
    path: Path,
    *,
    readelf: Path = READELF_PATH,
    readelf_pin: FilePin | None = None,
) -> ElfMetadata:
    if readelf_pin is None:
        _fail("READELF_REVIEWED_PIN_REQUIRED", str(readelf))
    descriptor = os.open(path, _file_flags())
    readelf_descriptor = os.open(readelf, _file_flags())
    try:
        opened = os.fstat(descriptor)
        readelf_opened = os.fstat(readelf_descriptor)
        if not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
            _fail("ELF_INPUT_INVALID", str(path))
        readelf_sha256, readelf_bytes = _hash_fd(readelf_descriptor)
        if (
            not stat.S_ISREG(readelf_opened.st_mode)
            or readelf_opened.st_nlink != 1
            or (readelf_sha256, readelf_bytes)
            != (readelf_pin.sha256, readelf_pin.size_bytes)
        ):
            _fail("READELF_PIN_MISMATCH", str(readelf))
        os.lseek(descriptor, 0, os.SEEK_SET)
        if os.read(descriptor, 4) != b"\x7fELF":
            _fail("ELF_INPUT_INVALID", str(path))
        result = subprocess.run(
            [
                f"/proc/self/fd/{readelf_descriptor}",
                "--wide",
                "--program-headers",
                "--dynamic",
                f"/proc/self/fd/{descriptor}",
            ],
            check=False,
            cwd="/",
            env={"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"},
            pass_fds=(descriptor, readelf_descriptor),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=60,
        )
        if result.returncode != 0 or result.stderr:
            _fail("READELF_FAILED", str(path))
        if _identity(os.fstat(descriptor)) != _identity(opened):
            _fail("ELF_INPUT_DRIFT", str(path))
        if _identity(os.fstat(readelf_descriptor)) != _identity(readelf_opened):
            _fail("READELF_DRIFT", str(readelf))
        return parse_readelf_output(result.stdout)
    finally:
        os.close(readelf_descriptor)
        os.close(descriptor)


def dynamic_search_paths(
    metadata: ElfMetadata,
    *,
    origin: Path,
    defaults: Sequence[Path] = SYSTEM_LIBRARY_DIRECTORIES,
) -> tuple[Path, ...]:
    """Expand deterministic RUNPATH/RPATH ordering without executing an ELF."""

    raw_paths = metadata.runpath or metadata.rpath
    result: list[Path] = []
    for raw in raw_paths:
        expanded = raw.replace("${ORIGIN}", str(origin)).replace("$ORIGIN", str(origin))
        if "$" in expanded:
            _fail("ELF_SEARCH_PATH_INVALID", raw)
        path = Path(expanded)
        if not path.is_absolute():
            _fail("ELF_SEARCH_PATH_INVALID", raw)
        normalized = Path(os.path.normpath(path))
        if normalized not in result:
            result.append(normalized)
    for path in defaults:
        if path not in result:
            result.append(path)
    return tuple(result)


def resolve_elf_closure(
    roots: Iterable[Path],
    *,
    inspect: Callable[[Path], ElfMetadata] = inspect_elf,
    soname_map: Mapping[str, Sequence[Path]],
) -> tuple[Path, ...]:
    queue = list(dict.fromkeys(Path(item) for item in roots))
    resolved: dict[str, Path] = {}
    seen: set[Path] = set()
    while queue:
        current = queue.pop(0)
        canonical = current.resolve(strict=True)
        if canonical in seen:
            continue
        seen.add(canonical)
        metadata = inspect(canonical)
        if metadata.interpreter is not None:
            queue.append(Path(metadata.interpreter))
        for soname in metadata.needed:
            candidates = tuple(
                dict.fromkeys(
                    path.resolve(strict=True) for path in soname_map.get(soname, ())
                )
            )
            if len(candidates) != 1:
                _fail(
                    "ELF_DEPENDENCY_AMBIGUOUS"
                    if candidates
                    else "ELF_DEPENDENCY_MISSING",
                    soname,
                )
            previous = resolved.setdefault(soname, candidates[0])
            if previous != candidates[0]:
                _fail("ELF_DEPENDENCY_AMBIGUOUS", soname)
            queue.append(candidates[0])
    return tuple(sorted(seen, key=str))


@dataclasses.dataclass(frozen=True)
class HeldSourceFile:
    requested_path: Path
    canonical_path: Path
    descriptor: int
    metadata: os.stat_result
    symlink_resolutions: tuple[dict[str, str], ...]


@contextlib.contextmanager
def hold_source_file_components(path: Path) -> Iterable[HeldSourceFile]:
    """Resolve each component with held openat/O_NOFOLLOW descriptors."""

    if not path.is_absolute() or os.path.normpath(path) != str(path):
        _fail("RUNTIME_SOURCE_INVALID", str(path))
    pending = list(path.parts[1:])
    resolutions: list[dict[str, str]] = []
    symlink_count = 0
    held_directories: list[int] = []
    final_descriptor: int | None = None
    try:
        while True:
            for descriptor in reversed(held_directories):
                os.close(descriptor)
            held_directories = [os.open("/", _directory_flags())]
            resolved: list[str] = []
            restart = False
            while pending:
                name = pending.pop(0)
                parent_fd = held_directories[-1]
                before = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
                if stat.S_ISLNK(before.st_mode):
                    target = os.readlink(name, dir_fd=parent_fd)
                    after = os.stat(name, dir_fd=parent_fd, follow_symlinks=False)
                    if _identity(before) != _identity(after):
                        _fail("RUNTIME_SOURCE_COMPONENT_DRIFT", str(path))
                    symlink_count += 1
                    if symlink_count > 40 or not target or "\x00" in target:
                        _fail("RUNTIME_SOURCE_SYMLINK_INVALID", str(path))
                    source_component = Path("/", *resolved, name)
                    target_path = Path(target)
                    if not target_path.is_absolute():
                        target_path = Path("/", *resolved) / target_path
                    combined = target_path.joinpath(*pending)
                    normalized = Path(os.path.normpath(combined))
                    if not normalized.is_absolute():
                        _fail("RUNTIME_SOURCE_SYMLINK_INVALID", str(path))
                    resolutions.append(
                        {
                            "source": str(source_component),
                            "target": target,
                            "normalized_target": str(normalized),
                        }
                    )
                    pending = list(normalized.parts[1:])
                    restart = True
                    break
                if pending:
                    if not stat.S_ISDIR(before.st_mode):
                        _fail("RUNTIME_SOURCE_COMPONENT_INVALID", str(path))
                    descriptor = os.open(name, _directory_flags(), dir_fd=parent_fd)
                    if _identity(os.fstat(descriptor)) != _identity(before):
                        os.close(descriptor)
                        _fail("RUNTIME_SOURCE_COMPONENT_DRIFT", str(path))
                    held_directories.append(descriptor)
                    resolved.append(name)
                    continue
                if not stat.S_ISREG(before.st_mode):
                    _fail("RUNTIME_SOURCE_INVALID", str(path))
                final_descriptor = os.open(name, _file_flags(), dir_fd=parent_fd)
                opened = os.fstat(final_descriptor)
                if _identity(opened) != _identity(before):
                    _fail("RUNTIME_SOURCE_COMPONENT_DRIFT", str(path))
                canonical = Path("/", *resolved, name)
                yield HeldSourceFile(
                    requested_path=path,
                    canonical_path=canonical,
                    descriptor=final_descriptor,
                    metadata=opened,
                    symlink_resolutions=tuple(resolutions),
                )
                return
            if not restart:
                _fail("RUNTIME_SOURCE_INVALID", str(path))
    finally:
        if final_descriptor is not None:
            os.close(final_descriptor)
        for descriptor in reversed(held_directories):
            os.close(descriptor)


def _source_is_forbidden(path: Path) -> bool:
    return path in FORBIDDEN_RUNTIME_SOURCE_FILES or any(
        path == prefix or path.is_relative_to(prefix)
        for prefix in FORBIDDEN_RUNTIME_SOURCE_PREFIXES
    )


def _held_source_record(
    requested: Path,
    destination: PurePosixPath,
    *,
    category: str,
    executable: bool = False,
) -> dict[str, Any]:
    relative = destination.as_posix()
    if not _safe_relative(relative):
        _fail("RUNTIME_DESTINATION_INVALID", relative)
    with hold_source_file_components(requested) as held:
        if _source_is_forbidden(held.canonical_path):
            _fail("RUNTIME_SOURCE_FORBIDDEN", str(requested))
        digest, size = _hash_fd(held.descriptor)
        if _identity(os.fstat(held.descriptor)) != _identity(held.metadata):
            _fail("RUNTIME_SOURCE_DRIFT", str(requested))
        source_mode = stat.S_IMODE(held.metadata.st_mode)
        return {
            "destination": relative,
            "category": category,
            "source": str(requested),
            "source_canonical": str(held.canonical_path),
            "source_identity": {
                "device": held.metadata.st_dev,
                "inode": held.metadata.st_ino,
                "mode": source_mode,
                "uid": held.metadata.st_uid,
                "gid": held.metadata.st_gid,
                "link_count": held.metadata.st_nlink,
                "mtime_ns": held.metadata.st_mtime_ns,
                "ctime_ns": held.metadata.st_ctime_ns,
            },
            "sha256": digest,
            "size_bytes": size,
            "mode": 0o555 if executable else 0o444,
            "symlink_resolutions": list(held.symlink_resolutions),
        }


def _validate_source_record(value: Any, label: str) -> dict[str, Any]:
    keys = {
        "destination",
        "category",
        "source",
        "source_canonical",
        "source_identity",
        "sha256",
        "size_bytes",
        "mode",
        "symlink_resolutions",
    }
    identity_keys = {
        "device",
        "inode",
        "mode",
        "uid",
        "gid",
        "link_count",
        "mtime_ns",
        "ctime_ns",
    }
    if (
        type(value) is not dict
        or set(value) != keys
        or type(value.get("destination")) is not str
        or not _safe_relative(value["destination"])
        or type(value.get("category")) is not str
        or not value["category"]
        or type(value.get("source")) is not str
        or not Path(value["source"]).is_absolute()
        or os.path.normpath(value["source"]) != value["source"]
        or type(value.get("source_canonical")) is not str
        or not Path(value["source_canonical"]).is_absolute()
        or os.path.normpath(value["source_canonical"]) != value["source_canonical"]
        or type(value.get("source_identity")) is not dict
        or set(value["source_identity"]) != identity_keys
        or any(
            type(value["source_identity"][key]) is not int
            or value["source_identity"][key] < 0
            for key in identity_keys
        )
        or type(value.get("sha256")) is not str
        or SHA256_RE.fullmatch(value["sha256"]) is None
        or type(value.get("size_bytes")) is not int
        or value["size_bytes"] < 0
        or value.get("mode") not in (0o444, 0o555)
        or type(value.get("symlink_resolutions")) is not list
    ):
        _fail("RUNTIME_SOURCE_RECORD_INVALID", label)
    for index, item in enumerate(value["symlink_resolutions"]):
        if (
            type(item) is not dict
            or set(item) != {"source", "target", "normalized_target"}
            or any(type(item[key]) is not str or not item[key] for key in item)
            or not Path(item["source"]).is_absolute()
            or not Path(item["normalized_target"]).is_absolute()
        ):
            _fail("RUNTIME_SOURCE_RECORD_INVALID", f"{label}.link[{index}]")
    return dict(value)


def _enumerate_regular_source_tree(
    source_root: Path,
    destination_root: PurePosixPath,
    *,
    category: str,
) -> list[dict[str, Any]]:
    """Hash one fixed tree without following directory symlinks.

    Final-component symlinks are allowed only when the component-held resolver
    reaches one regular file.  The requested destination remains the stable
    lexical name and the final authority receives a new regular file.
    """

    if not source_root.is_absolute() or os.path.normpath(source_root) != str(
        source_root
    ):
        _fail("RUNTIME_SOURCE_TREE_INVALID", str(source_root))
    try:
        before_root = os.lstat(source_root)
        root_fd = os.open(source_root, _directory_flags())
    except OSError as exc:
        raise AuthorityError("RUNTIME_SOURCE_TREE_INVALID", str(source_root)) from exc
    records: list[dict[str, Any]] = []
    folded: set[str] = set()
    try:
        opened_root = os.fstat(root_fd)
        if not stat.S_ISDIR(opened_root.st_mode) or _identity(opened_root) != _identity(
            before_root
        ):
            _fail("RUNTIME_SOURCE_TREE_INVALID", str(source_root))

        def visit(directory_fd: int, relative_parent: PurePosixPath) -> None:
            opened_directory = os.fstat(directory_fd)
            try:
                names = sorted(os.listdir(directory_fd))
            except OSError as exc:
                raise AuthorityError(
                    "RUNTIME_SOURCE_TREE_INVALID", str(source_root)
                ) from exc
            local_folded: set[str] = set()
            for name in names:
                if (
                    not name
                    or "/" in name
                    or name in (".", "..")
                    or unicodedata.normalize("NFC", name) != name
                    or name.casefold() in local_folded
                ):
                    _fail("RUNTIME_SOURCE_NAMESPACE_INVALID", name)
                local_folded.add(name.casefold())
                relative = relative_parent / name
                destination = destination_root / relative
                destination_text = destination.as_posix()
                if (
                    not _safe_relative(destination_text)
                    or destination_text.casefold() in folded
                ):
                    _fail("RUNTIME_SOURCE_NAMESPACE_INVALID", destination_text)
                folded.add(destination_text.casefold())
                try:
                    before = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
                except OSError as exc:
                    raise AuthorityError(
                        "RUNTIME_SOURCE_NAMESPACE_DRIFT", destination_text
                    ) from exc
                if stat.S_ISDIR(before.st_mode):
                    try:
                        child = os.open(name, _directory_flags(), dir_fd=directory_fd)
                    except OSError as exc:
                        raise AuthorityError(
                            "RUNTIME_SOURCE_NAMESPACE_DRIFT", destination_text
                        ) from exc
                    try:
                        if _identity(os.fstat(child)) != _identity(before):
                            _fail("RUNTIME_SOURCE_NAMESPACE_DRIFT", destination_text)
                        visit(child, relative)
                        if _identity(os.fstat(child)) != _identity(before):
                            _fail("RUNTIME_SOURCE_NAMESPACE_DRIFT", destination_text)
                    finally:
                        os.close(child)
                elif stat.S_ISREG(before.st_mode) or stat.S_ISLNK(before.st_mode):
                    records.append(
                        _held_source_record(
                            source_root / relative,
                            destination,
                            category=category,
                        )
                    )
                else:
                    _fail("RUNTIME_SOURCE_SPECIAL_NODE", destination_text)
            if _identity(os.fstat(directory_fd)) != _identity(opened_directory):
                _fail("RUNTIME_SOURCE_NAMESPACE_DRIFT", str(source_root))

        visit(root_fd, PurePosixPath())
        if _identity(os.fstat(root_fd)) != _identity(opened_root):
            _fail("RUNTIME_SOURCE_NAMESPACE_DRIFT", str(source_root))
    finally:
        os.close(root_fd)
    return sorted(records, key=lambda item: item["destination"])


def _projection_from_virtual_files(
    records: Sequence[Mapping[str, Any]], generated: Mapping[str, str]
) -> dict[str, Any]:
    files: dict[str, tuple[str, int, int]] = {}
    for index, value in enumerate(records):
        item = _validate_source_record(value, f"inventory[{index}]")
        relative = item["destination"]
        if relative in files:
            _fail("RUNTIME_DESTINATION_COLLISION", relative)
        files[relative] = (item["sha256"], item["size_bytes"], item["mode"])
    for relative, text in generated.items():
        if not _safe_relative(relative) or type(text) is not str:
            _fail("RUNTIME_GENERATED_ETC_INVALID", relative)
        raw = text.encode("utf-8", "strict")
        if relative in files:
            _fail("RUNTIME_DESTINATION_COLLISION", relative)
        files[relative] = (hashlib.sha256(raw).hexdigest(), len(raw), 0o444)
    directories: set[str] = set()
    for relative in files:
        parent = PurePosixPath(relative).parent
        while parent.as_posix() != ".":
            directories.add(parent.as_posix())
            parent = parent.parent
    entries: list[dict[str, Any]] = [
        {
            "path": relative,
            "type": "directory",
            "mode": 0o555,
            "uid": ROOT_UID,
            "gid": ROOT_GID,
            "size_bytes": 0,
            "sha256": "",
        }
        for relative in sorted(directories)
    ]
    entries.extend(
        {
            "path": relative,
            "type": "file",
            "mode": values[2],
            "uid": ROOT_UID,
            "gid": ROOT_GID,
            "size_bytes": values[1],
            "sha256": values[0],
        }
        for relative, values in sorted(files.items())
    )
    return {
        "tree_digest": _projection_digest(entries),
        "file_count": len(files),
        "directory_count": len(directories) + 1,
        "total_bytes": sum(item[1] for item in files.values()),
    }


def _require_immutable_tree(snapshot: TreeSnapshot, label: str) -> None:
    if any(
        item["uid"] != ROOT_UID
        or item["gid"] != ROOT_GID
        or (item["type"] == "directory" and item["mode"] != 0o555)
        or (item["type"] == "file" and item["mode"] not in (0o444, 0o555))
        for item in snapshot.entries
    ):
        _fail("IMMUTABLE_AUTHORITY_INVALID", label)


def _require_exact_directory(
    path: Path,
    names: set[str],
    label: str,
    *,
    mode: int = 0o555,
    owner: tuple[int, int] | None = None,
) -> None:
    if owner is None:
        owner = (ROOT_UID, ROOT_GID)
    try:
        before = os.lstat(path)
        descriptor = os.open(path, _directory_flags())
    except OSError as exc:
        raise AuthorityError("IMMUTABLE_AUTHORITY_INVALID", label) from exc
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISDIR(opened.st_mode)
            or _identity(opened) != _identity(before)
            or opened.st_uid != owner[0]
            or opened.st_gid != owner[1]
            or stat.S_IMODE(opened.st_mode) != mode
            or set(os.listdir(descriptor)) != names
        ):
            _fail("IMMUTABLE_AUTHORITY_INVALID", label)
    finally:
        os.close(descriptor)


def _load_engine_state() -> dict[str, Any]:
    if os.geteuid() == ROOT_UID:
        audit_existing_engine_authority(fsync=False)
    else:
        _require_exact_directory(
            ENGINE_AUTHORITY,
            {"engine", "engine-full-tree-manifest.json", "receipt.json"},
            "engine authority",
        )
    manifest, manifest_pin = load_sealed_document(
        ENGINE_MANIFEST, ENGINE_MANIFEST_SCHEMA, "engine manifest"
    )
    receipt, receipt_pin = load_sealed_document(
        ENGINE_AUTHORITY / "receipt.json",
        ENGINE_RECEIPT_SCHEMA,
        "engine receipt",
    )
    snapshot = snapshot_tree(ENGINE_ROOT)
    _require_immutable_tree(snapshot, "engine payload")
    if (
        manifest.get("entries") != list(snapshot.entries)
        or manifest.get("tree_root_digest") != snapshot.tree_digest
        or receipt.get("manifest")
        != {
            "pin": manifest_pin.public(),
            "content_digest": manifest["content_digest"],
        }
        or receipt.get("final_projection") != snapshot.projection()
    ):
        _fail("ENGINE_RECONCILIATION_INVALID", "engine state binding")
    return {
        "manifest": manifest,
        "manifest_pin": manifest_pin,
        "receipt": receipt,
        "receipt_pin": receipt_pin,
        "snapshot": snapshot,
    }


_BUILDPLUGIN_NEGATIVE_CLAIMS = {
    "ue_plugin_loaded": False,
    "ue_commandlet_executed": False,
    "animation_runtime_verified": False,
    "pickup_place_verified": False,
    "two_client_verified": False,
    "human_motion_quality_accepted": False,
    "photoreal_character_accepted": False,
    "gta_level_quality": False,
    "private_epic_content_used": False,
}


def _buildplugin_flat_pin(value: Any, label: str) -> FilePin:
    if (
        type(value) is not dict
        or set(value) != {"sha256", "size_bytes"}
        or type(value.get("sha256")) is not str
        or SHA256_RE.fullmatch(value["sha256"]) is None
        or type(value.get("size_bytes")) is not int
        or value["size_bytes"] <= 0
    ):
        _fail("BUILDPLUGIN_AUTHORITY_INVALID", label)
    return FilePin(value["sha256"], value["size_bytes"])


def _validate_buildplugin_publisher(value: Any) -> dict[str, Any]:
    if type(value) is not dict or set(value) != {"helper", "interpreter"}:
        _fail("BUILDPLUGIN_AUTHORITY_INVALID", "publisher fields")
    helper = value.get("helper")
    interpreter = value.get("interpreter")
    for item, path, mode, label in (
        (
            helper,
            BUILDPLUGIN_HELPER_INSTALL_PATH,
            "0500",
            "BuildPlugin publisher helper",
        ),
        (interpreter, PYTHON_PATH, "0755", "BuildPlugin publisher interpreter"),
    ):
        if (
            type(item) is not dict
            or set(item) != {"path", "sha256", "size_bytes", "mode"}
            or item.get("path") != str(path)
            or item.get("mode") != mode
        ):
            _fail("BUILDPLUGIN_AUTHORITY_INVALID", label)
        _buildplugin_flat_pin(
            {"sha256": item.get("sha256"), "size_bytes": item.get("size_bytes")},
            label,
        )
    return {"helper": dict(helper), "interpreter": dict(interpreter)}


def _validate_buildplugin_admin_receipt(
    document: Any,
    *,
    launcher_pin: FilePin,
    publisher: Mapping[str, Any],
    bootstrap_provenance: Mapping[str, Any],
) -> None:
    if type(document) is not dict or set(document) != {
        "schema",
        "status",
        "accepted",
        "authority_root",
        "launcher",
        "helper",
        "interpreter",
        "bootstrap_provenance",
        "claims",
        "content_digest",
    }:
        _fail("BUILDPLUGIN_AUTHORITY_INVALID", "admin receipt fields")
    if (
        document.get("schema") != BUILDPLUGIN_ADMIN_RECEIPT_SCHEMA
        or document.get("status")
        != "root_installed_immutable_buildplugin_admin_authority"
        or document.get("accepted") is not True
        or document.get("authority_root") != str(BUILDPLUGIN_ADMIN_INSTALL_ROOT)
        or document.get("content_digest") != content_digest(document)
        or document.get("launcher")
        != {
            "path": str(BUILDPLUGIN_ADMIN_INSTALL_PATH),
            "pin": launcher_pin.public(),
            "mode": "0500",
        }
        or document.get("helper")
        != {
            "path": str(BUILDPLUGIN_HELPER_INSTALL_PATH),
            "pin": {
                "sha256": publisher["helper"]["sha256"],
                "size_bytes": publisher["helper"]["size_bytes"],
            },
            "mode": "0500",
        }
        or document.get("interpreter")
        != {
            "path": str(PYTHON_PATH),
            "pin": {
                "sha256": publisher["interpreter"]["sha256"],
                "size_bytes": publisher["interpreter"]["size_bytes"],
            },
            "mode": "0755",
        }
        or document.get("bootstrap_provenance") != dict(bootstrap_provenance)
        or document.get("claims")
        != {
            "fresh_no_replace": True,
            "downstream_live_fsync_required": True,
            "admin_launcher_fd_required": True,
            "launcher_receipt_live_bound": True,
        }
    ):
        _fail("BUILDPLUGIN_AUTHORITY_INVALID", "admin receipt binding")


def _validate_buildplugin_admin_publication(
    value: Any, publisher: Mapping[str, Any], *, live: bool
) -> dict[str, Any]:
    if type(value) is not dict or set(value) != {
        "authority_root",
        "authority_mode",
        "launcher",
        "receipt",
        "bootstrap_provenance",
        "admin_launcher_fd_required",
    }:
        _fail("BUILDPLUGIN_AUTHORITY_INVALID", "admin publication fields")
    launcher = value.get("launcher")
    receipt = value.get("receipt")
    bootstrap = value.get("bootstrap_provenance")
    if (
        value.get("authority_root") != str(BUILDPLUGIN_ADMIN_INSTALL_ROOT)
        or value.get("authority_mode") != "0555"
        or value.get("admin_launcher_fd_required") is not True
        or type(launcher) is not dict
        or set(launcher) != {"name", "path", "sha256", "size_bytes", "mode"}
        or launcher.get("name") != BUILDPLUGIN_ADMIN_INSTALL_PATH.name
        or launcher.get("path") != str(BUILDPLUGIN_ADMIN_INSTALL_PATH)
        or launcher.get("mode") != "0500"
        or type(receipt) is not dict
        or set(receipt)
        != {
            "name",
            "path",
            "sha256",
            "size_bytes",
            "mode",
            "schema",
            "content_digest",
        }
        or receipt.get("name") != BUILDPLUGIN_ADMIN_RECEIPT_PATH.name
        or receipt.get("path") != str(BUILDPLUGIN_ADMIN_RECEIPT_PATH)
        or receipt.get("mode") != "0444"
        or receipt.get("schema") != BUILDPLUGIN_ADMIN_RECEIPT_SCHEMA
        or type(receipt.get("content_digest")) is not str
        or SHA256_RE.fullmatch(receipt["content_digest"]) is None
        or type(bootstrap) is not dict
        or set(bootstrap) != {"core_review_audit_pin", "content_digest"}
        or type(bootstrap.get("content_digest")) is not str
        or SHA256_RE.fullmatch(bootstrap["content_digest"]) is None
    ):
        _fail("BUILDPLUGIN_AUTHORITY_INVALID", "admin publication binding")
    launcher_pin = _buildplugin_flat_pin(
        {"sha256": launcher.get("sha256"), "size_bytes": launcher.get("size_bytes")},
        "admin launcher pin",
    )
    receipt_pin = _buildplugin_flat_pin(
        {"sha256": receipt.get("sha256"), "size_bytes": receipt.get("size_bytes")},
        "admin receipt pin",
    )
    _buildplugin_flat_pin(bootstrap.get("core_review_audit_pin"), "core review pin")

    if live:
        _require_exact_directory(
            BUILDPLUGIN_HELPER_INSTALL_ROOT,
            {BUILDPLUGIN_HELPER_INSTALL_PATH.name},
            "BuildPlugin publisher helper authority",
        )
        _helper_raw, observed_helper = _root_file(
            BUILDPLUGIN_HELPER_INSTALL_PATH,
            "BuildPlugin publisher helper",
            0o500,
        )
        _python_raw, observed_python = _root_file(
            PYTHON_PATH,
            "BuildPlugin publisher interpreter",
            0o755,
        )
        if (observed_helper.sha256, observed_helper.size_bytes) != (
            publisher["helper"]["sha256"],
            publisher["helper"]["size_bytes"],
        ) or (observed_python.sha256, observed_python.size_bytes) != (
            publisher["interpreter"]["sha256"],
            publisher["interpreter"]["size_bytes"],
        ):
            _fail(
                "BUILDPLUGIN_AUTHORITY_INVALID",
                "publisher helper or interpreter live pin",
            )
        _require_exact_directory(
            BUILDPLUGIN_ADMIN_INSTALL_ROOT,
            {BUILDPLUGIN_ADMIN_INSTALL_PATH.name, BUILDPLUGIN_ADMIN_RECEIPT_PATH.name},
            "BuildPlugin admin authority",
        )
        _launcher_raw, observed_launcher = _root_file(
            BUILDPLUGIN_ADMIN_INSTALL_PATH, "BuildPlugin admin launcher", 0o500
        )
        receipt_raw, observed_receipt = _root_file(
            BUILDPLUGIN_ADMIN_RECEIPT_PATH, "BuildPlugin admin receipt", 0o444
        )
        if (observed_launcher.sha256, observed_launcher.size_bytes) != (
            launcher_pin.sha256,
            launcher_pin.size_bytes,
        ) or (observed_receipt.sha256, observed_receipt.size_bytes) != (
            receipt_pin.sha256,
            receipt_pin.size_bytes,
        ):
            _fail("BUILDPLUGIN_AUTHORITY_INVALID", "admin publication live pin")
        admin_receipt = strict_json(receipt_raw, "BuildPlugin admin receipt")
        if admin_receipt.get("content_digest") != receipt["content_digest"]:
            _fail("BUILDPLUGIN_AUTHORITY_INVALID", "admin receipt content digest")
        _validate_buildplugin_admin_receipt(
            admin_receipt,
            launcher_pin=launcher_pin,
            publisher=publisher,
            bootstrap_provenance=bootstrap,
        )
    return {
        "authority_root": value["authority_root"],
        "authority_mode": value["authority_mode"],
        "launcher": dict(launcher),
        "receipt": dict(receipt),
        "bootstrap_provenance": {
            "core_review_audit_pin": dict(bootstrap["core_review_audit_pin"]),
            "content_digest": bootstrap["content_digest"],
        },
        "admin_launcher_fd_required": True,
    }


def _load_buildplugin_state() -> dict[str, Any]:
    _require_parent(AUTHORITY_PARENT)
    _require_exact_directory(
        BUILDPLUGIN_AUTHORITY,
        {"payload", "manifest.json", "receipt.json"},
        "BuildPlugin authority",
    )
    payload_info = os.lstat(BUILDPLUGIN_PAYLOAD)
    if (
        not stat.S_ISDIR(payload_info.st_mode)
        or payload_info.st_uid != ROOT_UID
        or payload_info.st_gid != ROOT_GID
        or stat.S_IMODE(payload_info.st_mode) != 0o555
    ):
        _fail("BUILDPLUGIN_AUTHORITY_INVALID", "payload root")
    snapshot = snapshot_tree(BUILDPLUGIN_PAYLOAD)
    _require_immutable_tree(snapshot, "BuildPlugin payload")
    manifest_raw, manifest_pin = _root_file(
        BUILDPLUGIN_AUTHORITY / "manifest.json", "BuildPlugin manifest"
    )
    manifest = strict_json(manifest_raw, "BuildPlugin manifest")
    if (
        set(manifest)
        != {"schema_version", "source", "authority", "critical_files", "entries"}
        or manifest.get("schema_version") != BUILDPLUGIN_MANIFEST_SCHEMA
        or type(manifest.get("source")) is not dict
        or type(manifest.get("authority")) is not dict
        or type(manifest.get("critical_files")) is not list
        or type(manifest.get("entries")) is not list
    ):
        _fail("BUILDPLUGIN_AUTHORITY_INVALID", "manifest contract")
    source = manifest["source"]
    if (
        set(source)
        != {
            "path",
            "projection_sha256",
            "inventory_sha256",
            "file_count",
            "directory_count",
            "total_bytes",
        }
        or source.get("projection_sha256") != snapshot.projection_sha256
        or source.get("file_count") != snapshot.file_count
        or source.get("directory_count") != snapshot.directory_count + 1
        or source.get("total_bytes") != snapshot.total_bytes
        or type(source.get("inventory_sha256")) is not str
        or SHA256_RE.fullmatch(source["inventory_sha256"]) is None
        or manifest["authority"]
        != {
            "root": str(BUILDPLUGIN_AUTHORITY),
            "payload": str(BUILDPLUGIN_PAYLOAD),
            "directory_mode": "0555",
            "file_mode": "0444",
        }
    ):
        _fail("BUILDPLUGIN_AUTHORITY_INVALID", "manifest projection")
    expected_entries: list[dict[str, Any]] = [
        {
            "kind": "directory",
            "path": ".",
            "source_mode": item.get("source_mode", ""),
            "authority_mode": "0555",
        }
        for item in []
    ]
    del expected_entries
    manifest_paths: set[str] = set()
    by_path = {item["path"]: item for item in snapshot.entries}
    for index, item in enumerate(manifest["entries"]):
        if type(item) is not dict or item.get("kind") not in ("directory", "file"):
            _fail("BUILDPLUGIN_AUTHORITY_INVALID", f"manifest entry[{index}]")
        relative = item.get("path")
        if (
            type(relative) is not str
            or (relative != "." and not _safe_relative(relative))
            or relative in manifest_paths
        ):
            _fail("BUILDPLUGIN_AUTHORITY_INVALID", f"manifest path[{index}]")
        manifest_paths.add(relative)
        if item["kind"] == "directory":
            if (
                set(item) != {"kind", "path", "source_mode", "authority_mode"}
                or item.get("authority_mode") != "0555"
                or (
                    relative != "."
                    and by_path.get(relative, {}).get("type") != "directory"
                )
            ):
                _fail("BUILDPLUGIN_AUTHORITY_INVALID", relative)
        else:
            record = by_path.get(relative)
            if (
                set(item)
                != {
                    "kind",
                    "path",
                    "source_mode",
                    "size_bytes",
                    "sha256",
                    "authority_mode",
                }
                or item.get("authority_mode") != "0444"
                or type(record) is not dict
                or record.get("type") != "file"
                or (item.get("sha256"), item.get("size_bytes"))
                != (record["sha256"], record["size_bytes"])
            ):
                _fail("BUILDPLUGIN_AUTHORITY_INVALID", relative)
    expected_paths = {
        ".",
        *(item["path"] for item in snapshot.entries),
    }
    if manifest_paths != expected_paths:
        _fail("BUILDPLUGIN_AUTHORITY_INVALID", "manifest inventory")
    receipt_raw, receipt_pin = _root_file(
        BUILDPLUGIN_AUTHORITY / "receipt.json", "BuildPlugin receipt"
    )
    receipt = strict_json(receipt_raw, "BuildPlugin receipt")
    if receipt.get("schema_version") != BUILDPLUGIN_RECEIPT_SCHEMA or receipt.get(
        "content_digest"
    ) != content_digest(receipt):
        _fail("BUILDPLUGIN_AUTHORITY_INVALID", "receipt seal")
    publisher = _validate_buildplugin_publisher(receipt.get("publisher"))
    admin_publication = _validate_buildplugin_admin_publication(
        receipt.get("admin_publication"),
        publisher,
        live=os.geteuid() == ROOT_UID,
    )
    if (
        set(receipt)
        != {
            "schema_version",
            "accepted",
            "status",
            "source",
            "authority",
            "publisher",
            "admin_publication",
            "policy",
            "claims",
            "content_digest",
        }
        or receipt.get("accepted") is not True
        or receipt.get("status") != "root_published_immutable_buildplugin_authority"
        or receipt.get("source") != source
        or receipt.get("authority")
        != {
            "root": str(BUILDPLUGIN_AUTHORITY),
            "payload": str(BUILDPLUGIN_PAYLOAD),
            "payload_projection_sha256": snapshot.projection_sha256,
            "manifest": {
                "path": "manifest.json",
                "sha256": manifest_pin.sha256,
                "size_bytes": manifest_pin.size_bytes,
            },
            "root_owned_nonwritable": True,
        }
        or receipt.get("publisher") != publisher
        or receipt.get("admin_publication") != admin_publication
        or receipt.get("policy")
        != {
            "copy_from_held_source_descriptors_only": True,
            "all_source_file_descriptors_held": True,
            "source_namespace_revalidated_after_copy": True,
            "fresh_staging_only": True,
            "atomic_publish": "renameat2_noreplace",
            "output_directory_mode": "0555",
            "output_file_mode": "0444",
        }
        or receipt.get("claims") != _BUILDPLUGIN_NEGATIVE_CLAIMS
    ):
        _fail("BUILDPLUGIN_AUTHORITY_INVALID", "receipt contract")
    return {
        "manifest": manifest,
        "manifest_pin": manifest_pin,
        "receipt": receipt,
        "receipt_pin": receipt_pin,
        "snapshot": snapshot,
    }


def _object_record(path: Path, source_kind: str) -> dict[str, Any]:
    raw, pin = _read_regular(path, f"ELF object {path}")
    return {
        "source": str(path),
        "source_canonical": str(path),
        "source_kind": source_kind,
        "sha256": pin.sha256,
        "size_bytes": pin.size_bytes,
        "elf": raw.startswith(b"\x7fELF"),
    }


def _object_from_source_record(value: Mapping[str, Any]) -> dict[str, Any]:
    item = _validate_source_record(value, str(value.get("destination")))
    return {
        "source": item["source"],
        "source_canonical": item["source_canonical"],
        "source_kind": "host-runtime-source",
        "sha256": item["sha256"],
        "size_bytes": item["size_bytes"],
        "elf": True,
    }


def _is_within(path: Path, root: Path) -> bool:
    return path == root or path.is_relative_to(root)


def _source_kind(path: Path) -> str:
    if _is_within(path, ENGINE_ROOT):
        return "engine-authority"
    if _is_within(path, BUILDPLUGIN_PAYLOAD):
        return "buildplugin-authority"
    return "host-runtime-source"


def _allowed_elf_search_directory(path: Path) -> bool:
    normalized = Path(os.path.normpath(path))
    return (
        any(_is_within(normalized, root) for root in (ENGINE_ROOT, BUILDPLUGIN_PAYLOAD))
        or normalized in SYSTEM_LIBRARY_DIRECTORIES
        or any(
            _is_within(normalized, root)
            for root in (PYTHON_STDLIB, *SYSTEM_LIBRARY_DIRECTORIES)
        )
    )


def _record_matches_live_source(record: Mapping[str, Any]) -> bool:
    expected = _validate_source_record(record, str(record.get("destination")))
    actual = _held_source_record(
        Path(expected["source"]),
        PurePosixPath(expected["destination"]),
        category=expected["category"],
        executable=expected["mode"] == 0o555,
    )
    return actual == expected


def _select_host_source(
    records: dict[str, dict[str, Any]],
    requested: Path,
    *,
    category: str,
    executable: bool = False,
) -> dict[str, Any]:
    if not requested.is_absolute() or os.path.normpath(requested) != str(requested):
        _fail("RUNTIME_SOURCE_INVALID", str(requested))
    destination = PurePosixPath(*requested.parts[1:])
    record = _held_source_record(
        requested,
        destination,
        category=category,
        executable=executable,
    )
    previous = records.get(record["destination"])
    if previous is not None and previous != record:
        _fail("RUNTIME_DESTINATION_COLLISION", record["destination"])
    records[record["destination"]] = record
    return record


def _try_dependency_candidate(path: Path) -> dict[str, Any] | None:
    try:
        with hold_source_file_components(path) as held:
            if _source_is_forbidden(held.canonical_path):
                _fail("RUNTIME_SOURCE_FORBIDDEN", str(path))
            digest, size = _hash_fd(held.descriptor)
            if _identity(os.fstat(held.descriptor)) != _identity(held.metadata):
                _fail("RUNTIME_SOURCE_DRIFT", str(path))
            return {
                "requested": str(path),
                "canonical": str(held.canonical_path),
                "sha256": digest,
                "size_bytes": size,
                "symlink_resolutions": list(held.symlink_resolutions),
            }
    except (FileNotFoundError, NotADirectoryError):
        return None


def _elf_seed_objects(
    engine_state: Mapping[str, Any],
    buildplugin_state: Mapping[str, Any],
    selected: Mapping[str, Mapping[str, Any]],
) -> list[dict[str, Any]]:
    seeds: list[dict[str, Any]] = []
    for root, state, kind in (
        (ENGINE_ROOT, engine_state, "engine-authority"),
        (BUILDPLUGIN_PAYLOAD, buildplugin_state, "buildplugin-authority"),
    ):
        snapshot = state["snapshot"]
        for entry in snapshot.entries:
            if entry["type"] != "file":
                continue
            path = root / entry["path"]
            raw, pin = _read_regular(path, f"{kind} file")
            if (pin.sha256, pin.size_bytes) != (
                entry["sha256"],
                entry["size_bytes"],
            ):
                _fail("IMMUTABLE_AUTHORITY_DRIFT", str(path))
            if raw.startswith(b"\x7fELF"):
                seeds.append(_object_record(path, kind))
    for item in selected.values():
        path = Path(item["source_canonical"])
        raw, pin = _read_regular(path, "host runtime source ELF candidate")
        if (pin.sha256, pin.size_bytes) != (item["sha256"], item["size_bytes"]):
            _fail("RUNTIME_SOURCE_DRIFT", str(path))
        if raw.startswith(b"\x7fELF"):
            seeds.append(_object_from_source_record(item))
    by_canonical: dict[str, dict[str, Any]] = {}
    for seed in seeds:
        previous = by_canonical.setdefault(seed["source_canonical"], seed)
        if previous != seed:
            _fail("ELF_SEED_CONFLICT", seed["source_canonical"])
    return sorted(by_canonical.values(), key=lambda item: item["source_canonical"])


def _resolve_runtime_elf_graph(
    seeds: Sequence[Mapping[str, Any]],
    selected: dict[str, dict[str, Any]],
    *,
    readelf_pin: FilePin,
) -> list[dict[str, Any]]:
    queue = [dict(item) for item in seeds]
    seen: dict[str, tuple[str, int]] = {}
    graph: list[dict[str, Any]] = []
    while queue:
        current = queue.pop(0)
        canonical = Path(current["source_canonical"])
        identity = (current["sha256"], current["size_bytes"])
        previous = seen.get(str(canonical))
        if previous is not None:
            if previous != identity:
                _fail("ELF_OBJECT_IDENTITY_CONFLICT", str(canonical))
            continue
        seen[str(canonical)] = identity
        metadata = inspect_elf(canonical, readelf=READELF_PATH, readelf_pin=readelf_pin)
        search_paths = dynamic_search_paths(metadata, origin=canonical.parent)
        if any(not _allowed_elf_search_directory(path) for path in search_paths):
            _fail("ELF_SEARCH_PATH_OUTSIDE_CLOSURE", str(canonical))
        decisions: list[dict[str, Any]] = []

        def enqueue_resolution(
            requested: Path,
            resolved: Mapping[str, Any],
            dependency_kind: str,
        ) -> None:
            resolved_canonical = Path(resolved["canonical"])
            kind = _source_kind(resolved_canonical)
            if kind == "host-runtime-source":
                executable = dependency_kind == "interpreter"
                host_record = _select_host_source(
                    selected,
                    requested,
                    category=(
                        "elf-interpreter" if executable else "elf-shared-library"
                    ),
                    executable=executable,
                )
                queued = _object_from_source_record(host_record)
            else:
                queued = {
                    "source": str(requested),
                    "source_canonical": str(resolved_canonical),
                    "source_kind": kind,
                    "sha256": resolved["sha256"],
                    "size_bytes": resolved["size_bytes"],
                    "elf": True,
                }
            queue.append(queued)

        if metadata.interpreter is not None:
            interpreter_path = Path(metadata.interpreter)
            resolved = _try_dependency_candidate(interpreter_path)
            if resolved is None:
                _fail("ELF_INTERPRETER_MISSING", metadata.interpreter)
            decisions.append(
                {
                    "dependency_kind": "interpreter",
                    "name": metadata.interpreter,
                    "ordered_search": [
                        {
                            "candidate": str(interpreter_path),
                            "result": "selected",
                            "canonical": resolved["canonical"],
                        }
                    ],
                    "selected": dict(resolved),
                }
            )
            enqueue_resolution(interpreter_path, resolved, "interpreter")
        for soname in metadata.needed:
            ordered: list[dict[str, Any]] = []
            selected_resolution: dict[str, Any] | None = None
            selected_path: Path | None = None
            for directory in search_paths:
                candidate = directory / soname
                resolved = _try_dependency_candidate(candidate)
                if resolved is None:
                    ordered.append({"candidate": str(candidate), "result": "not-found"})
                    continue
                ordered.append(
                    {
                        "candidate": str(candidate),
                        "result": "selected",
                        "canonical": resolved["canonical"],
                    }
                )
                selected_resolution = resolved
                selected_path = candidate
                break
            if selected_resolution is None or selected_path is None:
                _fail("ELF_DEPENDENCY_MISSING", f"{canonical}: {soname}")
            decisions.append(
                {
                    "dependency_kind": "needed",
                    "name": soname,
                    "ordered_search": ordered,
                    "selected": dict(selected_resolution),
                }
            )
            enqueue_resolution(selected_path, selected_resolution, "needed")
        graph.append(
            {
                "source": current["source"],
                "source_canonical": str(canonical),
                "source_kind": current["source_kind"],
                "sha256": current["sha256"],
                "size_bytes": current["size_bytes"],
                "metadata": {
                    "interpreter": metadata.interpreter,
                    "needed": list(metadata.needed),
                    "soname": metadata.soname,
                    "rpath": list(metadata.rpath),
                    "runpath": list(metadata.runpath),
                },
                "origin": str(canonical.parent),
                "ordered_search_paths": [str(path) for path in search_paths],
                "resolutions": decisions,
            }
        )
    return sorted(graph, key=lambda item: item["source_canonical"])


def _merge_source_records(
    selected: dict[str, dict[str, Any]], records: Iterable[Mapping[str, Any]]
) -> None:
    for value in records:
        item = _validate_source_record(value, str(value.get("destination")))
        previous = selected.get(item["destination"])
        if previous is not None and previous != item:
            _fail("RUNTIME_DESTINATION_COLLISION", item["destination"])
        selected[item["destination"]] = item


def _authority_binding(
    state: Mapping[str, Any], *, buildplugin: bool
) -> dict[str, Any]:
    snapshot: TreeSnapshot = state["snapshot"]
    manifest: Mapping[str, Any] = state["manifest"]
    receipt: Mapping[str, Any] = state["receipt"]
    return {
        "manifest_pin": state["manifest_pin"].public(),
        "manifest_content_digest": (
            state["manifest_pin"].sha256 if buildplugin else manifest["content_digest"]
        ),
        "receipt_pin": state["receipt_pin"].public(),
        "receipt_content_digest": receipt["content_digest"],
        "payload": snapshot.projection(),
    }


def derive_runtime_input_pin() -> dict[str, Any]:
    """Return the complete externally reviewable runtime input candidate.

    This operation performs no publication.  The returned bytes are not a
    trust anchor until an administrator publishes it as the exact sole pin
    file in ``RUNTIME_INPUT_AUTHORITY``.
    """

    if os.geteuid() == ROOT_UID:
        _fail("UNPRIVILEGED_REVIEW_REQUIRED", "runtime input discovery")
    _require_unprivileged_review_helper()
    engine_state = _load_engine_state()
    buildplugin_state = _load_buildplugin_state()
    selected: dict[str, dict[str, Any]] = {}
    python_record = _select_host_source(
        selected, PYTHON_PATH, category="runtime-tool", executable=True
    )
    bwrap_record = _select_host_source(
        selected, BWRAP_PATH, category="runtime-tool", executable=True
    )
    readelf_record = _select_host_source(
        selected, READELF_PATH, category="publisher-tool", executable=True
    )
    _merge_source_records(
        selected,
        _enumerate_regular_source_tree(
            PYTHON_STDLIB,
            PurePosixPath("usr/lib/python3.10"),
            category="python-stdlib",
        ),
    )
    data_allowlist: list[dict[str, Any]] = []
    for source in RUNTIME_DATA_ALLOWLIST:
        try:
            metadata = os.lstat(source)
        except OSError as exc:
            raise AuthorityError("RUNTIME_DATA_SOURCE_INVALID", str(source)) from exc
        destination = PurePosixPath(*source.parts[1:])
        if stat.S_ISDIR(metadata.st_mode):
            _merge_source_records(
                selected,
                _enumerate_regular_source_tree(
                    source, destination, category="runtime-data"
                ),
            )
            kind = "tree"
        elif stat.S_ISREG(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
            _merge_source_records(
                selected,
                [_held_source_record(source, destination, category="runtime-data")],
            )
            kind = "file"
        else:
            _fail("RUNTIME_DATA_SOURCE_INVALID", str(source))
        data_allowlist.append(
            {
                "source": str(source),
                "destination": destination.as_posix(),
                "kind": kind,
            }
        )
    readelf_pin = FilePin(readelf_record["sha256"], readelf_record["size_bytes"], True)
    seeds = _elf_seed_objects(engine_state, buildplugin_state, selected)
    graph = _resolve_runtime_elf_graph(seeds, selected, readelf_pin=readelf_pin)
    inventory = sorted(selected.values(), key=lambda item: item["destination"])
    symlink_resolutions = sorted(
        (
            {"destination": item["destination"], **resolution}
            for item in inventory
            for resolution in item["symlink_resolutions"]
        ),
        key=lambda item: canonical_json(item),
    )
    executable_destinations = sorted(
        item["destination"] for item in inventory if item["mode"] == 0o555
    )
    return seal_document(
        {
            "schema": RUNTIME_INPUT_PIN_SCHEMA,
            "fixed_paths": {
                "engine_authority": str(ENGINE_AUTHORITY),
                "engine_payload": str(ENGINE_ROOT),
                "buildplugin_authority": str(BUILDPLUGIN_AUTHORITY),
                "buildplugin_payload": str(BUILDPLUGIN_PAYLOAD),
                "runtime_authority": str(HOST_RUNTIME_AUTHORITY),
                "runtime_payload": str(HOST_RUNTIME_PAYLOAD),
                "python_stdlib": str(PYTHON_STDLIB),
            },
            "engine": _authority_binding(engine_state, buildplugin=False),
            "buildplugin": _authority_binding(buildplugin_state, buildplugin=True),
            "tool_pins": {
                "python": {
                    "source": str(PYTHON_PATH),
                    "destination": python_record["destination"],
                    "pin": {
                        "sha256": python_record["sha256"],
                        "size_bytes": python_record["size_bytes"],
                    },
                },
                "bwrap": {
                    "source": str(BWRAP_PATH),
                    "destination": bwrap_record["destination"],
                    "pin": {
                        "sha256": bwrap_record["sha256"],
                        "size_bytes": bwrap_record["size_bytes"],
                    },
                },
                "readelf": {
                    "source": str(READELF_PATH),
                    "destination": readelf_record["destination"],
                    "pin": {
                        "sha256": readelf_record["sha256"],
                        "size_bytes": readelf_record["size_bytes"],
                    },
                },
            },
            "inventory": inventory,
            "symlink_resolutions": symlink_resolutions,
            "elf_seeds": seeds,
            "elf_graph": graph,
            "generated_etc": dict(GENERATED_ETC),
            "data_allowlist": data_allowlist,
            "executable_destinations": executable_destinations,
            "final_projection": _projection_from_virtual_files(
                inventory, GENERATED_ETC
            ),
        }
    )


def build_runtime_input_review_candidate() -> dict[str, Any]:
    """Atomically publish the one-file unprivileged runtime-input candidate."""

    if os.geteuid() == ROOT_UID:
        _fail("UNPRIVILEGED_REVIEW_REQUIRED", "runtime input review candidate")
    _require_unprivileged_review_helper()
    final = RUNTIME_INPUT_REVIEW_CANDIDATE.parent
    if os.path.lexists(final):
        _fail("FINAL_NOT_FRESH", str(final))
    document = derive_runtime_input_pin()
    staging = Path(tempfile.mkdtemp(prefix=f".{final.name}.staging-", dir=final.parent))
    owner = (os.getuid(), os.getgid())
    try:
        pin = _write_new(
            staging / "input-pin.json",
            canonical_json(document),
            0o444,
            owner,
        )
        _seal_private_tree(staging, owner=owner)
        publish_staging(staging, final)
        return {
            "status": "user_published_runtime_input_review_candidate",
            "accepted": False,
            "candidate_root": str(final),
            "input_pin": pin.public(),
            "input_content_digest": document["content_digest"],
            "root_execution_performed": False,
        }
    finally:
        if os.path.lexists(staging):
            _remove_private_staging(staging)


def _validate_publication_binding(value: Any, label: str) -> dict[str, Any]:
    keys = {
        "manifest_pin",
        "manifest_content_digest",
        "receipt_pin",
        "receipt_content_digest",
        "payload",
    }
    projection_keys = {
        "tree_digest",
        "file_count",
        "directory_count",
        "total_bytes",
    }
    if (
        type(value) is not dict
        or set(value) != keys
        or type(value.get("manifest_content_digest")) is not str
        or SHA256_RE.fullmatch(value["manifest_content_digest"]) is None
        or type(value.get("receipt_content_digest")) is not str
        or SHA256_RE.fullmatch(value["receipt_content_digest"]) is None
        or type(value.get("payload")) is not dict
        or set(value["payload"]) != projection_keys
        or type(value["payload"]["tree_digest"]) is not str
        or SHA256_RE.fullmatch(value["payload"]["tree_digest"]) is None
        or any(
            type(value["payload"][key]) is not int or value["payload"][key] < 0
            for key in ("file_count", "directory_count", "total_bytes")
        )
    ):
        _fail("PUBLICATION_BINDING_INVALID", label)
    _parse_pin(value["manifest_pin"], f"{label} manifest")
    _parse_pin(value["receipt_pin"], f"{label} receipt")
    return dict(value)


_ELF_SOURCE_KINDS = {
    "engine-authority",
    "buildplugin-authority",
    "host-runtime-source",
}


def _validate_absolute_normal_path(value: Any, label: str) -> str:
    if (
        type(value) is not str
        or not Path(value).is_absolute()
        or os.path.normpath(value) != value
    ):
        _fail("RUNTIME_ELF_GRAPH_INVALID", label)
    return value


def _validate_elf_name(value: Any, label: str) -> str:
    if (
        type(value) is not str
        or not value
        or value in {".", ".."}
        or "/" in value
        or "\x00" in value
        or any(ord(character) < 0x20 for character in value)
    ):
        _fail("RUNTIME_ELF_GRAPH_INVALID", label)
    return value


def _validate_elf_object_identity(value: Any, label: str) -> dict[str, Any]:
    keys = {
        "source",
        "source_canonical",
        "source_kind",
        "sha256",
        "size_bytes",
    }
    if type(value) is not dict or not keys.issubset(value):
        _fail("RUNTIME_ELF_GRAPH_INVALID", label)
    _validate_absolute_normal_path(value["source"], f"{label}.source")
    _validate_absolute_normal_path(
        value["source_canonical"], f"{label}.source_canonical"
    )
    if value.get("source_kind") not in _ELF_SOURCE_KINDS:
        _fail("RUNTIME_ELF_GRAPH_INVALID", f"{label}.source_kind")
    _parse_pin(
        {"sha256": value.get("sha256"), "size_bytes": value.get("size_bytes")},
        label,
    )
    return dict(value)


def _validate_dependency_resolution(value: Any, label: str) -> dict[str, Any]:
    if (
        type(value) is not dict
        or set(value)
        != {"requested", "canonical", "sha256", "size_bytes", "symlink_resolutions"}
        or type(value.get("symlink_resolutions")) is not list
    ):
        _fail("RUNTIME_ELF_GRAPH_INVALID", label)
    _validate_absolute_normal_path(value["requested"], f"{label}.requested")
    _validate_absolute_normal_path(value["canonical"], f"{label}.canonical")
    _parse_pin(
        {"sha256": value.get("sha256"), "size_bytes": value.get("size_bytes")},
        label,
    )
    for index, item in enumerate(value["symlink_resolutions"]):
        if (
            type(item) is not dict
            or set(item) != {"source", "target", "normalized_target"}
            or type(item.get("target")) is not str
            or not item["target"]
        ):
            _fail("RUNTIME_ELF_GRAPH_INVALID", f"{label}.link[{index}]")
        _validate_absolute_normal_path(
            item.get("source"), f"{label}.link[{index}].source"
        )
        _validate_absolute_normal_path(
            item.get("normalized_target"),
            f"{label}.link[{index}].normalized_target",
        )
    return dict(value)


def _validate_elf_graph(
    seeds_value: Any, graph_value: Any
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    if type(seeds_value) is not list or type(graph_value) is not list:
        _fail("RUNTIME_ELF_GRAPH_INVALID", "top-level lists")
    seeds: list[dict[str, Any]] = []
    for index, value in enumerate(seeds_value):
        if (
            type(value) is not dict
            or set(value)
            != {
                "source",
                "source_canonical",
                "source_kind",
                "sha256",
                "size_bytes",
                "elf",
            }
            or value.get("elf") is not True
        ):
            _fail("RUNTIME_ELF_GRAPH_INVALID", f"seed[{index}]")
        seeds.append(_validate_elf_object_identity(value, f"seed[{index}]"))
    seed_paths = [item["source_canonical"] for item in seeds]
    if seed_paths != sorted(seed_paths) or len(set(seed_paths)) != len(seed_paths):
        _fail("RUNTIME_ELF_GRAPH_INVALID", "seed order")

    graph: list[dict[str, Any]] = []
    graph_by_path: dict[str, dict[str, Any]] = {}
    selected_objects: list[dict[str, Any]] = []
    for index, value in enumerate(graph_value):
        label = f"graph[{index}]"
        if type(value) is not dict or set(value) != {
            "source",
            "source_canonical",
            "source_kind",
            "sha256",
            "size_bytes",
            "metadata",
            "origin",
            "ordered_search_paths",
            "resolutions",
        }:
            _fail("RUNTIME_ELF_GRAPH_INVALID", label)
        item = _validate_elf_object_identity(value, label)
        canonical = Path(item["source_canonical"])
        if value.get("origin") != str(canonical.parent):
            _fail("RUNTIME_ELF_GRAPH_INVALID", f"{label}.origin")
        metadata = value.get("metadata")
        if type(metadata) is not dict or set(metadata) != {
            "interpreter",
            "needed",
            "soname",
            "rpath",
            "runpath",
        }:
            _fail("RUNTIME_ELF_GRAPH_INVALID", f"{label}.metadata")
        interpreter = metadata["interpreter"]
        if interpreter is not None:
            _validate_absolute_normal_path(interpreter, f"{label}.metadata.interpreter")
        for name in metadata["needed"] if type(metadata["needed"]) is list else ():
            _validate_elf_name(name, f"{label}.metadata.needed")
        if type(metadata["needed"]) is not list:
            _fail("RUNTIME_ELF_GRAPH_INVALID", f"{label}.metadata.needed")
        if metadata["soname"] is not None:
            _validate_elf_name(metadata["soname"], f"{label}.metadata.soname")
        if any(
            type(metadata[name]) is not list
            or any(type(entry) is not str for entry in metadata[name])
            for name in ("rpath", "runpath")
        ):
            _fail("RUNTIME_ELF_GRAPH_INVALID", f"{label}.metadata.search")
        expected_search = [
            str(path)
            for path in dynamic_search_paths(
                ElfMetadata(
                    interpreter,
                    tuple(metadata["needed"]),
                    metadata["soname"],
                    tuple(metadata["rpath"]),
                    tuple(metadata["runpath"]),
                ),
                origin=canonical.parent,
            )
        ]
        if value.get("ordered_search_paths") != expected_search or any(
            not _allowed_elf_search_directory(Path(path)) for path in expected_search
        ):
            _fail("RUNTIME_ELF_GRAPH_INVALID", f"{label}.ordered_search_paths")
        dependencies: list[tuple[str, str]] = []
        if interpreter is not None:
            dependencies.append(("interpreter", interpreter))
        dependencies.extend(("needed", name) for name in metadata["needed"])
        resolutions = value.get("resolutions")
        if type(resolutions) is not list or len(resolutions) != len(dependencies):
            _fail("RUNTIME_ELF_GRAPH_INVALID", f"{label}.resolutions")
        for resolution_index, ((kind, name), resolution) in enumerate(
            zip(dependencies, resolutions, strict=True)
        ):
            resolution_label = f"{label}.resolutions[{resolution_index}]"
            if (
                type(resolution) is not dict
                or set(resolution)
                != {"dependency_kind", "name", "ordered_search", "selected"}
                or resolution.get("dependency_kind") != kind
                or resolution.get("name") != name
                or type(resolution.get("ordered_search")) is not list
                or not resolution["ordered_search"]
            ):
                _fail("RUNTIME_ELF_GRAPH_INVALID", resolution_label)
            ordered = resolution["ordered_search"]
            expected_candidates = (
                [interpreter]
                if kind == "interpreter"
                else [str(Path(directory) / name) for directory in expected_search]
            )
            selected_index: int | None = None
            for candidate_index, decision in enumerate(ordered):
                candidate_label = f"{resolution_label}.ordered[{candidate_index}]"
                if (
                    candidate_index >= len(expected_candidates)
                    or type(decision) is not dict
                    or decision.get("candidate") != expected_candidates[candidate_index]
                ):
                    _fail("RUNTIME_ELF_GRAPH_INVALID", candidate_label)
                result = decision.get("result")
                expected_keys = (
                    {"candidate", "result"}
                    if result == "not-found"
                    else {"candidate", "result", "canonical"}
                )
                if set(decision) != expected_keys or result not in {
                    "not-found",
                    "selected",
                }:
                    _fail("RUNTIME_ELF_GRAPH_INVALID", candidate_label)
                if result == "selected":
                    if selected_index is not None:
                        _fail("RUNTIME_ELF_GRAPH_INVALID", candidate_label)
                    selected_index = candidate_index
                    _validate_absolute_normal_path(
                        decision.get("canonical"), f"{candidate_label}.canonical"
                    )
            if (
                selected_index is None
                or selected_index != len(ordered) - 1
                or len(ordered) > len(expected_candidates)
            ):
                _fail("RUNTIME_ELF_GRAPH_INVALID", resolution_label)
            selected = _validate_dependency_resolution(
                resolution["selected"], f"{resolution_label}.selected"
            )
            selected_decision = ordered[selected_index]
            if (
                selected["requested"] != selected_decision["candidate"]
                or selected["canonical"] != selected_decision["canonical"]
            ):
                _fail("RUNTIME_ELF_GRAPH_INVALID", resolution_label)
            selected_objects.append(selected)
        if item["source_canonical"] in graph_by_path:
            _fail("RUNTIME_ELF_GRAPH_INVALID", "duplicate graph object")
        graph.append(item)
        graph_by_path[item["source_canonical"]] = item
    graph_paths = [item["source_canonical"] for item in graph]
    if graph_paths != sorted(graph_paths):
        _fail("RUNTIME_ELF_GRAPH_INVALID", "graph order")
    for seed in seeds:
        graph_item = graph_by_path.get(seed["source_canonical"])
        if graph_item is None or any(
            graph_item[key] != seed[key]
            for key in ("source", "source_kind", "sha256", "size_bytes")
        ):
            _fail("RUNTIME_ELF_GRAPH_INVALID", "seed graph binding")
    for selected in selected_objects:
        graph_item = graph_by_path.get(selected["canonical"])
        if graph_item is None or (graph_item["sha256"], graph_item["size_bytes"]) != (
            selected["sha256"],
            selected["size_bytes"],
        ):
            _fail("RUNTIME_ELF_GRAPH_INVALID", "resolution graph binding")
    return seeds, graph


def validate_runtime_input_pin(document: Mapping[str, Any]) -> None:
    keys = {
        "schema",
        "fixed_paths",
        "engine",
        "buildplugin",
        "tool_pins",
        "inventory",
        "symlink_resolutions",
        "elf_seeds",
        "elf_graph",
        "generated_etc",
        "data_allowlist",
        "executable_destinations",
        "final_projection",
        "content_digest",
    }
    fixed_paths = {
        "engine_authority": str(ENGINE_AUTHORITY),
        "engine_payload": str(ENGINE_ROOT),
        "buildplugin_authority": str(BUILDPLUGIN_AUTHORITY),
        "buildplugin_payload": str(BUILDPLUGIN_PAYLOAD),
        "runtime_authority": str(HOST_RUNTIME_AUTHORITY),
        "runtime_payload": str(HOST_RUNTIME_PAYLOAD),
        "python_stdlib": str(PYTHON_STDLIB),
    }
    if (
        set(document) != keys
        or document.get("schema") != RUNTIME_INPUT_PIN_SCHEMA
        or document.get("content_digest") != content_digest(document)
        or document.get("fixed_paths") != fixed_paths
        or type(document.get("inventory")) is not list
        or type(document.get("symlink_resolutions")) is not list
        or type(document.get("elf_seeds")) is not list
        or type(document.get("elf_graph")) is not list
        or document.get("generated_etc") != GENERATED_ETC
        or type(document.get("data_allowlist")) is not list
        or type(document.get("executable_destinations")) is not list
    ):
        _fail("RUNTIME_INPUT_PIN_INVALID", "closed document")
    _validate_publication_binding(document["engine"], "engine")
    _validate_publication_binding(document["buildplugin"], "BuildPlugin")
    tool_pins = document.get("tool_pins")
    if type(tool_pins) is not dict or set(tool_pins) != {
        "python",
        "bwrap",
        "readelf",
    }:
        _fail("RUNTIME_INPUT_PIN_INVALID", "tool pins")
    expected_tools = {
        "python": PYTHON_PATH,
        "bwrap": BWRAP_PATH,
        "readelf": READELF_PATH,
    }
    for name, path in expected_tools.items():
        item = tool_pins[name]
        if (
            type(item) is not dict
            or set(item) != {"source", "destination", "pin"}
            or item.get("source") != str(path)
            or item.get("destination") != PurePosixPath(*path.parts[1:]).as_posix()
        ):
            _fail("RUNTIME_INPUT_PIN_INVALID", f"tool {name}")
        _parse_pin(item["pin"], f"runtime {name}")
    inventory = [
        _validate_source_record(item, f"inventory[{index}]")
        for index, item in enumerate(document["inventory"])
    ]
    destinations = [item["destination"] for item in inventory]
    if destinations != sorted(destinations) or len(set(destinations)) != len(
        destinations
    ):
        _fail("RUNTIME_INPUT_PIN_INVALID", "inventory order")
    executables = sorted(
        item["destination"] for item in inventory if item["mode"] == 0o555
    )
    if document["executable_destinations"] != executables:
        _fail("RUNTIME_INPUT_PIN_INVALID", "executable allowlist")
    if document["final_projection"] != _projection_from_virtual_files(
        inventory, GENERATED_ETC
    ):
        _fail("RUNTIME_INPUT_PIN_INVALID", "final projection")
    expected_data: list[dict[str, Any]] = []
    for path in RUNTIME_DATA_ALLOWLIST:
        expected_data.append(
            {
                "source": str(path),
                "destination": PurePosixPath(*path.parts[1:]).as_posix(),
                "kind": (
                    "tree"
                    if any(
                        item["destination"].startswith(
                            PurePosixPath(*path.parts[1:]).as_posix() + "/"
                        )
                        for item in inventory
                    )
                    else "file"
                ),
            }
        )
    if document["data_allowlist"] != expected_data:
        _fail("RUNTIME_INPUT_PIN_INVALID", "data allowlist")
    expected_links = sorted(
        (
            {"destination": item["destination"], **resolution}
            for item in inventory
            for resolution in item["symlink_resolutions"]
        ),
        key=canonical_json,
    )
    if document["symlink_resolutions"] != expected_links:
        _fail("RUNTIME_INPUT_PIN_INVALID", "symlink ledger")
    _validate_elf_graph(document["elf_seeds"], document["elf_graph"])


def _load_runtime_input_pin(
    *, review_candidate: bool = False
) -> tuple[dict[str, Any], FilePin]:
    path = (
        RUNTIME_INPUT_REVIEW_CANDIDATE if review_candidate else RUNTIME_INPUT_PIN_PATH
    )
    document, pin = load_sealed_document(
        path, RUNTIME_INPUT_PIN_SCHEMA, "runtime input pin"
    )
    validate_runtime_input_pin(document)
    return document, pin


def _validate_runtime_input_against_live(
    expected: Mapping[str, Any],
) -> dict[str, Any]:
    validate_runtime_input_pin(expected)
    engine_state = _load_engine_state()
    buildplugin_state = _load_buildplugin_state()
    if expected["engine"] != _authority_binding(
        engine_state, buildplugin=False
    ) or expected["buildplugin"] != _authority_binding(
        buildplugin_state, buildplugin=True
    ):
        _fail("RUNTIME_INPUT_REVIEWED_PIN_MISMATCH", "sealed authority differs")
    for index, record in enumerate(expected["inventory"]):
        if not _record_matches_live_source(record):
            _fail("RUNTIME_INPUT_REVIEWED_PIN_MISMATCH", f"source[{index}] differs")
    host_objects: dict[str, set[tuple[str, int]]] = {}
    for record in expected["inventory"]:
        host_objects.setdefault(record["source_canonical"], set()).add(
            (record["sha256"], record["size_bytes"])
        )
    authority_objects: dict[str, dict[str, tuple[str, int]]] = {}
    for kind, root, state in (
        ("engine-authority", ENGINE_ROOT, engine_state),
        ("buildplugin-authority", BUILDPLUGIN_PAYLOAD, buildplugin_state),
    ):
        authority_objects[kind] = {
            str(root / entry["path"]): (entry["sha256"], entry["size_bytes"])
            for entry in state["snapshot"].entries
            if entry["type"] == "file"
        }
    for index, item in enumerate((*expected["elf_seeds"], *expected["elf_graph"])):
        canonical = item["source_canonical"]
        identity = (item["sha256"], item["size_bytes"])
        kind = item["source_kind"]
        matches = (
            identity in host_objects.get(canonical, set())
            if kind == "host-runtime-source"
            else authority_objects.get(kind, {}).get(canonical) == identity
        )
        if not matches:
            _fail(
                "RUNTIME_INPUT_REVIEWED_PIN_MISMATCH",
                f"ELF object[{index}] differs",
            )
    # The independently reviewed input literal already contains the readelf
    # graph.  Privileged operations rehash every graph input but never execute
    # readelf (or any other discovery tool) as root.
    return dict(expected)


def _strict_json_object(raw: bytes, label: str, *, canonical: bool) -> dict[str, Any]:
    if len(raw) > MAX_JSON_BYTES:
        _fail("JSON_INVALID", f"{label} exceeds limit")
    try:
        value = json.loads(
            raw.decode("utf-8", "strict"),
            object_pairs_hook=_pairs,
            parse_constant=lambda token: (_ for _ in ()).throw(
                ValueError(f"nonfinite: {token}")
            ),
        )
    except (UnicodeError, ValueError, TypeError) as exc:
        raise AuthorityError("JSON_INVALID", label) from exc
    if type(value) is not dict or (canonical and canonical_json(value) != raw):
        _fail("JSON_INVALID", label)
    return value


def _load_runtime_state() -> dict[str, Any]:
    if os.geteuid() == ROOT_UID:
        audit_existing_host_runtime_authority(fsync=False)
    else:
        _require_exact_directory(
            HOST_RUNTIME_AUTHORITY,
            {"payload", "manifest.json", "receipt.json"},
            "host runtime authority",
        )
    manifest, manifest_pin = load_sealed_document(
        HOST_RUNTIME_AUTHORITY / "manifest.json",
        HOST_RUNTIME_MANIFEST_SCHEMA,
        "host runtime manifest",
    )
    receipt, receipt_pin = load_sealed_document(
        HOST_RUNTIME_AUTHORITY / "receipt.json",
        HOST_RUNTIME_RECEIPT_SCHEMA,
        "host runtime receipt",
    )
    snapshot = snapshot_tree(HOST_RUNTIME_PAYLOAD)
    _require_immutable_tree(snapshot, "host runtime payload")
    _validate_runtime_manifest(snapshot, manifest)
    if (
        receipt.get("manifest_pin") != manifest_pin.public()
        or receipt.get("manifest_content_digest") != manifest["content_digest"]
        or receipt.get("payload") != snapshot.projection()
    ):
        _fail("HOST_RUNTIME_AUTHORITY_INVALID", "runtime state binding")
    return {
        "manifest": manifest,
        "manifest_pin": manifest_pin,
        "receipt": receipt,
        "receipt_pin": receipt_pin,
        "snapshot": snapshot,
    }


def _load_r3_binding() -> dict[str, Any]:
    raw, receipt_pin = _read_regular(R3_RECEIPT_PATH, "R3 receipt")
    receipt = _strict_json_object(raw, "R3 receipt", canonical=False)
    snapshot = snapshot_tree(R3_PROJECT_ROOT)
    projection = {
        "tree_digest": snapshot.projection_sha256,
        "file_count": snapshot.file_count,
        "directory_count": snapshot.directory_count + 1,
        "total_bytes": snapshot.total_bytes,
    }
    expected_projection = {
        "sha256": projection["tree_digest"],
        "file_count": projection["file_count"],
        "directory_count": projection["directory_count"],
        "total_bytes": projection["total_bytes"],
    }
    if (
        receipt.get("schema_version")
        != "vista.makehuman-cc0-ue57-import-host-receipt/v1"
        or receipt.get("status") != "cc0_skeletal_import_post_exit_project_sealed"
        or receipt.get("accepted") is not False
        or receipt.get("content_digest") != content_digest(receipt)
        or receipt.get("output_project_projection") != expected_projection
    ):
        _fail("R3_AUTHORITY_INVALID", "receipt/project binding")
    return {
        "receipt_pin": receipt_pin.public(),
        "receipt_content_digest": receipt["content_digest"],
        "project": projection,
    }


def _load_r8_binding() -> dict[str, Any]:
    authority_info = os.lstat(R8_AUTHORITY)
    if (
        not stat.S_ISDIR(authority_info.st_mode)
        or authority_info.st_uid != ROOT_UID
        or authority_info.st_gid != ROOT_GID
        or stat.S_IMODE(authority_info.st_mode) != 0o555
    ):
        _fail("R8_AUTHORITY_INVALID", "root")
    raw, receipt_pin = _root_file(R8_RECEIPT_PATH, "R8 receipt")
    receipt = strict_json(raw, "R8 receipt")
    if (
        receipt.get("schema_version") != "vista.makehuman-cc0-animation-host-receipt/v1"
        or receipt.get("status")
        != "blender_stage_sealed_pending_ue_import_runtime_and_human_review"
        or receipt.get("accepted") is not False
        or receipt.get("content_digest") != content_digest(receipt)
        or type(receipt.get("artifacts")) is not list
    ):
        _fail("R8_AUTHORITY_INVALID", "receipt")
    by_path = {
        item.get("relative_path"): item
        for item in receipt["artifacts"]
        if type(item) is dict
    }
    expected_artifacts = {
        *R8_FBX_RELATIVE_PATHS,
        "library/vista_cc0_animation_library_r8.blend",
    }
    if set(by_path) != expected_artifacts or len(by_path) != len(receipt["artifacts"]):
        _fail("R8_AUTHORITY_INVALID", "artifact inventory")
    fbx_records: list[dict[str, Any]] = []
    for relative in R8_FBX_RELATIVE_PATHS:
        path = R8_AUTHORITY / "artifacts" / relative
        _raw, pin = _root_file(path, f"R8 {relative}")
        expected = {
            "relative_path": relative,
            "sha256": pin.sha256,
            "size_bytes": pin.size_bytes,
        }
        if by_path[relative] != expected:
            _fail("R8_AUTHORITY_INVALID", relative)
        fbx_records.append(expected)
    return {
        "attempt_name": R8_ATTEMPT_NAME,
        "receipt_pin": receipt_pin.public(),
        "receipt_content_digest": receipt["content_digest"],
        "fbx_files": fbx_records,
    }


def _parse_reviewed_git_tree(
    raw: bytes, expected_paths: Sequence[str]
) -> dict[str, str]:
    if not raw or not raw.endswith(b"\0"):
        _fail("GIT_SOURCE_INVALID", "commit tree framing")
    result: dict[str, str] = {}
    observed_order: list[str] = []
    for record in raw[:-1].split(b"\0"):
        metadata, separator, path_raw = record.partition(b"\t")
        fields = metadata.split(b" ")
        if separator != b"\t" or len(fields) != 3:
            _fail("GIT_SOURCE_INVALID", "commit tree record")
        mode, object_type, oid = fields
        try:
            path = path_raw.decode("utf-8", "strict")
            oid_text = oid.decode("ascii", "strict")
        except UnicodeDecodeError as exc:
            raise AuthorityError("GIT_SOURCE_INVALID", "commit tree encoding") from exc
        if (
            mode not in {b"100644", b"100755"}
            or object_type != b"blob"
            or re.fullmatch(r"[0-9a-f]{40}", oid_text) is None
            or not path
            or "\0" in path
            or path in result
        ):
            _fail("GIT_SOURCE_INVALID", f"commit tree entry: {path!r}")
        result[path] = oid_text
        observed_order.append(path)
    if observed_order != sorted(expected_paths) or set(result) != set(expected_paths):
        _fail("GIT_SOURCE_INVALID", "commit tree inventory")
    return result


def _git_source_binding(
    *, return_committed_sources: bool = False
) -> dict[str, Any] | tuple[dict[str, Any], dict[str, bytes]]:
    git_path = Path("/usr/bin/git")
    source_paths = [
        *BUNDLE_SOURCE_PATHS.values(),
        LAUNCHER_SOURCE,
        REVIEW_HELPER_SOURCE,
        ADMIN_LAUNCHER_SOURCE,
        STAGE_INSTALLER_SOURCE,
        STAGE_TRANSFER_LAUNCHER_SOURCE,
        ENGINE_WRAPPER_SOURCE,
        BUILDPLUGIN_HELPER_SOURCE,
        PARENT_SEAL_HELPER_SOURCE,
        PARENT_SEAL_LAUNCHER_SOURCE,
        INITIAL_BOOTSTRAP_HELPER_SOURCE,
        INITIAL_BOOTSTRAP_INSTALLER_SOURCE,
        INITIAL_BOOTSTRAP_LAUNCHER_SOURCE,
    ]
    relative_paths = _reviewed_git_relative_paths()
    by_relative = {
        path.relative_to(CHECKOUT_ROOT).as_posix(): path for path in source_paths
    }
    committed_sources: dict[str, bytes] = {}
    with hold_source_file_components(git_path) as held:
        git_sha, git_bytes = _hash_fd(held.descriptor)
        os.lseek(held.descriptor, 0, os.SEEK_SET)
        if os.read(held.descriptor, 4) != b"\x7fELF":
            _fail("GIT_SOURCE_INVALID", str(git_path))
        git_pin = FilePin(git_sha, git_bytes, True)

        def run_git(
            arguments: Sequence[str], *, text: bool
        ) -> subprocess.CompletedProcess[Any]:
            git_environment = {
                "PATH": "/usr/bin:/bin",
                "HOME": "/nonexistent",
                "XDG_CONFIG_HOME": "/nonexistent",
                "LANG": "C",
                "LC_ALL": "C",
                "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_CONFIG_GLOBAL": "/dev/null",
                "GIT_CONFIG_COUNT": "0",
                "GIT_NO_REPLACE_OBJECTS": "1",
                "GIT_ATTR_NOSYSTEM": "1",
                "GIT_CEILING_DIRECTORIES": str(CHECKOUT_ROOT.parent),
                "GIT_DISCOVERY_ACROSS_FILESYSTEM": "0",
                "GIT_TERMINAL_PROMPT": "0",
                "GIT_OPTIONAL_LOCKS": "0",
                "GIT_PAGER": "cat",
            }
            return subprocess.run(
                [str(git_path), "-C", str(CHECKOUT_ROOT), *arguments],
                executable=f"/proc/self/fd/{held.descriptor}",
                check=False,
                cwd="/",
                env=git_environment,
                pass_fds=(held.descriptor,),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=text,
                timeout=30,
            )

        commit = run_git(["rev-parse", "--verify", "HEAD^{commit}"], text=True)
        if (
            commit.returncode != 0
            or commit.stderr
            or re.fullmatch(r"[0-9a-f]{40}\n", commit.stdout) is None
        ):
            _fail("GIT_SOURCE_INVALID", "commit")
        commit_id = commit.stdout.strip()
        tree = run_git(
            [
                "ls-tree",
                "-r",
                "-z",
                "--full-tree",
                commit_id,
                "--",
                *relative_paths,
            ],
            text=False,
        )
        if tree.returncode != 0 or tree.stderr:
            _fail("GIT_SOURCE_INVALID", "commit tree")
        tree_oids = _parse_reviewed_git_tree(tree.stdout, relative_paths)
        for relative in relative_paths:
            path = by_relative[relative]
            committed = run_git(["cat-file", "blob", tree_oids[relative]], text=False)
            live_raw, _live_pin = _read_regular(path, f"Git source {relative}")
            if (
                committed.returncode != 0
                or committed.stderr
                or committed.stdout != live_raw
            ):
                _fail("GIT_SOURCE_INVALID", f"source differs from commit: {relative}")
            committed_sources[relative] = committed.stdout
        if _identity(os.fstat(held.descriptor)) != _identity(held.metadata):
            _fail("GIT_SOURCE_INVALID", "Git executable drift")
    binding = {
        "checkout_root": str(CHECKOUT_ROOT),
        "commit": commit_id,
        "git_canonical": str(held.canonical_path),
        "git_pin": git_pin.public(),
        "tracked_paths": sorted(relative_paths),
    }
    if return_committed_sources:
        return binding, committed_sources
    return binding


def _reviewed_git_relative_paths() -> list[str]:
    paths = [
        *BUNDLE_SOURCE_PATHS.values(),
        LAUNCHER_SOURCE,
        REVIEW_HELPER_SOURCE,
        ADMIN_LAUNCHER_SOURCE,
        STAGE_INSTALLER_SOURCE,
        STAGE_TRANSFER_LAUNCHER_SOURCE,
        ENGINE_WRAPPER_SOURCE,
        BUILDPLUGIN_HELPER_SOURCE,
        PARENT_SEAL_HELPER_SOURCE,
        PARENT_SEAL_LAUNCHER_SOURCE,
        INITIAL_BOOTSTRAP_HELPER_SOURCE,
        INITIAL_BOOTSTRAP_INSTALLER_SOURCE,
        INITIAL_BOOTSTRAP_LAUNCHER_SOURCE,
    ]
    try:
        return sorted(path.relative_to(CHECKOUT_ROOT).as_posix() for path in paths)
    except ValueError as exc:
        raise AuthorityError("GIT_SOURCE_INVALID", "source outside checkout") from exc


def _require_unprivileged_review_binding() -> tuple[dict[str, Any], dict[str, bytes]]:
    if (
        os.geteuid() != REVIEW_UID
        or os.getegid() != REVIEW_GID
        or Path(os.path.abspath(__file__)) != REVIEW_HELPER_SOURCE
        or str(REVIEW_HELPER_SOURCE).startswith("/root/")
    ):
        _fail("UNPRIVILEGED_REVIEW_REQUIRED", str(REVIEW_HELPER_SOURCE))
    # Held-FD Git execution is confined to the non-root review phase and proves
    # the helper, wrapper, launcher, and final bundle sources all equal HEAD.
    binding, committed_sources = _git_source_binding(return_committed_sources=True)
    if binding["tracked_paths"] != sorted(committed_sources):
        _fail("GIT_SOURCE_INVALID", "committed source inventory")
    return binding, committed_sources


def _require_unprivileged_review_helper() -> dict[str, bytes]:
    return _require_unprivileged_review_binding()[1]


def _runtime_executable_binding() -> dict[str, Any]:
    paths = {
        "python": HOST_RUNTIME_PAYLOAD / "usr/bin/python3.10",
        "bwrap": HOST_RUNTIME_PAYLOAD / "usr/bin/bwrap",
        "loader": HOST_RUNTIME_PAYLOAD / "lib64/ld-linux-x86-64.so.2",
    }
    result: dict[str, Any] = {}
    for name, path in paths.items():
        _raw, pin = _root_file(path, f"runtime {name}", 0o555)
        result[name] = {"path": str(path), "pin": pin.public()}
    return result


def _source_pins() -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for name, path in {
        **BUNDLE_SOURCE_PATHS,
        LAUNCHER_SOURCE.name: LAUNCHER_SOURCE,
    }.items():
        _raw, pin = _read_regular(path, f"bundle source {name}")
        result[name] = {"path": str(path), "pin": pin.public()}
    return result


def _launcher_build_spec(
    source_pins: Mapping[str, Mapping[str, Any]],
    runtime_executables: Mapping[str, Any],
) -> dict[str, Any]:
    with hold_source_file_components(COMPILER_PATH) as held:
        compiler_sha, compiler_bytes = _hash_fd(held.descriptor)
        if _identity(os.fstat(held.descriptor)) != _identity(held.metadata):
            _fail("COMPILER_DRIFT", str(COMPILER_PATH))
        compiler_driver_pin = {
            "sha256": compiler_sha,
            "size_bytes": compiler_bytes,
        }
        compiler_canonical = str(held.canonical_path)
    toolchain_artifact_ledger: list[dict[str, Any]] = []
    for path in COMPILER_TOOLCHAIN_ARTIFACTS:
        with hold_source_file_components(path) as held:
            digest, size = _hash_fd(held.descriptor)
            if _identity(os.fstat(held.descriptor)) != _identity(held.metadata):
                _fail("COMPILER_DRIFT", str(path))
            toolchain_artifact_ledger.append(
                {
                    "path": str(path),
                    "canonical": str(held.canonical_path),
                    "pin": {"sha256": digest, "size_bytes": size},
                }
            )
    loader = runtime_executables["loader"]
    python = runtime_executables["python"]
    return {
        "compiler_path": str(COMPILER_PATH),
        "compiler_canonical": compiler_canonical,
        "compiler_driver_pin": compiler_driver_pin,
        "toolchain_artifact_ledger": toolchain_artifact_ledger,
        "source_path": str(LAUNCHER_SOURCE),
        "source_pin": source_pins[LAUNCHER_SOURCE.name]["pin"],
        "flags": [
            "-std=c11",
            "-O2",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-static",
            "-s",
            "-Wl,--build-id=none",
            "-x",
            "c",
        ],
        "defines": {
            "REVIEWED_ATTEMPT_NAME": APPROVED_ATTEMPT_NAME,
            "REVIEWED_LIBRARY_PATH": ":".join(
                str(HOST_RUNTIME_PAYLOAD / relative)
                for relative in HOST_LIBRARY_RELATIVE_PATHS
            ),
            "REVIEWED_LOADER_BYTES": loader["pin"]["size_bytes"],
            "REVIEWED_LOADER_PATH": loader["path"],
            "REVIEWED_LOADER_SHA256": loader["pin"]["sha256"],
            "REVIEWED_PYTHON_BYTES": python["pin"]["size_bytes"],
            "REVIEWED_PYTHON_PATH": python["path"],
            "REVIEWED_PYTHON_SHA256": python["pin"]["sha256"],
        },
        "environment": {
            "PATH": "/usr/bin:/bin",
            "LANG": "C",
            "LC_ALL": "C",
            "SOURCE_DATE_EPOCH": "0",
        },
    }


def _validate_launcher_build_spec(value: Any) -> dict[str, Any]:
    if (
        type(value) is not dict
        or set(value)
        != {
            "compiler_path",
            "compiler_canonical",
            "compiler_driver_pin",
            "toolchain_artifact_ledger",
            "source_path",
            "source_pin",
            "flags",
            "defines",
            "environment",
        }
        or value.get("compiler_path") != str(COMPILER_PATH)
        or type(value.get("compiler_canonical")) is not str
        or not Path(value["compiler_canonical"]).is_absolute()
        or value.get("source_path") != str(LAUNCHER_SOURCE)
        or value.get("flags")
        != [
            "-std=c11",
            "-O2",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-static",
            "-s",
            "-Wl,--build-id=none",
            "-x",
            "c",
        ]
        or value.get("environment")
        != {
            "PATH": "/usr/bin:/bin",
            "LANG": "C",
            "LC_ALL": "C",
            "SOURCE_DATE_EPOCH": "0",
        }
    ):
        _fail("LAUNCHER_BUILD_SPEC_INVALID", "closed fields")
    _parse_pin(value["compiler_driver_pin"], "launcher compiler driver")
    ledger = value["toolchain_artifact_ledger"]
    if type(ledger) is not list or len(ledger) != len(COMPILER_TOOLCHAIN_ARTIFACTS):
        _fail("LAUNCHER_BUILD_SPEC_INVALID", "toolchain artifact ledger")
    for expected_path, item in zip(COMPILER_TOOLCHAIN_ARTIFACTS, ledger, strict=True):
        if (
            type(item) is not dict
            or set(item) != {"path", "canonical", "pin"}
            or item.get("path") != str(expected_path)
            or type(item.get("canonical")) is not str
            or not Path(item["canonical"]).is_absolute()
        ):
            _fail("LAUNCHER_BUILD_SPEC_INVALID", str(expected_path))
        _parse_pin(item["pin"], f"toolchain {expected_path}")
    _parse_pin(value["source_pin"], "launcher source")
    defines = value.get("defines")
    if type(defines) is not dict or set(defines) != {
        "REVIEWED_ATTEMPT_NAME",
        "REVIEWED_LIBRARY_PATH",
        "REVIEWED_LOADER_BYTES",
        "REVIEWED_LOADER_PATH",
        "REVIEWED_LOADER_SHA256",
        "REVIEWED_PYTHON_BYTES",
        "REVIEWED_PYTHON_PATH",
        "REVIEWED_PYTHON_SHA256",
    }:
        _fail("LAUNCHER_BUILD_SPEC_INVALID", "defines")
    for key in ("REVIEWED_LOADER_SHA256", "REVIEWED_PYTHON_SHA256"):
        if type(defines[key]) is not str or SHA256_RE.fullmatch(defines[key]) is None:
            _fail("LAUNCHER_BUILD_SPEC_INVALID", key)
    for key in ("REVIEWED_LOADER_BYTES", "REVIEWED_PYTHON_BYTES"):
        if type(defines[key]) is not int or defines[key] < 0:
            _fail("LAUNCHER_BUILD_SPEC_INVALID", key)
    if (
        defines["REVIEWED_ATTEMPT_NAME"] != APPROVED_ATTEMPT_NAME
        or defines["REVIEWED_LOADER_PATH"]
        != str(HOST_RUNTIME_PAYLOAD / "lib64/ld-linux-x86-64.so.2")
        or defines["REVIEWED_PYTHON_PATH"]
        != str(HOST_RUNTIME_PAYLOAD / "usr/bin/python3.10")
        or defines["REVIEWED_LIBRARY_PATH"]
        != ":".join(
            str(HOST_RUNTIME_PAYLOAD / relative)
            for relative in HOST_LIBRARY_RELATIVE_PATHS
        )
    ):
        _fail("LAUNCHER_BUILD_SPEC_INVALID", "literal values")
    return dict(value)


def _compile_launcher(build: Mapping[str, Any], output: Path) -> FilePin:
    if os.geteuid() == ROOT_UID:
        _fail("UNPRIVILEGED_REVIEW_REQUIRED", "launcher compilation")
    spec = _validate_launcher_build_spec(build)
    for item in spec["toolchain_artifact_ledger"]:
        with hold_source_file_components(Path(item["path"])) as held:
            digest, size = _hash_fd(held.descriptor)
            if (
                str(held.canonical_path) != item["canonical"]
                or (digest, size) != (item["pin"]["sha256"], item["pin"]["size_bytes"])
                or _identity(os.fstat(held.descriptor)) != _identity(held.metadata)
            ):
                _fail("LAUNCHER_BUILD_INPUT_DRIFT", item["path"])
    with (
        hold_source_file_components(COMPILER_PATH) as compiler,
        hold_source_file_components(LAUNCHER_SOURCE) as source,
    ):
        compiler_sha, compiler_bytes = _hash_fd(compiler.descriptor)
        source_sha, source_bytes = _hash_fd(source.descriptor)
        if (compiler_sha, compiler_bytes) != (
            spec["compiler_driver_pin"]["sha256"],
            spec["compiler_driver_pin"]["size_bytes"],
        ) or (source_sha, source_bytes) != (
            spec["source_pin"]["sha256"],
            spec["source_pin"]["size_bytes"],
        ):
            _fail("LAUNCHER_BUILD_INPUT_DRIFT", "compiler/source")
        defines: list[str] = []
        for name, value in sorted(spec["defines"].items()):
            if type(value) is int:
                defines.append(f"-D{name}={value}")
            else:
                escaped = value.replace("\\", "\\\\").replace('"', '\\"')
                defines.append(f'-D{name}="{escaped}"')
        command = [
            str(COMPILER_PATH),
            *spec["flags"],
            *defines,
            f"/proc/self/fd/{source.descriptor}",
            "-o",
            str(output),
        ]
        result = subprocess.run(
            command,
            executable=f"/proc/self/fd/{compiler.descriptor}",
            check=False,
            cwd="/",
            env=spec["environment"],
            pass_fds=(compiler.descriptor, source.descriptor),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=120,
        )
        if result.returncode != 0 or result.stdout or result.stderr:
            _fail("LAUNCHER_BUILD_FAILED", result.stderr.strip() or "compiler output")
        if _identity(os.fstat(compiler.descriptor)) != _identity(
            compiler.metadata
        ) or _identity(os.fstat(source.descriptor)) != _identity(source.metadata):
            _fail("LAUNCHER_BUILD_INPUT_DRIFT", "compiler/source")
    raw, pin = _read_regular(output, "launcher output")
    if not raw.startswith(b"\x7fELF"):
        _fail("LAUNCHER_BUILD_FAILED", "output is not ELF")
    return FilePin(pin.sha256, pin.size_bytes, True)


def _review_toolchain_artifact_pins() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in COMPILER_TOOLCHAIN_ARTIFACTS:
        with hold_source_file_components(path) as held:
            digest, size = _hash_fd(held.descriptor)
            if _identity(os.fstat(held.descriptor)) != _identity(held.metadata):
                _fail("COMPILER_DRIFT", str(path))
            records.append(
                {
                    "path": str(path),
                    "canonical": str(held.canonical_path),
                    "pin": {"sha256": digest, "size_bytes": size},
                }
            )
    return records


@contextlib.contextmanager
def _sealed_source_memfd(raw: bytes, label: str) -> Iterable[int]:
    required = (
        "memfd_create",
        "MFD_CLOEXEC",
        "MFD_ALLOW_SEALING",
    )
    if any(not hasattr(os, name) for name in required) or any(
        not hasattr(fcntl, name)
        for name in (
            "F_ADD_SEALS",
            "F_SEAL_SEAL",
            "F_SEAL_SHRINK",
            "F_SEAL_GROW",
            "F_SEAL_WRITE",
        )
    ):
        _fail("PLATFORM_UNSUPPORTED", "sealed memfd required")
    descriptor = os.memfd_create(
        label,
        flags=os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING,
    )
    try:
        offset = 0
        while offset < len(raw):
            written = os.write(descriptor, raw[offset:])
            if written <= 0:
                _fail("ADMIN_LAUNCHER_BUILD_INPUT_DRIFT", label)
            offset += written
        os.fchmod(descriptor, 0o400)
        fcntl.fcntl(
            descriptor,
            fcntl.F_ADD_SEALS,
            fcntl.F_SEAL_SEAL
            | fcntl.F_SEAL_SHRINK
            | fcntl.F_SEAL_GROW
            | fcntl.F_SEAL_WRITE,
        )
        os.lseek(descriptor, 0, os.SEEK_SET)
        yield descriptor
    finally:
        os.close(descriptor)


def _native_rebuild_bwrap_prefix() -> list[str]:
    return [
        "--unshare-all",
        "--die-with-parent",
        "--new-session",
        "--clearenv",
        "--proc",
        "/proc",
        "--dev",
        "/dev",
        "--tmpfs",
        "/tmp",
        "--ro-bind",
        "/usr",
        "/usr",
        "--ro-bind",
        "/lib",
        "/lib",
        "--ro-bind",
        "/lib64",
        "/lib64",
        "--chdir",
        "/",
        "--setenv",
        "PATH",
        "/usr/bin:/bin",
        "--setenv",
        "LANG",
        "C",
        "--setenv",
        "LC_ALL",
        "C",
        "--setenv",
        "SOURCE_DATE_EPOCH",
        "0",
    ]


CLONE_NEWUSER = 0x10000000
PR_GET_DUMPABLE = 3
PR_SET_DUMPABLE = 4


def _libc_prctl_dumpable(value: int | None = None) -> int:
    libc = ctypes.CDLL(None, use_errno=True)
    call = libc.prctl
    call.argtypes = [
        ctypes.c_int,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_ulong,
    ]
    call.restype = ctypes.c_int
    operation = PR_GET_DUMPABLE if value is None else PR_SET_DUMPABLE
    result = call(operation, 0 if value is None else value, 0, 0, 0)
    if result < 0:
        observed = ctypes.get_errno()
        _fail("PLATFORM_UNSUPPORTED", f"prctl dumpable errno={observed}")
    return result


def _root_mapping_tool_record(path: Path, label: str) -> dict[str, Any]:
    with hold_source_file_components(path) as held:
        info = held.metadata
        digest, size = _hash_fd(held.descriptor)
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != ROOT_UID
            or info.st_gid != ROOT_GID
            or info.st_nlink != 1
            or stat.S_IMODE(info.st_mode) != 0o4755
            or _identity(os.fstat(held.descriptor)) != _identity(info)
        ):
            _fail("NATIVE_BUILD_USERNS_INVALID", label)
        return {
            "path": str(path),
            "canonical": str(held.canonical_path),
            "pin": {"sha256": digest, "size_bytes": size},
            "mode": "04755",
            "uid": 0,
            "gid": 0,
            "nlink": 1,
        }


def _subid_allocation_record(path: Path, *, kind: str, start: int) -> dict[str, Any]:
    with hold_source_file_components(path) as held:
        info = held.metadata
        raw = bytearray()
        os.lseek(held.descriptor, 0, os.SEEK_SET)
        while block := os.read(held.descriptor, CHUNK_BYTES):
            raw.extend(block)
            if len(raw) > MAX_JSON_BYTES:
                _fail("NATIVE_BUILD_USERNS_INVALID", f"{kind} allocation size")
        os.lseek(held.descriptor, 0, os.SEEK_SET)
        digest, size = _hash_fd(held.descriptor)
        expected = f"{REVIEW_USERNAME}:{start}:{NATIVE_BUILD_SUBID_RANGE}"
        lines = bytes(raw).decode("utf-8", "strict").splitlines()
        if (
            not stat.S_ISREG(info.st_mode)
            or info.st_uid != ROOT_UID
            or info.st_gid != ROOT_GID
            or info.st_nlink != 1
            or stat.S_IMODE(info.st_mode) not in (0o644, 0o600)
            or lines.count(expected) != 1
            or _identity(os.fstat(held.descriptor)) != _identity(info)
        ):
            _fail("NATIVE_BUILD_USERNS_INVALID", f"{kind} allocation")
        return {
            "path": str(path),
            "canonical": str(held.canonical_path),
            "pin": {"sha256": digest, "size_bytes": size},
            "mode": f"0{stat.S_IMODE(info.st_mode):03o}",
            "uid": 0,
            "gid": 0,
            "nlink": 1,
            "allocation": {
                "username": REVIEW_USERNAME,
                "start": start,
                "count": NATIVE_BUILD_SUBID_RANGE,
            },
        }


def _run_id_map_helper(path: Path, arguments: Sequence[str], label: str) -> None:
    before = _root_mapping_tool_record(path, label)
    result = subprocess.run(
        [str(path), *arguments],
        check=False,
        cwd="/",
        env={"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"},
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=30,
    )
    if result.returncode != 0 or result.stdout or result.stderr:
        _fail("NATIVE_BUILD_USERNS_INVALID", result.stderr.strip() or label)
    if _root_mapping_tool_record(path, label) != before:
        _fail("NATIVE_BUILD_USERNS_INVALID", f"{label} drift")


def _recv_namespace_fd(channel: socket.socket) -> int:
    message, controls, _flags, _address = channel.recvmsg(
        16, socket.CMSG_SPACE(array.array("i", [0]).itemsize)
    )
    if message != b"USERNS_READY":
        _fail("NATIVE_BUILD_USERNS_INVALID", "keeper readiness")
    descriptors: list[int] = []
    for level, kind, payload in controls:
        if level == socket.SOL_SOCKET and kind == socket.SCM_RIGHTS:
            values = array.array("i")
            values.frombytes(payload[: len(payload) - (len(payload) % values.itemsize)])
            descriptors.extend(values)
    if len(descriptors) != 1:
        for descriptor in descriptors:
            os.close(descriptor)
        _fail("NATIVE_BUILD_USERNS_INVALID", "keeper namespace FD")
    return descriptors[0]


def _hostile_scanner_loop(channel: socket.socket) -> None:
    libc = ctypes.CDLL(None, use_errno=True)
    setns = libc.setns
    setns.argtypes = [ctypes.c_int, ctypes.c_int]
    setns.restype = ctypes.c_int
    try:
        while True:
            raw = channel.recv(65536)
            if not raw:
                break
            request = json.loads(raw.decode("utf-8"))
            if request == {"operation": "exit"}:
                break
            path = request["path"]
            operation = request["operation"]
            flags = os.O_RDWR if operation == "open-rdwr" else os.O_RDONLY
            opened = False
            open_errno = 0
            setns_succeeded = False
            setns_errno = 0
            descriptor = -1
            try:
                descriptor = os.open(path, flags | os.O_CLOEXEC)
                opened = True
                if operation == "open-userns-and-setns":
                    setns_succeeded = setns(descriptor, CLONE_NEWUSER) == 0
                    if not setns_succeeded:
                        setns_errno = ctypes.get_errno()
            except OSError as exc:
                open_errno = exc.errno
            finally:
                if descriptor >= 0:
                    os.close(descriptor)
            channel.send(
                canonical_json(
                    {
                        "opened": opened,
                        "open_errno": open_errno,
                        "setns_succeeded": setns_succeeded,
                        "setns_errno": setns_errno,
                    }
                ).rstrip(b"\n")
            )
    finally:
        channel.close()


def _assert_hostile_access_denied(
    channel: socket.socket, *, path: str, operation: str, label: str
) -> None:
    channel.send(canonical_json({"operation": operation, "path": path}).rstrip(b"\n"))
    response = strict_json(channel.recv(65536), f"{label} hostile scan")
    if (
        response.get("opened") is not False
        or response.get("open_errno") not in (errno.EACCES, errno.EPERM)
        or response.get("setns_succeeded") is not False
    ):
        _fail("NATIVE_BUILD_SAME_UID_ISOLATION_FAILED", label)


@dataclasses.dataclass
class ProtectedNativeOutput:
    descriptor: int
    user_namespace_fd: int
    keeper_pid: int
    scanner: socket.socket
    uid_map_bytes: str
    gid_map_bytes: str


def _parse_id_map(raw: str, label: str) -> list[tuple[int, int, int]]:
    try:
        records = [
            tuple(int(value) for value in line.split()) for line in raw.splitlines()
        ]
    except ValueError as exc:
        raise AuthorityError("NATIVE_BUILD_USERNS_INVALID", label) from exc
    if any(len(record) != 3 for record in records):
        _fail("NATIVE_BUILD_USERNS_INVALID", label)
    return records  # type: ignore[return-value]


@contextlib.contextmanager
def _protected_output_memfd(label: str) -> Iterable[ProtectedNativeOutput]:
    """Create output authority protected by a distinct host subordinate UID."""

    required_os = ("memfd_create", "MFD_CLOEXEC", "MFD_ALLOW_SEALING", "fork")
    if any(not hasattr(os, name) for name in required_os):
        _fail("PLATFORM_UNSUPPORTED", "subuid output isolation required")
    if os.getuid() != REVIEW_UID or os.getgid() != REVIEW_GID:
        _fail("UNPRIVILEGED_REVIEW_REQUIRED", "native output authority")
    _root_mapping_tool_record(NEWUIDMAP_PATH, "newuidmap")
    _root_mapping_tool_record(NEWGIDMAP_PATH, "newgidmap")
    _subid_allocation_record(SUBUID_PATH, kind="subuid", start=NATIVE_BUILD_SUBUID)
    _subid_allocation_record(SUBGID_PATH, kind="subgid", start=NATIVE_BUILD_SUBGID)

    scanner_parent, scanner_child = socket.socketpair(
        socket.AF_UNIX, socket.SOCK_SEQPACKET | socket.SOCK_CLOEXEC
    )
    scanner_pid = os.fork()
    if scanner_pid == 0:
        scanner_parent.close()
        _hostile_scanner_loop(scanner_child)
        os._exit(0)
    scanner_child.close()
    original_dumpable = _libc_prctl_dumpable()
    keeper_parent: socket.socket | None = None
    keeper_pid = -1
    namespace_fd = -1
    output_fd = -1
    try:
        _libc_prctl_dumpable(0)
        keeper_parent, keeper_child = socket.socketpair(
            socket.AF_UNIX, socket.SOCK_SEQPACKET | socket.SOCK_CLOEXEC
        )
        keeper_pid = os.fork()
        if keeper_pid == 0:
            keeper_parent.close()
            libc = ctypes.CDLL(None, use_errno=True)
            if libc.unshare(CLONE_NEWUSER) != 0:
                os._exit(121)
            if libc.prctl(PR_SET_DUMPABLE, 0, 0, 0, 0) != 0:
                os._exit(122)
            child_namespace_fd = os.open(
                "/proc/self/ns/user", os.O_RDONLY | os.O_CLOEXEC
            )
            rights = array.array("i", [child_namespace_fd])
            keeper_child.sendmsg(
                [b"USERNS_READY"],
                [(socket.SOL_SOCKET, socket.SCM_RIGHTS, rights)],
            )
            os.close(child_namespace_fd)
            if keeper_child.recv(16) != b"MAPS_READY":
                os._exit(123)
            with open("/proc/self/uid_map", "rb") as stream:
                uid_map = stream.read()
            with open("/proc/self/gid_map", "rb") as stream:
                gid_map = stream.read()
            keeper_child.send(
                canonical_json(
                    {
                        "uid_map_bytes": uid_map.decode("ascii"),
                        "gid_map_bytes": gid_map.decode("ascii"),
                    }
                ).rstrip(b"\n")
            )
            if keeper_child.recv(16) != b"KEEPER_EXIT":
                os._exit(124)
            keeper_child.close()
            os._exit(0)
        keeper_child.close()
        keeper_parent.settimeout(30)
        namespace_fd = _recv_namespace_fd(keeper_parent)
        _run_id_map_helper(
            NEWUIDMAP_PATH,
            (
                str(keeper_pid),
                "0",
                str(REVIEW_UID),
                "1",
                "1",
                str(NATIVE_BUILD_SUBUID),
                "1",
            ),
            "newuidmap",
        )
        try:
            with open(f"/proc/{keeper_pid}/setgroups", "w", encoding="ascii") as stream:
                stream.write("deny")
        except OSError as exc:
            if exc.errno not in (errno.EPERM, errno.EACCES):
                raise
        _run_id_map_helper(
            NEWGIDMAP_PATH,
            (
                str(keeper_pid),
                "0",
                str(REVIEW_GID),
                "1",
                "1",
                str(NATIVE_BUILD_SUBGID),
                "1",
            ),
            "newgidmap",
        )
        keeper_parent.send(b"MAPS_READY")
        maps = strict_json(keeper_parent.recv(65536), "native build userns maps")
        uid_map_bytes = maps.get("uid_map_bytes")
        gid_map_bytes = maps.get("gid_map_bytes")
        if (
            type(uid_map_bytes) is not str
            or type(gid_map_bytes) is not str
            or _parse_id_map(uid_map_bytes, "uid_map")
            != [(0, REVIEW_UID, 1), (1, NATIVE_BUILD_SUBUID, 1)]
            or _parse_id_map(gid_map_bytes, "gid_map")
            != [(0, REVIEW_GID, 1), (1, NATIVE_BUILD_SUBGID, 1)]
        ):
            _fail("NATIVE_BUILD_USERNS_INVALID", "exact maps")
        _assert_hostile_access_denied(
            scanner_parent,
            path=f"/proc/{keeper_pid}/ns/user",
            operation="open-userns-and-setns",
            label="keeper user namespace",
        )
        _assert_hostile_access_denied(
            scanner_parent,
            path=f"/proc/{os.getpid()}/fd/{namespace_fd}",
            operation="open-userns-and-setns",
            label="parent-held user namespace",
        )
        output_fd = os.memfd_create(label, flags=os.MFD_CLOEXEC | os.MFD_ALLOW_SEALING)
        yield ProtectedNativeOutput(
            descriptor=output_fd,
            user_namespace_fd=namespace_fd,
            keeper_pid=keeper_pid,
            scanner=scanner_parent,
            uid_map_bytes=uid_map_bytes,
            gid_map_bytes=gid_map_bytes,
        )
    finally:
        if output_fd >= 0:
            os.close(output_fd)
        if keeper_parent is not None:
            try:
                keeper_parent.send(b"KEEPER_EXIT")
            except OSError:
                pass
            keeper_parent.close()
        if keeper_pid > 0:
            _pid, status = os.waitpid(keeper_pid, 0)
            if status != 0 and not sys.exc_info()[0]:
                _fail("NATIVE_BUILD_USERNS_INVALID", f"keeper status={status}")
        if namespace_fd >= 0:
            os.close(namespace_fd)
        if original_dumpable != 0:
            _libc_prctl_dumpable(original_dumpable)
        try:
            scanner_parent.send(canonical_json({"operation": "exit"}).rstrip(b"\n"))
        except OSError:
            pass
        scanner_parent.close()
        _pid, scanner_status = os.waitpid(scanner_pid, 0)
        if scanner_status != 0 and not sys.exc_info()[0]:
            _fail("NATIVE_BUILD_SAME_UID_ISOLATION_FAILED", "scanner status")


def _seal_native_output_memfd(descriptor: int, label: str) -> FilePin:
    required = (
        "F_ADD_SEALS",
        "F_GET_SEALS",
        "F_SEAL_SEAL",
        "F_SEAL_SHRINK",
        "F_SEAL_GROW",
        "F_SEAL_WRITE",
    )
    if any(not hasattr(fcntl, name) for name in required):
        _fail("PLATFORM_UNSUPPORTED", "output memfd seals required")
    info = os.fstat(descriptor)
    if (
        not stat.S_ISREG(info.st_mode)
        or info.st_size <= 0
        or info.st_size > MAX_JSON_BYTES
    ):
        _fail("CORE_BOOTSTRAP_REVIEW_INVALID", f"{label} output metadata")
    os.fchmod(descriptor, 0o555)
    expected_seals = (
        fcntl.F_SEAL_SEAL | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_GROW | fcntl.F_SEAL_WRITE
    )
    try:
        fcntl.fcntl(descriptor, fcntl.F_ADD_SEALS, expected_seals)
    except OSError as exc:
        raise AuthorityError(
            "CORE_BOOTSTRAP_REVIEW_INVALID", f"{label} output seal"
        ) from exc
    if fcntl.fcntl(descriptor, fcntl.F_GET_SEALS) != expected_seals:
        _fail("CORE_BOOTSTRAP_REVIEW_INVALID", f"{label} output seal drift")
    digest, size = _hash_fd(descriptor)
    if size != info.st_size:
        _fail("CORE_BOOTSTRAP_REVIEW_INVALID", f"{label} output size drift")
    return FilePin(digest, size, True)


def _read_sealed_native_output(descriptor: int, label: str) -> tuple[bytes, FilePin]:
    pin = _seal_state_native_output_pin(descriptor, label)
    os.lseek(descriptor, 0, os.SEEK_SET)
    remaining = pin.size_bytes
    blocks: list[bytes] = []
    while remaining:
        block = os.read(descriptor, min(CHUNK_BYTES, remaining))
        if not block:
            _fail("CORE_BOOTSTRAP_REVIEW_INVALID", f"{label} short read")
        blocks.append(block)
        remaining -= len(block)
    if os.read(descriptor, 1):
        _fail("CORE_BOOTSTRAP_REVIEW_INVALID", f"{label} grew after seal")
    os.lseek(descriptor, 0, os.SEEK_SET)
    return b"".join(blocks), pin


def _seal_state_native_output_pin(descriptor: int, label: str) -> FilePin:
    expected_seals = (
        fcntl.F_SEAL_SEAL | fcntl.F_SEAL_SHRINK | fcntl.F_SEAL_GROW | fcntl.F_SEAL_WRITE
    )
    info = os.fstat(descriptor)
    if (
        not stat.S_ISREG(info.st_mode)
        or stat.S_IMODE(info.st_mode) != 0o555
        or info.st_size <= 0
        or info.st_size > MAX_JSON_BYTES
        or fcntl.fcntl(descriptor, fcntl.F_GET_SEALS) != expected_seals
    ):
        _fail("CORE_BOOTSTRAP_REVIEW_INVALID", f"{label} sealed output state")
    digest, size = _hash_fd(descriptor)
    return FilePin(digest, size, True)


def _native_rebuild_isolation_record(
    held_bwrap: HeldSourceFile,
) -> dict[str, Any]:
    digest, size = _hash_fd(held_bwrap.descriptor)
    if _identity(os.fstat(held_bwrap.descriptor)) != _identity(held_bwrap.metadata):
        _fail("CORE_BOOTSTRAP_REVIEW_INVALID", "bwrap drift")
    return {
        "sandbox_launcher": {
            "path": str(BWRAP_PATH),
            "canonical": str(held_bwrap.canonical_path),
            "pin": {"sha256": digest, "size_bytes": size},
        },
        "argv_prefix": _native_rebuild_bwrap_prefix(),
        "host_binds_read_only": ["/usr", "/lib", "/lib64"],
        "scratch": {
            "path": "/tmp",
            "kind": "private_tmpfs",
            "persistent": False,
        },
        "network_namespace_unshared": True,
        "output": {
            "kind": "sealed_memfd",
            "path_authority_used": False,
            "same_uid_procfs_guard": "PR_SET_DUMPABLE=0",
            "seals": [
                "F_SEAL_WRITE",
                "F_SEAL_GROW",
                "F_SEAL_SHRINK",
                "F_SEAL_SEAL",
            ],
        },
    }


def _compile_native_isolated(
    *,
    committed_source: bytes,
    source_path: Path,
    flags: Sequence[str],
    output_fd: int,
    label: str,
    failure_code: str,
    drift_code: str,
) -> tuple[FilePin, dict[str, Any]]:
    """Compile one review binary inside a fixed bwrap sandbox to a held memfd."""

    if os.geteuid() == ROOT_UID:
        _fail("UNPRIVILEGED_REVIEW_REQUIRED", f"{label} isolated rebuild")
    before_toolchain = _review_toolchain_artifact_pins()
    committed_pin = FilePin(
        hashlib.sha256(committed_source).hexdigest(), len(committed_source)
    )
    with (
        hold_source_file_components(COMPILER_PATH) as compiler,
        hold_source_file_components(BWRAP_PATH) as bwrap,
        _sealed_source_memfd(committed_source, f"{label}-source") as source_fd,
    ):
        compiler_pin = _hash_fd(compiler.descriptor)
        bwrap_pin = _hash_fd(bwrap.descriptor)
        source_pin = _hash_fd(source_fd)
        if source_pin != (committed_pin.sha256, committed_pin.size_bytes):
            _fail(drift_code, "Git blob memfd")
        isolation = _native_rebuild_isolation_record(bwrap)
        command = [
            str(BWRAP_PATH),
            *_native_rebuild_bwrap_prefix(),
            "--",
            f"/proc/self/fd/{compiler.descriptor}",
            *flags,
            f"/proc/self/fd/{source_fd}",
            "-o",
            f"/proc/self/fd/{output_fd}",
        ]
        result = subprocess.run(
            command,
            executable=f"/proc/self/fd/{bwrap.descriptor}",
            check=False,
            cwd="/",
            env={
                "PATH": "/usr/bin:/bin",
                "LANG": "C",
                "LC_ALL": "C",
                "SOURCE_DATE_EPOCH": "0",
            },
            pass_fds=(
                bwrap.descriptor,
                compiler.descriptor,
                source_fd,
                output_fd,
            ),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=120,
        )
        if result.returncode != 0 or result.stdout or result.stderr:
            _fail(failure_code, result.stderr.strip() or "sandboxed compiler output")
        if (
            _hash_fd(compiler.descriptor) != compiler_pin
            or _hash_fd(bwrap.descriptor) != bwrap_pin
            or _hash_fd(source_fd) != source_pin
            or _identity(os.fstat(compiler.descriptor)) != _identity(compiler.metadata)
            or _identity(os.fstat(bwrap.descriptor)) != _identity(bwrap.metadata)
        ):
            _fail(drift_code, "compiler/bwrap/source")
        output_pin = _seal_native_output_memfd(output_fd, label)
        compiler_record = {
            "path": str(COMPILER_PATH),
            "canonical": str(compiler.canonical_path),
            "pin": {
                "sha256": compiler_pin[0],
                "size_bytes": compiler_pin[1],
            },
        }
    if _review_toolchain_artifact_pins() != before_toolchain:
        _fail(drift_code, "toolchain")
    raw, sealed_pin = _read_sealed_native_output(output_fd, label)
    if not raw.startswith(b"\x7fELF") or sealed_pin != output_pin:
        _fail(failure_code, "sealed output is not stable ELF")
    return output_pin, {
        "source": {
            "git_path": source_path.relative_to(CHECKOUT_ROOT).as_posix(),
            "pin": committed_pin.public(),
            "compiled_from_sealed_memfd": True,
        },
        "compiler_driver": compiler_record,
        "toolchain_artifact_ledger": before_toolchain,
        "flags": list(flags),
        "environment": {
            "PATH": "/usr/bin:/bin",
            "LANG": "C",
            "LC_ALL": "C",
            "SOURCE_DATE_EPOCH": "0",
        },
        "output_pin": output_pin.public(),
        "isolation": isolation,
    }


def _compile_core_native_isolated(
    *,
    committed_source: bytes,
    source_path: Path,
    flags: Sequence[str],
    helper_pin: FilePin,
    python_pin: FilePin,
    output_fd: int,
    label: str,
    failure_code: str,
    drift_code: str,
) -> tuple[FilePin, dict[str, Any]]:
    output_pin, provenance = _compile_native_isolated(
        committed_source=committed_source,
        source_path=source_path,
        flags=flags,
        output_fd=output_fd,
        label=label,
        failure_code=failure_code,
        drift_code=drift_code,
    )
    provenance["python_pin"] = python_pin.public()
    provenance["helper_pin"] = helper_pin.public()
    return output_pin, provenance


def _require_static_review_elf_fd(descriptor: int, label: str) -> FilePin:
    """Inspect a sealed held ELF without converting it to pathname authority."""

    raw, before_pin = _read_sealed_native_output(descriptor, label)
    if not raw.startswith(b"\x7fELF"):
        _fail("CORE_BOOTSTRAP_REVIEW_INVALID", f"{label} is not ELF")
    with hold_source_file_components(READELF_PATH) as held_readelf:
        readelf_sha, readelf_size = _hash_fd(held_readelf.descriptor)
        result = subprocess.run(
            [
                f"/proc/self/fd/{held_readelf.descriptor}",
                "--wide",
                "--program-headers",
                "--dynamic",
                f"/proc/self/fd/{descriptor}",
            ],
            executable=f"/proc/self/fd/{held_readelf.descriptor}",
            check=False,
            cwd="/",
            env={"PATH": "/usr/bin:/bin", "LANG": "C", "LC_ALL": "C"},
            pass_fds=(held_readelf.descriptor, descriptor),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=60,
        )
        if result.returncode != 0 or result.stderr:
            _fail("CORE_BOOTSTRAP_REVIEW_INVALID", f"{label} readelf")
        if _hash_fd(held_readelf.descriptor) != (
            readelf_sha,
            readelf_size,
        ) or _identity(os.fstat(held_readelf.descriptor)) != _identity(
            held_readelf.metadata
        ):
            _fail("CORE_BOOTSTRAP_REVIEW_INVALID", "readelf drift")
    metadata = parse_readelf_output(result.stdout)
    if (
        metadata.interpreter is not None
        or metadata.needed
        or metadata.rpath
        or metadata.runpath
    ):
        _fail("CORE_BOOTSTRAP_REVIEW_INVALID", f"{label} is not static")
    _post_raw, after_pin = _read_sealed_native_output(descriptor, label)
    if after_pin != before_pin:
        _fail("CORE_BOOTSTRAP_REVIEW_INVALID", f"{label} drifted")
    return before_pin


def _compile_admin_launcher(
    stage: str,
    *,
    committed_source: bytes,
    python_pin: Mapping[str, Any],
    helper_pin: Mapping[str, Any],
    output: Path,
) -> tuple[FilePin, dict[str, Any]]:
    """Build one reviewed native stage launcher as the unprivileged reviewer."""

    if os.geteuid() == ROOT_UID:
        _fail("UNPRIVILEGED_REVIEW_REQUIRED", "admin launcher compilation")
    if stage not in {"runtime", "bundle"}:
        _fail("STAGE_AUTHORITY_INVALID", stage)
    expected_python = _parse_pin(python_pin, "admin launcher Python")
    expected_helper = _parse_pin(helper_pin, "admin launcher helper")
    before_toolchain = _review_toolchain_artifact_pins()
    committed_source_pin = FilePin(
        hashlib.sha256(committed_source).hexdigest(), len(committed_source)
    )
    with (
        hold_source_file_components(COMPILER_PATH) as compiler,
        _sealed_source_memfd(
            committed_source, "vista-r8-stage-admin-source"
        ) as source_fd,
    ):
        compiler_pin = _hash_fd(compiler.descriptor)
        source_pin = _hash_fd(source_fd)
        if source_pin != (
            committed_source_pin.sha256,
            committed_source_pin.size_bytes,
        ):
            _fail("ADMIN_LAUNCHER_BUILD_INPUT_DRIFT", "Git blob memfd")
        flags = [
            "-std=c11",
            "-O2",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-static",
            "-s",
            "-Wl,--build-id=none",
            "-x",
            "c",
            (
                "-DVISTA_R8_ADMIN_STAGE_RUNTIME"
                if stage == "runtime"
                else "-DVISTA_R8_ADMIN_STAGE_BUNDLE"
            ),
            f'-DEXPECTED_PYTHON_SHA256="{expected_python.sha256}"',
            f"-DEXPECTED_PYTHON_SIZE={expected_python.size_bytes}",
            f'-DEXPECTED_HELPER_SHA256="{expected_helper.sha256}"',
            f"-DEXPECTED_HELPER_SIZE={expected_helper.size_bytes}",
        ]
        command = [
            str(COMPILER_PATH),
            *flags,
            f"/proc/self/fd/{source_fd}",
            "-o",
            str(output),
        ]
        result = subprocess.run(
            command,
            executable=f"/proc/self/fd/{compiler.descriptor}",
            check=False,
            cwd="/",
            env={
                "PATH": "/usr/bin:/bin",
                "LANG": "C",
                "LC_ALL": "C",
                "SOURCE_DATE_EPOCH": "0",
            },
            pass_fds=(compiler.descriptor, source_fd),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=120,
        )
        if result.returncode != 0 or result.stdout or result.stderr:
            _fail(
                "ADMIN_LAUNCHER_BUILD_FAILED",
                result.stderr.strip() or "compiler output",
            )
        if (
            _hash_fd(compiler.descriptor) != compiler_pin
            or _hash_fd(source_fd) != source_pin
            or _identity(os.fstat(compiler.descriptor)) != _identity(compiler.metadata)
        ):
            _fail("ADMIN_LAUNCHER_BUILD_INPUT_DRIFT", stage)
    if _review_toolchain_artifact_pins() != before_toolchain:
        _fail("ADMIN_LAUNCHER_BUILD_INPUT_DRIFT", "toolchain")
    raw, built = _read_regular(output, f"{stage} admin launcher output")
    if not raw.startswith(b"\x7fELF"):
        _fail("ADMIN_LAUNCHER_BUILD_FAILED", "output is not ELF")
    output_pin = FilePin(built.sha256, built.size_bytes, True)
    return output_pin, {
        "source": {
            "git_path": ADMIN_LAUNCHER_SOURCE.relative_to(CHECKOUT_ROOT).as_posix(),
            "pin": committed_source_pin.public(),
            "compiled_from_sealed_memfd": True,
        },
        "compiler_driver": {
            "path": str(COMPILER_PATH),
            "canonical": str(compiler.canonical_path),
            "pin": {
                "sha256": compiler_pin[0],
                "size_bytes": compiler_pin[1],
            },
        },
        "toolchain_artifact_ledger": before_toolchain,
        "flags": flags,
        "environment": {
            "PATH": "/usr/bin:/bin",
            "LANG": "C",
            "LC_ALL": "C",
            "SOURCE_DATE_EPOCH": "0",
        },
        "python_pin": expected_python.public(),
        "helper_pin": expected_helper.public(),
        "output_pin": output_pin.public(),
    }


def _compile_stage_installer(
    key: str,
    *,
    committed_source: bytes,
    python_pin: Mapping[str, Any],
    helper_pin: Mapping[str, Any],
    primary_pin: Mapping[str, Any],
    secondary_pin: Mapping[str, Any] | None,
    output: Path,
) -> tuple[FilePin, dict[str, Any]]:
    """Build one candidate-bound stage installer as the unprivileged reviewer."""

    if os.geteuid() == ROOT_UID or key not in STAGE_KEYS:
        _fail("UNPRIVILEGED_REVIEW_REQUIRED", "stage installer compilation")
    expected_python = _parse_pin(python_pin, "stage installer Python")
    expected_helper = _parse_pin(helper_pin, "stage installer helper")
    expected_primary = _parse_pin(primary_pin, "stage installer primary input")
    expected_secondary = (
        None
        if secondary_pin is None
        else _parse_pin(secondary_pin, "stage installer secondary input")
    )
    if key.endswith("-plan") != (expected_secondary is not None):
        _fail("STAGE_INSTALLER_BUILD_INPUT_INVALID", key)
    before_toolchain = _review_toolchain_artifact_pins()
    committed_source_pin = FilePin(
        hashlib.sha256(committed_source).hexdigest(), len(committed_source)
    )
    stage_define = {
        "runtime-input": "VISTA_R8_STAGE_RUNTIME_INPUT",
        "runtime-plan": "VISTA_R8_STAGE_RUNTIME_PLAN",
        "bundle-input": "VISTA_R8_STAGE_BUNDLE_INPUT",
        "bundle-plan": "VISTA_R8_STAGE_BUNDLE_PLAN",
    }[key]
    input_defines = (
        [
            f'-DEXPECTED_INPUT_PIN_SHA256="{expected_primary.sha256}"',
            f"-DEXPECTED_INPUT_PIN_SIZE={expected_primary.size_bytes}",
        ]
        if expected_secondary is None
        else [
            f'-DEXPECTED_REVIEWED_PLAN_PIN_SHA256="{expected_primary.sha256}"',
            f"-DEXPECTED_REVIEWED_PLAN_PIN_SIZE={expected_primary.size_bytes}",
            f'-DEXPECTED_ADMIN_LAUNCHER_SHA256="{expected_secondary.sha256}"',
            f"-DEXPECTED_ADMIN_LAUNCHER_SIZE={expected_secondary.size_bytes}",
        ]
    )
    with (
        hold_source_file_components(COMPILER_PATH) as compiler,
        _sealed_source_memfd(
            committed_source, "vista-r8-stage-installer-source"
        ) as source_fd,
    ):
        compiler_pin = _hash_fd(compiler.descriptor)
        source_pin = _hash_fd(source_fd)
        if source_pin != (
            committed_source_pin.sha256,
            committed_source_pin.size_bytes,
        ):
            _fail("STAGE_INSTALLER_BUILD_INPUT_DRIFT", "Git blob memfd")
        flags = [
            "-std=c11",
            "-O2",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-static",
            "-s",
            "-Wl,--build-id=none",
            "-x",
            "c",
            f"-D{stage_define}",
            f'-DEXPECTED_PYTHON_SHA256="{expected_python.sha256}"',
            f"-DEXPECTED_PYTHON_SIZE={expected_python.size_bytes}",
            f'-DEXPECTED_HELPER_SHA256="{expected_helper.sha256}"',
            f"-DEXPECTED_HELPER_SIZE={expected_helper.size_bytes}",
            *input_defines,
        ]
        command = [
            str(COMPILER_PATH),
            *flags,
            f"/proc/self/fd/{source_fd}",
            "-o",
            str(output),
        ]
        result = subprocess.run(
            command,
            executable=f"/proc/self/fd/{compiler.descriptor}",
            check=False,
            cwd="/",
            env={
                "PATH": "/usr/bin:/bin",
                "LANG": "C",
                "LC_ALL": "C",
                "SOURCE_DATE_EPOCH": "0",
            },
            pass_fds=(compiler.descriptor, source_fd),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=120,
        )
        if result.returncode != 0 or result.stdout or result.stderr:
            _fail(
                "STAGE_INSTALLER_BUILD_FAILED",
                result.stderr.strip() or "compiler output",
            )
        if (
            _hash_fd(compiler.descriptor) != compiler_pin
            or _hash_fd(source_fd) != source_pin
            or _identity(os.fstat(compiler.descriptor)) != _identity(compiler.metadata)
        ):
            _fail("STAGE_INSTALLER_BUILD_INPUT_DRIFT", key)
    if _review_toolchain_artifact_pins() != before_toolchain:
        _fail("STAGE_INSTALLER_BUILD_INPUT_DRIFT", "toolchain")
    raw, built = _read_regular(output, f"{key} stage installer output")
    if not raw.startswith(b"\x7fELF"):
        _fail("STAGE_INSTALLER_BUILD_FAILED", "output is not ELF")
    output_pin = FilePin(built.sha256, built.size_bytes, True)
    return output_pin, {
        "source": {
            "git_path": STAGE_INSTALLER_SOURCE.relative_to(CHECKOUT_ROOT).as_posix(),
            "pin": committed_source_pin.public(),
            "compiled_from_sealed_memfd": True,
        },
        "compiler_driver": {
            "path": str(COMPILER_PATH),
            "canonical": str(compiler.canonical_path),
            "pin": {
                "sha256": compiler_pin[0],
                "size_bytes": compiler_pin[1],
            },
        },
        "toolchain_artifact_ledger": before_toolchain,
        "flags": flags,
        "environment": {
            "PATH": "/usr/bin:/bin",
            "LANG": "C",
            "LC_ALL": "C",
            "SOURCE_DATE_EPOCH": "0",
        },
        "python_pin": expected_python.public(),
        "helper_pin": expected_helper.public(),
        "primary_pin": expected_primary.public(),
        "secondary_pin": (
            None if expected_secondary is None else expected_secondary.public()
        ),
        "output_pin": output_pin.public(),
    }


def _compile_stage_transfer_launcher(
    *,
    committed_source: bytes,
    python_pin: Mapping[str, Any],
    helper_pin: Mapping[str, Any],
    output: Path,
) -> tuple[FilePin, dict[str, Any]]:
    """Build the generic core transfer launcher from one sealed Git blob."""

    if os.geteuid() == ROOT_UID:
        _fail("UNPRIVILEGED_REVIEW_REQUIRED", "stage transfer launcher build")
    expected_python = _parse_pin(python_pin, "stage transfer Python")
    expected_helper = _parse_pin(helper_pin, "stage transfer helper")
    before_toolchain = _review_toolchain_artifact_pins()
    committed_source_pin = FilePin(
        hashlib.sha256(committed_source).hexdigest(), len(committed_source)
    )
    with (
        hold_source_file_components(COMPILER_PATH) as compiler,
        _sealed_source_memfd(
            committed_source, "vista-r8-stage-transfer-source"
        ) as source_fd,
    ):
        compiler_pin = _hash_fd(compiler.descriptor)
        source_pin = _hash_fd(source_fd)
        if source_pin != (
            committed_source_pin.sha256,
            committed_source_pin.size_bytes,
        ):
            _fail("STAGE_TRANSFER_BUILD_INPUT_DRIFT", "Git blob memfd")
        flags = [
            "-std=c11",
            "-O2",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-static",
            "-s",
            "-Wl,--build-id=none",
            "-x",
            "c",
            f'-DEXPECTED_PYTHON_SHA256="{expected_python.sha256}"',
            f"-DEXPECTED_PYTHON_SIZE={expected_python.size_bytes}",
            f'-DEXPECTED_HELPER_SHA256="{expected_helper.sha256}"',
            f"-DEXPECTED_HELPER_SIZE={expected_helper.size_bytes}",
        ]
        command = [
            str(COMPILER_PATH),
            *flags,
            f"/proc/self/fd/{source_fd}",
            "-o",
            str(output),
        ]
        result = subprocess.run(
            command,
            executable=f"/proc/self/fd/{compiler.descriptor}",
            check=False,
            cwd="/",
            env={
                "PATH": "/usr/bin:/bin",
                "LANG": "C",
                "LC_ALL": "C",
                "SOURCE_DATE_EPOCH": "0",
            },
            pass_fds=(compiler.descriptor, source_fd),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=120,
        )
        if result.returncode != 0 or result.stdout or result.stderr:
            _fail(
                "STAGE_TRANSFER_BUILD_FAILED",
                result.stderr.strip() or "compiler output",
            )
        if (
            _hash_fd(compiler.descriptor) != compiler_pin
            or _hash_fd(source_fd) != source_pin
            or _identity(os.fstat(compiler.descriptor)) != _identity(compiler.metadata)
        ):
            _fail("STAGE_TRANSFER_BUILD_INPUT_DRIFT", "compiler/source")
    if _review_toolchain_artifact_pins() != before_toolchain:
        _fail("STAGE_TRANSFER_BUILD_INPUT_DRIFT", "toolchain")
    raw, built = _read_regular(output, "stage transfer launcher output")
    if not raw.startswith(b"\x7fELF"):
        _fail("STAGE_TRANSFER_BUILD_FAILED", "output is not ELF")
    output_pin = FilePin(built.sha256, built.size_bytes, True)
    return output_pin, {
        "source": {
            "git_path": STAGE_TRANSFER_LAUNCHER_SOURCE.relative_to(
                CHECKOUT_ROOT
            ).as_posix(),
            "pin": committed_source_pin.public(),
            "compiled_from_sealed_memfd": True,
        },
        "compiler_driver": {
            "path": str(COMPILER_PATH),
            "canonical": str(compiler.canonical_path),
            "pin": {
                "sha256": compiler_pin[0],
                "size_bytes": compiler_pin[1],
            },
        },
        "toolchain_artifact_ledger": before_toolchain,
        "flags": flags,
        "environment": {
            "PATH": "/usr/bin:/bin",
            "LANG": "C",
            "LC_ALL": "C",
            "SOURCE_DATE_EPOCH": "0",
        },
        "python_pin": expected_python.public(),
        "helper_pin": expected_helper.public(),
        "output_pin": output_pin.public(),
    }


def build_stage_transfer_launcher_review_candidate() -> dict[str, Any]:
    """Reject the obsolete local native-candidate build path."""

    _fail(
        "DEDICATED_BUILDER_AUTHORITY_REQUIRED",
        "stage transfer launcher is published only by native builder Phase A",
    )


def build_engine_source_pin_review_candidate(
    reviewed_pin: Mapping[str, Any],
) -> dict[str, Any]:
    """Freeze the independently reviewed full-engine projection pin."""

    if os.geteuid() != REVIEW_UID or os.getegid() != REVIEW_GID:
        _fail("UNPRIVILEGED_REVIEW_REQUIRED", "engine source pin candidate")
    expected = _parse_pin(reviewed_pin, "reviewed engine source pin")
    final = ENGINE_SOURCE_PIN_REVIEW_CANDIDATE.parent
    if os.path.lexists(final):
        _fail("FINAL_NOT_FRESH", str(final))
    snapshot = snapshot_tree(ENGINE_SOURCE)
    document = derive_engine_source_pin(snapshot)
    raw = canonical_json(document)
    if (hashlib.sha256(raw).hexdigest(), len(raw)) != (
        expected.sha256,
        expected.size_bytes,
    ):
        _fail("ENGINE_SOURCE_REVIEWED_PIN_MISMATCH", "external review pin")
    staging = Path(tempfile.mkdtemp(prefix=f".{final.name}.staging-", dir=final.parent))
    owner = (REVIEW_UID, REVIEW_GID)
    try:
        installed_pin = _write_new(
            staging / ENGINE_SOURCE_PIN_REVIEW_CANDIDATE.name,
            raw,
            0o444,
            owner,
        )
        _seal_private_tree(staging, owner=owner)
        publish_staging(staging, final)
        return {
            "status": "user_published_engine_source_pin_review_candidate",
            "accepted": False,
            "candidate_root": str(final),
            "source_pin": installed_pin.public(),
            "source_pin_content_digest": document["content_digest"],
            "projection": document["projection"],
            "root_execution_performed": False,
        }
    finally:
        if os.path.lexists(staging):
            _remove_private_staging(staging)


def _require_static_review_elf(path: Path, label: str) -> FilePin:
    raw, pin = _read_regular(path, label, exact_mode=0o555)
    if not raw.startswith(b"\x7fELF"):
        _fail("CORE_BOOTSTRAP_REVIEW_INVALID", f"{label} is not ELF")
    with hold_source_file_components(READELF_PATH) as held_readelf:
        if stat.S_IMODE(held_readelf.metadata.st_mode) != 0o755:
            _fail("CORE_BOOTSTRAP_REVIEW_INVALID", "readelf mode")
        readelf_sha, readelf_bytes = _hash_fd(held_readelf.descriptor)
        metadata = inspect_elf(
            path,
            readelf=held_readelf.canonical_path,
            readelf_pin=FilePin(readelf_sha, readelf_bytes, True),
        )
        if _hash_fd(held_readelf.descriptor) != (
            readelf_sha,
            readelf_bytes,
        ) or _identity(os.fstat(held_readelf.descriptor)) != _identity(
            held_readelf.metadata
        ):
            _fail("CORE_BOOTSTRAP_REVIEW_INVALID", "readelf drift")
    if (
        metadata.interpreter is not None
        or metadata.needed
        or metadata.rpath
        or metadata.runpath
    ):
        _fail("CORE_BOOTSTRAP_REVIEW_INVALID", f"{label} is not static")
    _post_raw, post_pin = _read_regular(path, label, exact_mode=0o555)
    if (post_pin.sha256, post_pin.size_bytes) != (pin.sha256, pin.size_bytes):
        _fail("CORE_BOOTSTRAP_REVIEW_INVALID", f"{label} drifted")
    return FilePin(pin.sha256, pin.size_bytes, True)


def _compile_parent_seal_launcher(
    *,
    committed_source: bytes,
    helper_pin: Mapping[str, Any],
    python_pin: Mapping[str, Any],
    output: Path,
) -> tuple[FilePin, dict[str, Any]]:
    if os.geteuid() == ROOT_UID:
        _fail("UNPRIVILEGED_REVIEW_REQUIRED", "parent seal launcher build")
    expected_helper = _parse_pin(helper_pin, "parent seal helper")
    expected_python = _parse_pin(python_pin, "parent seal Python")
    for literal, label in (
        (expected_helper.sha256.encode("ascii"), "helper sha256"),
        (str(expected_helper.size_bytes).encode("ascii"), "helper size"),
        (expected_python.sha256.encode("ascii"), "Python sha256"),
        (str(expected_python.size_bytes).encode("ascii"), "Python size"),
    ):
        if literal not in committed_source:
            _fail("PARENT_SEAL_BUILD_INPUT_DRIFT", label)
    before_toolchain = _review_toolchain_artifact_pins()
    committed_pin = FilePin(
        hashlib.sha256(committed_source).hexdigest(), len(committed_source)
    )
    with (
        hold_source_file_components(COMPILER_PATH) as compiler,
        _sealed_source_memfd(
            committed_source, "vista-authority-parent-seal-launcher-source"
        ) as source_fd,
    ):
        compiler_pin = _hash_fd(compiler.descriptor)
        source_pin = _hash_fd(source_fd)
        if source_pin != (committed_pin.sha256, committed_pin.size_bytes):
            _fail("PARENT_SEAL_BUILD_INPUT_DRIFT", "Git blob memfd")
        flags = [
            "-std=c11",
            "-O2",
            "-Wall",
            "-Wextra",
            "-Werror",
            "-static",
            "-s",
            "-Wl,--build-id=none",
            "-x",
            "c",
        ]
        command = [
            str(COMPILER_PATH),
            *flags,
            f"/proc/self/fd/{source_fd}",
            "-o",
            str(output),
        ]
        result = subprocess.run(
            command,
            executable=f"/proc/self/fd/{compiler.descriptor}",
            check=False,
            cwd="/",
            env={
                "PATH": "/usr/bin:/bin",
                "LANG": "C",
                "LC_ALL": "C",
                "SOURCE_DATE_EPOCH": "0",
            },
            pass_fds=(compiler.descriptor, source_fd),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=120,
        )
        if result.returncode != 0 or result.stdout or result.stderr:
            _fail(
                "PARENT_SEAL_BUILD_FAILED",
                result.stderr.strip() or "compiler output",
            )
        if (
            _hash_fd(compiler.descriptor) != compiler_pin
            or _hash_fd(source_fd) != source_pin
            or _identity(os.fstat(compiler.descriptor)) != _identity(compiler.metadata)
        ):
            _fail("PARENT_SEAL_BUILD_INPUT_DRIFT", "compiler/source")
    if _review_toolchain_artifact_pins() != before_toolchain:
        _fail("PARENT_SEAL_BUILD_INPUT_DRIFT", "toolchain")
    raw, built = _read_regular(output, "parent seal launcher output")
    if not raw.startswith(b"\x7fELF"):
        _fail("PARENT_SEAL_BUILD_FAILED", "output is not ELF")
    output_pin = FilePin(built.sha256, built.size_bytes, True)
    return output_pin, {
        "source": {
            "git_path": PARENT_SEAL_LAUNCHER_SOURCE.relative_to(
                CHECKOUT_ROOT
            ).as_posix(),
            "pin": committed_pin.public(),
            "compiled_from_sealed_memfd": True,
        },
        "compiler_driver": {
            "path": str(COMPILER_PATH),
            "canonical": str(compiler.canonical_path),
            "pin": {
                "sha256": compiler_pin[0],
                "size_bytes": compiler_pin[1],
            },
        },
        "toolchain_artifact_ledger": before_toolchain,
        "flags": flags,
        "environment": {
            "PATH": "/usr/bin:/bin",
            "LANG": "C",
            "LC_ALL": "C",
            "SOURCE_DATE_EPOCH": "0",
        },
        "python_pin": expected_python.public(),
        "helper_pin": expected_helper.public(),
        "output_pin": output_pin.public(),
    }


def _compile_initial_bootstrap_launcher(
    *,
    committed_source: bytes,
    helper_pin: Mapping[str, Any],
    python_pin: Mapping[str, Any],
    output_fd: int,
) -> tuple[FilePin, dict[str, Any]]:
    """Build the bootstrap launcher to one guarded, held, sealed memfd."""

    if os.geteuid() == ROOT_UID:
        _fail("UNPRIVILEGED_REVIEW_REQUIRED", "initial bootstrap launcher")
    expected_helper = _parse_pin(helper_pin, "initial bootstrap helper")
    expected_python = _parse_pin(python_pin, "initial bootstrap Python")
    flags = [
        "-std=c11",
        "-O2",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-static",
        "-s",
        "-Wl,--build-id=none",
        "-x",
        "c",
        f'-DEXPECTED_HELPER_SHA256="{expected_helper.sha256}"',
        f"-DEXPECTED_HELPER_SIZE={expected_helper.size_bytes}",
        f'-DEXPECTED_PYTHON_SHA256="{expected_python.sha256}"',
        f"-DEXPECTED_PYTHON_SIZE={expected_python.size_bytes}",
    ]
    return _compile_core_native_isolated(
        committed_source=committed_source,
        source_path=INITIAL_BOOTSTRAP_LAUNCHER_SOURCE,
        flags=flags,
        helper_pin=expected_helper,
        python_pin=expected_python,
        output_fd=output_fd,
        label="initial bootstrap launcher",
        failure_code="INITIAL_BOOTSTRAP_BUILD_FAILED",
        drift_code="INITIAL_BOOTSTRAP_BUILD_INPUT_DRIFT",
    )


def _compile_initial_bootstrap_installer(
    *,
    committed_source: bytes,
    launcher_pin: Mapping[str, Any],
    helper_pin: Mapping[str, Any],
    input_pin: Mapping[str, Any],
    output_fd: int,
) -> tuple[FilePin, dict[str, Any]]:
    """Build the finite-trust installer to one guarded, sealed output memfd."""

    if os.geteuid() == ROOT_UID:
        _fail("UNPRIVILEGED_REVIEW_REQUIRED", "initial bootstrap installer")
    expected_launcher = _parse_pin(launcher_pin, "initial bootstrap launcher")
    expected_helper = _parse_pin(helper_pin, "initial bootstrap helper")
    expected_input = _parse_pin(input_pin, "initial bootstrap input")
    flags = [
        "-std=c11",
        "-O2",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-static",
        "-s",
        "-Wl,--build-id=none",
        "-x",
        "c",
        f'-DEXPECTED_LAUNCHER_SHA256="{expected_launcher.sha256}"',
        f"-DEXPECTED_LAUNCHER_SIZE={expected_launcher.size_bytes}",
        f'-DEXPECTED_HELPER_SHA256="{expected_helper.sha256}"',
        f"-DEXPECTED_HELPER_SIZE={expected_helper.size_bytes}",
        f'-DEXPECTED_INPUT_PIN_SHA256="{expected_input.sha256}"',
        f"-DEXPECTED_INPUT_PIN_SIZE={expected_input.size_bytes}",
    ]
    output_pin, provenance = _compile_native_isolated(
        committed_source=committed_source,
        source_path=INITIAL_BOOTSTRAP_INSTALLER_SOURCE,
        flags=flags,
        output_fd=output_fd,
        label="initial bootstrap installer",
        failure_code="INITIAL_BOOTSTRAP_INSTALLER_BUILD_FAILED",
        drift_code="INITIAL_BOOTSTRAP_INSTALLER_BUILD_INPUT_DRIFT",
    )
    provenance["candidate_binding"] = {
        "root": str(INITIAL_BOOTSTRAP_REVIEW_CANDIDATE_ROOT),
        "root_mode": "0555",
        "launcher": expected_launcher.public(),
        "helper": expected_helper.public(),
        "input_pin": expected_input.public(),
    }
    return output_pin, provenance


def build_parent_seal_review_candidate() -> dict[str, Any]:
    """Reject the obsolete local native-candidate build path."""

    _fail(
        "DEDICATED_BUILDER_AUTHORITY_REQUIRED",
        "parent seal launcher is published only by native builder Phase A",
    )


def _buildplugin_admin_script(helper_pin: FilePin, python_pin: FilePin) -> bytes:
    publish_ack = (
        "I acknowledge one fresh publication of the reviewed VISTA R8 UE 5.7 "
        "BuildPlugin authority."
    )
    reconcile_ack = (
        "I acknowledge reconciliation of the existing VISTA R8 UE 5.7 "
        "BuildPlugin authority without republishing it."
    )
    return (
        "#!/bin/sh\n"
        "set -eu\n"
        f"SELF='{BUILDPLUGIN_ADMIN_INSTALL_PATH}'\n"
        f"HELPER='{BUILDPLUGIN_HELPER_INSTALL_PATH}'\n"
        f"PYTHON='{PYTHON_PATH}'\n"
        f"EXPECTED_HELPER_SHA256='{helper_pin.sha256}'\n"
        f"EXPECTED_HELPER_BYTES='{helper_pin.size_bytes}'\n"
        f"EXPECTED_PYTHON_SHA256='{python_pin.sha256}'\n"
        f"EXPECTED_PYTHON_BYTES='{python_pin.size_bytes}'\n"
        f"PUBLISH_ACK='{publish_ack}'\n"
        f"RECONCILE_ACK='{reconcile_ack}'\n"
        "fail() { printf '%s\\n' \"BUILDPLUGIN_ADMIN_FAILED: $*\" >&2; exit 2; }\n"
        "test \"$(/usr/bin/id -u)\" = 0 || fail 'root EUID required'\n"
        'test "$0" = "$SELF" || fail \'fixed wrapper path required\'\n'
        'exec 8<"$SELF"\n'
        'test "$(/usr/bin/stat -Lc \'%a:%u:%g:%h:%s\' "$SELF")" = '
        '"500:0:0:1:$(/usr/bin/stat -Lc %s "$SELF")" || '
        "fail 'wrapper metadata differs'\n"
        "test \"$(/usr/bin/stat -Lc '%d:%i:%s' /proc/self/fd/8)\" = "
        '"$(/usr/bin/stat -Lc \'%d:%i:%s\' "$SELF")" || '
        "fail 'held wrapper identity differs'\n"
        'test "$(/usr/bin/stat -Lc \'%a:%u:%g:%h:%s\' "$HELPER")" = '
        "\"500:0:0:1:$EXPECTED_HELPER_BYTES\" || fail 'helper metadata differs'\n"
        "LINE=$(/usr/bin/sha256sum \"$HELPER\") || fail 'helper hash failed'\n"
        'test "${LINE%% *}" = "$EXPECTED_HELPER_SHA256" || '
        "fail 'helper digest differs'\n"
        'exec 9<"$PYTHON"\n'
        "test \"$(/usr/bin/stat -Lc '%a:%u:%g:%h:%s' /proc/self/fd/9)\" = "
        "\"755:0:0:1:$EXPECTED_PYTHON_BYTES\" || fail 'Python metadata differs'\n"
        "LINE=$(/usr/bin/sha256sum /proc/self/fd/9) || fail 'Python hash failed'\n"
        'test "${LINE%% *}" = "$EXPECTED_PYTHON_SHA256" || '
        "fail 'Python digest differs'\n"
        "test \"$#\" = 2 || fail 'exact operation and acknowledgement required'\n"
        'case "$1" in\n'
        '  publish-buildplugin) test "$2" = "$PUBLISH_ACK" || '
        "fail 'publish acknowledgement differs'; MODE=--publish ;;\n"
        '  reconcile-buildplugin) test "$2" = "$RECONCILE_ACK" || '
        "fail 'reconcile acknowledgement differs'; MODE=--reconcile-published ;;\n"
        "  *) fail 'operation differs' ;;\n"
        "esac\n"
        "exec /usr/bin/env -i PATH=/usr/bin:/bin LANG=C.UTF-8 "
        '/proc/self/fd/9 -I -B "$HELPER" "$MODE" '
        '--acknowledgement "$2" --admin-launcher-fd 8\n'
    ).encode("utf-8")


def build_buildplugin_admin_review_candidate() -> dict[str, Any]:
    if os.geteuid() != REVIEW_UID or os.getegid() != REVIEW_GID:
        _fail("UNPRIVILEGED_REVIEW_REQUIRED", "BuildPlugin admin candidate")
    committed_sources = _require_unprivileged_review_helper()
    final = BUILDPLUGIN_ADMIN_REVIEW_CANDIDATE_ROOT
    if os.path.lexists(final):
        _fail("FINAL_NOT_FRESH", str(final))
    helper_relative = BUILDPLUGIN_HELPER_SOURCE.relative_to(CHECKOUT_ROOT).as_posix()
    helper_raw = committed_sources[helper_relative]
    helper_pin = FilePin(hashlib.sha256(helper_raw).hexdigest(), len(helper_raw))
    _python_raw, python_pin = _read_regular(
        PYTHON_PATH, "BuildPlugin admin Python", exact_mode=0o755
    )
    script_raw = _buildplugin_admin_script(helper_pin, python_pin)
    staging = Path(tempfile.mkdtemp(prefix=f".{final.name}.staging-", dir=final.parent))
    owner = (REVIEW_UID, REVIEW_GID)
    try:
        candidate_helper_pin = _write_new(
            staging / BUILDPLUGIN_HELPER_SOURCE.name,
            helper_raw,
            0o444,
            owner,
        )
        script_pin = _write_new(
            staging / BUILDPLUGIN_ADMIN_SCRIPT_NAME,
            script_raw,
            0o444,
            owner,
        )
        _seal_private_tree(staging, owner=owner)
        publish_staging(staging, final)
        return {
            "status": "user_published_buildplugin_admin_review_candidate",
            "accepted": False,
            "candidate_root": str(final),
            "helper_pin": candidate_helper_pin.public(),
            "admin_script_pin": script_pin.public(),
            "python_pin": python_pin.public(),
            "root_execution_performed": False,
        }
    finally:
        if os.path.lexists(staging):
            _remove_private_staging(staging)


def _engine_wrapper_review_bindings(
    raw: bytes,
    *,
    helper_pin: FilePin,
    source_pin: FilePin,
    python_pin: FilePin,
) -> dict[str, Any]:
    try:
        text = raw.decode("utf-8", "strict")
    except UnicodeError as exc:
        raise AuthorityError(
            "CORE_BOOTSTRAP_REVIEW_INVALID", "engine wrapper encoding"
        ) from exc
    if "REQUIRED" in text or "EXPECTED_" not in text:
        _fail("CORE_BOOTSTRAP_REVIEW_PENDING", "engine wrapper placeholders")
    assignments: dict[str, str] = {}
    for line in text.splitlines():
        match = re.fullmatch(r"([A-Z][A-Z0-9_]*)=(.*)", line)
        if match is not None:
            value = match.group(2)
            if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
                value = value[1:-1]
            assignments[match.group(1)] = value
    expected = {
        "SELF": str(INSTALLED_ENGINE_WRAPPER),
        "HELPER": str(INSTALLED_HELPER),
        "SOURCE_PIN": str(ENGINE_SOURCE_PIN_PATH),
        "PYTHON": str(PYTHON_PATH),
        "EXPECTED_HELPER_SHA256": helper_pin.sha256,
        "EXPECTED_HELPER_BYTES": str(helper_pin.size_bytes),
        "EXPECTED_SOURCE_PIN_SHA256": source_pin.sha256,
        "EXPECTED_SOURCE_PIN_BYTES": str(source_pin.size_bytes),
        "EXPECTED_PYTHON_SHA256": python_pin.sha256,
        "EXPECTED_PYTHON_BYTES": str(python_pin.size_bytes),
    }
    if any(assignments.get(name) != value for name, value in expected.items()):
        _fail("CORE_BOOTSTRAP_REVIEW_INVALID", "engine wrapper pin binding")
    if any(
        int(assignments[name]) <= 0
        for name in (
            "EXPECTED_HELPER_BYTES",
            "EXPECTED_SOURCE_PIN_BYTES",
            "EXPECTED_PYTHON_BYTES",
        )
    ):
        _fail("CORE_BOOTSTRAP_REVIEW_PENDING", "zero wrapper size")
    return expected


@dataclasses.dataclass
class HeldNativeBuilderPhase:
    stack: contextlib.ExitStack
    directory_fds: dict[str, int]
    directory_metadata: dict[str, os.stat_result]
    directory_paths: dict[str, Path]
    held_files: dict[str, HeldSourceFile]
    file_pins: dict[str, FilePin]
    component_chains: dict[str, tuple[Path, list[dict[str, Any]]]]

    def revalidate(self) -> None:
        for label, descriptor in self.directory_fds.items():
            metadata = self.directory_metadata[label]
            if _identity(os.fstat(descriptor)) != _identity(metadata) or _identity(
                os.stat(self.directory_paths[label], follow_symlinks=False)
            ) != _identity(metadata):
                _fail("NATIVE_BUILDER_AUTHORITY_DRIFT", label)
        for label, held in self.held_files.items():
            metadata = held.metadata
            digest, size = (
                _hash_kernel_virtual_sysctl_fd(held.descriptor)
                if held.canonical_path == NATIVE_BUILDER_KERNEL_VIRTUAL_SYSCTL_PATH
                else _hash_fd(held.descriptor)
            )
            if (
                _identity(os.fstat(held.descriptor)) != _identity(metadata)
                or (digest, size)
                != (
                    self.file_pins[label].sha256,
                    self.file_pins[label].size_bytes,
                )
                or _identity(os.stat(held.canonical_path, follow_symlinks=False))
                != _identity(metadata)
            ):
                _fail("NATIVE_BUILDER_AUTHORITY_DRIFT", label)
        for label, (path, expected) in self.component_chains.items():
            if _native_builder_live_component_chain(path, label) != expected:
                _fail("NATIVE_BUILDER_TRACE_INPUT_DRIFT", label)

    def close(self) -> None:
        for descriptor in self.directory_fds.values():
            os.close(descriptor)
        self.stack.close()


def _native_builder_read_held(
    authority: HeldNativeBuilderPhase,
    *,
    path: Path,
    mode: int,
    owner: tuple[int, int],
    maximum: int,
    label: str,
) -> tuple[bytes, FilePin]:
    held = authority.stack.enter_context(hold_source_file_components(path))
    info = held.metadata
    if (
        not stat.S_ISREG(info.st_mode)
        or stat.S_IMODE(info.st_mode) != mode
        or (info.st_uid, info.st_gid) != owner
        or info.st_nlink != 1
        or info.st_size <= 0
        or info.st_size > maximum
        or info.st_blocks * 512 < info.st_size
    ):
        _fail("NATIVE_BUILDER_AUTHORITY_INVALID", label)
    digest, size = _hash_fd(held.descriptor)
    pin = FilePin(digest, size, bool(mode & 0o111))
    os.lseek(held.descriptor, 0, os.SEEK_SET)
    blocks: list[bytes] = []
    remaining = size
    while remaining:
        block = os.read(held.descriptor, min(CHUNK_BYTES, remaining))
        if not block:
            _fail("NATIVE_BUILDER_AUTHORITY_DRIFT", label)
        blocks.append(block)
        remaining -= len(block)
    if os.read(held.descriptor, 1):
        _fail("NATIVE_BUILDER_AUTHORITY_DRIFT", label)
    os.lseek(held.descriptor, 0, os.SEEK_SET)
    authority.held_files[label] = held
    authority.file_pins[label] = pin
    return b"".join(blocks), pin


def _native_builder_directory(
    authority: HeldNativeBuilderPhase,
    *,
    path: Path,
    mode: int,
    owner: tuple[int, int],
    inventory: set[str] | None,
    label: str,
) -> int:
    descriptor = os.open(path, _directory_flags())
    info = os.fstat(descriptor)
    if (
        not stat.S_ISDIR(info.st_mode)
        or stat.S_IMODE(info.st_mode) != mode
        or (info.st_uid, info.st_gid) != owner
        or (inventory is not None and set(os.listdir(descriptor)) != inventory)
    ):
        os.close(descriptor)
        _fail("NATIVE_BUILDER_AUTHORITY_INVALID", label)
    authority.directory_fds[label] = descriptor
    authority.directory_metadata[label] = info
    authority.directory_paths[label] = path
    return descriptor


def _stdlib_require_static_elf(raw: bytes, label: str) -> None:
    """Reject PT_DYNAMIC/PT_INTERP without running a target or readelf."""

    if len(raw) < 52 or raw[:4] != b"\x7fELF" or raw[6] != 1:
        _fail("NATIVE_BUILDER_ARTIFACT_INVALID", f"{label} ELF ident")
    elf_class = raw[4]
    data = raw[5]
    if elf_class not in (1, 2) or data not in (1, 2):
        _fail("NATIVE_BUILDER_ARTIFACT_INVALID", f"{label} ELF format")
    endian = "<" if data == 1 else ">"
    if elf_class == 2:
        if len(raw) < 64:
            _fail("NATIVE_BUILDER_ARTIFACT_INVALID", f"{label} ELF64")
        program_offset = struct.unpack_from(f"{endian}Q", raw, 32)[0]
        entry_size = struct.unpack_from(f"{endian}H", raw, 54)[0]
        entry_count = struct.unpack_from(f"{endian}H", raw, 56)[0]
        minimum_size = 56
    else:
        program_offset = struct.unpack_from(f"{endian}I", raw, 28)[0]
        entry_size = struct.unpack_from(f"{endian}H", raw, 42)[0]
        entry_count = struct.unpack_from(f"{endian}H", raw, 44)[0]
        minimum_size = 32
    if (
        entry_count <= 0
        or entry_size < minimum_size
        or program_offset > len(raw)
        or entry_count > (len(raw) - program_offset) // entry_size
    ):
        _fail("NATIVE_BUILDER_ARTIFACT_INVALID", f"{label} program headers")
    for index in range(entry_count):
        entry_offset = program_offset + index * entry_size
        program_type = struct.unpack_from(f"{endian}I", raw, entry_offset)[0]
        if program_type in (2, 3):
            _fail("NATIVE_BUILDER_ARTIFACT_INVALID", f"{label} is dynamic")


def _require_native_builder_identity() -> None:
    try:
        account = pwd.getpwnam(NATIVE_BUILDER_NAME)
        group = grp.getgrnam(NATIVE_BUILDER_NAME)
    except KeyError as exc:
        raise AuthorityError("NATIVE_BUILDER_UNAVAILABLE", NATIVE_BUILDER_NAME) from exc
    if (
        account.pw_uid != NATIVE_BUILDER_UID
        or account.pw_gid != NATIVE_BUILDER_GID
        or account.pw_dir != str(NATIVE_BUILDER_ACCOUNT_HOME)
        or account.pw_shell != "/usr/sbin/nologin"
        or group.gr_gid != NATIVE_BUILDER_GID
        or group.gr_mem
        or any(
            NATIVE_BUILDER_NAME in candidate.gr_mem
            for candidate in grp.getgrall()
            if candidate.gr_gid != NATIVE_BUILDER_GID
        )
    ):
        _fail("NATIVE_BUILDER_IDENTITY_INVALID", NATIVE_BUILDER_NAME)
    for path in (Path("/etc/subuid"), Path("/etc/subgid")):
        raw, _pin = _read_regular(path, f"native builder {path.name}")
        for line in raw.decode("utf-8", "strict").splitlines():
            fields = line.split(":")
            if len(fields) != 3:
                _fail("NATIVE_BUILDER_IDENTITY_INVALID", path.name)
            try:
                start, count = int(fields[1]), int(fields[2])
            except ValueError as exc:
                raise AuthorityError(
                    "NATIVE_BUILDER_IDENTITY_INVALID", path.name
                ) from exc
            if fields[0] == NATIVE_BUILDER_NAME or start <= NATIVE_BUILDER_UID < (
                start + count
            ):
                _fail("NATIVE_BUILDER_IDENTITY_INVALID", path.name)


def _native_builder_component_record(
    path: Path, *, finite_kernel_virtual: bool = False
) -> dict[str, Any]:
    try:
        info = os.lstat(path)
    except OSError as exc:
        raise AuthorityError("NATIVE_BUILDER_TRACE_INPUT_DRIFT", str(path)) from exc
    if stat.S_ISREG(info.st_mode):
        kind = "regular"
    elif stat.S_ISDIR(info.st_mode):
        kind = "directory"
    elif stat.S_ISLNK(info.st_mode):
        kind = "symlink"
    else:
        _fail("NATIVE_BUILDER_TRACE_INPUT_DRIFT", str(path))
    record: dict[str, Any] = {
        "path": str(path),
        "kind": kind,
        "mode": f"{stat.S_IMODE(info.st_mode):04o}",
        "uid": info.st_uid,
        "gid": info.st_gid,
    }
    path_text = str(path)
    kernel_virtual_component = (
        finite_kernel_virtual
        and path_text in NATIVE_BUILDER_KERNEL_VIRTUAL_METADATA_VOLATILE_PATHS
    )
    if kernel_virtual_component:
        expected_kind = NATIVE_BUILDER_KERNEL_VIRTUAL_COMPONENT_KINDS[
            NATIVE_BUILDER_KERNEL_VIRTUAL_COMPONENT_PATHS.index(path_text)
        ]
        if kind != expected_kind:
            _fail("NATIVE_BUILDER_TRACE_INPUT_DRIFT", str(path))
        record["metadata_policy"] = NATIVE_BUILDER_KERNEL_VIRTUAL_COMPONENT_POLICY
        if path_text not in NATIVE_BUILDER_KERNEL_VIRTUAL_NLINK_VOLATILE_PATHS:
            record["nlink"] = info.st_nlink
    else:
        record.update(
            {
                "device": info.st_dev,
                "inode": info.st_ino,
                "nlink": info.st_nlink,
                "mtime_ns": info.st_mtime_ns,
                "ctime_ns": info.st_ctime_ns,
            }
        )
    if kind == "symlink":
        record["target"] = os.readlink(path)
    return record


def _native_builder_live_component_chain(
    path: Path, label: str
) -> list[dict[str, Any]]:
    if not path.is_absolute() or path.as_posix() != str(path):
        _fail("NATIVE_BUILDER_TRACE_INPUT_DRIFT", label)
    try:
        canonical = Path(os.path.realpath(path))
        finite_kernel_virtual = _native_builder_is_kernel_virtual_sysctl_target(
            path, canonical
        )
        chain = [
            _native_builder_component_record(
                Path("/"), finite_kernel_virtual=finite_kernel_virtual
            )
        ]
        current = Path("/")
        for part in path.parts[1:]:
            current /= part
            chain.append(
                _native_builder_component_record(
                    current, finite_kernel_virtual=finite_kernel_virtual
                )
            )
        current = Path("/")
        for part in canonical.parts[1:]:
            current /= part
            if all(item["path"] != str(current) for item in chain):
                chain.append(
                    _native_builder_component_record(
                        current, finite_kernel_virtual=finite_kernel_virtual
                    )
                )
        return chain
    except OSError as exc:
        raise AuthorityError("NATIVE_BUILDER_TRACE_INPUT_DRIFT", label) from exc


def _native_builder_validate_component_chain(
    value: Any, label: str, *, finite_kernel_virtual: bool = False
) -> list[dict[str, Any]]:
    if type(value) is not list or not value:
        _fail("NATIVE_BUILDER_TRACE_CONTRACT_INVALID", f"{label} chain")
    common = {
        "path",
        "kind",
        "mode",
        "uid",
        "gid",
        "device",
        "inode",
        "nlink",
        "mtime_ns",
        "ctime_ns",
    }
    kernel_virtual_base = {
        "path",
        "kind",
        "mode",
        "uid",
        "gid",
        "metadata_policy",
    }
    result: list[dict[str, Any]] = []
    paths: set[str] = set()
    seen_kernel_virtual_paths: set[str] = set()
    for item in value:
        if type(item) is not dict:
            _fail("NATIVE_BUILDER_TRACE_CONTRACT_INVALID", f"{label} component")
        path = item.get("path")
        is_kernel_virtual_component = (
            finite_kernel_virtual
            and type(path) is str
            and path in NATIVE_BUILDER_KERNEL_VIRTUAL_METADATA_VOLATILE_PATHS
        )
        kind = item.get("kind")
        if is_kernel_virtual_component:
            expected_fields = kernel_virtual_base | (
                set()
                if path in NATIVE_BUILDER_KERNEL_VIRTUAL_NLINK_VOLATILE_PATHS
                else {"nlink"}
            )
            expected_kind = NATIVE_BUILDER_KERNEL_VIRTUAL_COMPONENT_KINDS[
                NATIVE_BUILDER_KERNEL_VIRTUAL_COMPONENT_PATHS.index(path)
            ]
            if (
                set(item) != expected_fields
                or path in seen_kernel_virtual_paths
                or kind != expected_kind
                or item.get("metadata_policy")
                != NATIVE_BUILDER_KERNEL_VIRTUAL_COMPONENT_POLICY
            ):
                _fail(
                    "NATIVE_BUILDER_TRACE_CONTRACT_INVALID",
                    f"{label} kernel virtual component",
                )
            seen_kernel_virtual_paths.add(path)
        elif kind == "symlink":
            if set(item) != common | {"target"} or type(item.get("target")) is not str:
                _fail("NATIVE_BUILDER_TRACE_CONTRACT_INVALID", f"{label} symlink")
        elif kind not in {"regular", "directory"} or set(item) != common:
            _fail("NATIVE_BUILDER_TRACE_CONTRACT_INVALID", f"{label} kind")
        numeric_fields = ["uid", "gid"]
        if not is_kernel_virtual_component:
            numeric_fields.extend(("device", "inode", "nlink", "mtime_ns", "ctime_ns"))
        elif path not in NATIVE_BUILDER_KERNEL_VIRTUAL_NLINK_VOLATILE_PATHS:
            numeric_fields.append("nlink")
        if (
            type(path) is not str
            or not Path(path).is_absolute()
            or Path(path).as_posix() != path
            or path in paths
            or type(item.get("mode")) is not str
            or re.fullmatch(r"[0-7]{4}", item["mode"]) is None
            or any(
                type(item.get(key)) is not int or item[key] < 0
                for key in numeric_fields
            )
        ):
            _fail("NATIVE_BUILDER_TRACE_CONTRACT_INVALID", f"{label} values")
        paths.add(path)
        result.append(dict(item))
    if result[0]["path"] != "/" or result[0]["kind"] != "directory":
        _fail("NATIVE_BUILDER_TRACE_CONTRACT_INVALID", f"{label} root")
    expected_kernel_virtual_paths = (
        set(NATIVE_BUILDER_KERNEL_VIRTUAL_METADATA_VOLATILE_PATHS)
        if finite_kernel_virtual
        else set()
    )
    if seen_kernel_virtual_paths != expected_kernel_virtual_paths:
        _fail(
            "NATIVE_BUILDER_TRACE_CONTRACT_INVALID",
            f"{label} kernel virtual component policy",
        )
    return result


def _native_builder_component_chain_is_immutable_root_owned(
    chain: Sequence[Mapping[str, Any]],
) -> bool:
    return all(
        component.get("uid") == ROOT_UID
        and component.get("gid") == ROOT_GID
        and (
            component.get("kind") == "symlink"
            or (
                type(component.get("mode")) is str
                and int(component["mode"], 8) & 0o022 == 0
            )
        )
        for component in chain
    )


def _native_builder_deepest_existing_trace_directory(path: str) -> str:
    if not path.startswith("/"):
        _fail("NATIVE_BUILDER_TRACE_CONTRACT_INVALID", "search path")
    current = Path("/")
    deepest = current
    for part in PurePosixPath(path).parts[1:]:
        current /= part
        try:
            info = os.stat(current, follow_symlinks=True)
        except OSError as exc:
            if exc.errno in {errno.ENOENT, errno.ENOTDIR, errno.EACCES}:
                break
            raise AuthorityError(
                "NATIVE_BUILDER_TRACE_CONTRACT_INVALID", "search anchor"
            ) from exc
        if stat.S_ISDIR(info.st_mode):
            deepest = current
    chain = _native_builder_live_component_chain(deepest, "search anchor")
    if not _native_builder_component_chain_is_immutable_root_owned(chain):
        _fail("NATIVE_BUILDER_TRACE_CONTRACT_INVALID", "search anchor ownership")
    return str(deepest)


def _native_builder_expected_trace_invocations(
    phase: str,
) -> list[tuple[str, str]]:
    result = [
        ("python:builder-startup", "python"),
        ("git:init", "git"),
        ("git:fetch", "git"),
        ("git:rev-parse", "git"),
        *((f"git:cat-file:{path}", "git") for path in NATIVE_BUILDER_SOURCE_PATHS),
    ]
    jobs = (
        NATIVE_BUILDER_PHASE_A_JOB_IDS
        if phase == "phase-a"
        else NATIVE_BUILDER_PHASE_B_JOB_IDS
    )
    for job_id in jobs:
        for build_index in (1, 2):
            result.extend(
                (
                    (f"compiler:{job_id}:{build_index}", "compiler"),
                    (f"readelf:{job_id}:{build_index}", "readelf"),
                )
            )
    return result


def _native_builder_validate_trace_host_record(
    value: Any, label: str, *, kind: str
) -> dict[str, Any]:
    keys = {"path", "canonical", "component_chain"}
    if kind == "regular":
        keys |= {"mode", "pin", "storage"}
    if type(value) is not dict or set(value) != keys:
        _fail("NATIVE_BUILDER_TRACE_CONTRACT_INVALID", f"{label} fields")
    path = value.get("path")
    canonical = value.get("canonical")
    if (
        type(path) is not str
        or not Path(path).is_absolute()
        or "//" in path
        or (path != "/" and path.endswith("/"))
        or any(ord(character) < 0x20 for character in path)
        or type(canonical) is not str
        or not Path(canonical).is_absolute()
        or Path(canonical).as_posix() != canonical
    ):
        _fail(
            "NATIVE_BUILDER_TRACE_CONTRACT_INVALID",
            f"{label} path requested={path!r} canonical={canonical!r}",
        )
    finite_kernel_virtual = _native_builder_is_kernel_virtual_sysctl_target(
        path, canonical
    )
    if (
        _native_builder_path_is_procfs(path)
        or _native_builder_path_is_procfs(canonical)
    ) and not (kind == "regular" and finite_kernel_virtual):
        _fail(
            "NATIVE_BUILDER_TRACE_CONTRACT_INVALID",
            f"{label} unapproved procfs host input",
        )
    chain = _native_builder_validate_component_chain(
        value.get("component_chain"),
        label,
        finite_kernel_virtual=finite_kernel_virtual,
    )
    if finite_kernel_virtual and not (
        _native_builder_kernel_virtual_component_chain_is_exact(chain)
    ):
        _fail(
            "NATIVE_BUILDER_TRACE_CONTRACT_INVALID",
            f"{label} finite component sequence",
        )
    final = next((item for item in chain if item["path"] == canonical), None)
    if (
        final is None
        or final["kind"] != kind
        or final["uid"] != ROOT_UID
        or final["gid"] != ROOT_GID
        or (kind == "regular" and final["nlink"] != 1)
        or not _native_builder_component_chain_is_immutable_root_owned(chain)
    ):
        _fail("NATIVE_BUILDER_TRACE_CONTRACT_INVALID", f"{label} canonical")
    if kind == "regular":
        pin = _parse_pin(value.get("pin"), label)
        if (
            pin.size_bytes > MAX_NATIVE_BUILDER_TRACE_FILE_BYTES
            or value.get("mode") != final["mode"]
            or value.get("storage")
            not in {"empty", "regular", "sparse", "virtual", "kernel_virtual"}
            or (value.get("storage") == "virtual" and not canonical.startswith("/sys/"))
            or (
                finite_kernel_virtual
                and (
                    value.get("storage") != "kernel_virtual"
                    or value.get("mode") != "0644"
                    or pin not in _native_builder_kernel_virtual_sysctl_pins()
                )
            )
            or (value.get("storage") == "kernel_virtual" and not finite_kernel_virtual)
        ):
            _fail("NATIVE_BUILDER_TRACE_CONTRACT_INVALID", f"{label} storage")
    return dict(value)


def _native_builder_valid_trace_event(raw: str) -> bool:
    try:
        value = json.loads(
            raw,
            object_pairs_hook=_pairs,
            parse_constant=lambda token: (_ for _ in ()).throw(
                ValueError(f"nonfinite: {token}")
            ),
        )
    except (ValueError, TypeError):
        return False
    syscall = value.get("syscall") if type(value) is dict else None
    expected_fields = {"outcome", "paths", "syscall"}
    if syscall in NATIVE_BUILDER_TRACE_OPEN_SYSCALLS:
        expected_fields.add("open_flags")
    flags = value.get("open_flags") if type(value) is dict else None
    valid_open_flags = (
        type(flags) is list
        and bool(flags)
        and all(
            type(flag) is str and flag in NATIVE_BUILDER_TRACE_OPEN_FLAG_TOKENS
            for flag in flags
        )
        and len(flags) == len(set(flags))
        and sum(flag in NATIVE_BUILDER_TRACE_OPEN_ACCESS_MODES for flag in flags) == 1
    )
    if (
        type(value) is not dict
        or set(value) != expected_fields
        or syscall not in NATIVE_BUILDER_TRACE_FILE_SYSCALLS
        or value.get("outcome") not in ({"OK"} | NATIVE_BUILDER_TRACE_ALLOWED_ERRNOS)
        or type(value.get("paths")) is not list
        or not value["paths"]
        or any(type(path) is not str or not path for path in value["paths"])
        or (syscall in NATIVE_BUILDER_TRACE_OPEN_SYSCALLS and not valid_open_flags)
    ):
        return False
    if syscall in NATIVE_BUILDER_TRACE_OPEN_SYSCALLS and value["outcome"] == "OK":
        flag_set = set(flags)
        mutating = bool(
            flag_set & {"O_WRONLY", "O_RDWR", "O_CREAT", "O_TRUNC", "O_TMPFILE"}
        )
        if mutating:
            dev_null_allowed = "O_RDWR" in flag_set and flag_set <= (
                {"O_RDWR"} | NATIVE_BUILDER_TRACE_DEV_NULL_ALLOWED_NONMUTATING_FLAGS
            )
            if any(
                not (
                    path == "$SCRATCH"
                    or path.startswith("$SCRATCH/")
                    or (path == "/dev/null" and dev_null_allowed)
                )
                for path in value["paths"]
            ):
                return False
    return (
        json.dumps(
            value,
            ensure_ascii=True,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        == raw
    )


def _native_builder_kernel_virtual_open_flags_are_readonly(value: Any) -> bool:
    return (
        type(value) is list
        and bool(value)
        and "O_RDONLY" in value
        and len(value) == len(set(value))
        and all(
            flag == "O_RDONLY"
            or flag in NATIVE_BUILDER_KERNEL_VIRTUAL_ALLOWED_OPEN_FLAGS
            for flag in value
        )
    )


def _native_builder_validate_trace_events(
    value: Any, label: str
) -> list[dict[str, Any]]:
    if type(value) is not list or not value:
        _fail("NATIVE_BUILDER_TRACE_CONTRACT_INVALID", f"{label} events")
    previous = ""
    total = 0
    result: list[dict[str, Any]] = []
    for item in value:
        if (
            type(item) is not dict
            or set(item) != {"line", "count"}
            or type(item.get("line")) is not str
            or not item["line"]
            or "\n" in item["line"]
            or item["line"] <= previous
            or type(item.get("count")) is not int
            or item["count"] <= 0
            or (
                item["line"] == NATIVE_BUILDER_CPU_ONLINE_READ_EVENT_LINE
                and item["count"] != 1
            )
            or not _native_builder_valid_trace_event(item["line"])
        ):
            _fail("NATIVE_BUILDER_TRACE_CONTRACT_INVALID", f"{label} event")
        total += item["count"]
        if total > MAX_NATIVE_BUILDER_TRACE_LINES:
            _fail("NATIVE_BUILDER_TRACE_CONTRACT_INVALID", f"{label} event count")
        previous = item["line"]
        result.append(dict(item))
    return result


def _native_builder_validate_cpu_online_profile_binding(
    events: Sequence[Mapping[str, Any]],
    host_files: Sequence[str],
    label: str,
) -> bool:
    referenced = NATIVE_BUILDER_CPU_ONLINE_PATH in host_files
    observed = any(
        item["line"] == NATIVE_BUILDER_CPU_ONLINE_READ_EVENT_LINE for item in events
    )
    if observed and label != "git:fetch":
        _fail(
            "NATIVE_BUILDER_TRACE_CONTRACT_INVALID",
            f"{label} cpu online event profile",
        )
    if observed != referenced:
        _fail(
            "NATIVE_BUILDER_TRACE_CONTRACT_INVALID",
            f"{label} cpu online profile binding",
        )
    return observed


def _native_builder_validate_kernel_virtual_profile_binding(
    events: Sequence[Mapping[str, Any]],
    host_files: Sequence[str],
    label: str,
) -> bool:
    expected = str(NATIVE_BUILDER_KERNEL_VIRTUAL_SYSCTL_PATH)
    referenced = expected in host_files
    successful_read_open = False
    observed_event = False
    for item in events:
        event = json.loads(str(item["line"]), object_pairs_hook=_pairs)
        if expected not in event["paths"]:
            continue
        observed_event = True
        syscall = event["syscall"]
        if syscall not in NATIVE_BUILDER_KERNEL_VIRTUAL_READ_SYSCALLS:
            _fail(
                "NATIVE_BUILDER_TRACE_CONTRACT_INVALID",
                f"{label} kernel virtual syscall",
            )
        if syscall in NATIVE_BUILDER_TRACE_OPEN_SYSCALLS:
            if not _native_builder_kernel_virtual_open_flags_are_readonly(
                event.get("open_flags")
            ):
                _fail(
                    "NATIVE_BUILDER_TRACE_CONTRACT_INVALID",
                    f"{label} kernel virtual open flags",
                )
            if event["outcome"] == "OK":
                successful_read_open = True
    if observed_event and not referenced:
        _fail(
            "NATIVE_BUILDER_TRACE_CONTRACT_INVALID",
            f"{label} orphan kernel virtual event",
        )
    if referenced != successful_read_open:
        _fail(
            "NATIVE_BUILDER_TRACE_CONTRACT_INVALID",
            f"{label} kernel virtual profile binding",
        )
    return referenced


def _native_builder_validate_trace_searches(
    value: Any, label: str
) -> list[dict[str, Any]]:
    if type(value) is not list:
        _fail("NATIVE_BUILDER_TRACE_CONTRACT_INVALID", f"{label} searches")
    previous: tuple[str, str, str] | None = None
    result: list[dict[str, Any]] = []
    for item in value:
        if (
            type(item) is not dict
            or set(item) != {"syscall", "path", "errno", "count"}
            or item.get("syscall") not in NATIVE_BUILDER_TRACE_FILE_SYSCALLS
            or type(item.get("path")) is not str
            or not item["path"].startswith("/")
            or item.get("errno") not in NATIVE_BUILDER_TRACE_ALLOWED_ERRNOS
            or type(item.get("count")) is not int
            or item["count"] <= 0
        ):
            _fail("NATIVE_BUILDER_TRACE_CONTRACT_INVALID", f"{label} search")
        key = (item["syscall"], item["path"], item["errno"])
        if previous is not None and key <= previous:
            _fail("NATIVE_BUILDER_TRACE_CONTRACT_INVALID", f"{label} order")
        previous = key
        result.append(dict(item))
    return result


def _native_builder_validate_scratch_prestate(value: Any, label: str) -> None:
    if type(value) is not list:
        _fail("NATIVE_BUILDER_TRACE_CONTRACT_INVALID", f"{label} scratch prestate")
    previous = ""
    for record in value:
        if type(record) is not dict or record.get("kind") not in {
            "directory",
            "regular",
        }:
            _fail("NATIVE_BUILDER_TRACE_CONTRACT_INVALID", f"{label} scratch record")
        expected = {"relative_path", "kind", "mode"}
        if record["kind"] == "regular":
            expected.add("pin")
        relative = record.get("relative_path")
        if (
            set(record) != expected
            or type(relative) is not str
            or not _safe_relative(relative)
            or relative <= previous
            or type(record.get("mode")) is not str
            or re.fullmatch(r"[0-7]{4}", record["mode"]) is None
        ):
            _fail("NATIVE_BUILDER_TRACE_CONTRACT_INVALID", f"{label} scratch values")
        if record["kind"] == "regular":
            pin = _parse_pin(record.get("pin"), f"{label} scratch {relative}")
            if pin.size_bytes > MAX_NATIVE_BUILDER_TRACE_FILE_BYTES:
                _fail(
                    "NATIVE_BUILDER_TRACE_CONTRACT_INVALID",
                    f"{label} scratch pin",
                )
        previous = relative


def _native_builder_validate_trace_contract(value: Any) -> dict[str, Any]:
    if type(value) is not dict or set(value) != {
        "schema",
        "tracer_version",
        "host_files",
        "host_directories",
        "tracer_runtime_files",
        "builder_runtime_files",
        "path_aliases",
        "event_count_policies",
        "profiles",
        "phase_invocations",
    }:
        _fail("NATIVE_BUILDER_TRACE_CONTRACT_INVALID", "fields")
    if (
        value.get("schema") != NATIVE_BUILDER_TRACE_CONTRACT_SCHEMA
        or value.get("tracer_version") != NATIVE_BUILDER_STRACE_VERSION
    ):
        _fail("NATIVE_BUILDER_TRACE_CONTRACT_INVALID", "schema/version")
    _native_builder_validate_trace_event_count_policies(
        value.get("event_count_policies")
    )
    files = value.get("host_files")
    directories = value.get("host_directories")
    if type(files) is not list or not files or type(directories) is not list:
        _fail("NATIVE_BUILDER_TRACE_CONTRACT_INVALID", "host inventory")
    validated_files = [
        _native_builder_validate_trace_host_record(
            item, f"host file {index}", kind="regular"
        )
        for index, item in enumerate(files)
    ]
    validated_directories = [
        _native_builder_validate_trace_host_record(
            item, f"host directory {index}", kind="directory"
        )
        for index, item in enumerate(directories)
    ]
    file_paths = [item["path"] for item in validated_files]
    directory_paths = [item["path"] for item in validated_directories]
    if file_paths != sorted(set(file_paths)) or directory_paths != sorted(
        set(directory_paths)
    ):
        _fail("NATIVE_BUILDER_TRACE_CONTRACT_INVALID", "host order")

    def inode(record: Mapping[str, Any]) -> tuple[int, int] | None:
        if _native_builder_is_kernel_virtual_sysctl_target(
            record["path"], record["canonical"]
        ):
            # v5 closes this exact record's aliases after held-open inside the
            # review namespace; its cross-namespace inode is intentionally absent.
            return None
        final = next(
            item
            for item in record["component_chain"]
            if item["path"] == record["canonical"]
        )
        return final["device"], final["inode"]

    file_inodes = [inode(item) for item in validated_files]
    directory_inodes = [inode(item) for item in validated_directories]
    if {item for item in file_inodes if item is not None} & {
        item for item in directory_inodes if item is not None
    }:
        _fail("NATIVE_BUILDER_TRACE_CONTRACT_INVALID", "file/directory alias")
    alias_projection: list[dict[str, Any]] = []
    for kind, records in (
        ("regular", validated_files),
        ("directory", validated_directories),
    ):
        aliases: dict[str, list[dict[str, Any]]] = {}
        for record in records:
            aliases.setdefault(record["canonical"], []).append(record)
        for canonical, group in sorted(aliases.items()):
            if len(group) == 1:
                continue
            if any(
                record["path"] != canonical
                and not any(
                    component["kind"] == "symlink"
                    for component in record["component_chain"]
                )
                and ".." not in PurePosixPath(record["path"]).parts
                for record in group
            ):
                _fail("NATIVE_BUILDER_TRACE_CONTRACT_INVALID", "implicit path alias")
            alias_projection.append(
                {
                    "kind": kind,
                    "canonical": canonical,
                    "paths": sorted(record["path"] for record in group),
                }
            )
    alias_projection.sort(key=lambda item: (item["kind"], item["canonical"]))
    if value.get("path_aliases") != alias_projection:
        _fail("NATIVE_BUILDER_TRACE_CONTRACT_INVALID", "path aliases")
    for records, inodes in (
        (validated_files, file_inodes),
        (validated_directories, directory_inodes),
    ):
        observed: dict[tuple[int, int], str] = {}
        for record, identity in zip(records, inodes, strict=True):
            if identity is None:
                continue
            previous = observed.setdefault(identity, record["canonical"])
            if previous != record["canonical"]:
                _fail(
                    "NATIVE_BUILDER_TRACE_CONTRACT_INVALID",
                    "implicit hardlink or bind alias",
                )
    file_set = set(file_paths)
    kernel_virtual_path = str(NATIVE_BUILDER_KERNEL_VIRTUAL_SYSCTL_PATH)
    cpu_online_path = NATIVE_BUILDER_CPU_ONLINE_PATH
    runtime_sets: list[set[str]] = []
    for key in ("tracer_runtime_files", "builder_runtime_files"):
        paths = value.get(key)
        if (
            type(paths) is not list
            or not paths
            or paths != sorted(set(paths))
            or any(path not in file_set for path in paths)
            or kernel_virtual_path in paths
            or cpu_online_path in paths
        ):
            _fail("NATIVE_BUILDER_TRACE_CONTRACT_INVALID", key)
        runtime_sets.append(set(paths))
    expected_phase = {
        phase: [
            invocation
            for invocation, _tool in _native_builder_expected_trace_invocations(phase)
        ]
        for phase in ("phase-a", "phase-b")
    }
    if value.get("phase_invocations") != expected_phase:
        _fail("NATIVE_BUILDER_TRACE_CONTRACT_INVALID", "phase invocations")
    expected_tools = {
        invocation: tool
        for phase in ("phase-a", "phase-b")
        for invocation, tool in _native_builder_expected_trace_invocations(phase)
    }
    profiles = value.get("profiles")
    if type(profiles) is not list or len(profiles) != len(expected_tools):
        _fail("NATIVE_BUILDER_TRACE_CONTRACT_INVALID", "profiles")
    covered_files = set().union(*runtime_sets)
    covered_directories: set[str] = set()
    observed_ids: list[str] = []
    kernel_virtual_profile_seen = False
    cpu_online_profile_seen = False
    directory_set = set(directory_paths)
    for profile in profiles:
        if type(profile) is not dict or set(profile) != {
            "id",
            "tool",
            "event_multiset",
            "host_files",
            "host_directories",
            "search_state",
            "scratch_prestate",
        }:
            _fail("NATIVE_BUILDER_TRACE_CONTRACT_INVALID", "profile fields")
        profile_id = profile.get("id")
        if type(profile_id) is not str or expected_tools.get(profile_id) != profile.get(
            "tool"
        ):
            _fail("NATIVE_BUILDER_TRACE_CONTRACT_INVALID", "profile identity")
        events = _native_builder_validate_trace_events(
            profile.get("event_multiset"), profile_id
        )
        profile_files = profile.get("host_files")
        profile_directories = profile.get("host_directories")
        if (
            type(profile_files) is not list
            or profile_files != sorted(set(profile_files))
            or any(path not in file_set for path in profile_files)
            or type(profile_directories) is not list
            or profile_directories != sorted(set(profile_directories))
            or any(path not in directory_set for path in profile_directories)
        ):
            _fail("NATIVE_BUILDER_TRACE_CONTRACT_INVALID", profile_id)
        if _native_builder_validate_kernel_virtual_profile_binding(
            events, profile_files, profile_id
        ):
            kernel_virtual_profile_seen = True
        if _native_builder_validate_cpu_online_profile_binding(
            events, profile_files, profile_id
        ):
            cpu_online_profile_seen = True
        searches = _native_builder_validate_trace_searches(
            profile.get("search_state"), profile_id
        )
        for search in searches:
            anchor = _native_builder_deepest_existing_trace_directory(search["path"])
            if anchor not in profile_directories:
                _fail(
                    "NATIVE_BUILDER_TRACE_CONTRACT_INVALID",
                    f"{profile_id} search anchor",
                )
        _native_builder_validate_scratch_prestate(
            profile.get("scratch_prestate"), profile_id
        )
        covered_files.update(profile_files)
        covered_directories.update(profile_directories)
        observed_ids.append(profile_id)
    if observed_ids != sorted(expected_tools):
        _fail("NATIVE_BUILDER_TRACE_CONTRACT_INVALID", "profile order")
    if covered_files != file_set or covered_directories != directory_set:
        _fail("NATIVE_BUILDER_TRACE_CONTRACT_INVALID", "orphan host inputs")
    if (kernel_virtual_path in file_set) != kernel_virtual_profile_seen:
        _fail(
            "NATIVE_BUILDER_TRACE_CONTRACT_INVALID",
            "kernel virtual profile coverage",
        )
    if (cpu_online_path in file_set) != cpu_online_profile_seen:
        _fail(
            "NATIVE_BUILDER_TRACE_CONTRACT_INVALID",
            "cpu online profile coverage",
        )
    return dict(value)


def _native_builder_hold_trace_inputs(
    authority: HeldNativeBuilderPhase, contract: Mapping[str, Any]
) -> None:
    observed_file_inodes: dict[tuple[int, int], str] = {}
    for index, record in enumerate(contract["host_files"]):
        label = f"trace-file:{index}"
        requested = Path(record["path"])
        canonical = Path(record["canonical"])
        finite_kernel_virtual = _native_builder_is_kernel_virtual_sysctl_target(
            requested, canonical
        )
        expected_chain = list(record["component_chain"])
        if _native_builder_live_component_chain(requested, label) != expected_chain:
            _fail("NATIVE_BUILDER_TRACE_INPUT_DRIFT", label)
        descriptor = os.open(canonical, _file_flags())
        try:
            info = os.fstat(descriptor)
            sparse = info.st_size > 0 and info.st_blocks * 512 < info.st_size
            storage = (
                "kernel_virtual"
                if finite_kernel_virtual
                else "virtual"
                if str(canonical).startswith("/sys/") and (info.st_size == 0 or sparse)
                else "empty"
                if info.st_size == 0
                else "sparse"
                if sparse
                else "regular"
            )
            digest, size = (
                _hash_kernel_virtual_sysctl_fd(descriptor)
                if finite_kernel_virtual
                else _hash_fd(descriptor)
            )
            pin = FilePin(digest, size)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != ROOT_UID
                or info.st_gid != ROOT_GID
                or info.st_nlink != 1
                or stat.S_IMODE(info.st_mode) != int(record["mode"], 8)
                or (
                    finite_kernel_virtual
                    and (
                        stat.S_IMODE(info.st_mode) != 0o644
                        or info.st_size != 0
                        or pin not in _native_builder_kernel_virtual_sysctl_pins()
                    )
                )
                or storage != record["storage"]
                or pin != _parse_pin(record["pin"], label)
                or _identity(os.stat(canonical, follow_symlinks=False))
                != _identity(info)
            ):
                _fail("NATIVE_BUILDER_TRACE_INPUT_DRIFT", label)
            identity = (info.st_dev, info.st_ino)
            previous = observed_file_inodes.get(identity)
            if previous is not None and previous != record["canonical"]:
                _fail("NATIVE_BUILDER_TRACE_INPUT_ALIAS", record["path"])
            observed_file_inodes[identity] = record["canonical"]
            held = HeldSourceFile(requested, canonical, descriptor, info, ())
            authority.stack.callback(os.close, descriptor)
            authority.held_files[label] = held
            authority.file_pins[label] = pin
            authority.component_chains[label] = (requested, expected_chain)
        except BaseException:
            os.close(descriptor)
            raise
    observed_directory_inodes: dict[tuple[int, int], str] = {}
    for index, record in enumerate(contract["host_directories"]):
        label = f"trace-directory:{index}"
        requested = Path(record["path"])
        expected_chain = list(record["component_chain"])
        if _native_builder_live_component_chain(requested, label) != expected_chain:
            _fail("NATIVE_BUILDER_TRACE_INPUT_DRIFT", label)
        canonical = Path(record["canonical"])
        descriptor = os.open(canonical, _directory_flags())
        info = os.fstat(descriptor)
        if (
            not stat.S_ISDIR(info.st_mode)
            or info.st_uid != ROOT_UID
            or info.st_gid != ROOT_GID
            or _identity(os.stat(canonical, follow_symlinks=False)) != _identity(info)
        ):
            os.close(descriptor)
            _fail("NATIVE_BUILDER_TRACE_INPUT_DRIFT", label)
        identity = (info.st_dev, info.st_ino)
        previous = observed_directory_inodes.get(identity)
        if (
            previous is not None and previous != record["canonical"]
        ) or identity in observed_file_inodes:
            os.close(descriptor)
            _fail("NATIVE_BUILDER_TRACE_INPUT_ALIAS", record["path"])
        observed_directory_inodes[identity] = record["canonical"]
        authority.directory_fds[label] = descriptor
        authority.directory_metadata[label] = info
        authority.directory_paths[label] = canonical
        authority.component_chains[label] = (requested, expected_chain)


def _native_builder_trace_toolchain(
    contract: Mapping[str, Any],
) -> list[dict[str, Any]]:
    return [
        {key: record[key] for key in ("path", "canonical", "mode", "pin")}
        for record in contract["host_files"]
    ]


def _native_builder_job_tools(
    tools: Mapping[str, Any], trace_contract: Mapping[str, Any]
) -> dict[str, Any]:
    raw = canonical_json(trace_contract)
    return {
        "compiler": tools["compiler"],
        "readelf": tools["readelf"],
        "tracer": tools["tracer"],
        "toolchain": tools["toolchain"],
        "trace_contract": {
            "schema": NATIVE_BUILDER_TRACE_CONTRACT_SCHEMA,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "size_bytes": len(raw),
        },
    }


def _native_builder_tool(
    authority: HeldNativeBuilderPhase,
    value: Any,
    *,
    expected_path: Path,
    label: str,
) -> dict[str, Any]:
    if (
        type(value) is not dict
        or set(value) != {"path", "canonical", "pin", "mode"}
        or value.get("path") != str(expected_path)
        or value.get("mode") not in {"0644", "0755"}
    ):
        _fail("NATIVE_BUILDER_MANIFEST_INVALID", label)
    canonical = Path(os.path.realpath(expected_path))
    if value.get("canonical") != str(canonical):
        _fail("NATIVE_BUILDER_MANIFEST_INVALID", f"{label} canonical")
    _raw, pin = _native_builder_read_held(
        authority,
        path=canonical,
        mode=int(value["mode"], 8),
        owner=(ROOT_UID, ROOT_GID),
        maximum=MAX_JSON_BYTES,
        label=f"tool:{label}",
    )
    if pin.public() != _parse_pin(value.get("pin"), label).public():
        _fail("NATIVE_BUILDER_TOOL_DRIFT", label)
    return dict(value)


def _native_builder_expected_flags(
    job_id: str, bindings: Mapping[str, Any]
) -> list[str]:
    flags = [
        "-std=c11",
        "-O2",
        "-Wall",
        "-Wextra",
        "-Werror",
        "-static",
        "-s",
        "-Wl,--build-id=none",
        "-pipe",
        "-fno-use-linker-plugin",
        "-x",
        "c",
    ]
    names = (
        ("python_pin", "helper_pin")
        if job_id
        in {
            "stage-transfer-launcher",
            "parent-seal-launcher",
            "initial-bootstrap-launcher",
        }
        else ()
    )
    if job_id == "initial-bootstrap-installer":
        names = ("launcher_pin", "helper_pin", "input_pin")
    for name in names:
        pin = _parse_pin(bindings.get(name), f"{job_id} {name}")
        macro = (
            "INPUT_PIN" if name == "input_pin" else name.removesuffix("_pin").upper()
        )
        flags.extend(
            (
                f'-DEXPECTED_{macro}_SHA256="{pin.sha256}"',
                f"-DEXPECTED_{macro}_SIZE={pin.size_bytes}",
            )
        )
    return flags


def _native_builder_phase_a_jobs(
    request: Mapping[str, Any], source_pins: Mapping[str, FilePin], python_pin: FilePin
) -> dict[str, dict[str, Any]]:
    specifications = {
        "stage-transfer-launcher": (
            "tools/admin/vista_r8_ue57_stage_transfer_launcher.c",
            "transfer-r8-ue57-stage-installer",
            "tools/admin/vista_r8_ue57_authority_admin.py",
        ),
        "parent-seal-launcher": (
            "tools/admin/vista_authority_parent_seal_launcher.c",
            "launch-vista-authority-parent-seal",
            "tools/admin/vista_authority_parent_seal.py",
        ),
        "initial-bootstrap-launcher": (
            "tools/admin/vista_r8_ue57_initial_bootstrap_launcher.c",
            "bootstrap-r8-ue57-initial-authorities",
            "tools/admin/vista_r8_ue57_initial_bootstrap.py",
        ),
    }
    jobs = request.get("jobs")
    if type(jobs) is not list or len(jobs) != len(specifications):
        _fail("NATIVE_BUILDER_MANIFEST_INVALID", "phase A jobs")
    result: dict[str, dict[str, Any]] = {}
    for value, (job_id, (source, output, helper)) in zip(
        jobs, specifications.items(), strict=True
    ):
        if type(value) is not dict:
            _fail("NATIVE_BUILDER_MANIFEST_INVALID", f"job {job_id}")
        bindings = {
            "helper_pin": source_pins[helper].public(),
            "python_pin": python_pin.public(),
        }
        expected = {
            "id": job_id,
            "source_path": source,
            "output_name": output,
            "output_mode": "0555",
            "bindings": bindings,
            "flags": _native_builder_expected_flags(job_id, bindings),
        }
        if value != expected:
            _fail("NATIVE_BUILDER_MANIFEST_INVALID", f"job {job_id}")
        result[job_id] = expected
    return result


@contextlib.contextmanager
def _load_native_builder_phase_a(
    committed_sources: Mapping[str, bytes], *, python_pin: FilePin
) -> Iterable[dict[str, Any]]:
    _require_native_builder_identity()
    stack = contextlib.ExitStack()
    authority = HeldNativeBuilderPhase(stack, {}, {}, {}, {}, {}, {})
    try:
        expected_source_paths = tuple(
            sorted(
                {
                    path.relative_to(CHECKOUT_ROOT).as_posix()
                    for path in (
                        REVIEW_HELPER_SOURCE,
                        STAGE_TRANSFER_LAUNCHER_SOURCE,
                        PARENT_SEAL_HELPER_SOURCE,
                        PARENT_SEAL_LAUNCHER_SOURCE,
                        INITIAL_BOOTSTRAP_HELPER_SOURCE,
                        INITIAL_BOOTSTRAP_LAUNCHER_SOURCE,
                        INITIAL_BOOTSTRAP_INSTALLER_SOURCE,
                    )
                }
            )
        )
        source_pins = {
            path: FilePin(
                hashlib.sha256(committed_sources[path]).hexdigest(),
                len(committed_sources[path]),
            )
            for path in expected_source_paths
        }
        git_binding, current_sources = _require_unprivileged_review_binding()
        if any(
            current_sources[path] != committed_sources[path]
            for path in expected_source_paths
        ):
            _fail("NATIVE_BUILDER_GIT_MISMATCH", "current HEAD blobs")

        _native_builder_directory(
            authority,
            path=NATIVE_BUILDER_HOME,
            mode=0o555,
            owner=(ROOT_UID, ROOT_GID),
            inventory={"phase-a-slot", "phase-b-slot"},
            label="native builder state root",
        )
        phase_slot = NATIVE_BUILDER_PHASE_A_ROOT.parent
        _native_builder_directory(
            authority,
            path=phase_slot,
            mode=0o711,
            owner=(NATIVE_BUILDER_UID, NATIVE_BUILDER_GID),
            inventory={".build.lock", "published"},
            label="native builder phase A slot",
        )
        _native_builder_directory(
            authority,
            path=NATIVE_BUILDER_PHASE_A_ROOT,
            mode=0o555,
            owner=(NATIVE_BUILDER_UID, NATIVE_BUILDER_GID),
            inventory={
                "artifacts",
                "manifest.json",
                "manifests",
                "parent-seal-candidate",
            },
            label="native builder phase A root",
        )
        _native_builder_directory(
            authority,
            path=NATIVE_BUILDER_PHASE_A_ROOT / "artifacts",
            mode=0o555,
            owner=(NATIVE_BUILDER_UID, NATIVE_BUILDER_GID),
            inventory={
                "transfer-r8-ue57-stage-installer",
                "launch-vista-authority-parent-seal",
                "bootstrap-r8-ue57-initial-authorities",
            },
            label="native builder phase A artifacts",
        )
        _native_builder_directory(
            authority,
            path=NATIVE_BUILDER_PHASE_A_ROOT / "manifests",
            mode=0o555,
            owner=(NATIVE_BUILDER_UID, NATIVE_BUILDER_GID),
            inventory={
                "stage-transfer-launcher.json",
                "parent-seal-launcher.json",
                "initial-bootstrap-launcher.json",
            },
            label="native builder phase A manifests",
        )
        _native_builder_directory(
            authority,
            path=NATIVE_BUILDER_PHASE_A_PARENT_SEAL_ROOT,
            mode=0o555,
            owner=(NATIVE_BUILDER_UID, NATIVE_BUILDER_GID),
            inventory={
                PARENT_SEAL_HELPER_SOURCE.name,
                PARENT_SEAL_LAUNCHER_NAME,
            },
            label="native builder phase A parent seal candidate",
        )
        manifest_raw, manifest_pin = _native_builder_read_held(
            authority,
            path=NATIVE_BUILDER_PHASE_A_ROOT / "manifest.json",
            mode=0o444,
            owner=(NATIVE_BUILDER_UID, NATIVE_BUILDER_GID),
            maximum=MAX_JSON_BYTES,
            label="phase A manifest",
        )
        request_raw, request_pin = _native_builder_read_held(
            authority,
            path=NATIVE_BUILDER_PHASE_A_REQUEST,
            mode=0o444,
            owner=(ROOT_UID, ROOT_GID),
            maximum=MAX_JSON_BYTES,
            label="phase A request",
        )
        bundle_raw, bundle_pin = _native_builder_read_held(
            authority,
            path=NATIVE_BUILDER_BUNDLE,
            mode=0o444,
            owner=(ROOT_UID, ROOT_GID),
            maximum=MAX_NATIVE_BUILDER_BUNDLE_BYTES,
            label="source Git bundle",
        )
        builder_raw, builder_pin = _native_builder_read_held(
            authority,
            path=NATIVE_BUILDER_HELPER,
            mode=0o444,
            owner=(ROOT_UID, ROOT_GID),
            maximum=MAX_JSON_BYTES,
            label="installed native builder",
        )
        unit_raw, unit_pin = _native_builder_read_held(
            authority,
            path=NATIVE_BUILDER_PHASE_A_UNIT,
            mode=0o644,
            owner=(ROOT_UID, ROOT_GID),
            maximum=MAX_JSON_BYTES,
            label="phase A systemd unit",
        )
        request = strict_json(request_raw, "native builder phase A request")
        if (
            set(request)
            != {
                "schema",
                "phase",
                "status",
                "accepted",
                "builder",
                "source_bundle",
                "source_commit",
                "sources",
                "tools",
                "trace_contract",
                "jobs",
                "phase_inputs",
                "claims",
                "content_digest",
            }
            or request.get("schema") != NATIVE_BUILDER_REQUEST_SCHEMA
            or request.get("phase") != "phase-a"
            or request.get("status") != "reviewed_native_build_request"
            or request.get("accepted") is not False
            or request.get("content_digest") != content_digest(request)
            or request.get("source_commit") != git_binding["commit"]
            or request.get("phase_inputs") != {}
            or request.get("claims")
            != {
                "dedicated_builder_uid_gid": [
                    NATIVE_BUILDER_UID,
                    NATIVE_BUILDER_GID,
                ],
                "network_access": False,
                "double_build_required": True,
                "worktree_or_user_candidate_input": False,
                "write_root": str(NATIVE_BUILDER_HOME),
                "observation_only": True,
                "production_native_output": False,
            }
        ):
            _fail("NATIVE_BUILDER_MANIFEST_INVALID", "phase A request fields")
        if request.get("builder") != {
            "path": str(NATIVE_BUILDER_HELPER),
            "mode": "0444",
            "uid": ROOT_UID,
            "gid": ROOT_GID,
            "pin": builder_pin.public(),
            "service_unit": {
                "path": str(NATIVE_BUILDER_PHASE_A_UNIT),
                "mode": "0644",
                "uid": ROOT_UID,
                "gid": ROOT_GID,
                "pin": unit_pin.public(),
            },
        } or request.get("source_bundle") != {
            "path": str(NATIVE_BUILDER_BUNDLE),
            "mode": "0444",
            "uid": ROOT_UID,
            "gid": ROOT_GID,
            "pin": bundle_pin.public(),
        }:
            _fail("NATIVE_BUILDER_MANIFEST_INVALID", "phase A fixed inputs")
        source_records = request.get("sources")
        if source_records != [
            {"path": path, "pin": source_pins[path].public()}
            for path in expected_source_paths
        ]:
            _fail("NATIVE_BUILDER_GIT_MISMATCH", "source records")

        trace_contract = _native_builder_validate_trace_contract(
            request.get("trace_contract")
        )
        _native_builder_hold_trace_inputs(authority, trace_contract)
        tools = request.get("tools")
        if type(tools) is not dict or set(tools) != {
            "python",
            "git",
            "compiler",
            "readelf",
            "tracer",
            "toolchain",
        }:
            _fail("NATIVE_BUILDER_MANIFEST_INVALID", "phase A tools")
        expected_tool_paths = {
            "python": PYTHON_PATH,
            "git": Path("/usr/bin/git"),
            "compiler": COMPILER_PATH,
            "readelf": READELF_PATH,
            "tracer": STRACE_PATH,
        }
        validated_tools = {
            key: _native_builder_tool(
                authority, tools[key], expected_path=path, label=key
            )
            for key, path in expected_tool_paths.items()
        }
        if validated_tools["python"]["pin"] != python_pin.public():
            _fail("NATIVE_BUILDER_TOOL_DRIFT", "Python")
        ledger = tools.get("toolchain")
        expected_ledger = _native_builder_trace_toolchain(trace_contract)
        if ledger != expected_ledger:
            _fail("NATIVE_BUILDER_MANIFEST_INVALID", "toolchain")
        host_files = trace_contract["host_files"]
        for key, tool in validated_tools.items():
            matches = [
                record
                for record in host_files
                if record["canonical"] == tool["canonical"]
                and record["pin"] == tool["pin"]
                and record["mode"] == tool["mode"]
            ]
            if not matches:
                _fail("NATIVE_BUILDER_MANIFEST_INVALID", f"trace tool {key}")
        for key, runtime_key in (
            ("python", "builder_runtime_files"),
            ("tracer", "tracer_runtime_files"),
        ):
            if not any(
                record["path"] in trace_contract[runtime_key]
                and record["canonical"] == validated_tools[key]["canonical"]
                and record["pin"] == validated_tools[key]["pin"]
                for record in host_files
            ):
                _fail("NATIVE_BUILDER_MANIFEST_INVALID", f"trace runtime {key}")
        job_tools = _native_builder_job_tools(tools, trace_contract)
        jobs = _native_builder_phase_a_jobs(request, source_pins, python_pin)
        manifest = strict_json(manifest_raw, "native builder phase A manifest")
        if (
            set(manifest)
            != {
                "schema",
                "status",
                "accepted",
                "phase",
                "request_pin",
                "source_commit",
                "source_bundle_pin",
                "jobs",
                "inventory",
                "claims",
                "content_digest",
            }
            or manifest.get("schema") != NATIVE_BUILDER_PHASE_A_SCHEMA
            or manifest.get("status") != "dedicated_builder_phase_closed"
            or manifest.get("accepted") is not False
            or manifest.get("phase") != "phase-a"
            or manifest.get("content_digest") != content_digest(manifest)
            or manifest.get("request_pin") != request_pin.public()
            or manifest.get("source_commit") != request["source_commit"]
            or manifest.get("source_bundle_pin") != bundle_pin.public()
            or manifest.get("claims")
            != {
                "builder_uid_gid": [NATIVE_BUILDER_UID, NATIVE_BUILDER_GID],
                "network_access": False,
                "double_build_verified": True,
                "worktree_or_user_candidate_input": False,
                "closed": True,
            }
        ):
            _fail("NATIVE_BUILDER_MANIFEST_INVALID", "phase A manifest fields")
        manifest_jobs = manifest.get("jobs")
        if type(manifest_jobs) is not list or len(manifest_jobs) != len(jobs):
            _fail("NATIVE_BUILDER_MANIFEST_INVALID", "phase A manifest jobs")
        raw_by_key: dict[str, bytes] = {}
        pins_by_key: dict[str, FilePin] = {}
        provenance: dict[str, Any] = {}
        artifact_inventory: list[dict[str, Any]] = []
        job_manifest_inventory: list[dict[str, Any]] = []
        legacy_keys = {
            "stage-transfer-launcher": "stage-transfer",
            "parent-seal-launcher": "parent-seal",
            "initial-bootstrap-launcher": "initial-launcher",
        }
        for job_id, job_document in zip(jobs, manifest_jobs, strict=True):
            expected_job = jobs[job_id]
            if (
                type(job_document) is not dict
                or set(job_document)
                != {
                    "schema",
                    "status",
                    "accepted",
                    "phase",
                    "job_id",
                    "source",
                    "bindings",
                    "flags",
                    "environment",
                    "tools",
                    "output",
                    "determinism",
                    "static_elf",
                    "claims",
                    "content_digest",
                }
                or job_document.get("schema") != NATIVE_BUILDER_JOB_SCHEMA
                or job_document.get("status") != "deterministic_static_native_closed"
                or job_document.get("accepted") is not False
                or job_document.get("phase") != "phase-a"
                or job_document.get("job_id") != job_id
                or job_document.get("content_digest") != content_digest(job_document)
                or job_document.get("bindings") != expected_job["bindings"]
                or job_document.get("flags") != expected_job["flags"]
                or job_document.get("environment") != NATIVE_BUILDER_BUILD_ENVIRONMENT
                or job_document.get("tools") != job_tools
                or job_document.get("static_elf")
                != {
                    "interpreter": None,
                    "needed": [],
                    "readelf_pin": tools["readelf"]["pin"],
                }
                or job_document.get("claims")
                != {
                    "builder_uid_gid": [
                        NATIVE_BUILDER_UID,
                        NATIVE_BUILDER_GID,
                    ],
                    "network_access": False,
                    "worktree_input": False,
                    "user_candidate_input": False,
                }
            ):
                _fail("NATIVE_BUILDER_MANIFEST_INVALID", f"job {job_id}")
            source = job_document.get("source")
            if source != {
                "git_bundle_pin": bundle_pin.public(),
                "commit": request["source_commit"],
                "git_path": expected_job["source_path"],
                "pin": source_pins[expected_job["source_path"]].public(),
                "compiled_from_sealed_memfd": True,
            }:
                _fail("NATIVE_BUILDER_GIT_MISMATCH", f"job {job_id}")
            output = job_document.get("output")
            expected_relative = f"artifacts/{expected_job['output_name']}"
            if (
                type(output) is not dict
                or set(output) != {"relative_path", "mode", "pin"}
                or output.get("relative_path") != expected_relative
                or output.get("mode") != "0555"
            ):
                _fail("NATIVE_BUILDER_MANIFEST_INVALID", f"job {job_id} output")
            artifact_raw, artifact_pin = _native_builder_read_held(
                authority,
                path=NATIVE_BUILDER_PHASE_A_ROOT / expected_relative,
                mode=0o555,
                owner=(NATIVE_BUILDER_UID, NATIVE_BUILDER_GID),
                maximum=MAX_JSON_BYTES,
                label=f"artifact:{job_id}",
            )
            if output.get("pin") != artifact_pin.public():
                _fail("NATIVE_BUILDER_ARTIFACT_INVALID", job_id)
            _stdlib_require_static_elf(artifact_raw, job_id)
            if job_document.get("determinism") != {
                "build_count": 2,
                "byte_identical": True,
                "first_pin": artifact_pin.public(),
                "second_pin": artifact_pin.public(),
            }:
                _fail("NATIVE_BUILDER_MANIFEST_INVALID", f"job {job_id} determinism")
            job_raw, job_pin = _native_builder_read_held(
                authority,
                path=NATIVE_BUILDER_PHASE_A_ROOT / "manifests" / f"{job_id}.json",
                mode=0o444,
                owner=(NATIVE_BUILDER_UID, NATIVE_BUILDER_GID),
                maximum=MAX_JSON_BYTES,
                label=f"job-manifest:{job_id}",
            )
            if strict_json(job_raw, f"job manifest {job_id}") != job_document:
                _fail("NATIVE_BUILDER_MANIFEST_INVALID", f"job file {job_id}")
            key = legacy_keys[job_id]
            raw_by_key[key] = artifact_raw
            pins_by_key[key] = FilePin(
                artifact_pin.sha256, artifact_pin.size_bytes, True
            )
            provenance[key] = {
                "schema": "vista.r8-native-builder-artifact-provenance/v1",
                "authority": {
                    "root": str(NATIVE_BUILDER_PHASE_A_ROOT),
                    "uid": NATIVE_BUILDER_UID,
                    "gid": NATIVE_BUILDER_GID,
                    "manifest_pin": manifest_pin.public(),
                    "manifest_content_digest": manifest["content_digest"],
                    "request_pin": request_pin.public(),
                    "source_bundle_pin": bundle_pin.public(),
                    "builder_pin": builder_pin.public(),
                    "service_unit_pin": unit_pin.public(),
                    "trace_contract": job_tools["trace_contract"],
                },
                "job": job_document,
                "job_manifest_pin": job_pin.public(),
            }
            artifact_inventory.append(
                {
                    "job_id": job_id,
                    "relative_path": expected_relative,
                    "mode": "0555",
                    "pin": artifact_pin.public(),
                }
            )
            job_manifest_inventory.append(
                {
                    "job_id": job_id,
                    "relative_path": f"manifests/{job_id}.json",
                    "pin": job_pin.public(),
                    "content_digest": job_document["content_digest"],
                }
            )
        parent_helper_relative = PARENT_SEAL_HELPER_SOURCE.relative_to(
            CHECKOUT_ROOT
        ).as_posix()
        parent_helper_raw, parent_helper_pin = _native_builder_read_held(
            authority,
            path=(
                NATIVE_BUILDER_PHASE_A_PARENT_SEAL_ROOT / PARENT_SEAL_HELPER_SOURCE.name
            ),
            mode=0o444,
            owner=(NATIVE_BUILDER_UID, NATIVE_BUILDER_GID),
            maximum=MAX_JSON_BYTES,
            label="phase A parent seal helper candidate",
        )
        parent_launcher_raw, parent_launcher_pin = _native_builder_read_held(
            authority,
            path=(NATIVE_BUILDER_PHASE_A_PARENT_SEAL_ROOT / PARENT_SEAL_LAUNCHER_NAME),
            mode=0o555,
            owner=(NATIVE_BUILDER_UID, NATIVE_BUILDER_GID),
            maximum=MAX_JSON_BYTES,
            label="phase A parent seal launcher candidate",
        )
        if (
            parent_helper_raw != committed_sources[parent_helper_relative]
            or parent_helper_pin != source_pins[parent_helper_relative]
            or parent_launcher_raw != raw_by_key["parent-seal"]
            or parent_launcher_pin.public() != pins_by_key["parent-seal"].public()
        ):
            _fail("NATIVE_BUILDER_ARTIFACT_INVALID", "parent seal candidate")
        parent_candidate_inventory = {
            "relative_path": "parent-seal-candidate",
            "files": [
                {
                    "name": PARENT_SEAL_HELPER_SOURCE.name,
                    "mode": "0444",
                    "pin": parent_helper_pin.public(),
                    "git_path": parent_helper_relative,
                },
                {
                    "name": PARENT_SEAL_LAUNCHER_NAME,
                    "mode": "0555",
                    "pin": parent_launcher_pin.public(),
                    "job_id": "parent-seal-launcher",
                },
            ],
        }
        if manifest.get("inventory") != {
            "root_entries": [
                "artifacts",
                "manifest.json",
                "manifests",
                "parent-seal-candidate",
            ],
            "artifacts": artifact_inventory,
            "manifests": job_manifest_inventory,
            "parent_seal_candidate": parent_candidate_inventory,
        }:
            _fail("NATIVE_BUILDER_MANIFEST_INVALID", "phase A aggregate inventory")
        authority.revalidate()
        yield {
            "raw": raw_by_key,
            "pins": pins_by_key,
            "provenance": provenance,
            "manifest": manifest,
            "manifest_pin": manifest_pin,
            "request": request,
            "request_pin": request_pin,
            "trace_contract_summary": job_tools["trace_contract"],
            "parent_candidate_root": NATIVE_BUILDER_PHASE_A_PARENT_SEAL_ROOT,
            "parent_helper_raw": parent_helper_raw,
            "parent_helper_pin": parent_helper_pin,
            "parent_launcher_raw": parent_launcher_raw,
            "parent_launcher_pin": FilePin(
                parent_launcher_pin.sha256,
                parent_launcher_pin.size_bytes,
                True,
            ),
            "authority": authority,
        }
        authority.revalidate()
    finally:
        authority.close()


def _validated_phase_a_candidate_materials(
    committed_sources: Mapping[str, bytes],
    *,
    python_pin: FilePin,
    parent_helper_raw: bytes,
    parent_helper_pin: FilePin,
) -> dict[str, Any]:
    with _load_native_builder_phase_a(
        committed_sources, python_pin=python_pin
    ) as builder_phase_a:
        transfer_raw = builder_phase_a["raw"]["stage-transfer"]
        transfer_pin = builder_phase_a["pins"]["stage-transfer"]
        if (
            builder_phase_a["parent_helper_raw"] != parent_helper_raw
            or builder_phase_a["parent_helper_pin"] != parent_helper_pin
            or builder_phase_a["parent_launcher_raw"]
            != builder_phase_a["raw"]["parent-seal"]
            or builder_phase_a["parent_launcher_pin"].public()
            != builder_phase_a["pins"]["parent-seal"].public()
        ):
            _fail("CORE_BOOTSTRAP_REVIEW_INVALID", "parent seal builder mismatch")
        _stdlib_require_static_elf(transfer_raw, "stage transfer launcher")
        _stdlib_require_static_elf(
            builder_phase_a["parent_launcher_raw"], "parent seal launcher"
        )
        builder_phase_a["authority"].revalidate()
        return {
            "transfer_raw": transfer_raw,
            "transfer_pin": transfer_pin,
            "transfer_build_provenance": builder_phase_a["provenance"][
                "stage-transfer"
            ],
            "parent_candidate_root": builder_phase_a["parent_candidate_root"],
            "parent_helper_candidate_pin": builder_phase_a["parent_helper_pin"],
            "parent_launcher_pin": builder_phase_a["parent_launcher_pin"],
            "parent_build_provenance": builder_phase_a["provenance"]["parent-seal"],
            "initial_launcher_raw": builder_phase_a["raw"]["initial-launcher"],
            "initial_launcher_pin": builder_phase_a["pins"]["initial-launcher"],
            "initial_launcher_build_provenance": builder_phase_a["provenance"][
                "initial-launcher"
            ],
            "phase_a_manifest": builder_phase_a["manifest"],
            "phase_a_manifest_pin": builder_phase_a["manifest_pin"],
            "phase_a_request": builder_phase_a["request"],
            "phase_a_request_pin": builder_phase_a["request_pin"],
            "phase_a_trace_contract": builder_phase_a["trace_contract_summary"],
        }


def _core_bootstrap_review_materials(
    committed_sources: Mapping[str, bytes], *, require_core_candidate: bool
) -> dict[str, Any]:
    helper_relative = REVIEW_HELPER_SOURCE.relative_to(CHECKOUT_ROOT).as_posix()
    wrapper_relative = ENGINE_WRAPPER_SOURCE.relative_to(CHECKOUT_ROOT).as_posix()
    parent_helper_relative = PARENT_SEAL_HELPER_SOURCE.relative_to(
        CHECKOUT_ROOT
    ).as_posix()
    buildplugin_helper_relative = BUILDPLUGIN_HELPER_SOURCE.relative_to(
        CHECKOUT_ROOT
    ).as_posix()
    helper_raw = committed_sources[helper_relative]
    wrapper_raw = committed_sources[wrapper_relative]
    parent_helper_raw = committed_sources[parent_helper_relative]
    buildplugin_helper_raw = committed_sources[buildplugin_helper_relative]
    helper_pin = FilePin(hashlib.sha256(helper_raw).hexdigest(), len(helper_raw))
    parent_helper_pin = FilePin(
        hashlib.sha256(parent_helper_raw).hexdigest(), len(parent_helper_raw)
    )
    buildplugin_helper_pin = FilePin(
        hashlib.sha256(buildplugin_helper_raw).hexdigest(),
        len(buildplugin_helper_raw),
    )
    _python_raw, python_pin = _read_regular(
        PYTHON_PATH, "core bootstrap Python", exact_mode=0o755
    )

    engine_pin_root = ENGINE_SOURCE_PIN_REVIEW_CANDIDATE.parent
    _require_user_review_candidate(
        engine_pin_root,
        {ENGINE_SOURCE_PIN_REVIEW_CANDIDATE: 0o444},
        "engine source pin review candidate",
    )
    engine_document, engine_pin = load_sealed_document(
        ENGINE_SOURCE_PIN_REVIEW_CANDIDATE,
        ENGINE_SOURCE_PIN_SCHEMA,
        "engine source pin review candidate",
    )
    if engine_document.get("publisher_python_pin") != python_pin.public():
        _fail("CORE_BOOTSTRAP_REVIEW_INVALID", "engine source Python pin")

    builder_materials = _validated_phase_a_candidate_materials(
        committed_sources,
        python_pin=python_pin,
        parent_helper_raw=parent_helper_raw,
        parent_helper_pin=parent_helper_pin,
    )
    transfer_raw = builder_materials["transfer_raw"]
    transfer_pin = builder_materials["transfer_pin"]
    transfer_build_provenance = builder_materials["transfer_build_provenance"]
    parent_helper_candidate_pin = builder_materials["parent_helper_candidate_pin"]
    parent_launcher_pin = builder_materials["parent_launcher_pin"]
    parent_build_provenance = builder_materials["parent_build_provenance"]

    buildplugin_helper_candidate = (
        BUILDPLUGIN_ADMIN_REVIEW_CANDIDATE_ROOT / BUILDPLUGIN_HELPER_SOURCE.name
    )
    buildplugin_script_candidate = (
        BUILDPLUGIN_ADMIN_REVIEW_CANDIDATE_ROOT / BUILDPLUGIN_ADMIN_SCRIPT_NAME
    )
    _require_user_review_candidate(
        BUILDPLUGIN_ADMIN_REVIEW_CANDIDATE_ROOT,
        {
            buildplugin_helper_candidate: 0o444,
            buildplugin_script_candidate: 0o444,
        },
        "BuildPlugin admin review candidate",
    )
    live_buildplugin_helper, buildplugin_helper_candidate_pin = _read_regular(
        buildplugin_helper_candidate,
        "BuildPlugin helper candidate",
        exact_mode=0o444,
    )
    buildplugin_script_raw, buildplugin_script_pin = _read_regular(
        buildplugin_script_candidate,
        "BuildPlugin admin script candidate",
        exact_mode=0o444,
    )
    if (
        live_buildplugin_helper != buildplugin_helper_raw
        or buildplugin_script_raw
        != _buildplugin_admin_script(buildplugin_helper_pin, python_pin)
    ):
        _fail("CORE_BOOTSTRAP_REVIEW_INVALID", "BuildPlugin candidate binding")

    wrapper_bindings = _engine_wrapper_review_bindings(
        wrapper_raw,
        helper_pin=helper_pin,
        source_pin=engine_pin,
        python_pin=python_pin,
    )
    result: dict[str, Any] = {
        "engine_source_pin": {
            "path": str(ENGINE_SOURCE_PIN_REVIEW_CANDIDATE),
            "pin": engine_pin.public(),
            "content_digest": engine_document["content_digest"],
        },
        "helper_pin": helper_pin.public(),
        "engine_wrapper_pin": FilePin(
            hashlib.sha256(wrapper_raw).hexdigest(), len(wrapper_raw)
        ).public(),
        "engine_wrapper_bindings": wrapper_bindings,
        "python_pin": python_pin.public(),
        "stage_transfer_launcher": {
            "pin": transfer_pin.public(),
            "build_provenance": transfer_build_provenance,
        },
        "initial_bootstrap_launcher": {
            "pin": builder_materials["initial_launcher_pin"].public(),
            "build_provenance": builder_materials["initial_launcher_build_provenance"],
        },
        "native_builder_phase_a": {
            "root": str(NATIVE_BUILDER_PHASE_A_ROOT),
            "manifest_pin": builder_materials["phase_a_manifest_pin"].public(),
            "manifest_content_digest": builder_materials["phase_a_manifest"][
                "content_digest"
            ],
            "request_pin": builder_materials["phase_a_request_pin"].public(),
            "request_content_digest": builder_materials["phase_a_request"][
                "content_digest"
            ],
            "source_bundle": builder_materials["phase_a_request"]["source_bundle"],
            "source_commit": builder_materials["phase_a_request"]["source_commit"],
            "sources": builder_materials["phase_a_request"]["sources"],
            "builder": builder_materials["phase_a_request"]["builder"],
            "trace_contract": builder_materials["phase_a_trace_contract"],
        },
        "parent_seal": {
            "candidate_root": str(builder_materials["parent_candidate_root"]),
            "helper_pin": parent_helper_candidate_pin.public(),
            "launcher_pin": parent_launcher_pin.public(),
            "launcher_build_provenance": parent_build_provenance,
        },
        "buildplugin": {
            "helper_pin": buildplugin_helper_candidate_pin.public(),
            "admin_script_pin": buildplugin_script_pin.public(),
        },
    }
    if not require_core_candidate:
        result["core_candidate_files"] = {
            "vista_r8_ue57_authority_admin.py": helper_raw,
            "provision_vista_r8_ue57_engine.sh": wrapper_raw,
            "transfer-r8-ue57-stage-installer": transfer_raw,
            "engine-source-pin.json": canonical_json(engine_document),
        }
        return result

    core_paths = {
        CORE_BOOTSTRAP_REVIEW_CANDIDATE_ROOT
        / "vista_r8_ue57_authority_admin.py": 0o444,
        CORE_BOOTSTRAP_REVIEW_CANDIDATE_ROOT
        / "provision_vista_r8_ue57_engine.sh": 0o444,
        CORE_BOOTSTRAP_REVIEW_CANDIDATE_ROOT
        / "transfer-r8-ue57-stage-installer": 0o555,
        CORE_BOOTSTRAP_REVIEW_CANDIDATE_ROOT / "engine-source-pin.json": 0o444,
    }
    _require_user_review_candidate(
        CORE_BOOTSTRAP_REVIEW_CANDIDATE_ROOT,
        core_paths,
        "core bootstrap review candidate",
    )
    expected_core = {
        "vista_r8_ue57_authority_admin.py": helper_raw,
        "provision_vista_r8_ue57_engine.sh": wrapper_raw,
        "transfer-r8-ue57-stage-installer": transfer_raw,
        "engine-source-pin.json": canonical_json(engine_document),
    }
    core_pins: dict[str, dict[str, Any]] = {}
    for path, mode in core_paths.items():
        raw, pin = _read_regular(path, f"core candidate {path.name}", exact_mode=mode)
        if raw != expected_core[path.name]:
            _fail("CORE_BOOTSTRAP_REVIEW_INVALID", f"core {path.name}")
        core_pins[path.name] = pin.public()
    _stdlib_require_static_elf(
        expected_core["transfer-r8-ue57-stage-installer"],
        "core stage transfer launcher",
    )
    result["core_candidate"] = {
        "root": str(CORE_BOOTSTRAP_REVIEW_CANDIDATE_ROOT),
        "files": core_pins,
    }
    return result


def build_core_bootstrap_review_candidate() -> dict[str, Any]:
    if os.geteuid() != REVIEW_UID or os.getegid() != REVIEW_GID:
        _fail("UNPRIVILEGED_REVIEW_REQUIRED", "core bootstrap candidate")
    committed_sources = _require_unprivileged_review_helper()
    final = CORE_BOOTSTRAP_REVIEW_CANDIDATE_ROOT
    if os.path.lexists(final):
        _fail("FINAL_NOT_FRESH", str(final))
    materials = _core_bootstrap_review_materials(
        committed_sources, require_core_candidate=False
    )
    files = materials.pop("core_candidate_files")
    staging = Path(tempfile.mkdtemp(prefix=f".{final.name}.staging-", dir=final.parent))
    owner = (REVIEW_UID, REVIEW_GID)
    try:
        pins: dict[str, dict[str, Any]] = {}
        for name, raw in sorted(files.items()):
            mode = 0o555 if name == "transfer-r8-ue57-stage-installer" else 0o444
            pins[name] = _write_new(staging / name, raw, mode, owner).public()
        _seal_private_tree(staging, owner=owner)
        publish_staging(staging, final)
        return {
            "status": "user_published_core_bootstrap_review_candidate",
            "accepted": False,
            "candidate_root": str(final),
            "files": pins,
            "prerequisites": materials,
            "root_execution_performed": False,
        }
    finally:
        if os.path.lexists(staging):
            _remove_private_staging(staging)


def audit_core_bootstrap_review_inputs() -> dict[str, Any]:
    """Zero-write, user-only audit consumed by the later reviewed root installer."""

    if os.geteuid() != REVIEW_UID or os.getegid() != REVIEW_GID:
        _fail("UNPRIVILEGED_REVIEW_REQUIRED", "core bootstrap audit")
    git_binding, committed_sources = _require_unprivileged_review_binding()
    materials = _core_bootstrap_review_materials(
        committed_sources, require_core_candidate=True
    )
    return seal_document(
        {
            "schema": CORE_BOOTSTRAP_REVIEW_AUDIT_SCHEMA,
            "status": (
                "core_bootstrap_review_inputs_audited_without_"
                "persistent_authority_write"
            ),
            "accepted": False,
            "git": git_binding,
            "reviewed_inputs": materials,
            "final_layout": {
                "core": {
                    "root": str(INSTALLED_ROOT),
                    "root_mode": 0o555,
                    "files": {
                        "vista_r8_ue57_authority_admin.py": 0o500,
                        "provision_vista_r8_ue57_engine.sh": 0o500,
                        "transfer-r8-ue57-stage-installer": 0o555,
                        "engine-source-pin.json": 0o444,
                    },
                    "generated_locks": {
                        name: {"path": str(path), "mode": 0o600, "size_bytes": 0}
                        for name, path in sorted(OPERATION_LOCKS.items())
                    },
                },
                "parent_seal": {
                    "root": "/root/vista-authority-parent-seal-r1",
                    "root_mode": 0o555,
                    "files": {
                        PARENT_SEAL_LAUNCHER_NAME: 0o555,
                        PARENT_SEAL_HELPER_SOURCE.name: 0o500,
                    },
                },
                "buildplugin_helper": {
                    "root": str(BUILDPLUGIN_HELPER_INSTALL_ROOT),
                    "root_mode": 0o555,
                    "files": {BUILDPLUGIN_HELPER_SOURCE.name: 0o500},
                },
                "buildplugin_admin": {
                    "root": str(BUILDPLUGIN_ADMIN_INSTALL_ROOT),
                    "root_mode": 0o555,
                    "files": {
                        "publish-reconcile-buildplugin": 0o500,
                        "receipt.json": 0o444,
                    },
                },
            },
            "claims": {
                "root_execution_performed": False,
                "persistent_authority_write_performed": False,
                "ephemeral_review_build_performed": False,
                "dedicated_builder_phase_a_validated": True,
                "local_user_native_compile_performed": False,
                "native_candidates_byte_equal_deterministic_rebuild": True,
                "all_sources_equal_head": True,
                "engine_source_pin_final_before_core": True,
                "native_launchers_static": True,
                "root_compiler_execution": False,
            },
        }
    )


def _initial_bootstrap_sequence(
    audit_document: Mapping[str, Any], *, git_commit: str
) -> list[dict[str, Any]]:
    reviewed = audit_document["reviewed_inputs"]
    core = reviewed["core_candidate"]
    stage_transfer = reviewed["stage_transfer_launcher"]
    parent = reviewed["parent_seal"]
    buildplugin = reviewed["buildplugin"]
    if (
        stage_transfer.get("pin") != core["files"]["transfer-r8-ue57-stage-installer"]
        or stage_transfer.get("build_provenance", {})
        .get("job", {})
        .get("output", {})
        .get("pin")
        != stage_transfer.get("pin")
        or parent.get("launcher_build_provenance", {})
        .get("job", {})
        .get("output", {})
        .get("pin")
        != parent.get("launcher_pin")
        or parent.get("candidate_root") != str(NATIVE_BUILDER_PHASE_A_PARENT_SEAL_ROOT)
    ):
        _fail("INITIAL_BOOTSTRAP_INPUT_INVALID", "native review provenance binding")

    def record(
        source_name: str,
        destination_name: str,
        source_mode: str,
        final_mode: str,
        pin: Mapping[str, Any],
    ) -> dict[str, Any]:
        _parse_pin(pin, f"initial bootstrap {source_name}")
        return {
            "source_name": source_name,
            "destination_name": destination_name,
            "source_mode": source_mode,
            "final_mode": final_mode,
            "pin": dict(pin),
        }

    buildplugin_files = {
        "vista_r8_buildplugin_authority.py": buildplugin["helper_pin"],
        BUILDPLUGIN_ADMIN_SCRIPT_NAME: buildplugin["admin_script_pin"],
    }
    return [
        {
            "key": "core",
            "candidate_root": str(CORE_BOOTSTRAP_REVIEW_CANDIDATE_ROOT),
            "candidate_root_mode": "0555",
            "candidate_files": [
                record(
                    "vista_r8_ue57_authority_admin.py",
                    "vista_r8_ue57_authority_admin.py",
                    "0444",
                    "0500",
                    core["files"]["vista_r8_ue57_authority_admin.py"],
                ),
                record(
                    "provision_vista_r8_ue57_engine.sh",
                    "provision_vista_r8_ue57_engine.sh",
                    "0444",
                    "0500",
                    core["files"]["provision_vista_r8_ue57_engine.sh"],
                ),
                record(
                    "transfer-r8-ue57-stage-installer",
                    "transfer-r8-ue57-stage-installer",
                    "0555",
                    "0555",
                    core["files"]["transfer-r8-ue57-stage-installer"],
                ),
                record(
                    "engine-source-pin.json",
                    "engine-source-pin.json",
                    "0444",
                    "0444",
                    core["files"]["engine-source-pin.json"],
                ),
            ],
            "final_root": str(INSTALLED_ROOT),
            "final_root_mode": "0555",
            "generated_files": [
                {"name": name, "mode": "0600", "size_bytes": 0}
                for name in (
                    ".engine.lock",
                    ".runtime.lock",
                    ".bundle.lock",
                    ".executor.lock",
                )
            ],
            "native_build_provenance": stage_transfer["build_provenance"],
            "review_provenance": {
                "source": "core_review_audit.reviewed_inputs.core_candidate",
                "binding": dict(core),
                "git_commit": git_commit,
            },
        },
        {
            "key": "parent-seal",
            "candidate_root": str(NATIVE_BUILDER_PHASE_A_PARENT_SEAL_ROOT),
            "candidate_root_mode": "0555",
            "candidate_files": [
                record(
                    PARENT_SEAL_HELPER_SOURCE.name,
                    PARENT_SEAL_HELPER_SOURCE.name,
                    "0444",
                    "0500",
                    parent["helper_pin"],
                ),
                record(
                    PARENT_SEAL_LAUNCHER_NAME,
                    PARENT_SEAL_LAUNCHER_NAME,
                    "0555",
                    "0555",
                    parent["launcher_pin"],
                ),
            ],
            "final_root": "/root/vista-authority-parent-seal-r1",
            "final_root_mode": "0555",
            "generated_files": [],
            "native_build_provenance": parent["launcher_build_provenance"],
            "review_provenance": {
                "source": "core_review_audit.reviewed_inputs.parent_seal",
                "binding": {
                    "candidate_root": parent["candidate_root"],
                    "helper_pin": parent["helper_pin"],
                    "launcher_pin": parent["launcher_pin"],
                },
                "git_commit": git_commit,
            },
        },
        {
            "key": "buildplugin-helper",
            "candidate_root": str(BUILDPLUGIN_ADMIN_REVIEW_CANDIDATE_ROOT),
            "candidate_root_mode": "0555",
            "candidate_files": [
                record(
                    BUILDPLUGIN_HELPER_SOURCE.name,
                    BUILDPLUGIN_HELPER_SOURCE.name,
                    "0444",
                    "0500",
                    buildplugin_files[BUILDPLUGIN_HELPER_SOURCE.name],
                )
            ],
            "final_root": str(BUILDPLUGIN_HELPER_INSTALL_ROOT),
            "final_root_mode": "0555",
            "generated_files": [],
            "native_build_provenance": None,
            "review_provenance": {
                "source": "core_review_audit.reviewed_inputs.buildplugin",
                "binding": dict(buildplugin),
                "git_commit": git_commit,
            },
        },
        {
            "key": "buildplugin-admin",
            "candidate_root": str(BUILDPLUGIN_ADMIN_REVIEW_CANDIDATE_ROOT),
            "candidate_root_mode": "0555",
            "candidate_files": [
                record(
                    BUILDPLUGIN_ADMIN_SCRIPT_NAME,
                    "publish-reconcile-buildplugin",
                    "0444",
                    "0500",
                    buildplugin_files[BUILDPLUGIN_ADMIN_SCRIPT_NAME],
                )
            ],
            "final_root": str(BUILDPLUGIN_ADMIN_INSTALL_ROOT),
            "final_root_mode": "0555",
            "generated_files": [{"name": "receipt.json", "mode": "0444"}],
            "native_build_provenance": None,
            "review_provenance": {
                "source": "core_review_audit.reviewed_inputs.buildplugin",
                "binding": dict(buildplugin),
                "git_commit": git_commit,
            },
        },
    ]


def _legacy_test_only_build_initial_bootstrap_review_candidate(
    reviewed_core_audit_pin: Mapping[str, Any],
) -> dict[str, Any]:
    """Build and atomically freeze the generic four-root bootstrap candidate."""

    if os.geteuid() != REVIEW_UID or os.getegid() != REVIEW_GID:
        _fail("UNPRIVILEGED_REVIEW_REQUIRED", "initial bootstrap candidate")
    expected_audit_pin = _parse_pin(
        reviewed_core_audit_pin, "reviewed core bootstrap audit"
    )
    if expected_audit_pin.size_bytes <= 0:
        _fail("PIN_INVALID", "reviewed core bootstrap audit")
    git_binding, committed_sources = _require_unprivileged_review_binding()
    audit_document = audit_core_bootstrap_review_inputs()
    audit_raw = canonical_json(audit_document)
    observed_audit_pin = FilePin(hashlib.sha256(audit_raw).hexdigest(), len(audit_raw))
    if observed_audit_pin != expected_audit_pin:
        _fail("INITIAL_BOOTSTRAP_AUDIT_PIN_MISMATCH", "core bootstrap audit")
    if audit_document.get("git") != git_binding:
        _fail("INITIAL_BOOTSTRAP_BUILD_INPUT_DRIFT", "Git binding")
    if audit_document.get("content_digest") != content_digest(audit_document):
        _fail("INITIAL_BOOTSTRAP_BUILD_INPUT_DRIFT", "core audit seal")

    final = INITIAL_BOOTSTRAP_REVIEW_CANDIDATE_ROOT
    if os.path.lexists(final):
        _fail("FINAL_NOT_FRESH", str(final))
    helper_relative = INITIAL_BOOTSTRAP_HELPER_SOURCE.relative_to(
        CHECKOUT_ROOT
    ).as_posix()
    launcher_relative = INITIAL_BOOTSTRAP_LAUNCHER_SOURCE.relative_to(
        CHECKOUT_ROOT
    ).as_posix()
    helper_raw = committed_sources[helper_relative]
    launcher_source = committed_sources[launcher_relative]
    helper_pin = FilePin(hashlib.sha256(helper_raw).hexdigest(), len(helper_raw))
    _python_raw, python_pin = _read_regular(
        PYTHON_PATH, "initial bootstrap Python", exact_mode=0o755
    )
    staging = Path(tempfile.mkdtemp(prefix=f".{final.name}.staging-", dir=final.parent))
    owner = (REVIEW_UID, REVIEW_GID)
    try:
        launcher_path = staging / INITIAL_BOOTSTRAP_LAUNCHER_NAME
        with _protected_output_memfd(
            "vista-r8-initial-bootstrap-launcher"
        ) as output_fd:
            launcher_pin, launcher_build = _compile_initial_bootstrap_launcher(
                committed_source=launcher_source,
                helper_pin=helper_pin.public(),
                python_pin=python_pin.public(),
                output_fd=output_fd,
            )
            static_pin = _require_static_review_elf_fd(
                output_fd, "initial bootstrap launcher candidate"
            )
            launcher_raw, sealed_pin = _read_sealed_native_output(
                output_fd, "initial bootstrap launcher candidate"
            )
        if launcher_pin != static_pin or launcher_pin != sealed_pin:
            _fail("INITIAL_BOOTSTRAP_BUILD_INPUT_DRIFT", "sealed output pin")
        materialized_launcher_pin = _write_new(
            launcher_path, launcher_raw, 0o555, owner
        )
        if (
            materialized_launcher_pin.sha256,
            materialized_launcher_pin.size_bytes,
        ) != (launcher_pin.sha256, launcher_pin.size_bytes):
            _fail("INITIAL_BOOTSTRAP_BUILD_INPUT_DRIFT", "materialized launcher")
        _write_new(
            staging / INITIAL_BOOTSTRAP_HELPER_SOURCE.name,
            helper_raw,
            0o444,
            owner,
        )
        sequence = _initial_bootstrap_sequence(
            audit_document, git_commit=git_binding["commit"]
        )
        input_document = seal_document(
            {
                "schema": INITIAL_BOOTSTRAP_INPUT_PIN_SCHEMA,
                "status": "reviewed_initial_bootstrap_inputs_frozen",
                "accepted": False,
                "git": git_binding,
                "components": {
                    "installed_root": {
                        "path": str(INITIAL_BOOTSTRAP_INSTALL_ROOT),
                        "mode": "0555",
                    },
                    "launcher": {
                        "path": str(
                            INITIAL_BOOTSTRAP_INSTALL_ROOT
                            / INITIAL_BOOTSTRAP_LAUNCHER_NAME
                        ),
                        "mode": "0500",
                        "pin": launcher_pin.public(),
                        "build_provenance": launcher_build,
                    },
                    "helper": {
                        "path": str(
                            INITIAL_BOOTSTRAP_INSTALL_ROOT
                            / INITIAL_BOOTSTRAP_HELPER_SOURCE.name
                        ),
                        "mode": "0500",
                        "pin": helper_pin.public(),
                    },
                    "input_pin": {
                        "path": str(
                            INITIAL_BOOTSTRAP_INSTALL_ROOT
                            / INITIAL_BOOTSTRAP_INPUT_NAME
                        ),
                        "mode": "0444",
                    },
                    "lock": {
                        "path": str(INITIAL_BOOTSTRAP_INSTALL_ROOT / ".bootstrap.lock"),
                        "mode": "0600",
                        "size_bytes": 0,
                    },
                    "python": {
                        "path": str(PYTHON_PATH),
                        "mode": "0755",
                        "pin": python_pin.public(),
                    },
                },
                "core_review_audit": {
                    "schema": CORE_BOOTSTRAP_REVIEW_AUDIT_SCHEMA,
                    "pin": observed_audit_pin.public(),
                    "content_digest": audit_document["content_digest"],
                },
                "sequence": sequence,
                "operations": {
                    "publish": {
                        "operation": "publish-initial-authorities",
                        "acknowledgement": INITIAL_BOOTSTRAP_PUBLISH_ACKNOWLEDGEMENT,
                    },
                    "reconcile": {
                        "operation": "reconcile-initial-authorities",
                        "acknowledgement": INITIAL_BOOTSTRAP_RECONCILE_ACKNOWLEDGEMENT,
                    },
                    "resume": {
                        "operation": "resume-initial-authorities",
                        "acknowledgement": INITIAL_BOOTSTRAP_RESUME_ACKNOWLEDGEMENT,
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
                },
            }
        )
        input_pin = _write_new(
            staging / INITIAL_BOOTSTRAP_INPUT_NAME,
            canonical_json(input_document),
            0o444,
            owner,
        )
        _seal_private_tree(staging, owner=owner)
        publish_staging(staging, final)
        return {
            "status": "user_published_initial_bootstrap_review_candidate",
            "accepted": False,
            "candidate_root": str(final),
            "launcher_pin": launcher_pin.public(),
            "helper_pin": helper_pin.public(),
            "input_pin": input_pin.public(),
            "core_review_audit_pin": observed_audit_pin.public(),
            "core_review_audit_content_digest": audit_document["content_digest"],
            "git": git_binding,
            "launcher_build_provenance": launcher_build,
            "root_execution_performed": False,
        }
    finally:
        if os.path.lexists(staging):
            _remove_private_staging(staging)


def _legacy_test_only_build_initial_bootstrap_installer_review_candidate() -> dict[
    str, Any
]:
    """Freeze the sole static binary used by the manual root trust ceremony."""

    if os.geteuid() != REVIEW_UID or os.getegid() != REVIEW_GID:
        _fail("UNPRIVILEGED_REVIEW_REQUIRED", "initial bootstrap installer")
    git_binding, committed_sources = _require_unprivileged_review_binding()
    candidate_files = {
        INITIAL_BOOTSTRAP_REVIEW_CANDIDATE_ROOT
        / INITIAL_BOOTSTRAP_LAUNCHER_NAME: 0o555,
        INITIAL_BOOTSTRAP_REVIEW_CANDIDATE_ROOT
        / INITIAL_BOOTSTRAP_HELPER_SOURCE.name: 0o444,
        INITIAL_BOOTSTRAP_REVIEW_CANDIDATE_ROOT / INITIAL_BOOTSTRAP_INPUT_NAME: 0o444,
    }
    _require_user_review_candidate(
        INITIAL_BOOTSTRAP_REVIEW_CANDIDATE_ROOT,
        candidate_files,
        "initial bootstrap review candidate",
    )
    root_fd = os.open(INITIAL_BOOTSTRAP_REVIEW_CANDIDATE_ROOT, _directory_flags())
    descriptors: dict[str, int] = {}
    metadata: dict[str, os.stat_result] = {}
    raw_by_name: dict[str, bytes] = {}
    pins: dict[str, FilePin] = {}
    try:
        root_info = os.fstat(root_fd)
        if (
            not stat.S_ISDIR(root_info.st_mode)
            or root_info.st_nlink != 2
            or root_info.st_uid != REVIEW_UID
            or root_info.st_gid != REVIEW_GID
            or stat.S_IMODE(root_info.st_mode) != 0o555
            or set(os.listdir(root_fd)) != {path.name for path in candidate_files}
        ):
            _fail(
                "INITIAL_BOOTSTRAP_INSTALLER_CANDIDATE_INVALID",
                "candidate root",
            )
        for path, mode in candidate_files.items():
            descriptor = os.open(path.name, _file_flags(), dir_fd=root_fd)
            descriptors[path.name] = descriptor
            info = os.fstat(descriptor)
            metadata[path.name] = info
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_nlink != 1
                or info.st_uid != REVIEW_UID
                or info.st_gid != REVIEW_GID
                or stat.S_IMODE(info.st_mode) != mode
                or info.st_size <= 0
                or info.st_size > 64 * 1024 * 1024
                or info.st_blocks * 512 < info.st_size
            ):
                _fail(
                    "INITIAL_BOOTSTRAP_INSTALLER_CANDIDATE_INVALID",
                    path.name,
                )
            digest, size = _hash_fd(descriptor)
            os.lseek(descriptor, 0, os.SEEK_SET)
            raw = bytearray()
            while block := os.read(descriptor, CHUNK_BYTES):
                raw.extend(block)
            os.lseek(descriptor, 0, os.SEEK_SET)
            raw_by_name[path.name] = bytes(raw)
            pins[path.name] = FilePin(digest, size, bool(mode & 0o111))

        helper_relative = INITIAL_BOOTSTRAP_HELPER_SOURCE.relative_to(
            CHECKOUT_ROOT
        ).as_posix()
        launcher_relative = INITIAL_BOOTSTRAP_LAUNCHER_SOURCE.relative_to(
            CHECKOUT_ROOT
        ).as_posix()
        installer_relative = INITIAL_BOOTSTRAP_INSTALLER_SOURCE.relative_to(
            CHECKOUT_ROOT
        ).as_posix()
        if (
            raw_by_name[INITIAL_BOOTSTRAP_HELPER_SOURCE.name]
            != committed_sources[helper_relative]
        ):
            _fail(
                "INITIAL_BOOTSTRAP_INSTALLER_CANDIDATE_INVALID",
                "helper differs from exact HEAD",
            )
        launcher_pin = pins[INITIAL_BOOTSTRAP_LAUNCHER_NAME]
        helper_pin = pins[INITIAL_BOOTSTRAP_HELPER_SOURCE.name]
        input_pin = pins[INITIAL_BOOTSTRAP_INPUT_NAME]
        _python_raw, python_pin = _read_regular(
            PYTHON_PATH, "initial bootstrap installer Python", exact_mode=0o755
        )
        final = INITIAL_BOOTSTRAP_INSTALLER_REVIEW_CANDIDATE_ROOT
        if os.path.lexists(final):
            _fail("FINAL_NOT_FRESH", str(final))
        with _protected_output_memfd(
            "vista-r8-initial-bootstrap-launcher-reproduction"
        ) as reproduction_fd:
            reproduced_pin, reproduced_build = _compile_initial_bootstrap_launcher(
                committed_source=committed_sources[launcher_relative],
                helper_pin=helper_pin.public(),
                python_pin=python_pin.public(),
                output_fd=reproduction_fd,
            )
            reproduced_static_pin = _require_static_review_elf_fd(
                reproduction_fd, "reproduced initial bootstrap launcher"
            )
            reproduced_raw, reproduced_sealed_pin = _read_sealed_native_output(
                reproduction_fd, "reproduced initial bootstrap launcher"
            )
            if (
                reproduced_pin.public() != launcher_pin.public()
                or reproduced_pin != reproduced_static_pin
                or reproduced_pin != reproduced_sealed_pin
                or reproduced_raw != raw_by_name[INITIAL_BOOTSTRAP_LAUNCHER_NAME]
            ):
                _fail(
                    "INITIAL_BOOTSTRAP_INSTALLER_CANDIDATE_INVALID",
                    "launcher differs from deterministic exact-HEAD build",
                )

        audit_document = audit_core_bootstrap_review_inputs()
        audit_raw = canonical_json(audit_document)
        audit_pin = FilePin(hashlib.sha256(audit_raw).hexdigest(), len(audit_raw))
        if audit_document.get("git") != git_binding or audit_document.get(
            "content_digest"
        ) != content_digest(audit_document):
            _fail(
                "INITIAL_BOOTSTRAP_INSTALLER_CANDIDATE_INVALID",
                "live core audit differs",
            )
        sequence = _initial_bootstrap_sequence(
            audit_document, git_commit=git_binding["commit"]
        )
        input_document = strict_json(
            raw_by_name[INITIAL_BOOTSTRAP_INPUT_NAME],
            "initial bootstrap input pin",
        )
        expected_input_document = seal_document(
            {
                "schema": INITIAL_BOOTSTRAP_INPUT_PIN_SCHEMA,
                "status": "reviewed_initial_bootstrap_inputs_frozen",
                "accepted": False,
                "git": git_binding,
                "components": {
                    "installed_root": {
                        "path": str(INITIAL_BOOTSTRAP_INSTALL_ROOT),
                        "mode": "0555",
                    },
                    "launcher": {
                        "path": str(
                            INITIAL_BOOTSTRAP_INSTALL_ROOT
                            / INITIAL_BOOTSTRAP_LAUNCHER_NAME
                        ),
                        "mode": "0500",
                        "pin": launcher_pin.public(),
                        "build_provenance": reproduced_build,
                    },
                    "helper": {
                        "path": str(
                            INITIAL_BOOTSTRAP_INSTALL_ROOT
                            / INITIAL_BOOTSTRAP_HELPER_SOURCE.name
                        ),
                        "mode": "0500",
                        "pin": helper_pin.public(),
                    },
                    "input_pin": {
                        "path": str(
                            INITIAL_BOOTSTRAP_INSTALL_ROOT
                            / INITIAL_BOOTSTRAP_INPUT_NAME
                        ),
                        "mode": "0444",
                    },
                    "lock": {
                        "path": str(INITIAL_BOOTSTRAP_INSTALL_ROOT / ".bootstrap.lock"),
                        "mode": "0600",
                        "size_bytes": 0,
                    },
                    "python": {
                        "path": str(PYTHON_PATH),
                        "mode": "0755",
                        "pin": python_pin.public(),
                    },
                },
                "core_review_audit": {
                    "schema": CORE_BOOTSTRAP_REVIEW_AUDIT_SCHEMA,
                    "pin": audit_pin.public(),
                    "content_digest": audit_document["content_digest"],
                },
                "sequence": sequence,
                "operations": {
                    "publish": {
                        "operation": "publish-initial-authorities",
                        "acknowledgement": INITIAL_BOOTSTRAP_PUBLISH_ACKNOWLEDGEMENT,
                    },
                    "reconcile": {
                        "operation": "reconcile-initial-authorities",
                        "acknowledgement": INITIAL_BOOTSTRAP_RECONCILE_ACKNOWLEDGEMENT,
                    },
                    "resume": {
                        "operation": "resume-initial-authorities",
                        "acknowledgement": INITIAL_BOOTSTRAP_RESUME_ACKNOWLEDGEMENT,
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
                },
            }
        )
        if input_document != expected_input_document:
            _fail(
                "INITIAL_BOOTSTRAP_INSTALLER_CANDIDATE_INVALID",
                "closed input binding",
            )
        staging = Path(
            tempfile.mkdtemp(prefix=f".{final.name}.staging-", dir=final.parent)
        )
        owner = (REVIEW_UID, REVIEW_GID)
        try:
            output = staging / INITIAL_BOOTSTRAP_INSTALLER_NAME
            with _protected_output_memfd(
                "vista-r8-initial-bootstrap-installer"
            ) as installer_fd:
                installer_pin, build_provenance = _compile_initial_bootstrap_installer(
                    committed_source=committed_sources[installer_relative],
                    launcher_pin=launcher_pin.public(),
                    helper_pin=helper_pin.public(),
                    input_pin=input_pin.public(),
                    output_fd=installer_fd,
                )
                installer_static_pin = _require_static_review_elf_fd(
                    installer_fd, "initial bootstrap installer"
                )
                installer_raw, installer_sealed_pin = _read_sealed_native_output(
                    installer_fd, "initial bootstrap installer"
                )
            if (
                installer_pin != installer_static_pin
                or installer_pin != installer_sealed_pin
            ):
                _fail(
                    "INITIAL_BOOTSTRAP_INSTALLER_BUILD_INPUT_DRIFT",
                    "sealed output pin",
                )
            materialized_installer_pin = _write_new(output, installer_raw, 0o555, owner)
            if (
                materialized_installer_pin.sha256,
                materialized_installer_pin.size_bytes,
            ) != (installer_pin.sha256, installer_pin.size_bytes):
                _fail(
                    "INITIAL_BOOTSTRAP_INSTALLER_BUILD_INPUT_DRIFT",
                    "materialized installer",
                )
            for name, descriptor in descriptors.items():
                if (
                    _identity(os.fstat(descriptor)) != _identity(metadata[name])
                    or _hash_fd(descriptor)
                    != (pins[name].sha256, pins[name].size_bytes)
                    or _identity(os.stat(name, dir_fd=root_fd, follow_symlinks=False))
                    != _identity(metadata[name])
                ):
                    _fail(
                        "INITIAL_BOOTSTRAP_INSTALLER_CANDIDATE_DRIFT",
                        name,
                    )
            if (
                _identity(os.fstat(root_fd)) != _identity(root_info)
                or _identity(os.lstat(INITIAL_BOOTSTRAP_REVIEW_CANDIDATE_ROOT))
                != _identity(root_info)
                or set(os.listdir(root_fd)) != {path.name for path in candidate_files}
            ):
                _fail(
                    "INITIAL_BOOTSTRAP_INSTALLER_CANDIDATE_DRIFT",
                    "candidate root",
                )
            _seal_private_tree(staging, owner=owner)
            publish_staging(staging, final)
            return {
                "status": (
                    "user_published_initial_bootstrap_installer_review_candidate"
                ),
                "accepted": False,
                "candidate_root": str(final),
                "installer": {
                    "name": INITIAL_BOOTSTRAP_INSTALLER_NAME,
                    "pin": installer_pin.public(),
                    "review_mode": "0555",
                    "manual_install_root": str(
                        INITIAL_BOOTSTRAP_INSTALLER_INSTALL_ROOT
                    ),
                    "manual_install_root_mode": "0555",
                    "manual_install_mode": "0500",
                    "manual_install_inventory": [INITIAL_BOOTSTRAP_INSTALLER_NAME],
                },
                "reviewed_initial_bootstrap_candidate": {
                    "root": str(INITIAL_BOOTSTRAP_REVIEW_CANDIDATE_ROOT),
                    "root_mode": "0555",
                    "launcher_pin": launcher_pin.public(),
                    "helper_pin": helper_pin.public(),
                    "input_pin": input_pin.public(),
                },
                "operations": {
                    "install": {
                        "operation": "install-initial-bootstrap",
                        "acknowledgement": (INITIAL_BOOTSTRAP_INSTALL_ACKNOWLEDGEMENT),
                    },
                    "reconcile": {
                        "operation": "reconcile-initial-bootstrap",
                        "acknowledgement": (
                            INITIAL_BOOTSTRAP_INSTALL_RECONCILE_ACKNOWLEDGEMENT
                        ),
                    },
                },
                "git": git_binding,
                "build_provenance": build_provenance,
                "root_execution_performed": False,
                "manual_trust_boundary_complete": False,
            }
        finally:
            if os.path.lexists(staging):
                _remove_private_staging(staging)
    finally:
        for descriptor in descriptors.values():
            os.close(descriptor)
        os.close(root_fd)


def _native_builder_root_file_pin(path: Path, *, mode: int, label: str) -> FilePin:
    info = os.lstat(path)
    if (
        not stat.S_ISREG(info.st_mode)
        or stat.S_IMODE(info.st_mode) != mode
        or info.st_uid != ROOT_UID
        or info.st_gid != ROOT_GID
        or info.st_nlink != 1
        or info.st_size <= 0
        or info.st_blocks * 512 < info.st_size
    ):
        _fail("NATIVE_BUILDER_AUTHORITY_INVALID", label)
    _raw, pin = _read_regular(path, label, exact_mode=mode)
    return pin


def _initial_input_document_for_builder(
    *,
    audit_document: Mapping[str, Any],
    audit_pin: FilePin,
    git_binding: Mapping[str, Any],
    committed_sources: Mapping[str, bytes],
) -> dict[str, Any]:
    reviewed = audit_document["reviewed_inputs"]
    phase_a = reviewed["native_builder_phase_a"]
    launcher = reviewed["initial_bootstrap_launcher"]
    helper_relative = INITIAL_BOOTSTRAP_HELPER_SOURCE.relative_to(
        CHECKOUT_ROOT
    ).as_posix()
    helper_raw = committed_sources[helper_relative]
    helper_pin = FilePin(hashlib.sha256(helper_raw).hexdigest(), len(helper_raw))
    _python_raw, python_pin = _read_regular(
        PYTHON_PATH, "initial bootstrap Python", exact_mode=0o755
    )
    return seal_document(
        {
            "schema": INITIAL_BOOTSTRAP_INPUT_PIN_SCHEMA,
            "status": "dedicated_builder_initial_bootstrap_inputs_frozen",
            "accepted": False,
            "git": {
                "commit": git_binding["commit"],
                "source_bundle": phase_a["source_bundle"],
                "sources": phase_a["sources"],
            },
            "native_builder_phase_a": phase_a,
            "components": {
                "installed_root": {
                    "path": str(INITIAL_BOOTSTRAP_INSTALL_ROOT),
                    "mode": "0555",
                },
                "launcher": {
                    "path": str(
                        INITIAL_BOOTSTRAP_INSTALL_ROOT / INITIAL_BOOTSTRAP_LAUNCHER_NAME
                    ),
                    "mode": "0500",
                    "pin": launcher["pin"],
                    "build_provenance": launcher["build_provenance"],
                },
                "helper": {
                    "path": str(
                        INITIAL_BOOTSTRAP_INSTALL_ROOT
                        / INITIAL_BOOTSTRAP_HELPER_SOURCE.name
                    ),
                    "mode": "0500",
                    "pin": helper_pin.public(),
                },
                "input_pin": {
                    "path": str(
                        INITIAL_BOOTSTRAP_INSTALL_ROOT / INITIAL_BOOTSTRAP_INPUT_NAME
                    ),
                    "mode": "0444",
                },
                "lock": {
                    "path": str(INITIAL_BOOTSTRAP_INSTALL_ROOT / ".bootstrap.lock"),
                    "mode": "0600",
                    "size_bytes": 0,
                },
                "python": {
                    "path": str(PYTHON_PATH),
                    "mode": "0755",
                    "pin": python_pin.public(),
                },
            },
            "core_review_audit": {
                "schema": CORE_BOOTSTRAP_REVIEW_AUDIT_SCHEMA,
                "pin": audit_pin.public(),
                "content_digest": audit_document["content_digest"],
            },
            "sequence": _initial_bootstrap_sequence(
                audit_document, git_commit=git_binding["commit"]
            ),
            "operations": {
                "publish": {
                    "operation": "publish-initial-authorities",
                    "acknowledgement": INITIAL_BOOTSTRAP_PUBLISH_ACKNOWLEDGEMENT,
                },
                "reconcile": {
                    "operation": "reconcile-initial-authorities",
                    "acknowledgement": INITIAL_BOOTSTRAP_RECONCILE_ACKNOWLEDGEMENT,
                },
                "resume": {
                    "operation": "resume-initial-authorities",
                    "acknowledgement": INITIAL_BOOTSTRAP_RESUME_ACKNOWLEDGEMENT,
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


def _native_builder_validate_phase_b_cross_binding(
    *,
    phase_b_request: Mapping[str, Any],
    phase_a_request: Mapping[str, Any],
    phase_a_request_pin: FilePin,
    phase_a_manifest: Mapping[str, Any],
    phase_a_manifest_pin: FilePin,
) -> None:
    request_fields = {
        "schema",
        "phase",
        "status",
        "accepted",
        "builder",
        "source_bundle",
        "source_commit",
        "sources",
        "tools",
        "trace_contract",
        "jobs",
        "phase_inputs",
        "claims",
        "content_digest",
    }
    if (
        type(phase_a_request) is not dict
        or set(phase_a_request) != request_fields
        or phase_a_request.get("schema") != NATIVE_BUILDER_REQUEST_SCHEMA
        or phase_a_request.get("phase") != "phase-a"
        or phase_a_request.get("status") != "reviewed_native_build_request"
        or phase_a_request.get("accepted") is not False
        or phase_a_request.get("content_digest") != content_digest(phase_a_request)
        or type(phase_b_request) is not dict
        or set(phase_b_request) != request_fields
        or phase_b_request.get("schema") != NATIVE_BUILDER_REQUEST_SCHEMA
        or phase_b_request.get("phase") != "phase-b"
        or phase_b_request.get("status") != "reviewed_native_build_request"
        or phase_b_request.get("accepted") is not False
        or phase_b_request.get("content_digest") != content_digest(phase_b_request)
    ):
        _fail("NATIVE_BUILDER_PHASE_B_LINEAGE_INVALID", "request envelope")

    phase_a_source_bundle = phase_a_request.get("source_bundle")
    phase_a_source_bundle_pin = (
        phase_a_source_bundle.get("pin")
        if type(phase_a_source_bundle) is dict
        else None
    )
    manifest_fields = {
        "schema",
        "status",
        "accepted",
        "phase",
        "request_pin",
        "source_commit",
        "source_bundle_pin",
        "jobs",
        "inventory",
        "claims",
        "content_digest",
    }
    if (
        type(phase_a_manifest) is not dict
        or set(phase_a_manifest) != manifest_fields
        or phase_a_manifest.get("schema") != NATIVE_BUILDER_PHASE_A_SCHEMA
        or phase_a_manifest.get("status") != "dedicated_builder_phase_closed"
        or phase_a_manifest.get("accepted") is not False
        or phase_a_manifest.get("phase") != "phase-a"
        or phase_a_manifest.get("content_digest") != content_digest(phase_a_manifest)
        or phase_a_manifest.get("request_pin") != phase_a_request_pin.public()
        or phase_a_manifest.get("source_commit") != phase_a_request.get("source_commit")
        or phase_a_manifest.get("source_bundle_pin") != phase_a_source_bundle_pin
    ):
        _fail("NATIVE_BUILDER_PHASE_B_LINEAGE_INVALID", "phase A closure")

    phase_a_builder = phase_a_request.get("builder")
    phase_b_builder = phase_b_request.get("builder")
    builder_fields = {"path", "mode", "uid", "gid", "pin", "service_unit"}
    shared_builder_fields = ("path", "mode", "uid", "gid", "pin")
    if (
        type(phase_a_builder) is not dict
        or set(phase_a_builder) != builder_fields
        or type(phase_b_builder) is not dict
        or set(phase_b_builder) != builder_fields
        or any(
            phase_b_builder.get(key) != phase_a_builder.get(key)
            for key in shared_builder_fields
        )
    ):
        _fail("NATIVE_BUILDER_PHASE_B_LINEAGE_INVALID", "builder identity")

    common_fields = (
        "source_bundle",
        "source_commit",
        "sources",
        "tools",
        "trace_contract",
    )
    if any(
        phase_b_request.get(key) != phase_a_request.get(key) for key in common_fields
    ):
        _fail("NATIVE_BUILDER_PHASE_B_LINEAGE_INVALID", "common request inputs")
    phase_a_trace_raw = canonical_json(phase_a_request["trace_contract"])
    phase_b_trace_raw = canonical_json(phase_b_request["trace_contract"])
    if (
        phase_b_trace_raw != phase_a_trace_raw
        or hashlib.sha256(phase_b_trace_raw).digest()
        != hashlib.sha256(phase_a_trace_raw).digest()
    ):
        _fail("NATIVE_BUILDER_PHASE_B_LINEAGE_INVALID", "trace digest")

    phase_inputs = phase_b_request.get("phase_inputs")
    phase_a_binding = (
        phase_inputs.get("phase_a") if type(phase_inputs) is dict else None
    )
    if phase_a_binding != {
        "root": str(NATIVE_BUILDER_PHASE_A_ROOT),
        "manifest_pin": phase_a_manifest_pin.public(),
        "content_digest": phase_a_manifest["content_digest"],
    }:
        _fail("NATIVE_BUILDER_PHASE_B_LINEAGE_INVALID", "phase A binding")


def _derive_native_builder_phase_b_request(
    reviewed_core_audit_pin: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    if os.geteuid() != REVIEW_UID or os.getegid() != REVIEW_GID:
        _fail("UNPRIVILEGED_REVIEW_REQUIRED", "native builder phase B request")
    expected_audit_pin = _parse_pin(
        reviewed_core_audit_pin, "reviewed core bootstrap audit"
    )
    git_binding, committed_sources = _require_unprivileged_review_binding()
    audit_document = audit_core_bootstrap_review_inputs()
    audit_raw = canonical_json(audit_document)
    audit_pin = FilePin(hashlib.sha256(audit_raw).hexdigest(), len(audit_raw))
    if audit_pin != expected_audit_pin or audit_document.get("git") != git_binding:
        _fail("INITIAL_BOOTSTRAP_AUDIT_PIN_MISMATCH", "core bootstrap audit")
    initial_input = _initial_input_document_for_builder(
        audit_document=audit_document,
        audit_pin=audit_pin,
        git_binding=git_binding,
        committed_sources=committed_sources,
    )
    initial_input_pin = FilePin(
        hashlib.sha256(canonical_json(initial_input)).hexdigest(),
        len(canonical_json(initial_input)),
    )
    phase_a = audit_document["reviewed_inputs"]["native_builder_phase_a"]
    launcher = audit_document["reviewed_inputs"]["initial_bootstrap_launcher"]
    helper_relative = INITIAL_BOOTSTRAP_HELPER_SOURCE.relative_to(
        CHECKOUT_ROOT
    ).as_posix()
    helper_raw = committed_sources[helper_relative]
    helper_pin = FilePin(hashlib.sha256(helper_raw).hexdigest(), len(helper_raw))
    unit_pin = _native_builder_root_file_pin(
        NATIVE_BUILDER_PHASE_B_UNIT,
        mode=0o644,
        label="native builder phase B unit",
    )
    phase_a_builder = phase_a["builder"]
    phase_b_builder = {
        "path": str(NATIVE_BUILDER_HELPER),
        "mode": "0444",
        "uid": ROOT_UID,
        "gid": ROOT_GID,
        "pin": phase_a_builder["pin"],
        "service_unit": {
            "path": str(NATIVE_BUILDER_PHASE_B_UNIT),
            "mode": "0644",
            "uid": ROOT_UID,
            "gid": ROOT_GID,
            "pin": unit_pin.public(),
        },
    }
    bindings = {
        "launcher_pin": launcher["pin"],
        "helper_pin": helper_pin.public(),
        "input_pin": initial_input_pin.public(),
    }
    flags = _native_builder_expected_flags("initial-bootstrap-installer", bindings)
    phase_a_request_raw, phase_a_request_pin = _read_regular(
        NATIVE_BUILDER_PHASE_A_REQUEST,
        "native builder phase A request",
        exact_mode=0o444,
    )
    phase_a_request = strict_json(phase_a_request_raw, "native builder phase A request")
    if (
        phase_a_request_pin.public() != phase_a["request_pin"]
        or phase_a_request.get("content_digest") != phase_a["request_content_digest"]
    ):
        _fail("NATIVE_BUILDER_AUTHORITY_DRIFT", "phase A request")
    trace_contract = _native_builder_validate_trace_contract(
        phase_a_request.get("trace_contract")
    )
    phase_a_tools = phase_a_request.get("tools")
    if type(phase_a_tools) is not dict or phase_a_tools.get(
        "toolchain"
    ) != _native_builder_trace_toolchain(trace_contract):
        _fail("NATIVE_BUILDER_AUTHORITY_DRIFT", "phase A trace/toolchain")
    phase_a_manifest_raw, phase_a_manifest_pin = _read_regular(
        NATIVE_BUILDER_PHASE_A_ROOT / "manifest.json",
        "native builder phase A manifest",
        exact_mode=0o444,
    )
    phase_a_manifest = strict_json(
        phase_a_manifest_raw, "native builder phase A manifest"
    )
    if (
        phase_a_manifest_pin.public() != phase_a["manifest_pin"]
        or phase_a_manifest.get("content_digest") != phase_a["manifest_content_digest"]
    ):
        _fail("NATIVE_BUILDER_AUTHORITY_DRIFT", "phase A manifest")
    request = seal_document(
        {
            "schema": NATIVE_BUILDER_REQUEST_SCHEMA,
            "phase": "phase-b",
            "status": "reviewed_native_build_request",
            "accepted": False,
            "builder": phase_b_builder,
            "source_bundle": phase_a["source_bundle"],
            "source_commit": git_binding["commit"],
            "sources": phase_a["sources"],
            "tools": phase_a_request["tools"],
            "trace_contract": trace_contract,
            "jobs": [
                {
                    "id": "initial-bootstrap-installer",
                    "source_path": (
                        "tools/admin/vista_r8_ue57_initial_bootstrap_installer.c"
                    ),
                    "output_name": INITIAL_BOOTSTRAP_INSTALLER_NAME,
                    "output_mode": "0555",
                    "bindings": bindings,
                    "flags": flags,
                }
            ],
            "phase_inputs": {
                "phase_a": {
                    "root": str(NATIVE_BUILDER_PHASE_A_ROOT),
                    "manifest_pin": phase_a["manifest_pin"],
                    "content_digest": phase_a["manifest_content_digest"],
                },
                "core_review_audit": {
                    "document": audit_document,
                    "pin": audit_pin.public(),
                },
                "initial_input": {
                    "document": initial_input,
                    "pin": initial_input_pin.public(),
                },
            },
            "claims": {
                "dedicated_builder_uid_gid": [
                    NATIVE_BUILDER_UID,
                    NATIVE_BUILDER_GID,
                ],
                "network_access": False,
                "double_build_required": True,
                "worktree_or_user_candidate_input": False,
                "write_root": str(NATIVE_BUILDER_HOME),
                "observation_only": True,
                "production_native_output": False,
            },
        }
    )
    _native_builder_validate_phase_b_cross_binding(
        phase_b_request=request,
        phase_a_request=phase_a_request,
        phase_a_request_pin=phase_a_request_pin,
        phase_a_manifest=phase_a_manifest,
        phase_a_manifest_pin=phase_a_manifest_pin,
    )
    return request, initial_input, audit_document


def build_initial_bootstrap_review_candidate(
    reviewed_core_audit_pin: Mapping[str, Any],
) -> dict[str, Any]:
    """Derive the canonical Phase-B request; the dedicated unit builds it."""

    request, initial_input, audit_document = _derive_native_builder_phase_b_request(
        reviewed_core_audit_pin
    )
    request_raw = canonical_json(request)
    return {
        "status": "native_builder_phase_b_request_derived_zero_write",
        "accepted": False,
        "request_path": str(NATIVE_BUILDER_PHASE_B_REQUEST),
        "request_pin": {
            "sha256": hashlib.sha256(request_raw).hexdigest(),
            "size_bytes": len(request_raw),
        },
        "request_content_digest": request["content_digest"],
        "request_document": request,
        "initial_input_pin": {
            "sha256": hashlib.sha256(canonical_json(initial_input)).hexdigest(),
            "size_bytes": len(canonical_json(initial_input)),
        },
        "initial_input_content_digest": initial_input["content_digest"],
        "core_review_audit_content_digest": audit_document["content_digest"],
        "root_execution_performed": False,
        "candidate_publication_performed": False,
    }


@contextlib.contextmanager
def _held_native_builder_phase_b(
    expected_request: Mapping[str, Any],
) -> Iterable[tuple[HeldNativeBuilderPhase, dict[str, Any]]]:
    authority = HeldNativeBuilderPhase(contextlib.ExitStack(), {}, {}, {}, {}, {}, {})
    try:
        _native_builder_directory(
            authority,
            path=NATIVE_BUILDER_PHASE_B_ROOT.parent,
            mode=0o711,
            owner=(NATIVE_BUILDER_UID, NATIVE_BUILDER_GID),
            inventory={".build.lock", "published"},
            label="native builder phase B slot",
        )
        _native_builder_directory(
            authority,
            path=NATIVE_BUILDER_PHASE_B_ROOT,
            mode=0o555,
            owner=(NATIVE_BUILDER_UID, NATIVE_BUILDER_GID),
            inventory={
                "initial-bootstrap-candidate",
                "initial-bootstrap-installer",
                "manifest.json",
                "manifests",
            },
            label="native builder phase B root",
        )
        _native_builder_directory(
            authority,
            path=INITIAL_BOOTSTRAP_REVIEW_CANDIDATE_ROOT,
            mode=0o555,
            owner=(NATIVE_BUILDER_UID, NATIVE_BUILDER_GID),
            inventory={
                INITIAL_BOOTSTRAP_LAUNCHER_NAME,
                INITIAL_BOOTSTRAP_HELPER_SOURCE.name,
                INITIAL_BOOTSTRAP_INPUT_NAME,
            },
            label="native builder initial candidate",
        )
        _native_builder_directory(
            authority,
            path=INITIAL_BOOTSTRAP_INSTALLER_REVIEW_CANDIDATE_ROOT,
            mode=0o555,
            owner=(NATIVE_BUILDER_UID, NATIVE_BUILDER_GID),
            inventory={INITIAL_BOOTSTRAP_INSTALLER_NAME},
            label="native builder initial installer",
        )
        _native_builder_directory(
            authority,
            path=NATIVE_BUILDER_PHASE_B_ROOT / "manifests",
            mode=0o555,
            owner=(NATIVE_BUILDER_UID, NATIVE_BUILDER_GID),
            inventory={
                "initial-bootstrap-candidate.json",
                "initial-bootstrap-installer.json",
            },
            label="native builder phase B manifests",
        )
        request_raw, request_pin = _native_builder_read_held(
            authority,
            path=NATIVE_BUILDER_PHASE_B_REQUEST,
            mode=0o444,
            owner=(ROOT_UID, ROOT_GID),
            maximum=MAX_JSON_BYTES,
            label="phase B request",
        )
        request = strict_json(request_raw, "native builder phase B request")
        if request != expected_request:
            _fail("NATIVE_BUILDER_MANIFEST_INVALID", "phase B request differs")
        phase_a_request_raw, phase_a_request_pin = _native_builder_read_held(
            authority,
            path=NATIVE_BUILDER_PHASE_A_REQUEST,
            mode=0o444,
            owner=(ROOT_UID, ROOT_GID),
            maximum=MAX_JSON_BYTES,
            label="phase A request during phase B audit",
        )
        phase_a_manifest_raw, phase_a_manifest_pin = _native_builder_read_held(
            authority,
            path=NATIVE_BUILDER_PHASE_A_ROOT / "manifest.json",
            mode=0o444,
            owner=(NATIVE_BUILDER_UID, NATIVE_BUILDER_GID),
            maximum=MAX_JSON_BYTES,
            label="phase A manifest during phase B audit",
        )
        _native_builder_validate_phase_b_cross_binding(
            phase_b_request=request,
            phase_a_request=strict_json(
                phase_a_request_raw, "phase A request during phase B audit"
            ),
            phase_a_request_pin=phase_a_request_pin,
            phase_a_manifest=strict_json(
                phase_a_manifest_raw, "phase A manifest during phase B audit"
            ),
            phase_a_manifest_pin=phase_a_manifest_pin,
        )
        _bundle_raw, bundle_pin = _native_builder_read_held(
            authority,
            path=NATIVE_BUILDER_BUNDLE,
            mode=0o444,
            owner=(ROOT_UID, ROOT_GID),
            maximum=MAX_NATIVE_BUILDER_BUNDLE_BYTES,
            label="phase B source Git bundle",
        )
        _builder_raw, builder_pin = _native_builder_read_held(
            authority,
            path=NATIVE_BUILDER_HELPER,
            mode=0o444,
            owner=(ROOT_UID, ROOT_GID),
            maximum=MAX_JSON_BYTES,
            label="phase B installed builder",
        )
        _unit_raw, unit_pin = _native_builder_read_held(
            authority,
            path=NATIVE_BUILDER_PHASE_B_UNIT,
            mode=0o644,
            owner=(ROOT_UID, ROOT_GID),
            maximum=MAX_JSON_BYTES,
            label="phase B systemd unit",
        )
        if (
            request["source_bundle"]["pin"] != bundle_pin.public()
            or request["builder"]["pin"] != builder_pin.public()
            or request["builder"]["service_unit"]["pin"] != unit_pin.public()
        ):
            _fail("NATIVE_BUILDER_AUTHORITY_DRIFT", "phase B fixed inputs")
        trace_contract = _native_builder_validate_trace_contract(
            request.get("trace_contract")
        )
        _native_builder_hold_trace_inputs(authority, trace_contract)
        tools = request["tools"]
        for key, path in {
            "python": PYTHON_PATH,
            "git": Path("/usr/bin/git"),
            "compiler": COMPILER_PATH,
            "readelf": READELF_PATH,
            "tracer": STRACE_PATH,
        }.items():
            _native_builder_tool(authority, tools[key], expected_path=path, label=key)
        if tools["toolchain"] != _native_builder_trace_toolchain(trace_contract):
            _fail("NATIVE_BUILDER_MANIFEST_INVALID", "phase B toolchain")
        manifest_raw, manifest_pin = _native_builder_read_held(
            authority,
            path=NATIVE_BUILDER_PHASE_B_ROOT / "manifest.json",
            mode=0o444,
            owner=(NATIVE_BUILDER_UID, NATIVE_BUILDER_GID),
            maximum=MAX_JSON_BYTES,
            label="phase B manifest",
        )
        manifest = strict_json(manifest_raw, "native builder phase B manifest")
        if (
            set(manifest)
            != {
                "schema",
                "status",
                "accepted",
                "phase",
                "request_pin",
                "source_commit",
                "source_bundle_pin",
                "jobs",
                "inventory",
                "claims",
                "content_digest",
            }
            or manifest.get("schema") != NATIVE_BUILDER_PHASE_B_SCHEMA
            or manifest.get("status") != "dedicated_builder_phase_closed"
            or manifest.get("accepted") is not False
            or manifest.get("phase") != "phase-b"
            or manifest.get("request_pin") != request_pin.public()
            or manifest.get("source_commit") != request["source_commit"]
            or manifest.get("source_bundle_pin") != request["source_bundle"]["pin"]
            or manifest.get("content_digest") != content_digest(manifest)
            or manifest.get("claims")
            != {
                "builder_uid_gid": [NATIVE_BUILDER_UID, NATIVE_BUILDER_GID],
                "network_access": False,
                "double_build_verified": True,
                "worktree_or_user_candidate_input": False,
                "closed": True,
            }
            or type(manifest.get("inventory")) is not dict
            or set(manifest["inventory"])
            != {
                "root_entries",
                "candidate",
                "installer",
            }
            or manifest["inventory"].get("root_entries")
            != [
                "initial-bootstrap-candidate",
                "initial-bootstrap-installer",
                "manifest.json",
                "manifests",
            ]
        ):
            _fail("NATIVE_BUILDER_MANIFEST_INVALID", "phase B manifest")
        yield (
            authority,
            {
                "request": request,
                "request_pin": request_pin,
                "manifest": manifest,
                "manifest_pin": manifest_pin,
            },
        )
        authority.revalidate()
    finally:
        authority.close()


def _native_builder_validate_phase_b_job(
    value: Any,
    *,
    expected_request: Mapping[str, Any],
    installer_source_pin: Mapping[str, Any],
    installer_pin: FilePin,
) -> dict[str, Any]:
    fields = {
        "schema",
        "status",
        "accepted",
        "phase",
        "job_id",
        "source",
        "bindings",
        "flags",
        "environment",
        "tools",
        "output",
        "determinism",
        "static_elf",
        "claims",
        "content_digest",
    }
    expected_job = expected_request["jobs"][0]
    if (
        type(value) is not dict
        or set(value) != fields
        or value.get("schema") != NATIVE_BUILDER_JOB_SCHEMA
        or value.get("status") != "deterministic_static_native_closed"
        or value.get("accepted") is not False
        or value.get("phase") != "phase-b"
        or value.get("job_id") != "initial-bootstrap-installer"
        or value.get("content_digest") != content_digest(value)
        or value.get("bindings") != expected_job["bindings"]
        or value.get("flags") != expected_job["flags"]
        or value.get("source")
        != {
            "git_bundle_pin": expected_request["source_bundle"]["pin"],
            "commit": expected_request["source_commit"],
            "git_path": expected_job["source_path"],
            "pin": dict(installer_source_pin),
            "compiled_from_sealed_memfd": True,
        }
        or value.get("environment") != NATIVE_BUILDER_BUILD_ENVIRONMENT
        or value.get("tools")
        != _native_builder_job_tools(
            expected_request["tools"], expected_request["trace_contract"]
        )
        or value.get("output")
        != {
            "relative_path": (
                "initial-bootstrap-installer/" + INITIAL_BOOTSTRAP_INSTALLER_NAME
            ),
            "mode": "0555",
            "pin": installer_pin.public(),
        }
        or value.get("determinism")
        != {
            "build_count": 2,
            "byte_identical": True,
            "first_pin": installer_pin.public(),
            "second_pin": installer_pin.public(),
        }
        or value.get("static_elf")
        != {
            "interpreter": None,
            "needed": [],
            "readelf_pin": expected_request["tools"]["readelf"]["pin"],
        }
        or value.get("claims")
        != {
            "builder_uid_gid": [NATIVE_BUILDER_UID, NATIVE_BUILDER_GID],
            "network_access": False,
            "worktree_input": False,
            "user_candidate_input": False,
        }
    ):
        _fail("NATIVE_BUILDER_MANIFEST_INVALID", "phase B installer job")
    return dict(value)


def build_initial_bootstrap_installer_review_candidate() -> dict[str, Any]:
    """Validate the dedicated Phase-B candidate and sole installer authority."""

    if os.geteuid() != REVIEW_UID or os.getegid() != REVIEW_GID:
        _fail("UNPRIVILEGED_REVIEW_REQUIRED", "initial bootstrap installer")
    phase_b_raw, _phase_b_pin = _read_regular(
        NATIVE_BUILDER_PHASE_B_REQUEST,
        "native builder phase B request",
        exact_mode=0o444,
    )
    phase_b_request = strict_json(phase_b_raw, "native builder phase B request")
    audit_binding = phase_b_request.get("phase_inputs", {}).get("core_review_audit", {})
    expected_request, initial_input, _audit = _derive_native_builder_phase_b_request(
        audit_binding.get("pin")
    )
    with _held_native_builder_phase_b(expected_request) as (authority, observed):
        candidate_files = {
            INITIAL_BOOTSTRAP_LAUNCHER_NAME: (
                0o555,
                expected_request["jobs"][0]["bindings"]["launcher_pin"],
            ),
            INITIAL_BOOTSTRAP_HELPER_SOURCE.name: (
                0o444,
                expected_request["jobs"][0]["bindings"]["helper_pin"],
            ),
            INITIAL_BOOTSTRAP_INPUT_NAME: (
                0o444,
                expected_request["jobs"][0]["bindings"]["input_pin"],
            ),
        }
        candidate_pins: dict[str, dict[str, Any]] = {}
        for name, (mode, expected_pin) in candidate_files.items():
            raw, pin = _native_builder_read_held(
                authority,
                path=INITIAL_BOOTSTRAP_REVIEW_CANDIDATE_ROOT / name,
                mode=mode,
                owner=(NATIVE_BUILDER_UID, NATIVE_BUILDER_GID),
                maximum=MAX_JSON_BYTES,
                label=f"phase B candidate:{name}",
            )
            if pin.public() != expected_pin:
                _fail("NATIVE_BUILDER_ARTIFACT_INVALID", name)
            if name == INITIAL_BOOTSTRAP_LAUNCHER_NAME:
                _stdlib_require_static_elf(raw, name)
            if (
                name == INITIAL_BOOTSTRAP_INPUT_NAME
                and strict_json(raw, "phase B initial input") != initial_input
            ):
                _fail("NATIVE_BUILDER_ARTIFACT_INVALID", name)
            candidate_pins[name] = pin.public()
        candidate_manifest_raw, candidate_manifest_pin = _native_builder_read_held(
            authority,
            path=NATIVE_BUILDER_PHASE_B_ROOT
            / "manifests/initial-bootstrap-candidate.json",
            mode=0o444,
            owner=(NATIVE_BUILDER_UID, NATIVE_BUILDER_GID),
            maximum=MAX_JSON_BYTES,
            label="phase B candidate manifest",
        )
        candidate_manifest = strict_json(
            candidate_manifest_raw, "phase B candidate manifest"
        )
        expected_candidate_manifest = seal_document(
            {
                "schema": ("vista.r8-native-builder-initial-candidate-manifest/v1"),
                "status": "initial_bootstrap_candidate_closed",
                "accepted": False,
                "files": [
                    {
                        "name": INITIAL_BOOTSTRAP_LAUNCHER_NAME,
                        "mode": "0555",
                        "pin": candidate_pins[INITIAL_BOOTSTRAP_LAUNCHER_NAME],
                        "provenance": initial_input["components"]["launcher"][
                            "build_provenance"
                        ],
                    },
                    {
                        "name": INITIAL_BOOTSTRAP_HELPER_SOURCE.name,
                        "mode": "0444",
                        "pin": candidate_pins[INITIAL_BOOTSTRAP_HELPER_SOURCE.name],
                        "git_path": ("tools/admin/vista_r8_ue57_initial_bootstrap.py"),
                    },
                    {
                        "name": INITIAL_BOOTSTRAP_INPUT_NAME,
                        "mode": "0444",
                        "pin": candidate_pins[INITIAL_BOOTSTRAP_INPUT_NAME],
                        "content_digest": initial_input["content_digest"],
                    },
                ],
            }
        )
        aggregate_inventory = observed["manifest"]["inventory"]
        if candidate_manifest != expected_candidate_manifest or aggregate_inventory.get(
            "candidate"
        ) != {
            "relative_path": "initial-bootstrap-candidate",
            "manifest": {
                "relative_path": ("manifests/initial-bootstrap-candidate.json"),
                "pin": candidate_manifest_pin.public(),
                "content_digest": candidate_manifest["content_digest"],
            },
        }:
            _fail("NATIVE_BUILDER_MANIFEST_INVALID", "phase B candidate manifest")
        installer_raw, installer_pin = _native_builder_read_held(
            authority,
            path=INITIAL_BOOTSTRAP_INSTALLER_REVIEW_CANDIDATE_ROOT
            / INITIAL_BOOTSTRAP_INSTALLER_NAME,
            mode=0o555,
            owner=(NATIVE_BUILDER_UID, NATIVE_BUILDER_GID),
            maximum=MAX_JSON_BYTES,
            label="phase B initial installer",
        )
        _stdlib_require_static_elf(installer_raw, "initial bootstrap installer")
        jobs = observed["manifest"].get("jobs")
        if type(jobs) is not list or len(jobs) != 1:
            _fail("NATIVE_BUILDER_MANIFEST_INVALID", "phase B job")
        job = jobs[0]
        expected_job = expected_request["jobs"][0]
        installer_source_pin = next(
            item["pin"]
            for item in expected_request["sources"]
            if item["path"] == expected_job["source_path"]
        )
        job = _native_builder_validate_phase_b_job(
            job,
            expected_request=expected_request,
            installer_source_pin=installer_source_pin,
            installer_pin=installer_pin,
        )
        job_raw, job_pin = _native_builder_read_held(
            authority,
            path=NATIVE_BUILDER_PHASE_B_ROOT
            / "manifests/initial-bootstrap-installer.json",
            mode=0o444,
            owner=(NATIVE_BUILDER_UID, NATIVE_BUILDER_GID),
            maximum=MAX_JSON_BYTES,
            label="phase B installer manifest",
        )
        if strict_json(job_raw, "phase B installer manifest") != job:
            _fail("NATIVE_BUILDER_MANIFEST_INVALID", "phase B installer manifest")
        if aggregate_inventory.get("installer") != {
            "relative_path": (
                "initial-bootstrap-installer/" + INITIAL_BOOTSTRAP_INSTALLER_NAME
            ),
            "mode": "0555",
            "pin": installer_pin.public(),
            "manifest": {
                "relative_path": "manifests/initial-bootstrap-installer.json",
                "pin": job_pin.public(),
                "content_digest": job["content_digest"],
            },
        }:
            _fail("NATIVE_BUILDER_MANIFEST_INVALID", "phase B aggregate inventory")
        authority.revalidate()
        return {
            "status": "dedicated_builder_initial_bootstrap_authority_validated",
            "accepted": False,
            "candidate_root": str(INITIAL_BOOTSTRAP_REVIEW_CANDIDATE_ROOT),
            "candidate_owner": [NATIVE_BUILDER_UID, NATIVE_BUILDER_GID],
            "candidate_files": candidate_pins,
            "installer": {
                "path": str(
                    INITIAL_BOOTSTRAP_INSTALLER_REVIEW_CANDIDATE_ROOT
                    / INITIAL_BOOTSTRAP_INSTALLER_NAME
                ),
                "pin": installer_pin.public(),
                "manifest_pin": job_pin.public(),
                "manual_install_root": str(INITIAL_BOOTSTRAP_INSTALLER_INSTALL_ROOT),
                "manual_install_mode": "0500",
            },
            "phase_b_manifest_pin": observed["manifest_pin"].public(),
            "phase_b_manifest_content_digest": observed["manifest"]["content_digest"],
            "root_execution_performed": False,
            "manual_trust_boundary_complete": False,
        }


def _derive_bundle_input_document(
    launcher_pin: FilePin, *, expected_build: Mapping[str, Any] | None = None
) -> dict[str, Any]:
    source_pins = _source_pins()
    runtime_executables = _runtime_executable_binding()
    launcher_build = _launcher_build_spec(source_pins, runtime_executables)
    if expected_build is not None and launcher_build != dict(expected_build):
        _fail("LAUNCHER_BUILD_INPUT_DRIFT", "build spec changed")
    engine_state = _load_engine_state()
    runtime_state = _load_runtime_state()
    buildplugin_state = _load_buildplugin_state()
    git_binding = _git_source_binding()
    return seal_document(
        {
            "schema": BUNDLE_INPUT_PIN_SCHEMA,
            "fixed_paths": {
                "root_execution_authority": str(ROOT_EXECUTION_AUTHORITY),
                "root_bundle": str(ROOT_BUNDLE),
                "root_policy": str(ROOT_POLICY),
                "engine_authority": str(ENGINE_AUTHORITY),
                "runtime_authority": str(HOST_RUNTIME_AUTHORITY),
                "buildplugin_authority": str(BUILDPLUGIN_AUTHORITY),
                "r3_project": str(R3_PROJECT_ROOT),
                "r3_receipt": str(R3_RECEIPT_PATH),
                "r8_authority": str(R8_AUTHORITY),
                "launcher_review_candidate": str(BUNDLE_LAUNCHER_REVIEW_CANDIDATE),
                "bundle_input_launcher": str(BUNDLE_INPUT_LAUNCHER),
            },
            "git": git_binding,
            "source_pins": source_pins,
            "launcher_build": launcher_build,
            "launcher_binary_pin": launcher_pin.public(),
            "engine": _authority_binding(engine_state, buildplugin=False),
            "host_runtime": _authority_binding(runtime_state, buildplugin=False),
            "buildplugin": _authority_binding(buildplugin_state, buildplugin=True),
            "runtime_executables": runtime_executables,
            "r3": _load_r3_binding(),
            "r8": _load_r8_binding(),
        }
    )


def build_bundle_input_review_candidate() -> dict[str, Any]:
    """Reject local launch-r8 compilation until its builder recipe is frozen."""

    _fail(
        "DEDICATED_BUILDER_AUTHORITY_REQUIRED",
        "executor launcher recipe is not authorized in native builder R2",
    )


def derive_bundle_input_pin() -> dict[str, Any]:
    """Read and live-rehash the atomic unprivileged bundle candidate."""

    if os.geteuid() == ROOT_UID:
        _fail("UNPRIVILEGED_REVIEW_REQUIRED", "bundle input discovery")
    _require_unprivileged_review_helper()
    _require_exact_directory(
        BUNDLE_INPUT_REVIEW_CANDIDATE.parent,
        {"input-pin.json", LAUNCHER_NAME},
        "bundle input review candidate",
        owner=(os.getuid(), os.getgid()),
    )
    document, _pin = _load_bundle_input_pin(review_candidate=True)
    _validate_bundle_input_against_live(document)
    return document


def validate_bundle_input_pin(document: Mapping[str, Any]) -> None:
    keys = {
        "schema",
        "fixed_paths",
        "git",
        "source_pins",
        "launcher_build",
        "launcher_binary_pin",
        "engine",
        "host_runtime",
        "buildplugin",
        "runtime_executables",
        "r3",
        "r8",
        "content_digest",
    }
    fixed_paths = {
        "root_execution_authority": str(ROOT_EXECUTION_AUTHORITY),
        "root_bundle": str(ROOT_BUNDLE),
        "root_policy": str(ROOT_POLICY),
        "engine_authority": str(ENGINE_AUTHORITY),
        "runtime_authority": str(HOST_RUNTIME_AUTHORITY),
        "buildplugin_authority": str(BUILDPLUGIN_AUTHORITY),
        "r3_project": str(R3_PROJECT_ROOT),
        "r3_receipt": str(R3_RECEIPT_PATH),
        "r8_authority": str(R8_AUTHORITY),
        "launcher_review_candidate": str(BUNDLE_LAUNCHER_REVIEW_CANDIDATE),
        "bundle_input_launcher": str(BUNDLE_INPUT_LAUNCHER),
    }
    if (
        set(document) != keys
        or document.get("schema") != BUNDLE_INPUT_PIN_SCHEMA
        or document.get("content_digest") != content_digest(document)
        or document.get("fixed_paths") != fixed_paths
    ):
        _fail("BUNDLE_INPUT_PIN_INVALID", "closed document")
    for name in ("engine", "host_runtime", "buildplugin"):
        _validate_publication_binding(document[name], name)
    git = document.get("git")
    if (
        type(git) is not dict
        or set(git)
        != {
            "checkout_root",
            "commit",
            "git_canonical",
            "git_pin",
            "tracked_paths",
        }
        or git.get("checkout_root") != str(CHECKOUT_ROOT)
        or type(git.get("commit")) is not str
        or re.fullmatch(r"[0-9a-f]{40}", git["commit"]) is None
        or type(git.get("tracked_paths")) is not list
        or git["tracked_paths"] != _reviewed_git_relative_paths()
        or type(git.get("git_canonical")) is not str
        or not Path(git["git_canonical"]).is_absolute()
    ):
        _fail("BUNDLE_INPUT_PIN_INVALID", "Git binding")
    _parse_pin(git["git_pin"], "Git")
    expected_sources = {**BUNDLE_SOURCE_PATHS, LAUNCHER_SOURCE.name: LAUNCHER_SOURCE}
    source_pins = document.get("source_pins")
    if type(source_pins) is not dict or set(source_pins) != set(expected_sources):
        _fail("BUNDLE_INPUT_PIN_INVALID", "source pins")
    for name, path in expected_sources.items():
        value = source_pins[name]
        if (
            type(value) is not dict
            or set(value) != {"path", "pin"}
            or value.get("path") != str(path)
        ):
            _fail("BUNDLE_INPUT_PIN_INVALID", f"source {name}")
        _parse_pin(value["pin"], f"source {name}")
    build = _validate_launcher_build_spec(document["launcher_build"])
    if build["source_pin"] != source_pins[LAUNCHER_SOURCE.name]["pin"]:
        _fail("BUNDLE_INPUT_PIN_INVALID", "launcher source binding")
    _parse_pin(document["launcher_binary_pin"], "launcher binary")
    runtime_executables = document.get("runtime_executables")
    expected_runtime_paths = {
        "python": HOST_RUNTIME_PAYLOAD / "usr/bin/python3.10",
        "bwrap": HOST_RUNTIME_PAYLOAD / "usr/bin/bwrap",
        "loader": HOST_RUNTIME_PAYLOAD / "lib64/ld-linux-x86-64.so.2",
    }
    if type(runtime_executables) is not dict or set(runtime_executables) != set(
        expected_runtime_paths
    ):
        _fail("BUNDLE_INPUT_PIN_INVALID", "runtime executables")
    for name, path in expected_runtime_paths.items():
        value = runtime_executables[name]
        if (
            type(value) is not dict
            or set(value) != {"path", "pin"}
            or value.get("path") != str(path)
        ):
            _fail("BUNDLE_INPUT_PIN_INVALID", f"runtime {name}")
        _parse_pin(value["pin"], f"runtime {name}")
    r3 = document.get("r3")
    if (
        type(r3) is not dict
        or set(r3) != {"receipt_pin", "receipt_content_digest", "project"}
        or type(r3.get("receipt_content_digest")) is not str
        or SHA256_RE.fullmatch(r3["receipt_content_digest"]) is None
    ):
        _fail("BUNDLE_INPUT_PIN_INVALID", "R3")
    _parse_pin(r3["receipt_pin"], "R3 receipt")
    _validate_publication_binding(
        {
            "manifest_pin": r3["receipt_pin"],
            "manifest_content_digest": r3["receipt_content_digest"],
            "receipt_pin": r3["receipt_pin"],
            "receipt_content_digest": r3["receipt_content_digest"],
            "payload": r3["project"],
        },
        "R3 projection",
    )
    r8 = document.get("r8")
    if (
        type(r8) is not dict
        or set(r8)
        != {
            "attempt_name",
            "receipt_pin",
            "receipt_content_digest",
            "fbx_files",
        }
        or r8.get("attempt_name") != R8_ATTEMPT_NAME
        or type(r8.get("receipt_content_digest")) is not str
        or SHA256_RE.fullmatch(r8["receipt_content_digest"]) is None
        or type(r8.get("fbx_files")) is not list
        or [item.get("relative_path") for item in r8["fbx_files"]]
        != list(R8_FBX_RELATIVE_PATHS)
    ):
        _fail("BUNDLE_INPUT_PIN_INVALID", "R8")
    _parse_pin(r8["receipt_pin"], "R8 receipt")
    for index, item in enumerate(r8["fbx_files"]):
        if type(item) is not dict or set(item) != {
            "relative_path",
            "sha256",
            "size_bytes",
        }:
            _fail("BUNDLE_INPUT_PIN_INVALID", f"R8 FBX[{index}]")
        _parse_pin(
            {"sha256": item["sha256"], "size_bytes": item["size_bytes"]},
            f"R8 FBX[{index}]",
        )


def _load_bundle_input_pin(
    *, review_candidate: bool = False
) -> tuple[dict[str, Any], FilePin]:
    path = BUNDLE_INPUT_REVIEW_CANDIDATE if review_candidate else BUNDLE_INPUT_PIN_PATH
    document, pin = load_sealed_document(
        path, BUNDLE_INPUT_PIN_SCHEMA, "bundle input pin"
    )
    validate_bundle_input_pin(document)
    return document, pin


def _validate_bundle_input_against_live(
    expected: Mapping[str, Any],
    *,
    reviewed_launcher_pin: FilePin | None = None,
) -> dict[str, Any]:
    validate_bundle_input_pin(expected)
    engine_state = _load_engine_state()
    runtime_state = _load_runtime_state()
    buildplugin_state = _load_buildplugin_state()
    source_pins = _source_pins()
    runtime_executables = _runtime_executable_binding()
    reviewed_build = _validate_launcher_build_spec(expected["launcher_build"])
    if reviewed_build["source_pin"] != source_pins[LAUNCHER_SOURCE.name]["pin"]:
        _fail("BUNDLE_INPUT_REVIEWED_PIN_MISMATCH", "launcher source differs")
    if os.geteuid() != ROOT_UID:
        # Compiler/toolchain discovery is review-only.  Privileged publication
        # treats this ledger as reviewed provenance and never opens or executes
        # GCC, cc1, as, ld, specs, or any other toolchain artifact.
        if _launcher_build_spec(source_pins, runtime_executables) != reviewed_build:
            _fail("BUNDLE_INPUT_REVIEWED_PIN_MISMATCH", "build inputs differ")
    authority_bindings = {
        "engine": _authority_binding(engine_state, buildplugin=False),
        "host_runtime": _authority_binding(runtime_state, buildplugin=False),
        "buildplugin": _authority_binding(buildplugin_state, buildplugin=True),
    }
    if reviewed_launcher_pin is None:
        launcher_path = (
            BUNDLE_INPUT_LAUNCHER
            if os.geteuid() == ROOT_UID
            else BUNDLE_LAUNCHER_REVIEW_CANDIDATE
        )
        launcher_raw, live_launcher_pin = _read_regular(
            launcher_path, "reviewed launcher binary", exact_mode=0o555
        )
        if not launcher_raw.startswith(b"\x7fELF"):
            _fail("BUNDLE_INPUT_REVIEWED_PIN_MISMATCH", "launcher is not ELF")
        reviewed_launcher_pin = FilePin(
            live_launcher_pin.sha256, live_launcher_pin.size_bytes, True
        )
    if (
        source_pins != expected["source_pins"]
        or runtime_executables != expected["runtime_executables"]
        or reviewed_launcher_pin.public() != expected["launcher_binary_pin"]
        or any(
            expected[name] != binding for name, binding in authority_bindings.items()
        )
        or _load_r3_binding() != expected["r3"]
        or _load_r8_binding() != expected["r8"]
    ):
        _fail("BUNDLE_INPUT_REVIEWED_PIN_MISMATCH", "live inputs differ")
    # Git commit/tracked proof is produced once during unprivileged input
    # discovery.  Root never executes Git; exact source-byte rehashing above is
    # the privileged enforcement boundary.
    return dict(expected)


def _copy_reviewed_runtime_inventory(
    inventory: Sequence[Mapping[str, Any]],
    payload: Path,
    *,
    owner: tuple[int, int],
) -> None:
    for index, value in enumerate(inventory):
        expected = _validate_source_record(value, f"inventory[{index}]")
        source = Path(expected["source"])
        destination = payload / expected["destination"]
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with hold_source_file_components(source) as held:
            if _source_is_forbidden(held.canonical_path):
                _fail("RUNTIME_SOURCE_FORBIDDEN", str(source))
            digest, size = _hash_fd(held.descriptor)
            actual = {
                "destination": expected["destination"],
                "category": expected["category"],
                "source": str(source),
                "source_canonical": str(held.canonical_path),
                "source_identity": {
                    "device": held.metadata.st_dev,
                    "inode": held.metadata.st_ino,
                    "mode": stat.S_IMODE(held.metadata.st_mode),
                    "uid": held.metadata.st_uid,
                    "gid": held.metadata.st_gid,
                    "link_count": held.metadata.st_nlink,
                    "mtime_ns": held.metadata.st_mtime_ns,
                    "ctime_ns": held.metadata.st_ctime_ns,
                },
                "sha256": digest,
                "size_bytes": size,
                "mode": expected["mode"],
                "symlink_resolutions": list(held.symlink_resolutions),
            }
            if actual != expected:
                _fail("RUNTIME_SOURCE_DRIFT", str(source))
            target = os.open(
                destination,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                0o600,
            )
            try:
                copied = _copy_file_fd(held.descriptor, target)
                if (copied.sha256, copied.size_bytes) != (digest, size) or _identity(
                    os.fstat(held.descriptor)
                ) != _identity(held.metadata):
                    _fail("RUNTIME_SOURCE_DRIFT", str(source))
                os.fchown(target, *owner)
                os.fchmod(target, expected["mode"])
                os.fsync(target)
            finally:
                os.close(target)


def _seal_private_tree(root: Path, *, owner: tuple[int, int]) -> None:
    directories: list[Path] = []
    for current, child_directories, files in os.walk(
        root, topdown=True, followlinks=False
    ):
        current_path = Path(current)
        directories.append(current_path)
        for name in (*child_directories, *files):
            child = current_path / name
            metadata = os.lstat(child)
            if not (stat.S_ISDIR(metadata.st_mode) or stat.S_ISREG(metadata.st_mode)):
                _fail("STAGING_SPECIAL_NODE", str(child))
            if metadata.st_nlink != 1 and stat.S_ISREG(metadata.st_mode):
                _fail("STAGING_HARDLINK_ALIAS", str(child))
    for directory in sorted(
        directories, key=lambda path: len(path.parts), reverse=True
    ):
        descriptor = os.open(directory, _directory_flags())
        try:
            os.fchown(descriptor, *owner)
            os.fchmod(descriptor, 0o555)
            os.fsync(descriptor)
        finally:
            os.close(descriptor)


def _fsync_immutable_tree(root: Path, label: str) -> None:
    def visit(descriptor: int, relative: str) -> None:
        for name in sorted(os.listdir(descriptor)):
            before = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
            child_label = f"{relative}/{name}" if relative else name
            if stat.S_ISDIR(before.st_mode):
                child = os.open(name, _directory_flags(), dir_fd=descriptor)
                try:
                    if _identity(os.fstat(child)) != _identity(before):
                        _fail("DURABILITY_RECONCILIATION_INVALID", child_label)
                    visit(child, child_label)
                finally:
                    os.close(child)
            elif stat.S_ISREG(before.st_mode):
                child = os.open(name, _file_flags(), dir_fd=descriptor)
                try:
                    if _identity(os.fstat(child)) != _identity(before):
                        _fail("DURABILITY_RECONCILIATION_INVALID", child_label)
                    os.fsync(child)
                finally:
                    os.close(child)
            else:
                _fail("DURABILITY_RECONCILIATION_INVALID", child_label)
        os.fsync(descriptor)

    root_fd = os.open(root, _directory_flags())
    parent_fd = os.open(root.parent, _directory_flags())
    try:
        visit(root_fd, "")
        os.fsync(parent_fd)
    except OSError as exc:
        raise AuthorityError("DURABILITY_RECONCILIATION_FAILED", label) from exc
    finally:
        os.close(parent_fd)
        os.close(root_fd)


def _fsync_fixed_directory(path: Path, label: str) -> None:
    try:
        descriptor = os.open(path, _directory_flags())
    except OSError as exc:
        raise AuthorityError("DURABILITY_RECONCILIATION_FAILED", label) from exc
    try:
        os.fsync(descriptor)
    except OSError as exc:
        raise AuthorityError("DURABILITY_RECONCILIATION_FAILED", label) from exc
    finally:
        os.close(descriptor)


def copy_selected_regular_files(
    selected: Mapping[Path, Path],
    payload: Path,
    *,
    owner: tuple[int, int],
    executable_pins: Mapping[Path, FilePin] | None = None,
) -> list[dict[str, Any]]:
    executable_pins = {} if executable_pins is None else dict(executable_pins)
    if not set(executable_pins).issubset(selected):
        _fail("RUNTIME_EXECUTABLE_ALLOWLIST_INVALID", "extra executable pin")
    folded: set[str] = set()
    inventory: list[dict[str, Any]] = []
    for destination_relative, source_path in sorted(
        selected.items(), key=lambda item: str(item[0])
    ):
        relative = destination_relative.as_posix()
        if not _safe_relative(relative) or relative.casefold() in folded:
            _fail("RUNTIME_DESTINATION_INVALID", relative)
        folded.add(relative.casefold())
        destination = payload / relative
        destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with hold_source_file_components(source_path) as held:
            if held.canonical_path in FORBIDDEN_RUNTIME_SOURCE_FILES or any(
                held.canonical_path == prefix
                or held.canonical_path.is_relative_to(prefix)
                for prefix in FORBIDDEN_RUNTIME_SOURCE_PREFIXES
            ):
                _fail("RUNTIME_SOURCE_FORBIDDEN", str(source_path))
            target = os.open(
                destination,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                0o600,
            )
            try:
                copied = _copy_file_fd(held.descriptor, target)
                if _identity(os.fstat(held.descriptor)) != _identity(held.metadata):
                    _fail("RUNTIME_SOURCE_DRIFT", str(source_path))
                executable_pin = executable_pins.get(destination_relative)
                if executable_pin is not None and (
                    copied.sha256,
                    copied.size_bytes,
                ) != (executable_pin.sha256, executable_pin.size_bytes):
                    _fail("RUNTIME_EXECUTABLE_PIN_MISMATCH", relative)
                os.fchown(target, *owner)
                final_mode = 0o555 if executable_pin is not None else 0o444
                os.fchmod(target, final_mode)
                os.fsync(target)
            finally:
                os.close(target)
            inventory.append(
                {
                    "destination": relative,
                    "source": str(source_path),
                    "source_canonical": str(held.canonical_path),
                    "sha256": copied.sha256,
                    "size_bytes": copied.size_bytes,
                    "mode": final_mode,
                    "symlink_resolutions": list(held.symlink_resolutions),
                }
            )
    return inventory


def runtime_manifest(snapshot: TreeSnapshot) -> dict[str, Any]:
    return seal_document(
        {
            "schema": HOST_RUNTIME_MANIFEST_SCHEMA,
            "authority_root": str(HOST_RUNTIME_AUTHORITY),
            "payload_root": str(HOST_RUNTIME_PAYLOAD),
            "entries": list(snapshot.entries),
            "projection": snapshot.projection(),
        }
    )


def _validate_pin_content_binding(value: Any, label: str) -> dict[str, Any]:
    if (
        type(value) is not dict
        or set(value) != {"pin", "content_digest"}
        or type(value.get("content_digest")) is not str
        or SHA256_RE.fullmatch(value["content_digest"]) is None
    ):
        _fail("RUNTIME_RECEIPT_PROVENANCE_INVALID", label)
    _parse_pin(value["pin"], label)
    return dict(value)


def _validate_audit_plan_binding(value: Any, label: str) -> dict[str, Any]:
    if (
        type(value) is not dict
        or set(value) != {"sha256", "size_bytes", "content_digest"}
        or type(value.get("sha256")) is not str
        or SHA256_RE.fullmatch(value["sha256"]) is None
        or type(value.get("size_bytes")) is not int
        or value["size_bytes"] < 0
        or type(value.get("content_digest")) is not str
        or SHA256_RE.fullmatch(value["content_digest"]) is None
    ):
        _fail("RUNTIME_RECEIPT_PROVENANCE_INVALID", label)
    return dict(value)


def _validate_runtime_reviewed_publication(value: Any) -> dict[str, Any]:
    if type(value) is not dict or set(value) != {
        "input_pin",
        "reviewed_plan_pin",
        "audit_plan",
    }:
        _fail("RUNTIME_RECEIPT_PROVENANCE_INVALID", "reviewed publication")
    return {
        "input_pin": _validate_pin_content_binding(
            value["input_pin"], "runtime input pin"
        ),
        "reviewed_plan_pin": _validate_pin_content_binding(
            value["reviewed_plan_pin"], "runtime reviewed plan pin"
        ),
        "audit_plan": _validate_audit_plan_binding(
            value["audit_plan"], "runtime audit plan"
        ),
    }


def _validate_runtime_publisher(value: Any) -> dict[str, Any]:
    keys = {
        "helper_pin",
        "runtime_admin_launcher_pin",
        "interpreter_pin",
    }
    if type(value) is not dict or set(value) != keys:
        _fail("RUNTIME_RECEIPT_PROVENANCE_INVALID", "publisher")
    for name in sorted(keys):
        _parse_pin(value[name], f"runtime publisher {name}")
    return dict(value)


def runtime_receipt(
    snapshot: TreeSnapshot,
    manifest_pin: FilePin,
    manifest_content_digest: str,
    input_pin: Mapping[str, Any],
    *,
    reviewed_publication: Mapping[str, Any],
    publisher: Mapping[str, Any],
) -> dict[str, Any]:
    expected_input_keys = {
        "engine_manifest_pin",
        "buildplugin_manifest_pin",
        "buildplugin_receipt_pin",
        "python_pin",
        "readelf_pin",
    }
    if set(input_pin) != expected_input_keys:
        _fail("RUNTIME_RECEIPT_INPUT_INVALID", "input pin fields")
    for name in sorted(expected_input_keys):
        _parse_pin(input_pin[name], f"runtime receipt {name}")
    _parse_pin(manifest_pin.public(), "runtime manifest")
    if (
        type(manifest_content_digest) is not str
        or SHA256_RE.fullmatch(manifest_content_digest) is None
    ):
        _fail("RUNTIME_RECEIPT_INPUT_INVALID", "manifest content digest")
    return seal_document(
        {
            "schema": HOST_RUNTIME_RECEIPT_SCHEMA,
            "status": "root_published_immutable_host_runtime_authority",
            "accepted": True,
            "authority_root": str(HOST_RUNTIME_AUTHORITY),
            "manifest_pin": manifest_pin.public(),
            "manifest_content_digest": manifest_content_digest,
            "payload": snapshot.projection(),
            "source_authorities": {
                "engine_manifest_pin": input_pin["engine_manifest_pin"],
                "buildplugin_manifest_pin": input_pin["buildplugin_manifest_pin"],
                "buildplugin_receipt_pin": input_pin["buildplugin_receipt_pin"],
            },
            "tool_pins": {
                "python_pin": input_pin["python_pin"],
                "readelf_pin": input_pin["readelf_pin"],
            },
            "reviewed_publication": _validate_runtime_reviewed_publication(
                reviewed_publication
            ),
            "publisher": _validate_runtime_publisher(publisher),
            "claims": {
                "allowlisted_runtime_closure_only": True,
                "ldd_executed": False,
                "final_contains_symlinks": False,
                "secrets_copied": False,
                "gpu_runtime_included": False,
            },
        }
    )


def _pin_path(path: Path, expected: Any, label: str) -> FilePin:
    _raw, actual = _read_regular(path, label)
    pin = _parse_pin(expected, label)
    if (actual.sha256, actual.size_bytes) != (pin.sha256, pin.size_bytes):
        _fail("PIN_MISMATCH", label)
    return actual


def bundle_manifest(pins: Mapping[str, FilePin]) -> dict[str, Any]:
    return seal_document(
        {
            "schema": BUNDLE_MANIFEST_SCHEMA,
            "files": [
                {
                    "path": name,
                    "sha256": pin.sha256,
                    "size_bytes": pin.size_bytes,
                    "executable": pin.executable,
                }
                for name, pin in sorted(pins.items())
            ],
        }
    )


def runtime_audit_plan(
    *,
    input_pin: Mapping[str, Any],
    authority_pins: Mapping[str, Any],
    inventory: Sequence[Mapping[str, Any]],
    symlink_resolutions: Sequence[Mapping[str, Any]],
    elf_seeds: Sequence[Mapping[str, Any]],
    elf_graph: Sequence[Mapping[str, Any]],
    generated_etc: Mapping[str, str],
    data_allowlist: Sequence[Mapping[str, Any]],
    tool_pins: Mapping[str, Any],
    executable_destinations: Sequence[str],
    final_projection: Mapping[str, Any],
) -> dict[str, Any]:
    """Canonical review artifact; creating it performs no authority write."""

    return seal_document(
        {
            "schema": RUNTIME_AUDIT_PLAN_SCHEMA,
            "status": "review_required_before_host_runtime_publication",
            "accepted": False,
            "input_pin": dict(input_pin),
            "authority_pins": dict(authority_pins),
            "inventory": list(inventory),
            "symlink_resolutions": list(symlink_resolutions),
            "elf_seeds": list(elf_seeds),
            "elf_graph": list(elf_graph),
            "generated_etc": dict(generated_etc),
            "data_allowlist": list(data_allowlist),
            "tool_pins": dict(tool_pins),
            "executable_destinations": list(executable_destinations),
            "final_projection": dict(final_projection),
            "publication_performed": False,
        }
    )


def bundle_audit_plan(
    *,
    input_pin: Mapping[str, Any],
    source_pins: Mapping[str, Mapping[str, Any]],
    launcher_build: Mapping[str, Any],
    launcher_binary_pin: Mapping[str, Any],
    authority_pins: Mapping[str, Any],
    bundle_manifest_document: Mapping[str, Any],
    policy_core_document: Mapping[str, Any],
) -> dict[str, Any]:
    return seal_document(
        {
            "schema": BUNDLE_AUDIT_PLAN_SCHEMA,
            "status": "review_required_before_executor_bundle_publication",
            "accepted": False,
            "input_pin": dict(input_pin),
            "source_pins": dict(source_pins),
            "launcher_build": dict(launcher_build),
            "launcher_binary_pin": dict(launcher_binary_pin),
            "authority_pins": dict(authority_pins),
            "bundle_manifest_document": dict(bundle_manifest_document),
            # The final v3 policy adds the reviewed plan digest after this
            # plan is sealed.  Keeping the core here avoids a hash cycle.
            "policy_core_document": dict(policy_core_document),
            "root_layout": {
                "authority": str(ROOT_EXECUTION_AUTHORITY),
                "bundle": str(ROOT_BUNDLE),
                "policy": str(ROOT_POLICY),
                "single_atomic_rename": True,
            },
            "publication_performed": False,
        }
    )


def reviewed_plan_pin(
    plan: Mapping[str, Any], admin_launcher_pin: FilePin
) -> dict[str, Any]:
    raw = canonical_json(plan)
    _parse_pin(admin_launcher_pin.public(), "admin launcher")
    return seal_document(
        {
            "schema": REVIEWED_PLAN_PIN_SCHEMA,
            "plan_schema": plan.get("schema"),
            "plan_sha256": hashlib.sha256(raw).hexdigest(),
            "plan_size_bytes": len(raw),
            "plan_content_digest": plan.get("content_digest"),
            "admin_launcher_pin": admin_launcher_pin.public(),
        }
    )


def validate_reviewed_plan(
    plan: Mapping[str, Any],
    reviewed_pin: Mapping[str, Any],
    admin_launcher_pin: FilePin,
) -> None:
    if (
        set(reviewed_pin)
        != {
            "schema",
            "plan_schema",
            "plan_sha256",
            "plan_size_bytes",
            "plan_content_digest",
            "admin_launcher_pin",
            "content_digest",
        }
        or reviewed_pin.get("schema") != REVIEWED_PLAN_PIN_SCHEMA
        or reviewed_pin.get("content_digest") != content_digest(reviewed_pin)
    ):
        _fail("REVIEWED_AUDIT_PLAN_PIN_INVALID", str(plan.get("schema")))
    expected = reviewed_plan_pin(plan, admin_launcher_pin)
    if dict(reviewed_pin) != expected:
        _fail("REVIEWED_AUDIT_PLAN_PIN_MISMATCH", str(plan.get("schema")))


def _runtime_plan_from_input(
    document: Mapping[str, Any], pin: FilePin
) -> dict[str, Any]:
    validate_runtime_input_pin(document)
    return runtime_audit_plan(
        input_pin={
            "path": str(RUNTIME_INPUT_PIN_PATH),
            "pin": pin.public(),
            "content_digest": document["content_digest"],
        },
        authority_pins={
            "engine": document["engine"],
            "buildplugin": document["buildplugin"],
        },
        inventory=document["inventory"],
        symlink_resolutions=document["symlink_resolutions"],
        elf_seeds=document["elf_seeds"],
        elf_graph=document["elf_graph"],
        generated_etc=document["generated_etc"],
        data_allowlist=document["data_allowlist"],
        tool_pins=document["tool_pins"],
        executable_destinations=document["executable_destinations"],
        final_projection=document["final_projection"],
    )


def _load_reviewed_plan_pin(
    path: Path, plan: Mapping[str, Any], label: str, launcher_path: Path
) -> tuple[dict[str, Any], FilePin]:
    _launcher_raw, launcher_pin = _read_regular(
        launcher_path, f"{label} admin launcher", exact_mode=0o555
    )
    document, pin = load_sealed_document(
        path, REVIEWED_PLAN_PIN_SCHEMA, f"{label} reviewed plan pin"
    )
    validate_reviewed_plan(
        plan,
        document,
        FilePin(launcher_pin.sha256, launcher_pin.size_bytes, True),
    )
    return document, pin


def _bundle_file_pins(document: Mapping[str, Any]) -> dict[str, FilePin]:
    result: dict[str, FilePin] = {}
    for name in BUNDLE_SOURCE_PATHS:
        source_pin = _parse_pin(document["source_pins"][name]["pin"], name)
        result[name] = FilePin(
            source_pin.sha256,
            source_pin.size_bytes,
            name == "makehuman_cc0_animation_runtime_executor.py",
        )
    launcher = _parse_pin(document["launcher_binary_pin"], "launcher binary")
    result[LAUNCHER_NAME] = FilePin(launcher.sha256, launcher.size_bytes, True)
    return result


def _bundle_plan_from_input(
    document: Mapping[str, Any], input_file_pin: FilePin
) -> dict[str, Any]:
    validate_bundle_input_pin(document)
    engine_state = _load_engine_state()
    runtime_state = _load_runtime_state()
    buildplugin_state = _load_buildplugin_state()
    expected_bindings = {
        "engine": _authority_binding(engine_state, buildplugin=False),
        "host_runtime": _authority_binding(runtime_state, buildplugin=False),
        "buildplugin": _authority_binding(buildplugin_state, buildplugin=True),
    }
    if any(document[name] != value for name, value in expected_bindings.items()):
        _fail("BUNDLE_INPUT_REVIEWED_PIN_MISMATCH", "sealed authorities differ")
    bundle_pins = _bundle_file_pins(document)
    manifest_document = bundle_manifest(bundle_pins)
    manifest_raw = canonical_json(manifest_document)
    manifest_pin = FilePin(hashlib.sha256(manifest_raw).hexdigest(), len(manifest_raw))
    policy_input = {
        "python_pin": document["runtime_executables"]["python"]["pin"],
        "bwrap_pin": document["runtime_executables"]["bwrap"]["pin"],
        "r3": document["r3"],
        "r8": {
            "attempt_name": document["r8"]["attempt_name"],
            "receipt_pin": document["r8"]["receipt_pin"],
            "receipt_content_digest": document["r8"]["receipt_content_digest"],
        },
    }
    policy_core = build_root_policy_core(
        bundle_pins=bundle_pins,
        bundle_manifest_pin=manifest_pin,
        bundle_manifest_content_digest=manifest_document["content_digest"],
        input_pin=policy_input,
        engine_document=engine_state["manifest"],
        engine_pin=engine_state["manifest_pin"],
        engine_receipt_document=engine_state["receipt"],
        engine_receipt_pin=engine_state["receipt_pin"],
        runtime_document=runtime_state["manifest"],
        runtime_manifest_pin=runtime_state["manifest_pin"],
        runtime_receipt_document=runtime_state["receipt"],
        runtime_receipt_pin=runtime_state["receipt_pin"],
        buildplugin_document=buildplugin_state["manifest"],
        buildplugin_manifest_pin=buildplugin_state["manifest_pin"],
        buildplugin_receipt_document=buildplugin_state["receipt"],
        buildplugin_receipt_pin=buildplugin_state["receipt_pin"],
    )
    return bundle_audit_plan(
        input_pin={
            "path": str(BUNDLE_INPUT_PIN_PATH),
            "pin": input_file_pin.public(),
            "content_digest": document["content_digest"],
        },
        source_pins=document["source_pins"],
        launcher_build=document["launcher_build"],
        launcher_binary_pin=document["launcher_binary_pin"],
        authority_pins={
            **expected_bindings,
            "runtime_executables": document["runtime_executables"],
            "r3": document["r3"],
            "r8": document["r8"],
        },
        bundle_manifest_document=manifest_document,
        policy_core_document=policy_core,
    )


def _require_user_review_candidate(
    root: Path,
    files: Mapping[Path, int],
    label: str,
) -> None:
    _require_exact_directory(
        root,
        {path.name for path in files},
        label,
        owner=(REVIEW_UID, REVIEW_GID),
    )
    for path, mode in files.items():
        try:
            metadata = os.lstat(path)
        except OSError as exc:
            raise AuthorityError("UNPRIVILEGED_REVIEW_PATH_INVALID", label) from exc
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or metadata.st_uid != REVIEW_UID
            or metadata.st_gid != REVIEW_GID
            or stat.S_IMODE(metadata.st_mode) != mode
        ):
            _fail("UNPRIVILEGED_REVIEW_PATH_INVALID", str(path))


def _stage_candidate_configuration(
    stage: str,
) -> tuple[Path, Path, Path, Path, Path]:
    if stage == "runtime":
        return (
            RUNTIME_INPUT_REVIEW_CANDIDATE.parent,
            RUNTIME_INPUT_REVIEW_CANDIDATE,
            RUNTIME_PLAN_REVIEW_CANDIDATE_ROOT,
            RUNTIME_REVIEWED_PLAN_CANDIDATE,
            RUNTIME_ADMIN_LAUNCHER_CANDIDATE,
        )
    if stage == "bundle":
        return (
            BUNDLE_INPUT_REVIEW_CANDIDATE.parent,
            BUNDLE_INPUT_REVIEW_CANDIDATE,
            BUNDLE_PLAN_REVIEW_CANDIDATE_ROOT,
            BUNDLE_REVIEWED_PLAN_CANDIDATE,
            BUNDLE_ADMIN_LAUNCHER_CANDIDATE,
        )
    _fail("STAGE_AUTHORITY_INVALID", stage)


def _build_stage_plan_review_candidate(stage: str) -> dict[str, Any]:
    """Reject local runtime/bundle administrator compilation."""

    _fail(
        "DEDICATED_BUILDER_AUTHORITY_REQUIRED",
        f"{stage} admin launcher recipe is not authorized in native builder R2",
    )


def build_runtime_plan_review_candidate() -> dict[str, Any]:
    return _build_stage_plan_review_candidate("runtime")


def build_bundle_plan_review_candidate() -> dict[str, Any]:
    return _build_stage_plan_review_candidate("bundle")


def _stage_installer_build_inputs(
    key: str,
) -> tuple[FilePin, FilePin | None, FilePin, dict[str, Any]]:
    """Load only user-readable frozen candidates for a one-shot installer."""

    if key not in STAGE_KEYS:
        _fail("STAGE_AUTHORITY_INVALID", key)
    stage, phase = key.split("-", 1)
    input_root, input_path, plan_root, plan_path, admin_path = (
        _stage_candidate_configuration(stage)
    )
    if stage == "runtime":
        _require_user_review_candidate(
            input_root,
            {input_path: 0o444},
            "runtime input candidate for stage installer",
        )
        input_document, input_file_pin = _load_runtime_input_pin(review_candidate=True)
        python_pin = _parse_pin(
            input_document["tool_pins"]["python"]["pin"],
            "runtime stage installer Python",
        )
        plan = _runtime_plan_from_input(input_document, input_file_pin)
    else:
        _require_user_review_candidate(
            input_root,
            {
                input_path: 0o444,
                BUNDLE_LAUNCHER_REVIEW_CANDIDATE: 0o555,
            },
            "bundle input candidate for stage installer",
        )
        input_document, input_file_pin = _load_bundle_input_pin(review_candidate=True)
        _launcher_raw, launcher_pin = _read_regular(
            BUNDLE_LAUNCHER_REVIEW_CANDIDATE,
            "bundle input candidate launcher",
            exact_mode=0o555,
        )
        expected_launcher = _parse_pin(
            input_document["launcher_binary_pin"], "bundle candidate launcher"
        )
        if (launcher_pin.sha256, launcher_pin.size_bytes) != (
            expected_launcher.sha256,
            expected_launcher.size_bytes,
        ):
            _fail("STAGE_INSTALLER_BUILD_INPUT_DRIFT", "bundle launcher")
        python_pin = _parse_pin(
            input_document["runtime_executables"]["python"]["pin"],
            "bundle stage installer Python",
        )
        plan = _bundle_plan_from_input(input_document, input_file_pin)
    if phase == "input":
        return (
            input_file_pin,
            None,
            python_pin,
            {
                "candidate_root": str(input_root),
                "primary_name": input_path.name,
                "primary_pin": input_file_pin.public(),
                "primary_content_digest": input_document["content_digest"],
            },
        )
    _require_user_review_candidate(
        plan_root,
        {plan_path: 0o444, admin_path: 0o555},
        f"{stage} plan candidate for stage installer",
    )
    reviewed_document, reviewed_pin = _load_reviewed_plan_pin(
        plan_path, plan, stage, admin_path
    )
    admin_pin = _parse_pin(
        reviewed_document["admin_launcher_pin"],
        f"{stage} reviewed admin launcher",
    )
    return (
        reviewed_pin,
        admin_pin,
        python_pin,
        {
            "candidate_root": str(plan_root),
            "primary_name": plan_path.name,
            "primary_pin": reviewed_pin.public(),
            "primary_content_digest": reviewed_document["content_digest"],
            "secondary_name": admin_path.name,
            "secondary_pin": admin_pin.public(),
        },
    )


def build_stage_installer_review_candidate(key: str) -> dict[str, Any]:
    """Reject all four local stage-installer builds until recipes are frozen."""

    _fail(
        "DEDICATED_BUILDER_AUTHORITY_REQUIRED",
        f"{key} stage-installer recipe is not authorized in native builder R2",
    )


def _stage_authority_paths(stage: str, *, plan: bool) -> tuple[Path, Path, Path | None]:
    if (stage, plan) == ("runtime", False):
        return RUNTIME_INPUT_AUTHORITY, RUNTIME_INPUT_PIN_PATH, None
    if (stage, plan) == ("runtime", True):
        return (
            RUNTIME_PLAN_AUTHORITY,
            RUNTIME_REVIEWED_PLAN_PIN_PATH,
            RUNTIME_ADMIN_LAUNCHER,
        )
    if (stage, plan) == ("bundle", False):
        return BUNDLE_INPUT_AUTHORITY, BUNDLE_INPUT_PIN_PATH, BUNDLE_INPUT_LAUNCHER
    if (stage, plan) == ("bundle", True):
        return (
            BUNDLE_PLAN_AUTHORITY,
            BUNDLE_REVIEWED_PLAN_PIN_PATH,
            BUNDLE_ADMIN_LAUNCHER,
        )
    _fail("STAGE_AUTHORITY_INVALID", stage)


def _read_held_bytes(held: HeldSourceFile, expected: FilePin, label: str) -> bytes:
    if (
        held.canonical_path != held.requested_path
        or held.metadata.st_nlink != 1
        or held.metadata.st_uid != REVIEW_UID
        or held.metadata.st_gid != REVIEW_GID
        or held.metadata.st_size != expected.size_bytes
        or expected.size_bytes > MAX_JSON_BYTES
    ):
        _fail("STAGE_EXTERNAL_REVIEW_PIN_MISMATCH", label)
    digest, size = _hash_fd(held.descriptor)
    if (digest, size) != (expected.sha256, expected.size_bytes):
        _fail("STAGE_EXTERNAL_REVIEW_PIN_MISMATCH", label)
    raw = bytearray()
    while block := os.read(held.descriptor, CHUNK_BYTES):
        raw.extend(block)
        if len(raw) > MAX_JSON_BYTES:
            _fail("STAGE_REVIEW_CANDIDATE_INVALID", f"{label} exceeds limit")
    os.lseek(held.descriptor, 0, os.SEEK_SET)
    if _identity(os.fstat(held.descriptor)) != _identity(held.metadata):
        _fail("STAGE_REVIEW_CANDIDATE_DRIFT", label)
    return bytes(raw)


def _held_candidate(
    stack: contextlib.ExitStack,
    path: Path,
    mode: int,
    expected: FilePin,
    label: str,
) -> tuple[HeldSourceFile, bytes]:
    held = stack.enter_context(hold_source_file_components(path))
    if stat.S_IMODE(held.metadata.st_mode) != mode:
        _fail("STAGE_REVIEW_CANDIDATE_INVALID", label)
    return held, _read_held_bytes(held, expected, label)


def _copy_held_stage_file(
    held: HeldSourceFile,
    destination: Path,
    expected: FilePin,
    mode: int,
) -> FilePin:
    descriptor = os.open(
        destination,
        os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
        0o600,
    )
    try:
        copied = _copy_file_fd(held.descriptor, descriptor)
        if (
            (copied.sha256, copied.size_bytes) != (expected.sha256, expected.size_bytes)
            or _hash_fd(held.descriptor) != (expected.sha256, expected.size_bytes)
            or _identity(os.fstat(held.descriptor)) != _identity(held.metadata)
        ):
            _fail("STAGE_REVIEW_CANDIDATE_DRIFT", str(held.requested_path))
        os.fchown(descriptor, ROOT_UID, ROOT_GID)
        os.fchmod(descriptor, mode)
        os.fsync(descriptor)
        return FilePin(copied.sha256, copied.size_bytes, mode == 0o555)
    finally:
        os.close(descriptor)


def _flat_stage_identity(stage: str, *, plan: bool) -> tuple[Any, ...]:
    root, pin, other = _stage_authority_paths(stage, plan=plan)
    _require_stage_authority(stage, plan=plan)
    result: list[Any] = []
    for path in (root, pin, other):
        if path is None:
            continue
        metadata = os.lstat(path)
        record: list[Any] = [
            str(path),
            metadata.st_dev,
            metadata.st_ino,
            metadata.st_mode,
            metadata.st_uid,
            metadata.st_gid,
            metadata.st_nlink,
            metadata.st_size,
        ]
        if stat.S_ISREG(metadata.st_mode):
            _raw, file_pin = _root_file(
                path,
                f"{stage} {'plan' if plan else 'input'} identity",
                0o555 if path == other else 0o444,
            )
            record.extend((file_pin.sha256, file_pin.size_bytes))
        result.append(tuple(record))
    return tuple(result)


def _core_authority_identity() -> tuple[Any, ...]:
    _require_core_installed()
    names = (
        "vista_r8_ue57_authority_admin.py",
        "provision_vista_r8_ue57_engine.sh",
        "transfer-r8-ue57-stage-installer",
        "engine-source-pin.json",
        ".engine.lock",
        ".runtime.lock",
        ".bundle.lock",
        ".executor.lock",
    )
    result: list[Any] = []
    for path in (INSTALLED_ROOT, *(INSTALLED_ROOT / name for name in names)):
        metadata = os.lstat(path)
        record: list[Any] = [
            str(path),
            metadata.st_dev,
            metadata.st_ino,
            metadata.st_mode,
            metadata.st_uid,
            metadata.st_gid,
            metadata.st_nlink,
            metadata.st_size,
        ]
        if stat.S_ISREG(metadata.st_mode):
            mode = (
                0o500
                if path.name
                in {
                    "vista_r8_ue57_authority_admin.py",
                    "provision_vista_r8_ue57_engine.sh",
                }
                else 0o555
                if path.name == "transfer-r8-ue57-stage-installer"
                else 0o600
                if path.name.startswith(".")
                else 0o444
            )
            _raw, pin = _root_file(path, f"core authority identity {path.name}", mode)
            record.extend((pin.sha256, pin.size_bytes))
        result.append(tuple(record))
    return tuple(result)


def _previous_stage_identities(stage: str, *, plan: bool) -> dict[str, tuple[Any, ...]]:
    ordered = {
        ("runtime", False): (),
        ("runtime", True): (("runtime", False),),
        ("bundle", False): (("runtime", False), ("runtime", True)),
        ("bundle", True): (
            ("runtime", False),
            ("runtime", True),
            ("bundle", False),
        ),
    }[(stage, plan)]
    identities = {
        f"{previous_stage}-{'plan' if previous_plan else 'input'}": (
            _flat_stage_identity(previous_stage, plan=previous_plan)
        )
        for previous_stage, previous_plan in ordered
    }
    identities["core"] = _core_authority_identity()
    identities["stage-installer"] = _stage_installer_authority_identity(
        _stage_key(stage, plan=plan)
    )
    return identities


def _require_stage_parent(final: Path) -> None:
    metadata = os.lstat(final.parent)
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != ROOT_UID
        or metadata.st_gid != ROOT_GID
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        _fail("STAGE_AUTHORITY_PARENT_INVALID", str(final.parent))


def _publish_held_flat_stage(
    final: Path,
    files: Sequence[tuple[HeldSourceFile, str, FilePin, int]],
) -> dict[str, FilePin]:
    _require_stage_parent(final)
    if os.path.lexists(final):
        _fail("FINAL_NOT_FRESH", str(final))
    staging = Path(tempfile.mkdtemp(prefix=f".{final.name}.staging-", dir=final.parent))
    os.chown(staging, ROOT_UID, ROOT_GID, follow_symlinks=False)
    copied: dict[str, FilePin] = {}
    try:
        for held, name, expected, mode in files:
            copied[name] = _copy_held_stage_file(held, staging / name, expected, mode)
        _seal_private_tree(staging, owner=(ROOT_UID, ROOT_GID))
        publish_staging(staging, final)
        return copied
    finally:
        if os.path.lexists(staging):
            _remove_private_staging(staging)


def _parse_candidate_document(raw: bytes, schema: str, label: str) -> dict[str, Any]:
    document = strict_json(raw, label)
    if document.get("schema") != schema or document.get(
        "content_digest"
    ) != content_digest(document):
        _fail("STAGE_REVIEW_CANDIDATE_INVALID", label)
    return document


def _stage_key(stage: str, *, plan: bool) -> str:
    key = f"{stage}-{'plan' if plan else 'input'}"
    if key not in STAGE_KEYS:
        _fail("STAGE_AUTHORITY_INVALID", key)
    return key


def _stage_transfer_contract(stage: str, *, plan: bool) -> dict[str, Any]:
    key = _stage_key(stage, plan=plan)
    candidate_root = (
        _stage_candidate_configuration(stage)[2]
        if plan
        else _stage_candidate_configuration(stage)[0]
    )
    final_root = _stage_authority_paths(stage, plan=plan)[0]
    return {
        "install_operation": f"install-{key}-authority",
        "reconcile_operation": f"reconcile-{key}-authority",
        "install_acknowledgement": STAGE_ACKNOWLEDGEMENTS[(stage, plan, "install")],
        "reconcile_acknowledgement": STAGE_ACKNOWLEDGEMENTS[(stage, plan, "reconcile")],
        "candidate_root": str(candidate_root),
        "final_root": str(final_root),
    }


def stage_installer_transfer_receipt(
    stage: str,
    *,
    plan: bool,
    installer_pin: FilePin,
    helper_pin: FilePin,
    interpreter_pin: FilePin,
    stage_transfer_launcher_pin: FilePin,
) -> dict[str, Any]:
    key = _stage_key(stage, plan=plan)
    review_path = STAGE_INSTALLER_REVIEW_ROOTS[key] / STAGE_INSTALLER_NAME
    authority = STAGE_INSTALLER_AUTHORITIES[key]
    installed_path = authority / STAGE_INSTALLER_NAME
    return seal_document(
        {
            "schema": STAGE_INSTALLER_RECEIPT_SCHEMA,
            "status": "root_published_immutable_stage_installer_authority",
            "accepted": True,
            "stage": key,
            "authority_root": str(authority),
            "installer": {
                "path": str(installed_path),
                "pin": installer_pin.public(),
            },
            "reviewed_candidate": {
                "path": str(review_path),
                "pin": installer_pin.public(),
                "uid": REVIEW_UID,
                "gid": REVIEW_GID,
                "mode": 0o555,
            },
            "publisher": {
                "helper_pin": helper_pin.public(),
                "interpreter_pin": interpreter_pin.public(),
                "stage_transfer_launcher_pin": stage_transfer_launcher_pin.public(),
            },
            "stage_contract": _stage_transfer_contract(stage, plan=plan),
            "claims": {
                "external_review_pin_required": True,
                "no_replace": True,
                "held_fd_copy": True,
                "reconcile_only": True,
                "no_deletion": True,
            },
        }
    )


def _core_publisher_pins() -> tuple[FilePin, FilePin, FilePin]:
    helper_pin = _root_file(INSTALLED_HELPER, "installed helper", 0o500)[1]
    source_pin_document, _source_pin_file = load_sealed_document(
        ENGINE_SOURCE_PIN_PATH,
        ENGINE_SOURCE_PIN_SCHEMA,
        "engine source pin",
    )
    interpreter_pin = _require_live_python(
        source_pin_document.get("publisher_python_pin")
    )
    transfer_pin = _root_file(
        INSTALLED_STAGE_TRANSFER_LAUNCHER,
        "installed stage transfer launcher",
        0o555,
    )[1]
    return (
        helper_pin,
        interpreter_pin,
        FilePin(transfer_pin.sha256, transfer_pin.size_bytes, True),
    )


def _ensure_stage_installer_parent() -> None:
    parent = STAGE_INSTALLER_AUTHORITY_PARENT
    root_parent = parent.parent
    root_metadata = os.lstat(root_parent)
    if (
        not stat.S_ISDIR(root_metadata.st_mode)
        or root_metadata.st_uid != ROOT_UID
        or root_metadata.st_gid != ROOT_GID
        or stat.S_IMODE(root_metadata.st_mode) != 0o700
    ):
        _fail("STAGE_INSTALLER_PARENT_INVALID", str(root_parent))
    try:
        os.mkdir(parent, 0o700)
        os.chown(parent, ROOT_UID, ROOT_GID, follow_symlinks=False)
        _fsync_fixed_directory(parent, "stage installer parent")
        _fsync_fixed_directory(root_parent, "stage installer root parent")
    except FileExistsError:
        pass
    metadata = os.lstat(parent)
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != ROOT_UID
        or metadata.st_gid != ROOT_GID
        or stat.S_IMODE(metadata.st_mode) != 0o700
        or any(name not in STAGE_KEYS for name in os.listdir(parent))
    ):
        _fail("STAGE_INSTALLER_PARENT_INVALID", str(parent))


def _require_stage_installer_sequence(key: str, *, include_current: bool) -> None:
    """Require the exact append-only installer-authority prefix for *key*.

    The parent deliberately remains 0700 so four independently reviewed
    authorities can be appended.  That writable parent must not make the
    children reorderable: before a fresh transfer it contains exactly the
    earlier stage prefix, and before reconcile it contains that prefix plus
    the current stage.  Future or out-of-order children therefore fail closed.
    """

    if key not in STAGE_KEYS:
        _fail("STAGE_AUTHORITY_INVALID", key)
    index = STAGE_KEYS.index(key)
    expected = set(STAGE_KEYS[: index + int(include_current)])
    try:
        metadata = os.lstat(STAGE_INSTALLER_AUTHORITY_PARENT)
        descriptor = os.open(STAGE_INSTALLER_AUTHORITY_PARENT, _directory_flags())
    except OSError as exc:
        raise AuthorityError(
            "STAGE_INSTALLER_PARENT_INVALID",
            str(STAGE_INSTALLER_AUTHORITY_PARENT),
        ) from exc
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISDIR(opened.st_mode)
            or _identity(opened) != _identity(metadata)
            or opened.st_uid != ROOT_UID
            or opened.st_gid != ROOT_GID
            or stat.S_IMODE(opened.st_mode) != 0o700
            or set(os.listdir(descriptor)) != expected
        ):
            _fail(
                "STAGE_INSTALLER_SEQUENCE_INVALID",
                f"{key}:{sorted(expected)}",
            )
    finally:
        os.close(descriptor)


def _validate_stage_installer_authority(
    stage: str,
    *,
    plan: bool,
    expected_external_pin: FilePin | None = None,
    fsync: bool = False,
) -> tuple[dict[str, Any], FilePin]:
    _require_core_installed()
    key = _stage_key(stage, plan=plan)
    authority = STAGE_INSTALLER_AUTHORITIES[key]
    installer_path = authority / STAGE_INSTALLER_NAME
    receipt_path = authority / "receipt.json"
    _require_exact_directory(
        authority,
        {STAGE_INSTALLER_NAME, "receipt.json"},
        f"{key} installer authority",
    )
    installer_raw, installer_pin = _root_file(
        installer_path, f"{key} installed stage installer", 0o555
    )
    if not installer_raw.startswith(b"\x7fELF"):
        _fail("STAGE_INSTALLER_AUTHORITY_INVALID", "installer is not ELF")
    if expected_external_pin is not None and (
        installer_pin.sha256,
        installer_pin.size_bytes,
    ) != (expected_external_pin.sha256, expected_external_pin.size_bytes):
        _fail("STAGE_EXTERNAL_REVIEW_PIN_MISMATCH", str(installer_path))
    receipt, receipt_pin = load_sealed_document(
        receipt_path,
        STAGE_INSTALLER_RECEIPT_SCHEMA,
        f"{key} installer receipt",
    )
    helper_pin, interpreter_pin, transfer_pin = _core_publisher_pins()
    expected_receipt = stage_installer_transfer_receipt(
        stage,
        plan=plan,
        installer_pin=FilePin(installer_pin.sha256, installer_pin.size_bytes, True),
        helper_pin=helper_pin,
        interpreter_pin=interpreter_pin,
        stage_transfer_launcher_pin=transfer_pin,
    )
    if receipt != expected_receipt:
        _fail("STAGE_INSTALLER_AUTHORITY_INVALID", "receipt binding")
    if fsync:
        _fsync_immutable_tree(authority, f"{key} installer authority")
    return receipt, receipt_pin


def _stage_installer_authority_identity(key: str) -> tuple[Any, ...]:
    if key not in STAGE_KEYS:
        _fail("STAGE_AUTHORITY_INVALID", key)
    stage, phase = key.split("-", 1)
    _validate_stage_installer_authority(stage, plan=phase == "plan")
    authority = STAGE_INSTALLER_AUTHORITIES[key]
    result: list[Any] = []
    for path, mode in (
        (authority, 0o555),
        (authority / STAGE_INSTALLER_NAME, 0o555),
        (authority / "receipt.json", 0o444),
    ):
        metadata = os.lstat(path)
        record: list[Any] = [
            str(path),
            metadata.st_dev,
            metadata.st_ino,
            metadata.st_mode,
            metadata.st_uid,
            metadata.st_gid,
            metadata.st_nlink,
            metadata.st_size,
        ]
        if stat.S_ISREG(metadata.st_mode):
            _raw, pin = _root_file(path, f"{key} installer identity", mode)
            record.extend((pin.sha256, pin.size_bytes))
        result.append(tuple(record))
    return tuple(result)


def _previous_stage_installer_identities(key: str) -> dict[str, tuple[Any, ...]]:
    if key not in STAGE_KEYS:
        _fail("STAGE_AUTHORITY_INVALID", key)
    return {
        previous: _stage_installer_authority_identity(previous)
        for previous in STAGE_KEYS[: STAGE_KEYS.index(key)]
    }


def _require_stage_transfer_invocation(descriptor: int) -> FilePin:
    _require_core_installed()
    if type(descriptor) is not int or descriptor < 3:
        _fail("STAGE_TRANSFER_INVOCATION_INVALID", "descriptor")
    try:
        installed_fd = os.open(INSTALLED_STAGE_TRANSFER_LAUNCHER, _file_flags())
        passed_fd = os.open(f"/proc/self/fd/{descriptor}", os.O_RDONLY | os.O_CLOEXEC)
    except OSError as exc:
        raise AuthorityError(
            "STAGE_TRANSFER_INVOCATION_INVALID", "launcher FD"
        ) from exc
    try:
        installed_info = os.fstat(installed_fd)
        passed_info = os.fstat(passed_fd)
        installed_pin = _hash_fd(installed_fd)
        passed_pin = _hash_fd(passed_fd)
        if (
            installed_info.st_uid != ROOT_UID
            or installed_info.st_gid != ROOT_GID
            or installed_info.st_nlink != 1
            or stat.S_IMODE(installed_info.st_mode) != 0o555
            or (installed_info.st_dev, installed_info.st_ino, installed_info.st_size)
            != (passed_info.st_dev, passed_info.st_ino, passed_info.st_size)
            or installed_pin != passed_pin
        ):
            _fail("STAGE_TRANSFER_INVOCATION_INVALID", "launcher identity")
        result = FilePin(installed_pin[0], installed_pin[1], True)
    finally:
        os.close(passed_fd)
        os.close(installed_fd)
    _live_fsync_core_authority()
    return result


def install_stage_installer_authority(
    stage: str,
    *,
    plan: bool,
    reviewed_installer_pin: Mapping[str, Any],
    stage_transfer_launcher_fd: int,
) -> dict[str, Any]:
    live_transfer_pin = _require_stage_transfer_invocation(stage_transfer_launcher_fd)
    expected = _parse_pin(reviewed_installer_pin, f"{stage} reviewed stage installer")
    key = _stage_key(stage, plan=plan)
    review_root = STAGE_INSTALLER_REVIEW_ROOTS[key]
    review_path = review_root / STAGE_INSTALLER_NAME
    _require_user_review_candidate(
        review_root,
        {review_path: 0o555},
        f"{key} stage installer candidate",
    )
    _ensure_stage_installer_parent()
    final = STAGE_INSTALLER_AUTHORITIES[key]
    with operation_lock(stage):
        if os.path.lexists(final):
            _fail("FINAL_NOT_FRESH", str(final))
        _require_stage_installer_sequence(key, include_current=False)
        core_before = _core_authority_identity()
        previous_before = _previous_stage_installer_identities(key)
        with contextlib.ExitStack() as stack:
            held, raw = _held_candidate(
                stack,
                review_path,
                0o555,
                expected,
                f"{key} reviewed stage installer",
            )
            if not raw.startswith(b"\x7fELF"):
                _fail("STAGE_REVIEW_CANDIDATE_INVALID", "installer is not ELF")
            helper_pin, interpreter_pin, transfer_pin = _core_publisher_pins()
            if transfer_pin != live_transfer_pin:
                _fail("STAGE_TRANSFER_INVOCATION_INVALID", "publisher pin")
            receipt = stage_installer_transfer_receipt(
                stage,
                plan=plan,
                installer_pin=FilePin(expected.sha256, expected.size_bytes, True),
                helper_pin=helper_pin,
                interpreter_pin=interpreter_pin,
                stage_transfer_launcher_pin=transfer_pin,
            )
            _require_stage_parent(final)
            staging = Path(
                tempfile.mkdtemp(prefix=f".{final.name}.staging-", dir=final.parent)
            )
            os.chown(staging, ROOT_UID, ROOT_GID, follow_symlinks=False)
            try:
                installed_pin = _copy_held_stage_file(
                    held,
                    staging / STAGE_INSTALLER_NAME,
                    FilePin(expected.sha256, expected.size_bytes, True),
                    0o555,
                )
                receipt_pin = _write_new(
                    staging / "receipt.json",
                    canonical_json(receipt),
                    0o444,
                    (ROOT_UID, ROOT_GID),
                )
                _seal_private_tree(staging, owner=(ROOT_UID, ROOT_GID))
                publish_staging(staging, final)
            finally:
                if os.path.lexists(staging):
                    _remove_private_staging(staging)
        _validate_stage_installer_authority(
            stage, plan=plan, expected_external_pin=expected
        )
        if _core_authority_identity() != core_before:
            _fail("EARLIER_STAGE_AUTHORITY_DRIFT", "core")
        if _previous_stage_installer_identities(key) != previous_before:
            _fail("EARLIER_STAGE_AUTHORITY_DRIFT", "stage installers")
        return {
            "status": f"installed_fresh_{key}_stage_installer_authority",
            "accepted": True,
            "authority_root": str(final),
            "installer_pin": installed_pin.public(),
            "receipt_pin": receipt_pin.public(),
            "receipt_content_digest": receipt["content_digest"],
            "publication_performed": True,
        }


def reconcile_stage_installer_authority(
    stage: str,
    *,
    plan: bool,
    reviewed_installer_pin: Mapping[str, Any],
    stage_transfer_launcher_fd: int,
) -> dict[str, Any]:
    live_transfer_pin = _require_stage_transfer_invocation(stage_transfer_launcher_fd)
    expected = _parse_pin(reviewed_installer_pin, f"{stage} reviewed stage installer")
    key = _stage_key(stage, plan=plan)
    with operation_lock(stage):
        _require_stage_installer_sequence(key, include_current=True)
        core_before = _core_authority_identity()
        previous_before = _previous_stage_installer_identities(key)
        receipt, receipt_pin = _validate_stage_installer_authority(
            stage,
            plan=plan,
            expected_external_pin=expected,
            fsync=True,
        )
        if receipt["publisher"]["stage_transfer_launcher_pin"] != (
            live_transfer_pin.public()
        ):
            _fail("STAGE_TRANSFER_INVOCATION_INVALID", "receipt publisher")
        if _core_authority_identity() != core_before:
            _fail("EARLIER_STAGE_AUTHORITY_DRIFT", "core")
        if _previous_stage_installer_identities(key) != previous_before:
            _fail("EARLIER_STAGE_AUTHORITY_DRIFT", "stage installers")
        return {
            "status": f"reconciled_existing_{key}_stage_installer_authority",
            "accepted": True,
            "authority_root": str(STAGE_INSTALLER_AUTHORITIES[key]),
            "installer_pin": expected.public(),
            "receipt_pin": receipt_pin.public(),
            "receipt_content_digest": receipt["content_digest"],
            "publication_performed": False,
            "deletion_performed": False,
        }


def _require_stage_installer_invocation(
    stage: str, *, plan: bool, descriptor: int
) -> dict[str, Any]:
    if type(descriptor) is not int or descriptor < 3:
        _fail("STAGE_INSTALLER_INVOCATION_INVALID", "descriptor")
    receipt, _receipt_pin = _validate_stage_installer_authority(stage, plan=plan)
    key = _stage_key(stage, plan=plan)
    installer_path = STAGE_INSTALLER_AUTHORITIES[key] / STAGE_INSTALLER_NAME
    try:
        installed_fd = os.open(installer_path, _file_flags())
        passed_fd = os.open(f"/proc/self/fd/{descriptor}", os.O_RDONLY | os.O_CLOEXEC)
    except OSError as exc:
        raise AuthorityError("STAGE_INSTALLER_INVOCATION_INVALID", key) from exc
    try:
        installed_info = os.fstat(installed_fd)
        passed_info = os.fstat(passed_fd)
        installed_pin = _hash_fd(installed_fd)
        passed_pin = _hash_fd(passed_fd)
        expected = _parse_pin(receipt["installer"]["pin"], "stage installer")
        if (
            (installed_info.st_dev, installed_info.st_ino, installed_info.st_size)
            != (passed_info.st_dev, passed_info.st_ino, passed_info.st_size)
            or installed_pin != passed_pin
            or installed_pin != (expected.sha256, expected.size_bytes)
        ):
            _fail("STAGE_INSTALLER_INVOCATION_INVALID", key)
    finally:
        os.close(passed_fd)
        os.close(installed_fd)
    return receipt


def install_stage_input_authority(
    stage: str,
    reviewed_input_pin: Mapping[str, Any],
    *,
    stage_installer_fd: int,
) -> dict[str, Any]:
    _require_stage_installer_invocation(
        stage, plan=False, descriptor=stage_installer_fd
    )
    expected_input = _parse_pin(reviewed_input_pin, f"{stage} reviewed input")
    input_root, input_path, _plan_root, _plan_pin, _admin = (
        *_stage_candidate_configuration(stage),
    )
    candidate_files = (
        {input_path: 0o444}
        if stage == "runtime"
        else {
            input_path: 0o444,
            BUNDLE_LAUNCHER_REVIEW_CANDIDATE: 0o555,
        }
    )
    _require_user_review_candidate(
        input_root, candidate_files, f"{stage} input candidate"
    )
    final, _final_pin, final_other = _stage_authority_paths(stage, plan=False)
    with operation_lock(stage):
        earlier = _previous_stage_identities(stage, plan=False)
        with contextlib.ExitStack() as stack:
            held_input, input_raw = _held_candidate(
                stack, input_path, 0o444, expected_input, f"{stage} input pin"
            )
            if stage == "runtime":
                document = _parse_candidate_document(
                    input_raw, RUNTIME_INPUT_PIN_SCHEMA, "runtime input pin"
                )
                validate_runtime_input_pin(document)
                _validate_runtime_input_against_live(document)
                python_value = document["tool_pins"]["python"]["pin"]
                files = [(held_input, "input-pin.json", expected_input, 0o444)]
            else:
                document = _parse_candidate_document(
                    input_raw, BUNDLE_INPUT_PIN_SCHEMA, "bundle input pin"
                )
                validate_bundle_input_pin(document)
                launcher_expected = _parse_pin(
                    document["launcher_binary_pin"], "reviewed bundle launcher"
                )
                held_launcher, launcher_raw = _held_candidate(
                    stack,
                    BUNDLE_LAUNCHER_REVIEW_CANDIDATE,
                    0o555,
                    launcher_expected,
                    "reviewed bundle launcher",
                )
                if not launcher_raw.startswith(b"\x7fELF"):
                    _fail("STAGE_REVIEW_CANDIDATE_INVALID", "bundle launcher")
                _validate_bundle_input_against_live(
                    document,
                    reviewed_launcher_pin=FilePin(
                        launcher_expected.sha256,
                        launcher_expected.size_bytes,
                        True,
                    ),
                )
                python_value = document["runtime_executables"]["python"]["pin"]
                files = [
                    (held_input, "input-pin.json", expected_input, 0o444),
                    (
                        held_launcher,
                        LAUNCHER_NAME,
                        FilePin(
                            launcher_expected.sha256,
                            launcher_expected.size_bytes,
                            True,
                        ),
                        0o555,
                    ),
                ]
            live_python = _require_live_python(python_value)
            copied = _publish_held_flat_stage(final, files)
        _require_stage_authority(stage, plan=False)
        if _previous_stage_identities(stage, plan=False) != earlier:
            _fail("EARLIER_STAGE_AUTHORITY_DRIFT", stage)
        return {
            "status": f"installed_fresh_{stage}_input_authority",
            "accepted": True,
            "authority_root": str(final),
            "reviewed_input_pin": expected_input.public(),
            "installed_files": {
                name: pin.public() for name, pin in sorted(copied.items())
            },
            "publisher_python_pin": live_python.public(),
            "publication_performed": True,
        }


def _installed_stage_input_and_plan(
    stage: str,
) -> tuple[dict[str, Any], FilePin, dict[str, Any]]:
    _require_stage_authority(stage, plan=False)
    if stage == "runtime":
        document, input_pin = _load_runtime_input_pin()
        _validate_runtime_input_against_live(document)
        plan = _runtime_plan_from_input(document, input_pin)
    else:
        document, input_pin = _load_bundle_input_pin()
        _validate_bundle_input_against_live(document)
        plan = _bundle_plan_from_input(document, input_pin)
    return document, input_pin, plan


def install_stage_plan_authority(
    stage: str,
    reviewed_plan_file_pin: Mapping[str, Any],
    reviewed_admin_launcher_pin: Mapping[str, Any],
    *,
    stage_installer_fd: int,
) -> dict[str, Any]:
    _require_stage_installer_invocation(stage, plan=True, descriptor=stage_installer_fd)
    expected_plan_file = _parse_pin(
        reviewed_plan_file_pin, f"{stage} reviewed plan file"
    )
    expected_admin = _parse_pin(
        reviewed_admin_launcher_pin, f"{stage} reviewed admin launcher"
    )
    (
        _input_root,
        _input_path,
        candidate_root,
        candidate_plan,
        candidate_admin,
    ) = _stage_candidate_configuration(stage)
    _require_user_review_candidate(
        candidate_root,
        {candidate_plan: 0o444, candidate_admin: 0o555},
        f"{stage} plan candidate",
    )
    final, _final_plan, _final_admin = _stage_authority_paths(stage, plan=True)
    with operation_lock(stage):
        earlier = _previous_stage_identities(stage, plan=True)
        input_document, _input_file_pin, plan = _installed_stage_input_and_plan(stage)
        live_python = _require_live_python(
            input_document["tool_pins"]["python"]["pin"]
            if stage == "runtime"
            else input_document["runtime_executables"]["python"]["pin"]
        )
        with contextlib.ExitStack() as stack:
            held_plan, plan_raw = _held_candidate(
                stack,
                candidate_plan,
                0o444,
                expected_plan_file,
                f"{stage} reviewed plan pin",
            )
            held_admin, admin_raw = _held_candidate(
                stack,
                candidate_admin,
                0o555,
                expected_admin,
                f"{stage} reviewed admin launcher",
            )
            if not admin_raw.startswith(b"\x7fELF"):
                _fail("STAGE_REVIEW_CANDIDATE_INVALID", "admin launcher")
            reviewed_document = _parse_candidate_document(
                plan_raw, REVIEWED_PLAN_PIN_SCHEMA, f"{stage} reviewed plan pin"
            )
            validate_reviewed_plan(
                plan,
                reviewed_document,
                FilePin(expected_admin.sha256, expected_admin.size_bytes, True),
            )
            helper_pin = _root_file(INSTALLED_HELPER, "installed helper", 0o500)[1]
            if (
                helper_pin.sha256.encode("ascii") not in admin_raw
                or live_python.sha256.encode("ascii") not in admin_raw
            ):
                _fail("STAGE_REVIEW_CANDIDATE_INVALID", "embedded publisher pins")
            copied = _publish_held_flat_stage(
                final,
                [
                    (held_plan, "reviewed-plan-pin.json", expected_plan_file, 0o444),
                    (
                        held_admin,
                        ADMIN_LAUNCHER_NAME,
                        FilePin(expected_admin.sha256, expected_admin.size_bytes, True),
                        0o555,
                    ),
                ],
            )
        _require_stage_authority(stage, plan=True)
        if _previous_stage_identities(stage, plan=True) != earlier:
            _fail("EARLIER_STAGE_AUTHORITY_DRIFT", stage)
        return {
            "status": f"installed_fresh_{stage}_plan_authority",
            "accepted": True,
            "authority_root": str(final),
            "reviewed_plan_file_pin": expected_plan_file.public(),
            "reviewed_admin_launcher_pin": expected_admin.public(),
            "installed_files": {
                name: pin.public() for name, pin in sorted(copied.items())
            },
            "publisher_python_pin": live_python.public(),
            "publication_performed": True,
        }


def reconcile_stage_authority(
    stage: str,
    *,
    plan: bool,
    reviewed_primary_pin: Mapping[str, Any],
    reviewed_admin_launcher_pin: Mapping[str, Any] | None = None,
    stage_installer_fd: int,
) -> dict[str, Any]:
    _require_stage_installer_invocation(stage, plan=plan, descriptor=stage_installer_fd)
    expected_primary = _parse_pin(
        reviewed_primary_pin, f"{stage} reviewed {'plan' if plan else 'input'}"
    )
    with operation_lock(stage):
        earlier = _previous_stage_identities(stage, plan=plan)
        _require_stage_authority(stage, plan=plan)
        _document, _input_pin, derived_plan = _installed_stage_input_and_plan(stage)
        final, primary_path, other_path = _stage_authority_paths(stage, plan=plan)
        primary_raw, primary_pin = _root_file(
            primary_path,
            f"{stage} installed {'plan' if plan else 'input'} pin",
            0o444,
        )
        if (primary_pin.sha256, primary_pin.size_bytes) != (
            expected_primary.sha256,
            expected_primary.size_bytes,
        ):
            _fail("STAGE_EXTERNAL_REVIEW_PIN_MISMATCH", str(primary_path))
        installed: dict[str, FilePin] = {primary_path.name: primary_pin}
        if plan:
            if reviewed_admin_launcher_pin is None or other_path is None:
                _fail("STAGE_EXTERNAL_REVIEW_PIN_MISMATCH", "admin launcher pin")
            expected_admin = _parse_pin(
                reviewed_admin_launcher_pin, f"{stage} reviewed admin launcher"
            )
            _admin_raw, admin_pin = _root_file(
                other_path, f"{stage} installed admin launcher", 0o555
            )
            if (admin_pin.sha256, admin_pin.size_bytes) != (
                expected_admin.sha256,
                expected_admin.size_bytes,
            ):
                _fail("STAGE_EXTERNAL_REVIEW_PIN_MISMATCH", str(other_path))
            reviewed_document = _parse_candidate_document(
                primary_raw,
                REVIEWED_PLAN_PIN_SCHEMA,
                f"{stage} installed reviewed plan",
            )
            validate_reviewed_plan(
                derived_plan,
                reviewed_document,
                FilePin(admin_pin.sha256, admin_pin.size_bytes, True),
            )
            installed[other_path.name] = admin_pin
        elif stage == "bundle":
            if other_path is None:
                _fail("STAGE_AUTHORITY_INVALID", stage)
            input_document = _parse_candidate_document(
                primary_raw, BUNDLE_INPUT_PIN_SCHEMA, "bundle installed input"
            )
            expected_launcher = _parse_pin(
                input_document["launcher_binary_pin"], "bundle launcher"
            )
            _launcher_raw, launcher_pin = _root_file(
                other_path, "installed bundle launcher", 0o555
            )
            if (launcher_pin.sha256, launcher_pin.size_bytes) != (
                expected_launcher.sha256,
                expected_launcher.size_bytes,
            ):
                _fail("STAGE_EXTERNAL_REVIEW_PIN_MISMATCH", str(other_path))
            installed[other_path.name] = launcher_pin
        _fsync_immutable_tree(final, f"{stage} {'plan' if plan else 'input'} stage")
        if _previous_stage_identities(stage, plan=plan) != earlier:
            _fail("EARLIER_STAGE_AUTHORITY_DRIFT", stage)
        return {
            "status": f"reconciled_existing_{stage}_{'plan' if plan else 'input'}_authority",
            "accepted": True,
            "authority_root": str(final),
            "installed_files": {
                name: pin.public() for name, pin in sorted(installed.items())
            },
            "publication_performed": False,
            "deletion_performed": False,
        }


def _sealed_pin(path: Path, schema: str, label: str) -> tuple[dict[str, Any], FilePin]:
    document, pin = load_sealed_document(path, schema, label)
    return document, pin


def _projection_from_buildplugin_manifest(
    document: Mapping[str, Any],
) -> dict[str, Any]:
    source = document.get("source")
    if type(source) is not dict:
        _fail("BUILDPLUGIN_MANIFEST_INVALID", "source")
    projection = {
        "tree_digest": source.get("projection_sha256"),
        "file_count": source.get("file_count"),
        "directory_count": source.get("directory_count"),
        "total_bytes": source.get("total_bytes"),
    }
    if (
        type(projection["tree_digest"]) is not str
        or SHA256_RE.fullmatch(projection["tree_digest"]) is None
        or any(
            type(projection[key]) is not int
            for key in ("file_count", "directory_count", "total_bytes")
        )
    ):
        _fail("BUILDPLUGIN_MANIFEST_INVALID", "projection")
    return projection


def build_root_policy_core(
    *,
    bundle_pins: Mapping[str, FilePin],
    bundle_manifest_pin: FilePin,
    bundle_manifest_content_digest: str,
    input_pin: Mapping[str, Any],
    engine_document: Mapping[str, Any],
    engine_pin: FilePin,
    engine_receipt_document: Mapping[str, Any],
    engine_receipt_pin: FilePin,
    runtime_document: Mapping[str, Any],
    runtime_manifest_pin: FilePin,
    runtime_receipt_document: Mapping[str, Any],
    runtime_receipt_pin: FilePin,
    buildplugin_document: Mapping[str, Any],
    buildplugin_manifest_pin: FilePin,
    buildplugin_receipt_document: Mapping[str, Any],
    buildplugin_receipt_pin: FilePin,
) -> dict[str, Any]:
    critical_by_path = {item["path"]: item for item in engine_document["entries"]}
    critical = []
    for relative in CRITICAL_ENGINE_FILES:
        item = critical_by_path.get(relative)
        if type(item) is not dict or item.get("type") != "file":
            _fail("ENGINE_CRITICAL_FILE_MISSING", relative)
        critical.append(
            {
                "relative_path": relative,
                "sha256": item["sha256"],
                "size_bytes": item["size_bytes"],
                "executable": bool(item["mode"] & 0o111),
            }
        )
    python_pin = _parse_pin(input_pin["python_pin"], "Python")
    bwrap_pin = _parse_pin(input_pin["bwrap_pin"], "bubblewrap")
    runtime_projection = runtime_document["projection"]
    buildplugin_projection = _projection_from_buildplugin_manifest(buildplugin_document)
    return seal_document(
        {
            "schema": ROOT_POLICY_CORE_SCHEMA,
            "approved_attempt_name": APPROVED_ATTEMPT_NAME,
            "invocation_ledger_path": str(INVOCATION_LEDGER_PATH),
            "operation_lock_path": str(OPERATION_LOCKS["executor"]),
            "bundle_manifest_pin": bundle_manifest_pin.public(),
            "bundle_manifest_content_digest": bundle_manifest_content_digest,
            "executor_pin": bundle_pins[
                "makehuman_cc0_animation_runtime_executor.py"
            ].public(),
            "wrapper_pin": bundle_pins[
                "makehuman_cc0_animation_runtime_sandbox_wrapper.py"
            ].public(),
            "commandlet_pin": bundle_pins[
                "makehuman_cc0_animation_runtime_commandlet.py"
            ].public(),
            "launcher_pin": bundle_pins[LAUNCHER_NAME].public(),
            "live_python_pin": python_pin.public(),
            "host_runtime": {
                "manifest_pin": runtime_manifest_pin.public(),
                "manifest_content_digest": runtime_document["content_digest"],
                "receipt_pin": runtime_receipt_pin.public(),
                "receipt_content_digest": runtime_receipt_document["content_digest"],
                "payload": runtime_projection,
            },
            "engine": {
                "manifest_pin": engine_pin.public(),
                "manifest_content_digest": engine_document["content_digest"],
                "receipt_pin": engine_receipt_pin.public(),
                "receipt_content_digest": engine_receipt_document["content_digest"],
                "tree_digest": engine_document["tree_root_digest"],
                "critical_files": critical,
            },
            "r3": input_pin["r3"],
            "r8": input_pin["r8"],
            "buildplugin": {
                "manifest_pin": buildplugin_manifest_pin.public(),
                # The published BuildPlugin v1 manifest predates sealed JSON;
                # its reviewed canonical-file digest is therefore the only
                # non-cyclic content digest available.
                "manifest_content_digest": buildplugin_manifest_pin.sha256,
                "receipt_pin": buildplugin_receipt_pin.public(),
                "receipt_content_digest": buildplugin_receipt_document[
                    "content_digest"
                ],
                "payload": buildplugin_projection,
            },
            "bwrap_pin": bwrap_pin.public(),
        }
    )


def _validate_publication_provenance(value: Any) -> dict[str, Any]:
    if type(value) is not dict or set(value) != {
        "bundle_input_pin",
        "reviewed_plan_pin",
        "audit_plan",
        "publisher",
        "launcher_build",
    }:
        _fail("ROOT_POLICY_PROVENANCE_INVALID", "fields")
    for name in ("bundle_input_pin", "reviewed_plan_pin"):
        item = value[name]
        if (
            type(item) is not dict
            or set(item) != {"pin", "content_digest"}
            or type(item.get("content_digest")) is not str
            or SHA256_RE.fullmatch(item["content_digest"]) is None
        ):
            _fail("ROOT_POLICY_PROVENANCE_INVALID", name)
        _parse_pin(item["pin"], name)
    audit = value["audit_plan"]
    if (
        type(audit) is not dict
        or set(audit) != {"sha256", "size_bytes", "content_digest"}
        or type(audit.get("sha256")) is not str
        or SHA256_RE.fullmatch(audit["sha256"]) is None
        or type(audit.get("size_bytes")) is not int
        or audit["size_bytes"] < 0
        or type(audit.get("content_digest")) is not str
        or SHA256_RE.fullmatch(audit["content_digest"]) is None
    ):
        _fail("ROOT_POLICY_PROVENANCE_INVALID", "audit plan")
    publisher = value["publisher"]
    if type(publisher) is not dict or set(publisher) != {
        "helper_pin",
        "bundle_admin_launcher_pin",
        "interpreter_pin",
    }:
        _fail("ROOT_POLICY_PROVENANCE_INVALID", "publisher")
    for name, pin in publisher.items():
        _parse_pin(pin, f"publisher {name}")
    build = value["launcher_build"]
    if type(build) is not dict or set(build) != {
        "source_pin",
        "compiler_driver_pin",
        "toolchain_artifact_ledger_digest",
        "output_pin",
    }:
        _fail("ROOT_POLICY_PROVENANCE_INVALID", "launcher build")
    for name, pin in build.items():
        if name == "toolchain_artifact_ledger_digest":
            if type(pin) is not str or SHA256_RE.fullmatch(pin) is None:
                _fail("ROOT_POLICY_PROVENANCE_INVALID", name)
            continue
        _parse_pin(pin, f"launcher {name}")
    return dict(value)


def finalize_root_policy(
    core: Mapping[str, Any], publication_provenance: Mapping[str, Any]
) -> dict[str, Any]:
    if core.get("schema") != ROOT_POLICY_CORE_SCHEMA or core.get(
        "content_digest"
    ) != content_digest(core):
        _fail("ROOT_POLICY_CORE_INVALID", "core")
    body = dict(core)
    body.pop("content_digest")
    body["schema"] = ROOT_POLICY_SCHEMA
    body["publication_provenance"] = _validate_publication_provenance(
        publication_provenance
    )
    return seal_document(body)


def build_root_policy(
    *,
    publication_provenance: Mapping[str, Any],
    **kwargs: Any,
) -> dict[str, Any]:
    return finalize_root_policy(
        build_root_policy_core(**kwargs), publication_provenance
    )


def _require_regular_metadata(path: Path, mode: int, label: str) -> None:
    try:
        metadata = os.lstat(path)
    except OSError as exc:
        raise AuthorityError("INSTALLED_ROOT_HELPER_REQUIRED", label) from exc
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or metadata.st_uid != ROOT_UID
        or metadata.st_gid != ROOT_GID
        or stat.S_IMODE(metadata.st_mode) != mode
    ):
        _fail("INSTALLED_ROOT_HELPER_REQUIRED", label)


def _require_core_installed() -> None:
    if os.geteuid() != ROOT_UID:
        _fail("INSTALLED_ROOT_HELPER_REQUIRED", str(INSTALLED_HELPER))
    _require_exact_directory(
        INSTALLED_ROOT,
        {
            "vista_r8_ue57_authority_admin.py",
            "provision_vista_r8_ue57_engine.sh",
            "transfer-r8-ue57-stage-installer",
            "engine-source-pin.json",
            ".engine.lock",
            ".runtime.lock",
            ".bundle.lock",
            ".executor.lock",
        },
        "core bootstrap authority",
    )
    _require_regular_metadata(INSTALLED_HELPER, 0o500, "installed helper")
    current = Path(__file__)
    current_text = str(current)
    if (
        current != INSTALLED_HELPER
        and re.fullmatch(r"/proc/self/fd/[0-9]+", current_text) is None
    ):
        _fail("INSTALLED_ROOT_HELPER_REQUIRED", current_text)
    try:
        current_resolved = current.resolve(strict=True)
    except OSError as exc:
        raise AuthorityError("INSTALLED_ROOT_HELPER_REQUIRED", current_text) from exc
    if current_resolved != INSTALLED_HELPER:
        _fail("INSTALLED_ROOT_HELPER_REQUIRED", current_text)
    installed_fd = os.open(INSTALLED_HELPER, _file_flags())
    try:
        current_fd = os.open(current, os.O_RDONLY | os.O_CLOEXEC)
    except OSError as exc:
        os.close(installed_fd)
        raise AuthorityError("INSTALLED_ROOT_HELPER_REQUIRED", current_text) from exc
    try:
        installed_info = os.fstat(installed_fd)
        current_info = os.fstat(current_fd)
        installed_hash = _hash_fd(installed_fd)
        current_hash = _hash_fd(current_fd)
        if (
            not stat.S_ISREG(current_info.st_mode)
            or (current_info.st_dev, current_info.st_ino, current_info.st_size)
            != (
                installed_info.st_dev,
                installed_info.st_ino,
                installed_info.st_size,
            )
            or current_hash != installed_hash
        ):
            _fail("INSTALLED_ROOT_HELPER_REQUIRED", current_text)
    finally:
        os.close(current_fd)
        os.close(installed_fd)
    _require_regular_metadata(
        INSTALLED_ENGINE_WRAPPER, 0o500, "installed engine wrapper"
    )
    _require_regular_metadata(
        INSTALLED_STAGE_TRANSFER_LAUNCHER,
        0o555,
        "installed stage transfer launcher",
    )
    _require_regular_metadata(
        ENGINE_SOURCE_PIN_PATH, 0o444, "installed engine source pin"
    )
    for name, path in OPERATION_LOCKS.items():
        _require_regular_metadata(path, 0o600, f"{name} operation lock")
        if os.lstat(path).st_size != 0:
            _fail("OPERATION_LOCK_INVALID", str(path))


def _live_fsync_core_authority() -> None:
    """Make the exact eight-file core root durable before downstream writes."""

    _require_core_installed()
    file_modes = {
        INSTALLED_HELPER.name: 0o500,
        INSTALLED_ENGINE_WRAPPER.name: 0o500,
        INSTALLED_STAGE_TRANSFER_LAUNCHER.name: 0o555,
        ENGINE_SOURCE_PIN_PATH.name: 0o444,
        **{path.name: 0o600 for path in OPERATION_LOCKS.values()},
    }
    descriptors: list[int] = []
    try:
        parent_path = INSTALLED_ROOT.parent
        parent_before = os.lstat(parent_path)
        parent_fd = os.open(parent_path, _directory_flags())
        descriptors.append(parent_fd)
        parent_info = os.fstat(parent_fd)
        if (
            _identity(parent_before) != _identity(parent_info)
            or not stat.S_ISDIR(parent_info.st_mode)
            or parent_info.st_uid != ROOT_UID
            or parent_info.st_gid != ROOT_GID
            or stat.S_IMODE(parent_info.st_mode) != 0o700
        ):
            _fail("CORE_AUTHORITY_LIVE_FSYNC_REQUIRED", "held /root differs")
        root_fd = os.open(INSTALLED_ROOT.name, _directory_flags(), dir_fd=parent_fd)
        descriptors.append(root_fd)
        root_info = os.fstat(root_fd)
        if (
            not stat.S_ISDIR(root_info.st_mode)
            or root_info.st_nlink != 2
            or root_info.st_uid != ROOT_UID
            or root_info.st_gid != ROOT_GID
            or stat.S_IMODE(root_info.st_mode) != 0o555
            or set(os.listdir(root_fd)) != set(file_modes)
        ):
            _fail("CORE_AUTHORITY_LIVE_FSYNC_REQUIRED", "core root differs")
        records: dict[str, tuple[int, tuple[int, ...], tuple[str, int]]] = {}
        for name, mode in file_modes.items():
            descriptor = os.open(name, _file_flags(), dir_fd=root_fd)
            descriptors.append(descriptor)
            info = os.fstat(descriptor)
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_nlink != 1
                or info.st_uid != ROOT_UID
                or info.st_gid != ROOT_GID
                or stat.S_IMODE(info.st_mode) != mode
                or (mode == 0o600 and info.st_size != 0)
            ):
                _fail("CORE_AUTHORITY_LIVE_FSYNC_REQUIRED", name)
            records[name] = (descriptor, _identity(info), _hash_fd(descriptor))
        for descriptor, _identity_before, _pin in records.values():
            os.fsync(descriptor)
        os.fsync(root_fd)
        os.fsync(parent_fd)
        if (
            _identity(os.fstat(root_fd)) != _identity(root_info)
            or set(os.listdir(root_fd)) != set(file_modes)
            or _identity(os.lstat(INSTALLED_ROOT)) != _identity(root_info)
            or _identity(os.fstat(parent_fd)) != _identity(parent_info)
            or _identity(os.lstat(parent_path)) != _identity(parent_info)
        ):
            _fail(
                "CORE_AUTHORITY_LIVE_FSYNC_REQUIRED",
                "core namespace drifted during live fsync",
            )
        for name, (descriptor, identity_before, pin) in records.items():
            if (
                _identity(os.fstat(descriptor)) != identity_before
                or _hash_fd(descriptor) != pin
                or _identity(os.stat(name, dir_fd=root_fd, follow_symlinks=False))
                != identity_before
            ):
                _fail(
                    "CORE_AUTHORITY_LIVE_FSYNC_REQUIRED",
                    f"{name} drifted during live fsync",
                )
    except AuthorityError:
        raise
    except OSError as exc:
        raise AuthorityError(
            "CORE_AUTHORITY_LIVE_FSYNC_REQUIRED",
            f"core authority live fsync failed: {exc}",
        ) from exc
    finally:
        for descriptor in reversed(descriptors):
            try:
                os.close(descriptor)
            except OSError:
                pass


def _require_installed(wrapper: Path) -> None:
    _require_core_installed()
    if wrapper != INSTALLED_ENGINE_WRAPPER:
        _fail("INSTALLED_ROOT_HELPER_REQUIRED", str(wrapper))


def _require_stage_authority(stage: str, *, plan: bool) -> Path | None:
    if (stage, plan) == ("runtime", False):
        root, pin, wrapper = RUNTIME_INPUT_AUTHORITY, RUNTIME_INPUT_PIN_PATH, None
        names = {pin.name}
    elif (stage, plan) == ("runtime", True):
        root, pin, wrapper = (
            RUNTIME_PLAN_AUTHORITY,
            RUNTIME_REVIEWED_PLAN_PIN_PATH,
            RUNTIME_ADMIN_LAUNCHER,
        )
        names = {pin.name, wrapper.name}
    elif (stage, plan) == ("bundle", False):
        root, pin, wrapper = BUNDLE_INPUT_AUTHORITY, BUNDLE_INPUT_PIN_PATH, None
        names = {pin.name, BUNDLE_INPUT_LAUNCHER.name}
    elif (stage, plan) == ("bundle", True):
        root, pin, wrapper = (
            BUNDLE_PLAN_AUTHORITY,
            BUNDLE_REVIEWED_PLAN_PIN_PATH,
            BUNDLE_ADMIN_LAUNCHER,
        )
        names = {pin.name, wrapper.name}
    else:
        _fail("STAGE_AUTHORITY_INVALID", stage)
    _require_exact_directory(
        root,
        names,
        f"{stage} {'plan' if plan else 'input'} authority",
    )
    _require_regular_metadata(pin, 0o444, f"{stage} stage pin")
    if wrapper is not None:
        _require_regular_metadata(wrapper, 0o555, f"{stage} admin launcher")
    if (stage, plan) == ("bundle", False):
        _require_regular_metadata(
            BUNDLE_INPUT_LAUNCHER, 0o555, "reviewed launcher input"
        )
    return wrapper


def _require_stage_installed(stage: str) -> None:
    _require_core_installed()
    _require_stage_authority(stage, plan=False)
    wrapper = _require_stage_authority(stage, plan=True)
    expected = {
        "runtime": RUNTIME_ADMIN_LAUNCHER,
        "bundle": BUNDLE_ADMIN_LAUNCHER,
    }.get(stage)
    if wrapper != expected:
        _fail("STAGE_AUTHORITY_INVALID", stage)


def _require_live_python(expected_value: Any) -> FilePin:
    expected = _parse_pin(expected_value, "live publisher Python")
    try:
        path_fd = os.open(PYTHON_PATH, _file_flags())
        live_fd = os.open("/proc/self/exe", os.O_RDONLY | os.O_CLOEXEC)
    except OSError as exc:
        raise AuthorityError("LIVE_PYTHON_INVALID", "/proc/self/exe") from exc
    try:
        path_info = os.fstat(path_fd)
        live_info = os.fstat(live_fd)
        path_sha, path_bytes = _hash_fd(path_fd)
        live_sha, live_bytes = _hash_fd(live_fd)
        if (
            not stat.S_ISREG(path_info.st_mode)
            or not stat.S_ISREG(live_info.st_mode)
            or (path_info.st_dev, path_info.st_ino, path_info.st_size)
            != (live_info.st_dev, live_info.st_ino, live_info.st_size)
            or (path_sha, path_bytes) != (expected.sha256, expected.size_bytes)
            or (live_sha, live_bytes) != (expected.sha256, expected.size_bytes)
        ):
            _fail("LIVE_PYTHON_INVALID", "/proc/self/exe differs from reviewed pin")
        return FilePin(live_sha, live_bytes, True)
    finally:
        os.close(live_fd)
        os.close(path_fd)


@contextlib.contextmanager
def operation_lock(name: str) -> Iterable[None]:
    path = OPERATION_LOCKS.get(name)
    if path is None:
        _fail("OPERATION_LOCK_INVALID", name)
    try:
        metadata = os.lstat(path)
        descriptor = os.open(path, os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC)
    except OSError as exc:
        raise AuthorityError("OPERATION_LOCK_INVALID", str(path)) from exc
    try:
        opened = os.fstat(descriptor)
        if (
            not stat.S_ISREG(opened.st_mode)
            or opened.st_nlink != 1
            or opened.st_uid != ROOT_UID
            or opened.st_gid != ROOT_GID
            or stat.S_IMODE(opened.st_mode) != 0o600
            or _identity(opened) != _identity(metadata)
        ):
            _fail("OPERATION_LOCK_INVALID", str(path))
        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise AuthorityError("OPERATION_ALREADY_ACTIVE", name) from exc
        yield
    finally:
        os.close(descriptor)


def audit_engine() -> dict[str, Any]:
    pin_document, _pin = load_sealed_document(
        ENGINE_SOURCE_PIN_PATH, ENGINE_SOURCE_PIN_SCHEMA, "engine source pin"
    )
    snapshot = snapshot_tree(ENGINE_SOURCE)
    validate_engine_source_pin(snapshot, pin_document)
    return {
        "status": "engine_source_audited_zero_write",
        "accepted": False,
        "source_manifest_sha256": hashlib.sha256(
            canonical_json(source_manifest(snapshot))
        ).hexdigest(),
        "projection": snapshot.projection(),
        "final_exists": os.path.lexists(ENGINE_AUTHORITY),
    }


def audit_engine_source() -> dict[str, Any]:
    """Checkout-safe, zero-write source scan for independent pin review."""

    snapshot = snapshot_tree(ENGINE_SOURCE)
    return {
        "status": "engine_source_review_candidate_zero_write",
        "accepted": False,
        "source_manifest": source_manifest(snapshot),
        "derived_engine_source_pin": derive_engine_source_pin(snapshot),
        "publication_performed": False,
    }


def _root_file(path: Path, label: str, mode: int = 0o444) -> tuple[bytes, FilePin]:
    metadata = os.lstat(path)
    if (
        not stat.S_ISREG(metadata.st_mode)
        or metadata.st_nlink != 1
        or metadata.st_uid != ROOT_UID
        or metadata.st_gid != ROOT_GID
        or stat.S_IMODE(metadata.st_mode) != mode
    ):
        _fail("ENGINE_RECONCILIATION_INVALID", label)
    return _read_regular(path, label, exact_mode=mode)


def _critical_engine_records(
    entries: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    by_path = {item.get("path"): item for item in entries}
    result: list[dict[str, Any]] = []
    for relative in CRITICAL_ENGINE_FILES:
        item = by_path.get(relative)
        if type(item) is not dict or item.get("type") != "file":
            _fail("ENGINE_CRITICAL_FILE_MISSING", relative)
        result.append(
            {
                "relative_path": relative,
                "sha256": item["sha256"],
                "size_bytes": item["size_bytes"],
                "executable": bool(item["mode"] & 0o111),
            }
        )
    return result


def audit_existing_engine_authority(*, fsync: bool = False) -> dict[str, Any]:
    """Validate an existing final authority; never create, replace, or delete."""

    _require_parent(AUTHORITY_PARENT)
    root_info = os.lstat(ENGINE_AUTHORITY)
    engine_info = os.lstat(ENGINE_ROOT)
    if (
        not stat.S_ISDIR(root_info.st_mode)
        or root_info.st_uid != ROOT_UID
        or root_info.st_gid != ROOT_GID
        or stat.S_IMODE(root_info.st_mode) != 0o555
        or not stat.S_ISDIR(engine_info.st_mode)
        or engine_info.st_uid != ROOT_UID
        or engine_info.st_gid != ROOT_GID
        or stat.S_IMODE(engine_info.st_mode) != 0o555
    ):
        _fail("ENGINE_RECONCILIATION_INVALID", "authority root metadata")
    root_fd = os.open(ENGINE_AUTHORITY, _directory_flags())
    try:
        if set(os.listdir(root_fd)) != {
            "engine",
            "engine-full-tree-manifest.json",
            "receipt.json",
        }:
            _fail("ENGINE_RECONCILIATION_INVALID", "authority root inventory")
    finally:
        os.close(root_fd)

    manifest_raw, manifest_pin = _root_file(ENGINE_MANIFEST, "engine manifest")
    manifest = strict_json(manifest_raw, "engine manifest")
    if (
        set(manifest)
        != {"schema", "engine_root", "entries", "tree_root_digest", "content_digest"}
        or manifest.get("schema") != ENGINE_MANIFEST_SCHEMA
        or manifest.get("engine_root") != str(ENGINE_ROOT)
        or manifest.get("content_digest") != content_digest(manifest)
        or type(manifest.get("entries")) is not list
    ):
        _fail("ENGINE_RECONCILIATION_INVALID", "engine manifest contract")
    snapshot = snapshot_tree(ENGINE_ROOT)
    if (
        manifest["entries"] != list(snapshot.entries)
        or manifest["tree_root_digest"] != snapshot.tree_digest
        or any(
            item["uid"] != ROOT_UID
            or item["gid"] != ROOT_GID
            or (item["type"] == "directory" and item["mode"] != 0o555)
            or (item["type"] == "file" and item["mode"] not in (0o444, 0o555))
            for item in snapshot.entries
        )
    ):
        _fail("ENGINE_RECONCILIATION_INVALID", "engine inventory differs")

    source_pin_raw, source_pin_file = _root_file(
        ENGINE_SOURCE_PIN_PATH, "reviewed engine source pin"
    )
    source_pin = strict_json(source_pin_raw, "reviewed engine source pin")
    source_pin_keys = {
        "schema",
        "source_root",
        "source_manifest_sha256",
        "source_manifest_size_bytes",
        "source_manifest_content_digest",
        "tree_root_digest",
        "projection",
        "publisher_python_pin",
        "content_digest",
    }
    if (
        set(source_pin) != source_pin_keys
        or source_pin.get("schema") != ENGINE_SOURCE_PIN_SCHEMA
        or source_pin.get("source_root") != str(ENGINE_SOURCE)
        or source_pin.get("content_digest") != content_digest(source_pin)
    ):
        _fail("ENGINE_RECONCILIATION_INVALID", "reviewed source pin")
    live_python = _require_live_python(source_pin.get("publisher_python_pin"))
    receipt_path = ENGINE_AUTHORITY / "receipt.json"
    receipt_raw, receipt_pin = _root_file(receipt_path, "engine receipt")
    receipt = strict_json(receipt_raw, "engine receipt")
    receipt_keys = {
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
    reviewed_source = {
        "sha256": source_pin["source_manifest_sha256"],
        "size_bytes": source_pin["source_manifest_size_bytes"],
        "content_digest": source_pin["source_manifest_content_digest"],
        "tree_digest": source_pin["tree_root_digest"],
        "projection": source_pin["projection"],
    }
    expected_source_projection = {
        "projection": source_pin["projection"],
        "manifest_sha256": source_pin["source_manifest_sha256"],
        "manifest_content_digest": source_pin["source_manifest_content_digest"],
    }
    helper_pin = _root_file(INSTALLED_HELPER, "installed helper", 0o500)[1]
    if (
        set(receipt) != receipt_keys
        or receipt.get("schema") != ENGINE_RECEIPT_SCHEMA
        or receipt.get("status") != "root_published_immutable_ue57_engine_authority"
        or receipt.get("accepted") is not True
        or receipt.get("authority_root") != str(ENGINE_AUTHORITY)
        or receipt.get("content_digest") != content_digest(receipt)
        or receipt.get("manifest")
        != {
            "pin": manifest_pin.public(),
            "content_digest": manifest["content_digest"],
        }
        or receipt.get("reviewed_source_manifest") != reviewed_source
        or receipt.get("source_projections")
        != {
            "pre": expected_source_projection,
            "post": expected_source_projection,
        }
        or receipt.get("final_projection") != snapshot.projection()
        or receipt.get("critical_engine_files")
        != _critical_engine_records(snapshot.entries)
        or receipt.get("publisher")
        != {
            "helper_pin": helper_pin.public(),
            "interpreter_pin": live_python.public(),
        }
        or receipt.get("publication_policy")
        != {
            "copy_from_nofollow_descriptors": True,
            "xattrs_acls_caps_inherited": False,
            "source_pre_post_full_projection_equal": True,
            "renameat2_noreplace": True,
            "final_and_parent_fsynced": True,
        }
        or receipt.get("claims")
        != {
            "host_runtime_included": False,
            "buildplugin_included": False,
            "runtime_interaction_verified": False,
            "human_motion_quality_accepted": False,
            "gta_level_quality": False,
        }
    ):
        _fail("ENGINE_RECONCILIATION_INVALID", "engine receipt contract")

    if fsync:

        def sync_directory(descriptor: int) -> None:
            for name in sorted(os.listdir(descriptor)):
                before = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
                if stat.S_ISDIR(before.st_mode):
                    child = os.open(name, _directory_flags(), dir_fd=descriptor)
                    try:
                        if _identity(os.fstat(child)) != _identity(before):
                            _fail("ENGINE_RECONCILIATION_INVALID", name)
                        sync_directory(child)
                    finally:
                        os.close(child)
                elif stat.S_ISREG(before.st_mode):
                    child = os.open(name, _file_flags(), dir_fd=descriptor)
                    try:
                        if _identity(os.fstat(child)) != _identity(before):
                            _fail("ENGINE_RECONCILIATION_INVALID", name)
                        os.fsync(child)
                    finally:
                        os.close(child)
                else:
                    _fail("ENGINE_RECONCILIATION_INVALID", name)
            os.fsync(descriptor)

        final_fd = os.open(ENGINE_AUTHORITY, _directory_flags())
        parent_fd = os.open(AUTHORITY_PARENT, _directory_flags())
        try:
            sync_directory(final_fd)
            os.fsync(parent_fd)
        finally:
            os.close(parent_fd)
            os.close(final_fd)
    return {
        "status": (
            "existing_engine_authority_durability_reconciled"
            if fsync
            else "existing_engine_authority_audited"
        ),
        "accepted": True,
        "publication_performed": False,
        "deletion_performed": False,
        "manifest_pin": manifest_pin.public(),
        "receipt_pin": receipt_pin.public(),
        "source_pin": source_pin_file.public(),
        "projection": snapshot.projection(),
    }


def publish_engine() -> dict[str, Any]:
    _require_installed(INSTALLED_ENGINE_WRAPPER)
    _live_fsync_core_authority()
    _require_parent(AUTHORITY_PARENT)
    pin_document, _pin = load_sealed_document(
        ENGINE_SOURCE_PIN_PATH, ENGINE_SOURCE_PIN_SCHEMA, "engine source pin"
    )
    with operation_lock("engine"):
        live_python = _require_live_python(pin_document["publisher_python_pin"])
        return publish_engine_from_snapshot(
            snapshot_tree(ENGINE_SOURCE),
            pin_document,
            publisher_pins={
                "helper": _read_regular(INSTALLED_HELPER, "installed helper")[1],
                "interpreter": live_python,
            },
        )


def reconcile_engine() -> dict[str, Any]:
    _require_installed(INSTALLED_ENGINE_WRAPPER)
    _live_fsync_core_authority()
    with operation_lock("engine"):
        return audit_existing_engine_authority(fsync=True)


def _runtime_receipt_inputs(document: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "engine_manifest_pin": document["engine"]["manifest_pin"],
        "buildplugin_manifest_pin": document["buildplugin"]["manifest_pin"],
        "buildplugin_receipt_pin": document["buildplugin"]["receipt_pin"],
        "python_pin": document["tool_pins"]["python"]["pin"],
        "readelf_pin": document["tool_pins"]["readelf"]["pin"],
    }


def _runtime_review_context(
    input_document: Mapping[str, Any],
    input_file_pin: FilePin,
    plan: Mapping[str, Any],
    reviewed_plan_document: Mapping[str, Any],
    reviewed_plan_file_pin: FilePin,
    *,
    live_python: FilePin,
) -> tuple[dict[str, Any], dict[str, Any]]:
    plan_raw = canonical_json(plan)
    reviewed_publication = {
        "input_pin": {
            "pin": input_file_pin.public(),
            "content_digest": input_document["content_digest"],
        },
        "reviewed_plan_pin": {
            "pin": reviewed_plan_file_pin.public(),
            "content_digest": reviewed_plan_document["content_digest"],
        },
        "audit_plan": {
            "sha256": hashlib.sha256(plan_raw).hexdigest(),
            "size_bytes": len(plan_raw),
            "content_digest": plan["content_digest"],
        },
    }
    publisher = {
        "helper_pin": _root_file(INSTALLED_HELPER, "installed helper", 0o500)[
            1
        ].public(),
        "runtime_admin_launcher_pin": _root_file(
            RUNTIME_ADMIN_LAUNCHER, "runtime admin launcher", 0o555
        )[1].public(),
        "interpreter_pin": live_python.public(),
    }
    return reviewed_publication, publisher


def audit_host_runtime_plan() -> dict[str, Any]:
    review_candidate = os.geteuid() != ROOT_UID
    if review_candidate:
        _require_unprivileged_review_helper()
        if any(
            str(path).startswith("/root/") for path in (RUNTIME_INPUT_REVIEW_CANDIDATE,)
        ):
            _fail("UNPRIVILEGED_REVIEW_PATH_INVALID", "runtime input candidate")
        _require_exact_directory(
            RUNTIME_INPUT_REVIEW_CANDIDATE.parent,
            {"input-pin.json"},
            "runtime input review candidate",
            owner=(os.getuid(), os.getgid()),
        )
        metadata = os.lstat(RUNTIME_INPUT_REVIEW_CANDIDATE)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_nlink != 1
            or metadata.st_uid != os.getuid()
            or metadata.st_gid != os.getgid()
            or stat.S_IMODE(metadata.st_mode) != 0o444
        ):
            _fail("UNPRIVILEGED_REVIEW_PATH_INVALID", "runtime input pin")
    else:
        _require_core_installed()
        _require_stage_authority("runtime", plan=False)
    lock = contextlib.nullcontext() if review_candidate else operation_lock("runtime")
    with lock:
        document, pin = _load_runtime_input_pin(review_candidate=review_candidate)
        _validate_runtime_input_against_live(document)
        plan = _runtime_plan_from_input(document, pin)
    return {
        "status": "host_runtime_audit_plan_candidate_zero_write",
        "accepted": False,
        "audit_plan": plan,
        "reviewed_plan_pin_pending_admin_launcher": True,
        "publication_performed": False,
    }


def _validate_runtime_manifest(
    snapshot: TreeSnapshot, document: Mapping[str, Any]
) -> None:
    if (
        set(document)
        != {
            "schema",
            "authority_root",
            "payload_root",
            "entries",
            "projection",
            "content_digest",
        }
        or document.get("schema") != HOST_RUNTIME_MANIFEST_SCHEMA
        or document.get("authority_root") != str(HOST_RUNTIME_AUTHORITY)
        or document.get("payload_root") != str(HOST_RUNTIME_PAYLOAD)
        or document.get("content_digest") != content_digest(document)
        or document.get("entries") != list(snapshot.entries)
        or document.get("projection") != snapshot.projection()
    ):
        _fail("HOST_RUNTIME_AUTHORITY_INVALID", "manifest")


def audit_existing_host_runtime_authority(*, fsync: bool = False) -> dict[str, Any]:
    _require_parent(AUTHORITY_PARENT)
    _require_exact_directory(
        HOST_RUNTIME_AUTHORITY,
        {"payload", "manifest.json", "receipt.json"},
        "host runtime authority",
    )
    payload_info = os.lstat(HOST_RUNTIME_PAYLOAD)
    if (
        not stat.S_ISDIR(payload_info.st_mode)
        or payload_info.st_uid != ROOT_UID
        or payload_info.st_gid != ROOT_GID
        or stat.S_IMODE(payload_info.st_mode) != 0o555
    ):
        _fail("HOST_RUNTIME_AUTHORITY_INVALID", "payload root")
    snapshot = snapshot_tree(HOST_RUNTIME_PAYLOAD)
    _require_immutable_tree(snapshot, "host runtime payload")
    input_document, input_file_pin = _load_runtime_input_pin()
    plan = _runtime_plan_from_input(input_document, input_file_pin)
    reviewed_plan_document, reviewed_plan_file_pin = _load_reviewed_plan_pin(
        RUNTIME_REVIEWED_PLAN_PIN_PATH,
        plan,
        "runtime",
        RUNTIME_ADMIN_LAUNCHER,
    )
    if snapshot.projection() != input_document["final_projection"]:
        _fail("HOST_RUNTIME_AUTHORITY_INVALID", "payload projection")
    manifest, manifest_pin = load_sealed_document(
        HOST_RUNTIME_AUTHORITY / "manifest.json",
        HOST_RUNTIME_MANIFEST_SCHEMA,
        "host runtime manifest",
    )
    _validate_runtime_manifest(snapshot, manifest)
    live_python = _require_live_python(input_document["tool_pins"]["python"]["pin"])
    reviewed_publication, publisher = _runtime_review_context(
        input_document,
        input_file_pin,
        plan,
        reviewed_plan_document,
        reviewed_plan_file_pin,
        live_python=live_python,
    )
    expected_receipt = runtime_receipt(
        snapshot,
        manifest_pin,
        manifest["content_digest"],
        _runtime_receipt_inputs(input_document),
        reviewed_publication=reviewed_publication,
        publisher=publisher,
    )
    receipt, receipt_pin = load_sealed_document(
        HOST_RUNTIME_AUTHORITY / "receipt.json",
        HOST_RUNTIME_RECEIPT_SCHEMA,
        "host runtime receipt",
    )
    if receipt != expected_receipt:
        _fail("HOST_RUNTIME_AUTHORITY_INVALID", "receipt")
    if fsync:
        _fsync_immutable_tree(HOST_RUNTIME_AUTHORITY, "host runtime")
    return {
        "status": (
            "existing_host_runtime_authority_durability_reconciled"
            if fsync
            else "existing_host_runtime_authority_audited"
        ),
        "accepted": True,
        "publication_performed": False,
        "deletion_performed": False,
        "manifest_pin": manifest_pin.public(),
        "receipt_pin": receipt_pin.public(),
        "projection": snapshot.projection(),
    }


def publish_host_runtime() -> dict[str, Any]:
    _require_stage_installed("runtime")
    _require_parent(AUTHORITY_PARENT)
    with operation_lock("runtime"):
        input_document, input_file_pin = _load_runtime_input_pin()
        live_python = _require_live_python(input_document["tool_pins"]["python"]["pin"])
        _validate_runtime_input_against_live(input_document)
        plan = _runtime_plan_from_input(input_document, input_file_pin)
        reviewed_plan_document, reviewed_plan_file_pin = _load_reviewed_plan_pin(
            RUNTIME_REVIEWED_PLAN_PIN_PATH,
            plan,
            "runtime",
            RUNTIME_ADMIN_LAUNCHER,
        )
        if os.path.lexists(HOST_RUNTIME_AUTHORITY):
            _fail("FINAL_NOT_FRESH", str(HOST_RUNTIME_AUTHORITY))
        staging = Path(
            tempfile.mkdtemp(
                prefix=f".{HOST_RUNTIME_AUTHORITY.name}.staging-",
                dir=AUTHORITY_PARENT,
            )
        )
        os.chown(staging, ROOT_UID, ROOT_GID, follow_symlinks=False)
        try:
            payload = staging / "payload"
            payload.mkdir(mode=0o700)
            os.chown(payload, ROOT_UID, ROOT_GID, follow_symlinks=False)
            _copy_reviewed_runtime_inventory(
                input_document["inventory"],
                payload,
                owner=(ROOT_UID, ROOT_GID),
            )
            for relative, text in input_document["generated_etc"].items():
                destination = payload / relative
                destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                _write_new(
                    destination,
                    text.encode("utf-8", "strict"),
                    0o444,
                    (ROOT_UID, ROOT_GID),
                )
            _seal_private_tree(payload, owner=(ROOT_UID, ROOT_GID))
            snapshot = snapshot_tree(payload)
            _require_immutable_tree(snapshot, "staged host runtime")
            if snapshot.projection() != input_document["final_projection"]:
                _fail("HOST_RUNTIME_COPY_DIFFERS", str(payload))
            manifest_document = runtime_manifest(snapshot)
            manifest_pin = _write_new(
                staging / "manifest.json",
                canonical_json(manifest_document),
                0o444,
                (ROOT_UID, ROOT_GID),
            )
            reviewed_publication, publisher = _runtime_review_context(
                input_document,
                input_file_pin,
                plan,
                reviewed_plan_document,
                reviewed_plan_file_pin,
                live_python=live_python,
            )
            receipt_document = runtime_receipt(
                snapshot,
                manifest_pin,
                manifest_document["content_digest"],
                _runtime_receipt_inputs(input_document),
                reviewed_publication=reviewed_publication,
                publisher=publisher,
            )
            receipt_pin = _write_new(
                staging / "receipt.json",
                canonical_json(receipt_document),
                0o444,
                (ROOT_UID, ROOT_GID),
            )
            _seal_private_tree(staging, owner=(ROOT_UID, ROOT_GID))
            publish_staging(staging, HOST_RUNTIME_AUTHORITY)
            return {
                "status": "published_immutable_host_runtime_authority",
                "accepted": True,
                "authority_root": str(HOST_RUNTIME_AUTHORITY),
                "manifest_pin": manifest_pin.public(),
                "manifest_content_digest": manifest_document["content_digest"],
                "receipt_pin": receipt_pin.public(),
                "receipt_content_digest": receipt_document["content_digest"],
                "projection": snapshot.projection(),
            }
        finally:
            if os.path.lexists(staging):
                _remove_private_staging(staging)


def reconcile_host_runtime() -> dict[str, Any]:
    _require_stage_installed("runtime")
    with operation_lock("runtime"):
        return audit_existing_host_runtime_authority(fsync=True)


def _bundle_publication_provenance(
    input_document: Mapping[str, Any],
    input_file_pin: FilePin,
    plan: Mapping[str, Any],
    reviewed_plan_document: Mapping[str, Any],
    reviewed_plan_file_pin: FilePin,
    *,
    live_python: FilePin,
) -> dict[str, Any]:
    plan_raw = canonical_json(plan)
    return {
        "bundle_input_pin": {
            "pin": input_file_pin.public(),
            "content_digest": input_document["content_digest"],
        },
        "reviewed_plan_pin": {
            "pin": reviewed_plan_file_pin.public(),
            "content_digest": reviewed_plan_document["content_digest"],
        },
        "audit_plan": {
            "sha256": hashlib.sha256(plan_raw).hexdigest(),
            "size_bytes": len(plan_raw),
            "content_digest": plan["content_digest"],
        },
        "publisher": {
            "helper_pin": _root_file(INSTALLED_HELPER, "installed helper", 0o500)[
                1
            ].public(),
            "bundle_admin_launcher_pin": _root_file(
                BUNDLE_ADMIN_LAUNCHER, "bundle admin launcher", 0o555
            )[1].public(),
            "interpreter_pin": live_python.public(),
        },
        "launcher_build": {
            "source_pin": input_document["launcher_build"]["source_pin"],
            "compiler_driver_pin": input_document["launcher_build"][
                "compiler_driver_pin"
            ],
            "toolchain_artifact_ledger_digest": hashlib.sha256(
                canonical_json(
                    input_document["launcher_build"]["toolchain_artifact_ledger"]
                )
            ).hexdigest(),
            "output_pin": input_document["launcher_binary_pin"],
        },
    }


def audit_executor_bundle_plan() -> dict[str, Any]:
    review_candidate = os.geteuid() != ROOT_UID
    if review_candidate:
        _require_unprivileged_review_helper()
        if any(
            str(path).startswith("/root/")
            for path in (
                BUNDLE_INPUT_REVIEW_CANDIDATE,
                BUNDLE_LAUNCHER_REVIEW_CANDIDATE,
            )
        ):
            _fail("UNPRIVILEGED_REVIEW_PATH_INVALID", "bundle input candidate")
        _require_exact_directory(
            BUNDLE_INPUT_REVIEW_CANDIDATE.parent,
            {"input-pin.json", LAUNCHER_NAME},
            "bundle input review candidate",
            owner=(os.getuid(), os.getgid()),
        )
        for path, mode in (
            (BUNDLE_INPUT_REVIEW_CANDIDATE, 0o444),
            (BUNDLE_LAUNCHER_REVIEW_CANDIDATE, 0o555),
        ):
            metadata = os.lstat(path)
            if (
                not stat.S_ISREG(metadata.st_mode)
                or metadata.st_nlink != 1
                or metadata.st_uid != os.getuid()
                or metadata.st_gid != os.getgid()
                or stat.S_IMODE(metadata.st_mode) != mode
            ):
                _fail("UNPRIVILEGED_REVIEW_PATH_INVALID", str(path))
    else:
        _require_core_installed()
        _require_stage_authority("bundle", plan=False)
    lock = contextlib.nullcontext() if review_candidate else operation_lock("bundle")
    with lock:
        document, pin = _load_bundle_input_pin(review_candidate=review_candidate)
        _validate_bundle_input_against_live(document)
        plan = _bundle_plan_from_input(document, pin)
    return {
        "status": "executor_bundle_audit_plan_candidate_zero_write",
        "accepted": False,
        "audit_plan": plan,
        "reviewed_plan_pin_pending_admin_launcher": True,
        "publication_performed": False,
    }


def _require_root_execution_parent() -> None:
    metadata = os.lstat(ROOT_EXECUTION_AUTHORITY.parent)
    if (
        not stat.S_ISDIR(metadata.st_mode)
        or metadata.st_uid != ROOT_UID
        or metadata.st_gid != ROOT_GID
        or stat.S_IMODE(metadata.st_mode) != 0o700
    ):
        _fail("ROOT_EXECUTION_PARENT_INVALID", str(ROOT_EXECUTION_AUTHORITY.parent))


def _write_reviewed_bundle_sources(
    document: Mapping[str, Any], bundle: Path
) -> dict[str, FilePin]:
    pins: dict[str, FilePin] = {}
    for name, source in BUNDLE_SOURCE_PATHS.items():
        raw, actual = _read_regular(source, f"bundle source {name}")
        expected = _parse_pin(document["source_pins"][name]["pin"], name)
        if (actual.sha256, actual.size_bytes) != (
            expected.sha256,
            expected.size_bytes,
        ):
            _fail("BUNDLE_SOURCE_DRIFT", name)
        mode = 0o555 if name == "makehuman_cc0_animation_runtime_executor.py" else 0o444
        pins[name] = _write_new(bundle / name, raw, mode, (ROOT_UID, ROOT_GID))
    return pins


def _expected_final_policy(
    input_document: Mapping[str, Any],
    input_file_pin: FilePin,
    plan: Mapping[str, Any],
    reviewed_plan_document: Mapping[str, Any],
    reviewed_plan_file_pin: FilePin,
    *,
    live_python: FilePin,
) -> dict[str, Any]:
    provenance = _bundle_publication_provenance(
        input_document,
        input_file_pin,
        plan,
        reviewed_plan_document,
        reviewed_plan_file_pin,
        live_python=live_python,
    )
    return finalize_root_policy(plan["policy_core_document"], provenance)


def audit_existing_executor_bundle(*, fsync: bool = False) -> dict[str, Any]:
    _require_root_execution_parent()
    _require_exact_directory(
        ROOT_EXECUTION_AUTHORITY,
        {"bundle", "policy.json"},
        "root execution authority",
    )
    _require_exact_directory(
        ROOT_BUNDLE,
        {
            *BUNDLE_SOURCE_PATHS,
            LAUNCHER_NAME,
            "bundle-manifest.json",
        },
        "root execution bundle",
    )
    input_document, input_file_pin = _load_bundle_input_pin()
    plan = _bundle_plan_from_input(input_document, input_file_pin)
    reviewed_plan_document, reviewed_plan_file_pin = _load_reviewed_plan_pin(
        BUNDLE_REVIEWED_PLAN_PIN_PATH,
        plan,
        "bundle",
        BUNDLE_ADMIN_LAUNCHER,
    )
    live_python = _require_live_python(
        input_document["runtime_executables"]["python"]["pin"]
    )
    expected_policy = _expected_final_policy(
        input_document,
        input_file_pin,
        plan,
        reviewed_plan_document,
        reviewed_plan_file_pin,
        live_python=live_python,
    )
    expected_bundle_pins = _bundle_file_pins(input_document)
    for name, expected in expected_bundle_pins.items():
        mode = 0o555 if expected.executable else 0o444
        _raw, actual = _root_file(ROOT_BUNDLE / name, name, mode)
        if (actual.sha256, actual.size_bytes) != (
            expected.sha256,
            expected.size_bytes,
        ):
            _fail("ROOT_EXECUTION_AUTHORITY_INVALID", name)
    manifest, manifest_pin = load_sealed_document(
        ROOT_BUNDLE / "bundle-manifest.json",
        BUNDLE_MANIFEST_SCHEMA,
        "bundle manifest",
    )
    if manifest != plan["bundle_manifest_document"]:
        _fail("ROOT_EXECUTION_AUTHORITY_INVALID", "bundle manifest")
    policy, policy_pin = load_sealed_document(
        ROOT_POLICY, ROOT_POLICY_SCHEMA, "root policy"
    )
    if policy != expected_policy:
        _fail("ROOT_EXECUTION_AUTHORITY_INVALID", "root policy")
    if fsync:
        _fsync_immutable_tree(ROOT_EXECUTION_AUTHORITY, "root executor bundle")
    return {
        "status": (
            "existing_executor_bundle_durability_reconciled"
            if fsync
            else "existing_executor_bundle_audited"
        ),
        "accepted": True,
        "publication_performed": False,
        "deletion_performed": False,
        "bundle_manifest_pin": manifest_pin.public(),
        "policy_pin": policy_pin.public(),
        "policy_content_digest": policy["content_digest"],
    }


def publish_executor_bundle() -> dict[str, Any]:
    _require_stage_installed("bundle")
    _require_root_execution_parent()
    with operation_lock("bundle"):
        input_document, input_file_pin = _load_bundle_input_pin()
        live_python = _require_live_python(
            input_document["runtime_executables"]["python"]["pin"]
        )
        _validate_bundle_input_against_live(input_document)
        plan = _bundle_plan_from_input(input_document, input_file_pin)
        reviewed_plan_document, reviewed_plan_file_pin = _load_reviewed_plan_pin(
            BUNDLE_REVIEWED_PLAN_PIN_PATH,
            plan,
            "bundle",
            BUNDLE_ADMIN_LAUNCHER,
        )
        if os.path.lexists(ROOT_EXECUTION_AUTHORITY):
            _fail("FINAL_NOT_FRESH", str(ROOT_EXECUTION_AUTHORITY))
        staging = Path(
            tempfile.mkdtemp(
                prefix=f".{ROOT_EXECUTION_AUTHORITY.name}.staging-",
                dir=ROOT_EXECUTION_AUTHORITY.parent,
            )
        )
        os.chown(staging, ROOT_UID, ROOT_GID, follow_symlinks=False)
        try:
            bundle = staging / "bundle"
            bundle.mkdir(mode=0o700)
            os.chown(bundle, ROOT_UID, ROOT_GID, follow_symlinks=False)
            actual_pins = _write_reviewed_bundle_sources(input_document, bundle)
            launcher_path = bundle / LAUNCHER_NAME
            expected_launcher = _parse_pin(
                input_document["launcher_binary_pin"], "launcher"
            )
            with hold_source_file_components(BUNDLE_INPUT_LAUNCHER) as held:
                if (
                    held.canonical_path != BUNDLE_INPUT_LAUNCHER
                    or held.metadata.st_uid != ROOT_UID
                    or held.metadata.st_gid != ROOT_GID
                    or held.metadata.st_nlink != 1
                    or stat.S_IMODE(held.metadata.st_mode) != 0o555
                ):
                    _fail("REVIEWED_LAUNCHER_INPUT_INVALID", str(held.canonical_path))
                source_sha, source_bytes = _hash_fd(held.descriptor)
                if (source_sha, source_bytes) != (
                    expected_launcher.sha256,
                    expected_launcher.size_bytes,
                ):
                    _fail("REVIEWED_LAUNCHER_INPUT_INVALID", "pin")
                launcher_fd = os.open(
                    launcher_path,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW | os.O_CLOEXEC,
                    0o600,
                )
                try:
                    copied = _copy_file_fd(held.descriptor, launcher_fd)
                    if (copied.sha256, copied.size_bytes) != (
                        expected_launcher.sha256,
                        expected_launcher.size_bytes,
                    ) or _identity(os.fstat(held.descriptor)) != _identity(
                        held.metadata
                    ):
                        _fail("REVIEWED_LAUNCHER_INPUT_INVALID", "copy")
                    os.fchown(launcher_fd, ROOT_UID, ROOT_GID)
                    os.fchmod(launcher_fd, 0o555)
                    os.fsync(launcher_fd)
                finally:
                    os.close(launcher_fd)
            launcher_pin = FilePin(
                expected_launcher.sha256, expected_launcher.size_bytes, True
            )
            actual_pins[LAUNCHER_NAME] = FilePin(
                launcher_pin.sha256, launcher_pin.size_bytes, True
            )
            if actual_pins != _bundle_file_pins(input_document):
                _fail("BUNDLE_SOURCE_DRIFT", "final bundle pins")
            manifest_document = plan["bundle_manifest_document"]
            manifest_pin = _write_new(
                bundle / "bundle-manifest.json",
                canonical_json(manifest_document),
                0o444,
                (ROOT_UID, ROOT_GID),
            )
            expected_manifest_raw = canonical_json(manifest_document)
            expected_manifest_pin = FilePin(
                hashlib.sha256(expected_manifest_raw).hexdigest(),
                len(expected_manifest_raw),
            )
            if manifest_pin != expected_manifest_pin:
                _fail("BUNDLE_MANIFEST_DIFFERS", "staged manifest")
            policy_document = _expected_final_policy(
                input_document,
                input_file_pin,
                plan,
                reviewed_plan_document,
                reviewed_plan_file_pin,
                live_python=live_python,
            )
            policy_pin = _write_new(
                staging / "policy.json",
                canonical_json(policy_document),
                0o444,
                (ROOT_UID, ROOT_GID),
            )
            _seal_private_tree(staging, owner=(ROOT_UID, ROOT_GID))
            publish_staging(staging, ROOT_EXECUTION_AUTHORITY)
            return {
                "status": "published_atomic_r2_executor_authority",
                "accepted": True,
                "authority_root": str(ROOT_EXECUTION_AUTHORITY),
                "bundle_manifest_pin": manifest_pin.public(),
                "bundle_manifest_content_digest": manifest_document["content_digest"],
                "policy_pin": policy_pin.public(),
                "policy_content_digest": policy_document["content_digest"],
            }
        finally:
            if os.path.lexists(staging):
                _remove_private_staging(staging)


def reconcile_executor_bundle() -> dict[str, Any]:
    _require_stage_installed("bundle")
    with operation_lock("bundle"):
        return audit_existing_executor_bundle(fsync=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    def stage_command(name: str, *, plan: bool) -> None:
        command = sub.add_parser(name)
        prefix = "plan" if plan else "input"
        command.add_argument(f"--reviewed-{prefix}-sha256", required=True)
        command.add_argument(f"--reviewed-{prefix}-size", required=True, type=int)
        if plan:
            command.add_argument("--reviewed-admin-sha256", required=True)
            command.add_argument("--reviewed-admin-size", required=True, type=int)
        command.add_argument("--stage-installer-fd", required=True, type=int)
        command.add_argument("--acknowledgement", required=True)

    def installer_transfer_command(name: str) -> None:
        command = sub.add_parser(name)
        command.add_argument("--stage", required=True, choices=STAGE_KEYS)
        command.add_argument("--reviewed-installer-sha256", required=True)
        command.add_argument("--reviewed-installer-size", required=True, type=int)
        command.add_argument("--stage-transfer-launcher-fd", required=True, type=int)
        command.add_argument("--acknowledgement", required=True)

    sub.add_parser("audit-engine-source")
    engine_pin_candidate = sub.add_parser("build-engine-source-pin-review-candidate")
    engine_pin_candidate.add_argument("--reviewed-pin-sha256", required=True)
    engine_pin_candidate.add_argument("--reviewed-pin-size", required=True, type=int)
    sub.add_parser("build-parent-seal-review-candidate")
    sub.add_parser("build-buildplugin-admin-review-candidate")
    sub.add_parser("audit-engine")
    publish = sub.add_parser("publish-engine")
    publish.add_argument("--acknowledgement", required=True)
    reconcile = sub.add_parser("reconcile-engine")
    reconcile.add_argument("--acknowledgement", required=True)
    sub.add_parser("derive-host-runtime-input-pin")
    sub.add_parser("build-stage-transfer-launcher-review-candidate")
    sub.add_parser("build-core-bootstrap-review-candidate")
    sub.add_parser("audit-core-bootstrap-review-inputs")
    initial_bootstrap = sub.add_parser("build-initial-bootstrap-review-candidate")
    initial_bootstrap.add_argument("--reviewed-core-audit-sha256", required=True)
    initial_bootstrap.add_argument(
        "--reviewed-core-audit-size", required=True, type=int
    )
    sub.add_parser("build-initial-bootstrap-installer-review-candidate")
    sub.add_parser("build-runtime-input-review-candidate")
    sub.add_parser("build-runtime-plan-review-candidate")
    for stage_key in STAGE_KEYS:
        sub.add_parser(f"build-{stage_key}-stage-installer-review-candidate")
    sub.add_parser("audit-host-runtime-plan")
    installer_transfer_command("install-stage-installer-authority")
    installer_transfer_command("reconcile-stage-installer-authority")
    stage_command("install-runtime-input-authority", plan=False)
    stage_command("reconcile-runtime-input-authority", plan=False)
    stage_command("install-runtime-plan-authority", plan=True)
    stage_command("reconcile-runtime-plan-authority", plan=True)
    runtime = sub.add_parser("publish-host-runtime")
    runtime.add_argument("--acknowledgement", required=True)
    runtime_reconcile = sub.add_parser("reconcile-host-runtime")
    runtime_reconcile.add_argument("--acknowledgement", required=True)
    sub.add_parser("build-bundle-input-review-candidate")
    sub.add_parser("derive-executor-bundle-input-pin")
    sub.add_parser("build-bundle-plan-review-candidate")
    sub.add_parser("audit-executor-bundle-plan")
    stage_command("install-bundle-input-authority", plan=False)
    stage_command("reconcile-bundle-input-authority", plan=False)
    stage_command("install-bundle-plan-authority", plan=True)
    stage_command("reconcile-bundle-plan-authority", plan=True)
    bundle = sub.add_parser("publish-executor-bundle")
    bundle.add_argument("--acknowledgement", required=True)
    bundle_reconcile = sub.add_parser("reconcile-executor-bundle")
    bundle_reconcile.add_argument("--acknowledgement", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        root_commands = {
            "audit-engine",
            "publish-engine",
            "reconcile-engine",
            "install-stage-installer-authority",
            "reconcile-stage-installer-authority",
            "install-runtime-input-authority",
            "reconcile-runtime-input-authority",
            "install-runtime-plan-authority",
            "reconcile-runtime-plan-authority",
            "publish-host-runtime",
            "reconcile-host-runtime",
            "install-bundle-input-authority",
            "reconcile-bundle-input-authority",
            "install-bundle-plan-authority",
            "reconcile-bundle-plan-authority",
            "publish-executor-bundle",
            "reconcile-executor-bundle",
        }
        review_commands = {
            "audit-engine-source",
            "build-engine-source-pin-review-candidate",
            "build-parent-seal-review-candidate",
            "build-buildplugin-admin-review-candidate",
            "derive-host-runtime-input-pin",
            "build-stage-transfer-launcher-review-candidate",
            "build-core-bootstrap-review-candidate",
            "audit-core-bootstrap-review-inputs",
            "build-initial-bootstrap-review-candidate",
            "build-runtime-input-review-candidate",
            "build-runtime-plan-review-candidate",
            "build-bundle-input-review-candidate",
            "build-bundle-plan-review-candidate",
            "derive-executor-bundle-input-pin",
            *(f"build-{key}-stage-installer-review-candidate" for key in STAGE_KEYS),
        }
        # Audit-plan commands intentionally support two fixed modes: an
        # unprivileged committed-checkout candidate path, or the installed root
        # input authority.  Every other state-changing command has one EUID.
        if args.command in root_commands and os.geteuid() != ROOT_UID:
            _fail("ROOT_EUID_REQUIRED", args.command)
        if args.command in review_commands and (
            os.geteuid() != REVIEW_UID or os.getegid() != REVIEW_GID
        ):
            _fail("UNPRIVILEGED_REVIEW_REQUIRED", args.command)
        if os.geteuid() == ROOT_UID:
            os.environ.clear()
            os.environ.update(
                {
                    "PATH": "/usr/bin:/bin",
                    "HOME": "/nonexistent",
                    "LANG": "C.UTF-8",
                    "PYTHONNOUSERSITE": "1",
                    "PYTHONDONTWRITEBYTECODE": "1",
                }
            )
            os.umask(0o077)
        stage_operations = {
            "install-runtime-input-authority": ("runtime", False, "install"),
            "reconcile-runtime-input-authority": (
                "runtime",
                False,
                "reconcile",
            ),
            "install-runtime-plan-authority": ("runtime", True, "install"),
            "reconcile-runtime-plan-authority": ("runtime", True, "reconcile"),
            "install-bundle-input-authority": ("bundle", False, "install"),
            "reconcile-bundle-input-authority": (
                "bundle",
                False,
                "reconcile",
            ),
            "install-bundle-plan-authority": ("bundle", True, "install"),
            "reconcile-bundle-plan-authority": ("bundle", True, "reconcile"),
        }
        stage_operation = stage_operations.get(args.command)
        if args.command in {
            "install-stage-installer-authority",
            "reconcile-stage-installer-authority",
        }:
            key = args.stage
            stage, phase = key.split("-", 1)
            is_plan = phase == "plan"
            action = (
                "install"
                if args.command == "install-stage-installer-authority"
                else "reconcile"
            )
            if (
                args.acknowledgement
                != STAGE_INSTALLER_TRANSFER_ACKNOWLEDGEMENTS[(key, action)]
            ):
                _fail(
                    "ACKNOWLEDGEMENT_REQUIRED",
                    f"{key} stage installer transfer acknowledgement",
                )
            reviewed_installer_pin = {
                "sha256": args.reviewed_installer_sha256,
                "size_bytes": args.reviewed_installer_size,
            }
            if action == "install":
                result = install_stage_installer_authority(
                    stage,
                    plan=is_plan,
                    reviewed_installer_pin=reviewed_installer_pin,
                    stage_transfer_launcher_fd=args.stage_transfer_launcher_fd,
                )
            else:
                result = reconcile_stage_installer_authority(
                    stage,
                    plan=is_plan,
                    reviewed_installer_pin=reviewed_installer_pin,
                    stage_transfer_launcher_fd=args.stage_transfer_launcher_fd,
                )
        elif stage_operation is not None:
            stage, is_plan, action = stage_operation
            if args.acknowledgement != STAGE_ACKNOWLEDGEMENTS[(stage, is_plan, action)]:
                _fail("ACKNOWLEDGEMENT_REQUIRED", f"{stage} stage acknowledgement")
            prefix = "plan" if is_plan else "input"
            primary_pin = {
                "sha256": getattr(args, f"reviewed_{prefix}_sha256"),
                "size_bytes": getattr(args, f"reviewed_{prefix}_size"),
            }
            admin_pin = (
                {
                    "sha256": args.reviewed_admin_sha256,
                    "size_bytes": args.reviewed_admin_size,
                }
                if is_plan
                else None
            )
            if action == "install" and is_plan:
                if admin_pin is None:
                    _fail("PIN_INVALID", "stage admin launcher")
                result = install_stage_plan_authority(
                    stage,
                    primary_pin,
                    admin_pin,
                    stage_installer_fd=args.stage_installer_fd,
                )
            elif action == "install":
                result = install_stage_input_authority(
                    stage,
                    primary_pin,
                    stage_installer_fd=args.stage_installer_fd,
                )
            else:
                result = reconcile_stage_authority(
                    stage,
                    plan=is_plan,
                    reviewed_primary_pin=primary_pin,
                    reviewed_admin_launcher_pin=admin_pin,
                    stage_installer_fd=args.stage_installer_fd,
                )
        elif args.command == "audit-engine-source":
            result = audit_engine_source()
        elif args.command == "build-engine-source-pin-review-candidate":
            result = build_engine_source_pin_review_candidate(
                {
                    "sha256": args.reviewed_pin_sha256,
                    "size_bytes": args.reviewed_pin_size,
                }
            )
        elif args.command == "build-parent-seal-review-candidate":
            result = build_parent_seal_review_candidate()
        elif args.command == "build-buildplugin-admin-review-candidate":
            result = build_buildplugin_admin_review_candidate()
        elif args.command == "audit-engine":
            result = audit_engine()
        elif args.command == "publish-engine":
            if args.acknowledgement != ENGINE_ACKNOWLEDGEMENT:
                _fail("ACKNOWLEDGEMENT_REQUIRED", "engine acknowledgement differs")
            result = publish_engine()
        elif args.command == "reconcile-engine":
            if args.acknowledgement != ENGINE_RECONCILIATION_ACKNOWLEDGEMENT:
                _fail(
                    "ACKNOWLEDGEMENT_REQUIRED",
                    "engine reconciliation acknowledgement differs",
                )
            result = reconcile_engine()
        elif args.command == "derive-host-runtime-input-pin":
            result = derive_runtime_input_pin()
        elif args.command == "build-stage-transfer-launcher-review-candidate":
            result = build_stage_transfer_launcher_review_candidate()
        elif args.command == "build-core-bootstrap-review-candidate":
            result = build_core_bootstrap_review_candidate()
        elif args.command == "audit-core-bootstrap-review-inputs":
            result = audit_core_bootstrap_review_inputs()
        elif args.command == "build-initial-bootstrap-review-candidate":
            result = build_initial_bootstrap_review_candidate(
                {
                    "sha256": args.reviewed_core_audit_sha256,
                    "size_bytes": args.reviewed_core_audit_size,
                }
            )
        elif args.command == "build-initial-bootstrap-installer-review-candidate":
            result = build_initial_bootstrap_installer_review_candidate()
        elif args.command == "build-runtime-input-review-candidate":
            result = build_runtime_input_review_candidate()
        elif args.command == "build-runtime-plan-review-candidate":
            result = build_runtime_plan_review_candidate()
        elif args.command.startswith("build-") and args.command.endswith(
            "-stage-installer-review-candidate"
        ):
            key = args.command.removeprefix("build-").removesuffix(
                "-stage-installer-review-candidate"
            )
            result = build_stage_installer_review_candidate(key)
        elif args.command == "audit-host-runtime-plan":
            result = audit_host_runtime_plan()
        elif args.command == "publish-host-runtime":
            if args.acknowledgement != HOST_RUNTIME_ACKNOWLEDGEMENT:
                _fail(
                    "ACKNOWLEDGEMENT_REQUIRED", "host-runtime acknowledgement differs"
                )
            result = publish_host_runtime()
        elif args.command == "reconcile-host-runtime":
            if args.acknowledgement != HOST_RUNTIME_RECONCILIATION_ACKNOWLEDGEMENT:
                _fail(
                    "ACKNOWLEDGEMENT_REQUIRED",
                    "host-runtime reconciliation acknowledgement differs",
                )
            result = reconcile_host_runtime()
        elif args.command == "build-bundle-input-review-candidate":
            result = build_bundle_input_review_candidate()
        elif args.command == "derive-executor-bundle-input-pin":
            result = derive_bundle_input_pin()
        elif args.command == "build-bundle-plan-review-candidate":
            result = build_bundle_plan_review_candidate()
        elif args.command == "audit-executor-bundle-plan":
            result = audit_executor_bundle_plan()
        elif args.command == "publish-executor-bundle":
            if args.acknowledgement != BUNDLE_ACKNOWLEDGEMENT:
                _fail("ACKNOWLEDGEMENT_REQUIRED", "bundle acknowledgement differs")
            result = publish_executor_bundle()
        else:
            if args.acknowledgement != BUNDLE_RECONCILIATION_ACKNOWLEDGEMENT:
                _fail(
                    "ACKNOWLEDGEMENT_REQUIRED",
                    "bundle reconciliation acknowledgement differs",
                )
            result = reconcile_executor_bundle()
        print(canonical_json(result).decode("utf-8"), end="")
        return 0
    except AuthorityError as exc:
        print(str(exc), file=os.sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
