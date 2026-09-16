"""Run one isolated Isaac experiment; stop only its process group on limits.

Use the workspace uv Python for this supervisor, not the simulator interpreter.
The simulator's Kit settings must also disable multi-GPU (CUDA_VISIBLE_DEVICES
alone does not select the Vulkan renderer).
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time


def gpu_sample():
    result = subprocess.run([
        "nvidia-smi", "--query-gpu=index,uuid,memory.used,utilization.gpu",
        "--format=csv,noheader,nounits",
    ], capture_output=True, text=True, check=True, timeout=10)
    return [dict(zip(("index", "uuid", "memory_mib", "utilization_pct"),
                     (int(a), b.strip(), int(c), int(d))))
            for a, b, c, d in (line.split(",") for line in result.stdout.splitlines())]


def inspect_result(output):
    """Kit may exit 0 while discarding a Python exception; require evidence."""
    result_path = output / "data" / "results.json"
    error_path = output / "data" / "error.txt"
    status = {"results_present": result_path.is_file(),
              "python_error_present": error_path.is_file(), "checks_pass": False}
    if not result_path.is_file() or error_path.is_file():
        return status
    try:
        result = json.loads(result_path.read_text())
        checks = result.get("checks") if isinstance(result, dict) else None
        status["checks_pass"] = (isinstance(checks, dict) and bool(checks)
                                 and all(value is True for value in checks.values()))
    except (ValueError, OSError):
        status["checks_pass"] = False
    return status


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--python", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--timeout", type=float, default=900)
    p.add_argument("--gpu-memory-limit-mib", type=int, default=30000)
    p.add_argument("command", nargs=argparse.REMAINDER)
    args = p.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command:
        p.error("a simulation script is required")
    args.output.mkdir(parents=True, exist_ok=False)
    env = os.environ.copy()
    env.pop("DISPLAY", None)
    env.update(CUDA_VISIBLE_DEVICES="0", OMNI_KIT_ACCEPT_EULA="YES",
               VK_ICD_FILENAMES="/usr/share/vulkan/icd.d/nvidia_icd.json",
               PYTHONUNBUFFERED="1")
    start = time.monotonic()
    receipt = {"schema": "vista.isaac-run/v1", "command": [str(args.python), *command],
               "baseline_gpus": gpu_sample(), "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
               "timeout_s": args.timeout, "gpu_memory_limit_mib": args.gpu_memory_limit_mib,
               "scope": "single owned process group; GPU 0; no service changes"}
    receipt["source_sha256"] = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                                for path in Path(__file__).parent.glob("*.py")}
    with (args.output / "native.log").open("w") as log, (args.output / "resources.jsonl").open("w") as resources:
        process = subprocess.Popen(receipt["command"], env=env, stdout=log,
                                   stderr=subprocess.STDOUT, start_new_session=True)
        receipt["pid"] = process.pid
        (args.output / "launch.json").write_text(json.dumps(receipt, indent=2) + "\n")
        reason = None
        try:
            while process.poll() is None:
                elapsed = time.monotonic() - start
                gpus = gpu_sample()
                resources.write(json.dumps({"elapsed_s": elapsed, "gpus": gpus}) + "\n")
                resources.flush()
                if elapsed > args.timeout:
                    reason = "timeout"
                if next(g for g in gpus if g["index"] == 0)["memory_mib"] > args.gpu_memory_limit_mib:
                    reason = "GPU 0 memory limit"
                if reason:
                    break
                time.sleep(2)
        finally:
            if process.poll() is None:
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait(timeout=10)
            receipt.update(exit_code=process.returncode, stop_reason=reason,
                           elapsed_s=time.monotonic() - start, final_gpus=gpu_sample())
            # Kit fast shutdown can exit 0 while a Python exception is unwinding.
            # Exit status alone is never evidence that the experiment succeeded.
            receipt.update(inspect_result(args.output))
            (args.output / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))
    raise SystemExit(0 if process.returncode == 0 and reason is None and receipt["checks_pass"] else 1)


if __name__ == "__main__":
    main()
