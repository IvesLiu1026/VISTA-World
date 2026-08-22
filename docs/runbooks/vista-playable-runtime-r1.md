# VISTA Playable Runtime R1 Runbook

This runbook is the VISTA-World entry point for the extracted playable-home
source. Run commands from the repository root. Commands shown without
`--apply` are planning or read-only validation commands; adding `--apply`
requires the authorization named below.

## Current truth

- HouseSpec, seven VISTA-derived EventSpecs, and the BuildPlan compiler exist.
- UE plugin, Blender/HSSD/realism pipelines, UE composition, package planning,
  runtime acceptance, and Sunshine app generation source exist.
- The T9 event-outcome plugin passed 198 offline tests and UE 5.7.3
  BuildPlugin for Editor, Development, and Shipping targets.
- No VISTA-World composed map, playable package, renderer proof, accepted
  animation library, or Moonlight control proof has yet been accepted.

## Repository environment

Use the root `uv.lock`; do not install with `pip` and do not use the upstream
SimWorld `tools/pyproject.toml` examples.

```bash
uv sync --frozen
```

The source-only offline suite is:

```bash
PYTHONPATH=.:tools uv run --offline --no-sync --with pytest \
  python -m unittest discover -s tools/tests \
  -p 'test_vista_playable_home_*.py' -v
```

This command does not launch UE, Blender, a GPU workload, a listener, or a
service. It is the T6 gate before any runtime claim. The extraction baseline
passed 195 discovered tests; the T9 outcome-evaluator revision passed 198 on
2026-08-22.

## Optional HSSD research plan

Planning reads a local HSSD checkout and does not download data or run
Blender. The explicit acknowledgement is required because HSSD is
CC BY-NC 4.0 and the R1 demo is private non-commercial research only.

```bash
PYTHONPATH=. uv run --offline --no-sync python \
  -m tools.blender.vista_playable_home_hssd \
  --normalized-manifest /absolute/run/blender/normalized-manifest.json \
  --hssd-root /absolute/private/hssd-hab \
  --output /absolute/run/hssd-binding-plan.json \
  --license-accept CC-BY-NC-4.0
```

No HSSD bytes or generated derivatives may be committed.

## UE host preflight

After T6 passes and the user authorizes UE inspection, run only the read-only
host report first:

```bash
PYTHONPATH=. uv run --offline --no-sync python \
  tools/runtime/vista_playable_home/preflight.py \
  --ue-editor /absolute/UE_5.7.3/Engine/Binaries/Linux/UnrealEditor
```

The required engine is UE 5.7.3 for Linux x86_64. A different engine version
does not satisfy the contract.

## Authorization checkpoints

| Gate | Operation | Explicit approval required because |
| --- | --- | --- |
| T6 | Run imported offline tests | Uses local CPU only; no runtime lifecycle |
| T7 | UE `BuildPlugin` | Invokes the installed UE toolchain and writes a disposable package |
| T8 | Compose/package disposable project | Can use substantial CPU, disk, and later GPU resources |
| T10 | Launch three-room `mmg_044` slice | Starts UE/GPU and a loopback runtime listener |
| T11 | Acquire external visual assets | Uses network and creates licensed local payloads |
| T12-T13 | Import/retarget animation content | Uses UE content pipelines and possibly licensed assets |
| T15 | Install/restart Sunshine entry | Mutates host service configuration and input-device policy |

Each authorization applies only to the named attempt, paths, devices, and
commands presented immediately before execution. It never authorizes paid
models, deployment, scheduler/auto-merge, unrelated services, or destructive
cleanup.
