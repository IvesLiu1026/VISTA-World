# VISTA R20 external live-scene upgrade

This lane copies the sealed R6 static project projection into one fresh
append-only attempt. It never edits R6 or live services. It installs a
caller-pinned compiled plugin, overlays R8/R14/R15 and Manny R18 action UAssets,
overlays the successful r1h articulated-fridge meshes, then runs network-isolated
UE author and cold-verify processes. All output remains external to Git and is
unaccepted private human-operated visual-demo material.

## 1. Materialize the caller-pinned binding

Set `PLUGIN_ROOT` to the integrated BuildPlugin output and `MANNY_R18_ROOT` /
`MANNY_R18_RECEIPT` to the successful R18 retarget output. The following writes
only the new external binding file.

```bash
export PLUGIN_ROOT=/data/sysx/vista-world/runs/vista-action-world-r1/REPLACE_WITH_INTEGRATED_BUILDPLUGIN
export MANNY_R18_ROOT=/data/sysx/vista-world/runs/vista-action-world-r1/REPLACE_WITH_R18_RETARGET/project/Content/VISTA/Manny/R18/DetailActions
export MANNY_R18_RECEIPT=/data/sysx/vista-world/runs/vista-action-world-r1/REPLACE_WITH_R18_RETARGET/manny-r18-retarget-host-receipt.json
export R20_BINDINGS=/data/sysx/vista-world/runs/vista-action-world-r1/r20-live-scene-input-bindings.json

PYTHONPATH=. uv run python - <<'PY'
import os
from pathlib import Path

from tools.runtime.vista_playable_home import human_visual_demo_launch as live
from tools.ue.vista_playable_home import build_home
from tools.ue.vista_playable_home import run_live_scene_upgrade_r20 as r20

run_parent = Path("/data/sysx/vista-world/runs/vista-action-world-r1")
r6_root = run_parent / "hssd-r2-citysample-live-r6-human-fit-20260831a"
r6 = r6_root / "project"

def artifact(path):
    seal = r20.sha256_file(Path(path))
    return seal.public()

def tree(path):
    path = Path(path).resolve(strict=True)
    seal = build_home.snapshot_tree(path, "R20 caller-pinned tree")
    return {
        "root": str(path),
        "tree_sha256": seal.sha256,
        "file_count": seal.file_count,
        "total_bytes": seal.total_bytes,
    }

descriptor = r6 / "VistaPlayableHome.uproject"
static_tree = live.compute_project_static_tree(descriptor)
binding = r20.seal_document({
    "schema_version": r20.BINDING_SCHEMA,
    "run_parent": str(run_parent),
    "source_project": {
        "static_tree": {"root": str(r6), **static_tree},
        "descriptor": artifact(descriptor),
        "map": artifact(r6 / "Content/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome.umap"),
        "manifest": artifact(r6_root / "human-fit-live-nonpromotable-manifest.json"),
    },
    "compiled_plugin": tree(os.environ["PLUGIN_ROOT"]),
    "typed_profile": artifact(
        Path("world_packs/vista_playable_home_r1/composition_profiles/")
        / "vista_home_typed_scene_r18.json"
    ),
    "overlays": {
        "r8": {
            "tree": tree(run_parent / "makehuman-cc0-animation-ue57-dev-r1-20260901g/project/Content/VISTA/MakeHumanCC0/R8/Animations"),
            "receipt": artifact(run_parent / "makehuman-cc0-animation-ue57-dev-r1-20260901g/makehuman-cc0-animation-runtime-receipt.json"),
        },
        "r14": {
            "tree": tree(run_parent / "makehuman-cc0-detail-actions-r14-ue57-dev-r1-20260901a/project/Content/VISTA/MakeHumanCC0/R14/DetailActions"),
            "receipt": artifact(run_parent / "makehuman-cc0-detail-actions-r14-ue57-dev-r1-20260901a/r14-detail-action-import-receipt.json"),
        },
        "r15": {
            "tree": tree(run_parent / "makehuman-cc0-detail-actions-r15-ue57-dev-r1-20260901b/project/Content/VISTA/MakeHumanCC0/R15/DetailActions"),
            "receipt": artifact(run_parent / "makehuman-cc0-detail-actions-r15-ue57-dev-r1-20260901b/r15-detail-action-import-receipt.json"),
        },
        "manny_r18": {
            "tree": tree(os.environ["MANNY_R18_ROOT"]),
            "receipt": artifact(os.environ["MANNY_R18_RECEIPT"]),
        },
        "fridge": {
            "tree": tree(run_parent / "hssd-r2-action-fridge-dev-r1-20260901h/project/Content/VISTA/Dev/ArticulatedFridge/r1_20260901h/Assets/Assets"),
            "receipt": artifact(run_parent / "hssd-r2-action-fridge-dev-r1-20260901h/articulated-fridge-scene-receipt.json"),
            "execution": artifact(run_parent / "hssd-r2-action-fridge-dev-r1-20260901h/articulated-fridge-execution.json"),
        },
    },
    "toolchain": {
        "unreal_editor_cmd": artifact("/mnt/NAS2/yhliu/UE_5.7.3_prebuilt/Engine/Binaries/Linux/UnrealEditor-Cmd"),
        "bwrap": artifact("/usr/bin/bwrap"),
    },
})
path = Path(os.environ["R20_BINDINGS"])
path.write_bytes(r20.canonical_json(binding))
path.chmod(0o600)
print(path)
print(r20.sha256_file(path).sha256)
PY
```

## 2. Zero-write preflight

Use the printed SHA as `BINDINGS_SHA`. A successful preflight creates no
attempt directory.

```bash
export BINDINGS_SHA=REPLACE_WITH_PRINTED_SHA256
PYTHONPATH=. uv run python tools/ue/vista_playable_home/run_live_scene_upgrade_r20.py \
  --attempt-name live-scene-upgrade-r20-candidate-a \
  --bindings "$R20_BINDINGS" \
  --bindings-sha256 "$BINDINGS_SHA"
```

## 3. Execute after explicit runtime ownership is assigned

This is the only state-changing step. It creates one fresh attempt and runs
NullRHI author/cold verification; it does not start or switch Sunshine.

```bash
ACK='I authorize one external append-only private research R20 candidate; R6 and live services remain untouched, external UAssets stay out of Git, and no visual, runtime, dataset, AI/VLM, or production acceptance is claimed.'
PYTHONPATH=. uv run python tools/ue/vista_playable_home/run_live_scene_upgrade_r20.py \
  --attempt-name live-scene-upgrade-r20-candidate-a \
  --bindings "$R20_BINDINGS" \
  --bindings-sha256 "$BINDINGS_SHA" \
  --execute \
  --acknowledgement "$ACK"
```

Promotion or live launch is not authorized by this receipt. The coordinator
must separately build/launch on the assigned GPU, inspect logs, and obtain a
human Sunshine interaction test before making any playable or quality claim.
