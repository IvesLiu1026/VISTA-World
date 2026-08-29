#!/usr/bin/env python3
"""Build a read-only launch plan for a sealed human visual package.

Loading the final receipt re-hashes the complete package archive and all fixed
entry points.  The default (and only) CLI behavior prints a plan: it does not
create cache directories, start Sunshine, launch a process, or inspect pixels.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from tools.ue.vista_playable_home import human_visual_package_receipt as package_lane


PLAN_SCHEMA = "simworld.vista.human-visual-packaged-launch-plan/v1"
DISPLAY = ":118"
GPU = 0
WIDTH = 1920
HEIGHT = 1080
TARGET_FPS = 60
SCREEN_PERCENTAGE = 100
CAMERA_PROFILE = "realistic_interior_r2"
PROVIDER_ID = "citysample_crowd_visual_demo_v1"
CACHE_PARENT = Path("/data/sysx/vista-world/cache/human-visual-packaged")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
TRUSTED_PATH = "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"


class HumanVisualPackagedLaunchError(RuntimeError):
    """Raised when a packaged launch plan would weaken the sealed boundary."""


@dataclass(frozen=True)
class PackagedLaunchInputs:
    package: package_lane.FinalPackageBinding
    cache_root: Path
    network_wrapper: package_lane.FileSeal


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
        ).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise HumanVisualPackagedLaunchError(
            "value is not finite canonical JSON"
        ) from exc


def load_inputs(receipt: Path) -> PackagedLaunchInputs:
    try:
        package = package_lane.load_final_package_receipt(receipt)
    except package_lane.HumanVisualPackageError as exc:
        raise HumanVisualPackagedLaunchError(
            "final package receipt was refused"
        ) from exc
    if SHA256_RE.fullmatch(package.receipt_sha256) is None:
        raise HumanVisualPackagedLaunchError("package receipt identity is invalid")
    try:
        wrapper = package_lane.validate_network_wrapper()
    except package_lane.HumanVisualPackageError as exc:
        raise HumanVisualPackagedLaunchError("network wrapper was refused") from exc
    return PackagedLaunchInputs(
        package=package,
        cache_root=CACHE_PARENT / package.receipt_sha256,
        network_wrapper=wrapper,
    )


def build_command(inputs: PackagedLaunchInputs) -> list[str]:
    return [
        str(inputs.network_wrapper.path),
        "--unshare-net",
        "--die-with-parent",
        "--dev-bind",
        "/",
        "/",
        "--",
        str(inputs.package.launcher.path),
        "-game",
        "-Windowed",
        "-ForceRes",
        f"-ResX={WIDTH}",
        f"-ResY={HEIGHT}",
        f"-graphicsadapter={GPU}",
        f"-UserDir={inputs.cache_root / 'user'}",
        f"-LocalDataCachePath={inputs.cache_root / 'ddc'}",
        "-SaveToUserDir",
        "-NoSplash",
        "-NOSOUND",
        "-NoAnalytics",
        "-NoVSync",
        "-notraceserver",
        f"-ExecCmds=t.MaxFPS {TARGET_FPS},r.ScreenPercentage {SCREEN_PERCENTAGE}",
        "-UDPMESSAGING_TRANSPORT_ENABLE=0",
        "-ini:Engine:[/Script/TcpMessaging.TcpMessagingSettings]:EnableTransport=False",
        f"-VistaCameraProfile={CAMERA_PROFILE}",
        f"-VistaCharacterProvider={PROVIDER_ID}",
        "-VistaHumanOperatedVisualDemo",
    ]


def environment_plan(inputs: PackagedLaunchInputs) -> dict[str, str]:
    return {
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "PATH": TRUSTED_PATH,
        "DISPLAY": DISPLAY,
        "CUDA_VISIBLE_DEVICES": str(GPU),
        "NVIDIA_VISIBLE_DEVICES": str(GPU),
        "HOME": str(inputs.cache_root / "user"),
        "XDG_CACHE_HOME": str(inputs.cache_root / "user/xdg-cache"),
        "XDG_CONFIG_HOME": str(inputs.cache_root / "user/xdg-config"),
        "XDG_DATA_HOME": str(inputs.cache_root / "user/xdg-data"),
        "UE_LocalDataCachePath": str(inputs.cache_root / "ddc"),
        "VISTA_CHARACTER_PROVIDER": PROVIDER_ID,
        "VISTA_HUMAN_OPERATED_VISUAL_DEMO": "1",
    }


def build_plan(inputs: PackagedLaunchInputs) -> dict[str, Any]:
    try:
        refreshed_package = package_lane.load_final_package_receipt(
            inputs.package.receipt
        )
    except package_lane.HumanVisualPackageError as exc:
        raise HumanVisualPackagedLaunchError(
            "final package changed during launch planning"
        ) from exc
    if refreshed_package != inputs.package:
        raise HumanVisualPackagedLaunchError(
            "final package identity changed after input loading"
        )
    if inputs.cache_root != CACHE_PARENT / refreshed_package.receipt_sha256:
        raise HumanVisualPackagedLaunchError("package cache identity differs")
    try:
        observed_wrapper = package_lane.validate_network_wrapper()
    except package_lane.HumanVisualPackageError as exc:
        raise HumanVisualPackagedLaunchError("network wrapper was refused") from exc
    if observed_wrapper != inputs.network_wrapper:
        raise HumanVisualPackagedLaunchError(
            "network wrapper changed after input validation"
        )
    command = build_command(inputs)
    environment = environment_plan(inputs)
    return {
        "schema_version": PLAN_SCHEMA,
        "status": "dry_run_validated",
        "execution": "not_authorized_plan_only",
        "mode": "human_operated_packaged_visual_demo_only",
        "package": {
            "receipt": str(inputs.package.receipt),
            "receipt_sha256": inputs.package.receipt_sha256,
            "receipt_content_digest": inputs.package.receipt_content_digest,
            "source_receipt_sha256": inputs.package.source_receipt_sha256,
            "pso_expand_receipt_sha256": inputs.package.pso_expand_receipt_sha256,
            "stable_cache_sha256": inputs.package.stable_cache_sha256,
            "archive_root": str(inputs.package.archive_root),
            "archive_tree_sha256": inputs.package.archive_tree_sha256,
            "launcher_sha256": inputs.package.launcher.sha256,
            "executable_sha256": inputs.package.executable.sha256,
            "pak_sha256": inputs.package.pak.sha256,
            "archive_rehashed_during_plan": True,
        },
        "runtime": {
            "display": DISPLAY,
            "gpu": GPU,
            "width": WIDTH,
            "height": HEIGHT,
            "target_fps": TARGET_FPS,
            "screen_percentage": SCREEN_PERCENTAGE,
            "camera_profile": CAMERA_PROFILE,
            "provider_id": PROVIDER_ID,
        },
        "persistent_user_cache": {
            "root": str(inputs.cache_root),
            "identity": "final_package_receipt_sha256",
            "required_mode": "0700",
            "required_owner": "launching_euid",
            "directories": [
                str(inputs.cache_root / "ddc"),
                str(inputs.cache_root / "user"),
                str(inputs.cache_root / "user/xdg-cache"),
                str(inputs.cache_root / "user/xdg-config"),
                str(inputs.cache_root / "user/xdg-data"),
            ],
            "created_by_dry_run": False,
        },
        "command": command,
        "command_sha256": hashlib.sha256(canonical_json(command)).hexdigest(),
        "environment": environment,
        "security": {
            "shell": False,
            "closed_argv": True,
            "closed_environment": True,
            "extra_arguments_refused": True,
            "private_network_namespace": True,
            "network_wrapper": str(inputs.network_wrapper.path),
            "network_wrapper_sha256": inputs.network_wrapper.sha256,
            "network_wrapper_size_bytes": inputs.network_wrapper.size_bytes,
            "network_wrapper_rehashed_during_plan": True,
            "agent_runtime_invoked": False,
            "agent_adapter_present": False,
            "pso_capture_logging_disabled": "-logpso" not in command,
            "default_zero_write": True,
            "default_zero_subprocess": True,
            "cache_directories_created": False,
            "pixels_inspected": False,
        },
        "legal_scope": dict(package_lane.HUMAN_ONLY_LEGAL_BOUNDARY),
        "claims": dict(package_lane.CLAIMS),
        "acceptance_gates": {
            "human_visual_signoff_required": True,
            "human_interaction_signoff_required": True,
            "median_fps_minimum": 55,
            "one_percent_low_fps_minimum": 30,
            "frame_time_p95_ms_maximum": 25,
            "stall_over_one_second_count_maximum": 0,
            "new_pso_hitches_after_warmup_maximum": 0,
            "archive_rehash_after_smoke_required": True,
            "claims_remain_false_in_this_plan": True,
        },
    }


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--package-receipt", required=True, type=Path)
    return result


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    try:
        print(
            canonical_json(build_plan(load_inputs(args.package_receipt))).decode(),
            end="",
        )
        return 0
    except HumanVisualPackagedLaunchError as exc:
        print(f"human visual packaged launch refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
