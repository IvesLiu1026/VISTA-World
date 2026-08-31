# MakeHuman CC0 action overlay: isolated development demo R1

## Outcome and boundary

This runbook is the shortest current path from the fresh, root-published R8
Blender animation files to a **private, human-operated Unreal development
demo**. It is deliberately a separate lane from accepted VISTA research
evidence.

The runner is:

```text
tools/ue/vista_playable_home/run_makehuman_cc0_animation_dev_demo.py
```

It has two append-only stages:

1. copy the known R3 MakeHuman CC0 character project, install the current R6
   compiled plugin, and use UE 5.7 `UnrealEditor-Cmd -nullrhi` to import five
   R8 FBXs and author nine runtime packages; then
2. copy the inactive HSSD/City Sample `h` project to a fresh attempt and
   overlay the exact R3 character, R8 animation packages, and R6 plugin.

The tool never launches the interactive renderer, Sunshine, a GPU process, or
a service. Both outputs say `accepted:false`, `development-only`,
`unaccepted`, and `nonpromotable`. They are not VISTA dataset/database input,
AI/VLM training, testing, evaluation, or review input, or production
authority. HSSD, City Sample, and all generated UAssets remain outside Git and
within the already approved private, noncommercial, human-operated UE demo
scope.

Current implementation status on 2026-09-01:

- real pinned-input `plan-import` passed with zero writes;
- the five fresh R8 FBXs, 23 R3 packages, 241-file R6 plugin, UE commandlet,
  bubblewrap, and receipts matched their fixed seals;
- the inactive `h` receipt, project/map bindings, legal boundary, and declared
  9.15 GB project tree matched;
- focused source tests passed; and
- no UE, GPU, current live process, service, or output attempt was run or
  changed by that validation.

## Exact development asset closure

The import creates only:

- five `AnimSequence` packages: idle, walk, run, countertop mug pickup, and
  countertop mug place;
- one locomotion `BlendSpace1D` at 0/350/600 cm/s;
- one MakeHuman R8 `AnimBlueprint`; and
- two `AnimMontage` packages for pickup and place.

Pickup emits `vista_pickup_contact` at frame 34 and
`vista_pickup_completed` at frame 59. Place emits `vista_drop_release` at
frame 34 and `vista_drop_completed` at frame 59. The importer cannot create a
new skeleton, skeletal mesh, physics asset, static mesh, material, texture, or
arbitrary caller-selected asset.

This is not an open/close-fridge or inspect animation library. Those are a
separate next slice and must not be inferred from this overlay.

## Inputs fixed by the runner

| Input | Fixed development source |
| --- | --- |
| Fresh R8 publication | `/data/vista-published/vista-action-world-r1/makehuman-cc0-animation-r8-20260830a` |
| R3 character project | `/data/sysx/vista-world/runs/vista-action-world-r1/makehuman-cc0-ue-import-r3-20260829/project` |
| R6 compiled plugin | `/data/sysx/vista-world/runs/vista-action-world-r1/hssd-r2-citysample-live-r6-human-fit-20260831a/project/Plugins/VistaPlayableHome` |
| Inactive visual base | `/data/sysx/vista-world/runs/vista-action-world-r1/hssd-r2-citysample-live-r5-20260830h/project` |
| UE 5.7 engine | `/mnt/NAS2/yhliu/UE_5.7.3_prebuilt` |
| Append-only output parent | `/data/sysx/vista-world/runs/vista-action-world-r1` |

There are no CLI flags for replacing those authorities. An attempt name must
be one fresh direct child matching the fixed development prefix.

## Stage 1: CPU-only R8 import

Run from this worktree:

```bash
cd /home/yhliu/VISTA-World-worktrees/vista-playable-actions-r2
```

Repeat the zero-write plan immediately before execution:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. uv run python -m \
  tools.ue.vista_playable_home.run_makehuman_cc0_animation_dev_demo \
  plan-import \
  --attempt-name makehuman-cc0-animation-ue57-dev-r1-20260901a
```

The plan must report `mode: dry_run_zero_writes`,
`status: ready_for_development_import`, `writes_performed: false`, and all
development claims unchanged. It must not create the named attempt.

The exact future execution command is:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. uv run python -m \
  tools.ue.vista_playable_home.run_makehuman_cc0_animation_dev_demo \
  execute-import \
  --attempt-name makehuman-cc0-animation-ue57-dev-r1-20260901a \
  --acknowledgement \
  'I acknowledge this CPU-only UE animation import is development-only, unaccepted, nonpromotable, and cannot be used as VISTA research evidence.'
```

This creates one fresh output and runs only `UnrealEditor-Cmd -nullrhi` inside
an offline bubblewrap namespace. It does not reserve or touch a GPU. A failure
leaves its partial attempt in place for diagnosis; never reuse or delete that
name. Choose a new suffix for a retry.

Success requires:

