# R18 Manny detail-action retarget authority

## Outcome

This lane converts fourteen sealed, project-authored CC0 R8/R14/R15 interaction
actions to the exact UE 5.7 Manny skeleton used as the hidden animation source
for the private City Sample human-operated visual demo.

The source milestone is complete. The production dry-run validates the pinned
R8, R14, and R15 receipts, all 28 source animation packages, the exact CC0 and Manny
mesh/skeleton packages, the 19-chain mapping, UnrealEditor-Cmd, and bubblewrap.
It performs no writes. UE execution and human motion review have not been run,
so no generated R18 UAsset or visual-quality acceptance is claimed.

## Closed asset contract

- Source mesh: `/Game/VISTA/MakeHumanCC0/R6/SK_VISTA_CC0_Hero_R6`
- Source skeleton: `/Game/VISTA/MakeHumanCC0/R6/SK_VISTA_CC0_Hero_R6_Skeleton`
- Target mesh: `/Game/Characters/Mannequins/Meshes/SKM_Manny`
- Target skeleton: `/Game/Characters/Mannequins/Meshes/SK_Mannequin`
- Output namespace: `/Game/VISTA/Manny/R18/DetailActions`
- Output inventory: two IK rigs, one IK retargeter, fourteen AnimSequences, and
  fourteen AnimMontages; exactly 31 packages.

The output names replace `VistaCC0` and the source revision suffix with
`VistaManny..._R18`. Original R8/R14/R15 assets are never renamed or overwritten.
The host checks their SHA-256 values before authoring, after authoring, and
after cold verification.

The retarget roots are both `pelvis`. Nineteen exact-name chains cover Root,
Spine, Head, both clavicles, both arms, both legs, and all ten finger chains.
Manny-only corrective branches are not represented as mapped motion.

## Read-only dry-run

From the repository root:

```bash
PYTHONPATH=. uv run python \
  tools/ue/vista_playable_home/run_manny_detail_actions_retarget_r18.py \
  --attempt-name manny-detail-actions-retarget-r18-review
```

Expected terminal fields include:

```text
schema_version: vista.manny-detail-actions-retarget-r18-plan/v1
status: dry_run_validated_zero_write
writes_performed: false
output.asset_count: 31
```

The attempt name must not already exist. Dry-run does not reserve it or create
the directory.

## Approved execution handoff

Execution is intentionally separate from this source milestone. The
coordinator may run it only after choosing a fresh attempt name and retaining
the exact acknowledgement:

```bash
PYTHONPATH=. uv run python \
  tools/ue/vista_playable_home/run_manny_detail_actions_retarget_r18.py \
  --attempt-name manny-detail-actions-retarget-r18-ue57-r1 \
  --execute \
  --acknowledgement \
  'I acknowledge this R18 Manny retarget is private UE-only development output, stays outside Git, and is not accepted human-motion evidence.'
```

The runner creates an append-only external project. It uses the sealed R14
project as a small base, overlays only the four exact R8 pickup/place source
packages, the sealed R15 packages, and pinned Manny content, and then starts two
network-isolated `UnrealEditor-Cmd` processes:

1. `author` creates the exact rigs, retargeter, sequences, and montages.
2. `verify` cold-loads the saved packages in a new editor process.

No UE game, renderer, GPU service, Sunshine service, or production process is
started. A failed attempt remains quarantined for diagnosis and is never
silently reused.

## Verification gates

Each cold-loaded sequence must retain 30 fps, the exact source frame count,
the full Manny target track inventory, disabled root motion with forced
reference-pose lock, and finite non-zero motion on clip-specific probe bones.

Each montage must contain one `DefaultSlot` segment, one iteration, the exact
new Manny sequence reference, and the original typed notify signal at the
exact contract frame. Notify comparisons are sorted by trigger time rather
than relying on API return order.

The host receipt is published only when:

- author and cold-verify inspections are byte-for-byte equal as JSON values;
- the 28 source animation packages and both source/target mesh and skeleton
  packages remain byte-identical;
- Content gained exactly the 31 allowlisted packages;
- no temporary `VISTA_R18_RETARGET_TMP_` asset remains anywhere under `/Game`.

The receipt remains `accepted: false`. It does not establish contact quality,
runtime interaction success, photorealism, GTA-level quality, dataset use, or
AI/VLM use authority.

## Runtime selection

The runtime selects this namespace only when the provider reports the gated
City Sample human-operated visual demo as active, the hidden owner mesh is the
exact Manny mesh and skeleton, and the selected exact R18 montage loads with
that same skeleton. The MakeHuman provider keeps its existing CC0 paths.

The provider performs its full visual/retarget validation once during
activation and records a transient validated bit. Tick-time action enumeration
uses that bit plus cheap live component and exact mesh checks; it does not rerun
the full City Sample validation. Montage preflight checks an already loaded
object before using synchronous load, so the selector does not reload an asset
on every tick. A missing exact package is negatively cached for the lifetime of
the process; after integrating a new external R18 package set, restart the UE
process before review.

A null target may return `ANIMATION_TARGET_PREFLIGHT_DEFERRED` only to a
read-only queue/enumeration preflight. `StartNpcAction` checks the exact target
requirement before consulting that preflight and fails with
`ANIMATION_TARGET_REQUIRED`; the deferred result cannot begin playback or a
mutation transaction.

Pickup uses the retargeted R8 pickup montage. Place and Drop share the exact
retargeted R8 place/release montage because their existing transaction contract
uses the same `vista_drop_release` frame 34 and `vista_drop_completed` frame 59
signals. The MakeHuman provider continues to use the original CC0 montages. A
CC0 montage presented to the City Sample/Manny provider is rejected before
playback.

## Remaining acceptance work

After a successful external execution, integrate only the sealed R18 package
inventory into a fresh City Sample demo project. Then perform human-operated
review of body scale, hand contact timing, refrigerator and cabinet reach,
button/rotary contact, sitting alignment, standing clearance, inspection,
pickup, place/drop release, and pouring. That visual receipt is a separate gate and must not reuse this
source milestone as acceptance evidence.
