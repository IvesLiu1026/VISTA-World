#!/usr/bin/env python3
"""Trusted in-sandbox runtime wrapper for the R5 multi-client proof.

This file is projected from an exact Git blob into the private bubblewrap
namespace. Unreal writes its receipt and Automation report only to the private
tmpfs. The wrapper emits one canonical base64 envelope on stdout after both
artifacts pass their minimal closed checks. Unreal logs are redirected to
stderr and are never success evidence.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import pathlib
import subprocess
import sys
from typing import Any


AUTOMATION_TEST = (
    "VISTA.R5.VistaR5MultiClientProof.ReplicatesTransactionalPhysicalState"
)
ENVELOPE_SCHEMA = "vista.r5-private-runtime-envelope/v1"
ENVELOPE_MARKER = "VISTA_R5_PRIVATE_ENVELOPE_V1:"
RECEIPT_SCHEMA = "vista.r5-multiclient-proof-receipt/v3"
PRIVATE_ROOT = pathlib.Path("/vista-private")
RECEIPT_PATH = PRIVATE_ROOT / "r5-multiclient-proof-receipt.json"
REPORT_ROOT = PRIVATE_ROOT / "automation-report"
REPORT_PATH = REPORT_ROOT / "index.json"
MAX_RECEIPT_BYTES = 512 * 1024
MAX_REPORT_BYTES = 4 * 1024 * 1024
REPORT_KEYS = frozenset(
    {
        "devices",
        "reportCreatedOn",
        "succeeded",
        "succeededWithWarnings",
        "failed",
        "notRun",
        "inProcess",
        "totalDuration",
        "comparisonExported",
        "comparisonExportDirectory",
        "tests",
    }
)
TEST_KEYS = frozenset(
    {
        "testDisplayName",
        "fullTestPath",
        "tags",
        "state",
        "deviceInstance",
        "duration",
        "dateTime",
        "entries",
        "warnings",
        "errors",
        "artifacts",
    }
)


class CaptureError(RuntimeError):
    pass


def _fail(message: str) -> None:
    raise CaptureError(message)


def _canonical(value: dict[str, Any]) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":")).encode() + b"\n"


def _read_private_regular(path: pathlib.Path, limit: int, label: str) -> bytes:
    if path.is_symlink():
        _fail(f"{label} must not be a symlink")
    try:
        resolved = path.resolve(strict=True)
        info = path.stat()
    except OSError as exc:
        raise CaptureError(f"{label} is missing") from exc
    if resolved != path or not path.is_file() or not (0 < info.st_size <= limit):
        _fail(f"{label} path/size contract differs")
    return path.read_bytes()


def _json_object(raw: bytes, label: str) -> dict[str, Any]:
    try:
        value = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CaptureError(f"{label} is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        _fail(f"{label} must be a JSON object")
    return value


def _validate_report(raw: bytes) -> None:
    report = _json_object(raw, "Automation report")
    if frozenset(report) != REPORT_KEYS:
        _fail("Automation report fields differ")
    expected_totals = {
        "succeeded": 1,
        "succeededWithWarnings": 0,
        "failed": 0,
        "notRun": 0,
        "inProcess": 0,
    }
    for key, expected in expected_totals.items():
        value = report.get(key)
        if not isinstance(value, int) or isinstance(value, bool) or value != expected:
            _fail(f"Automation report {key} differs")
    tests = report.get("tests")
    if not isinstance(tests, list) or len(tests) != 1:
        _fail("Automation report must contain exactly the requested test")
    test = tests[0]
    if not isinstance(test, dict) or frozenset(test) != TEST_KEYS:
        _fail("Automation test result fields differ")
    if (
        test.get("fullTestPath") != AUTOMATION_TEST
        or test.get("state") != "Success"
        or test.get("warnings") != 0
        or test.get("errors") != 0
    ):
        _fail("requested Automation test did not succeed without errors")
    if not isinstance(test.get("warnings"), int) or isinstance(
        test.get("warnings"), bool
    ):
        _fail("Automation test warnings is not an integer")
    if not isinstance(test.get("errors"), int) or isinstance(test.get("errors"), bool):
        _fail("Automation test errors is not an integer")


def _validate_receipt(raw: bytes) -> None:
    receipt = _json_object(raw, "private receipt")
    if receipt.get("schema") != RECEIPT_SCHEMA or receipt.get("status") != "passed":
        _fail("private receipt did not close as passed v3")


def _validate_command(command: list[str]) -> None:
    if not command or command[0] != (
        "/data/vista-authorities/ue-5.7.3-r1/engine/Engine/Binaries/Linux/"
        "UnrealEditor-Cmd"
    ):
        _fail("runtime executable is not the immutable authority")
    required = {
        f"-ExecCmds=Automation RunTests {AUTOMATION_TEST}",
        "-ReportExportPath=/vista-private/automation-report",
        "-VistaR5ProofReceipt=/vista-private/r5-multiclient-proof-receipt.json",
        "-nullrhi",
    }
    if not required.issubset(command):
        _fail("runtime command proof arguments differ")


def main(argv: list[str]) -> int:
    try:
        if len(argv) < 3 or argv[1] != "--":
            _fail("wrapper requires a command after --")
        command = argv[2:]
        _validate_command(command)
        if any(PRIVATE_ROOT.iterdir()):
            _fail("private runtime tmpfs is not fresh")
        completed = subprocess.run(
            command,
            stdin=subprocess.DEVNULL,
            stdout=sys.stderr,
            stderr=sys.stderr,
            check=False,
            env=dict(os.environ),
        )
        if completed.returncode != 0:
            _fail("Unreal runtime returned nonzero")
        receipt_raw = _read_private_regular(
            RECEIPT_PATH, MAX_RECEIPT_BYTES, "private receipt"
        )
        report_raw = _read_private_regular(
            REPORT_PATH, MAX_REPORT_BYTES, "Automation report"
        )
        _validate_receipt(receipt_raw)
        _validate_report(report_raw)
        envelope = {
            "schema": ENVELOPE_SCHEMA,
            "automation_test": AUTOMATION_TEST,
            "runtime_exit_code": completed.returncode,
            "receipt_base64": base64.b64encode(receipt_raw).decode("ascii"),
            "receipt_sha256": hashlib.sha256(receipt_raw).hexdigest(),
            "automation_report_base64": base64.b64encode(report_raw).decode("ascii"),
            "automation_report_sha256": hashlib.sha256(report_raw).hexdigest(),
        }
        encoded = base64.b64encode(_canonical(envelope)).decode("ascii")
        sys.stdout.write(f"{ENVELOPE_MARKER}{encoded}\n")
        sys.stdout.flush()
        return 0
    except CaptureError as exc:
        print(f"R5_PRIVATE_CAPTURE_FAILED: {exc}", file=sys.stderr)
        return 74


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