```text
dev-animation-import-host-manifest.json
status = dev_animation_import_complete_unaccepted_nonpromotable
accepted = false
package_inventory = exactly 9 sealed UAssets
```

## Stage 2: copy-only playable overlay

Only after stage 1 succeeds, run the overlay plan:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. uv run python -m \
  tools.ue.vista_playable_home.run_makehuman_cc0_animation_dev_demo \
  plan-overlay \
  --attempt-name hssd-r2-makehuman-action-dev-r1-20260901a \
  --import-attempt-name makehuman-cc0-animation-ue57-dev-r1-20260901a
```

The exact future copy command is:

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. uv run python -m \
  tools.ue.vista_playable_home.run_makehuman_cc0_animation_dev_demo \
  execute-overlay \
  --attempt-name hssd-r2-makehuman-action-dev-r1-20260901a \
  --import-attempt-name makehuman-cc0-animation-ue57-dev-r1-20260901a \
  --acknowledgement \
  'I acknowledge this private human-operated scene overlay is development-only, unaccepted, nonpromotable, and keeps all external assets outside Git.'
```

This is a roughly 9.2 GB append-only project copy. It omits the base's old
plugin while copying, installs the pinned R6 plugin without deleting source
bytes, and adds the copied MakeHuman namespace; it does not mutate the inactive
base or current live project. It validates all 23 R3 and nine R8 package seals
and the exact 32-file MakeHuman namespace before sealing the result:

```text
dev-action-overlay-host-manifest.json
status = dev_action_overlay_complete_unaccepted_nonpromotable
accepted = false
interactive_renderer_launched = false
gpu_used = false
service_changed = false
```

That manifest contains a pinned `suggested_interactive_launch_argv`. It wraps
UE with the existing nonblocking display/GPU lock and a private network
namespace, selects `DISPLAY=:118`, GPU 0, the MakeHuman R8 provider, and the
human-operated visual-demo boundary. A runtime owner must inspect it,
checkpoint any current live demo, confirm GPU ownership, and only then launch
it separately. This runner will not stop, restart, or replace the existing
Sunshine or UE services.

After that coordination, the exact recorded array can be launched without
shell re-parsing its arguments:

```bash
MANIFEST=/data/sysx/vista-world/runs/vista-action-world-r1/\
hssd-r2-makehuman-action-dev-r1-20260901a/\
dev-action-overlay-host-manifest.json
LOCK_DIR=/tmp/vista-human-visual-demo-locks-$(id -u)
install -d -m 0700 "$LOCK_DIR"
mapfile -d '' -t VISTA_LAUNCH < <(
  jq -j '.suggested_interactive_launch_argv[] | . + "\u0000"' "$MANIFEST"
)
DISPLAY=:118 "${VISTA_LAUNCH[@]}"
```

Exit code `75` means another owner still holds display `:118` / GPU 0; do not
bypass the lock. Sunshine remains a separate existing service.

## What is required now versus research ceremony

For this isolated human-only development demo, the necessary gates are:

- the fixed R8/R3/R6/base/engine/tool pins still match;
- both output names are fresh;
- the exact acknowledgement is supplied for each write stage;
- the append-only parent remains writable and has at least about 10 GB free;
- stage 1's nine-package manifest completes before stage 2; and
- a runtime coordinator owns the GPU before any later interactive launch.

The current host has a writable run parent, ample disk space, an executable UE
commandlet, and unprivileged user namespaces enabled. No root or systemd
change is known to be necessary for the two stages. The first real UE run can
still expose an engine/import defect; that is why its output stays a disposable
development attempt.

The following remain mandatory before any **accepted research** or promotable
claim, but they can wait for this isolated development demo:

- the independent root-owned executor policy, bundle, full immutable engine,
  BuildPlugin, interpreter, and publication ceremony described in
  `docs/runbooks/vista-r8-ue-animation-runtime-r1.md`;
- dedicated-server/two-client runtime evidence;
- human motion-quality review;
- interaction, photoreal-character, and GTA-quality acceptance; and
- a separate approved promotion decision.

The development manifest cannot be relabeled or promoted in place. A later
accepted lane must rerun from independently reviewed immutable authorities.

## Verification

```bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=. uv run --with pytest \
  python -m pytest -q \
  tools/tests/test_vista_playable_home_makehuman_cc0_animation_dev_demo.py

PYTHONDONTWRITEBYTECODE=1 uv run ruff check \
  tools/ue/vista_playable_home/run_makehuman_cc0_animation_dev_demo.py \
  tools/tests/test_vista_playable_home_makehuman_cc0_animation_dev_demo.py

git diff --check -- \
  tools/ue/vista_playable_home/run_makehuman_cc0_animation_dev_demo.py \
  tools/tests/test_vista_playable_home_makehuman_cc0_animation_dev_demo.py \
  docs/runbooks/vista-makehuman-cc0-action-dev-demo-r1.md
```
