# VISTA R23 pickup/place demo checkpoint (2026-09-01)

## Purpose

This checkpoint preserves the exact external animation authority and live
runtime configuration selected for the short human-operated pickup/place demo.
It is a recovery record, not a claim that the complete interaction has passed
visual acceptance.

The Unreal project and all third-party UAssets remain outside Git. The tracked
source tip before this checkpoint is `d45ab0e2` on
`codex/vista-playable-actions-r2`.

## Frozen animation authority

- Fresh append-only authority:
  `/data/sysx/vista-world/runs/vista-action-world-r1/manny-detail-actions-retarget-r18-ue57-r1-20260901h`
- Host receipt:
  `manny-r18-retarget-host-receipt.json`
- Receipt status:
  `manny_r18_detail_actions_retargeted_cold_verified_external_only`
- Package inventory: exactly 31 UAssets
- Source assets remained byte-identical through author and cold verification.
- Pickup montage:
  `/Game/VISTA/Manny/R18/DetailActions/Montages/AM_VistaMannyMugPickupCountertop_R18`
- Place montage:
  `/Game/VISTA/Manny/R18/DetailActions/Montages/AM_VistaMannyMugPlaceCountertop_R18`
- Pickup montage SHA-256:
  `42865f29e743e18969be1c91f966da8cb9c08839fa1ef22998d89967828fbca8`
- Place montage SHA-256:
  `8006844d58884467fb2cdf5c45fe365a33a30384f304ad5d0f8e96dcbd88a9cf`
- Pickup contact notify: frame 34 (approximately 1.133 seconds)
- Pickup completion notify: frame 59 (approximately 1.967 seconds)
- Place release notify: frame 34 (approximately 1.133 seconds)
- Place completion notify: frame 59 (approximately 1.967 seconds)

The prior live R18 asset set was traced to the quarantined failed attempt
`manny-detail-actions-retarget-r18-ue57-r1-20260901d`. Its montage-slot closure
did not match the authored contract. It must not be restored as animation
authority. A recovery-only copy is retained at:

`/data/sysx/tmp/vista-playable-actions-r2/r23-r18-quarantined-d-backup-20260901t1300`

## Live demo snapshot

At checkpoint time these user services were active:

- `vista-action-demo-xvfb-r21.service` on X11 display `:119`
- `vista-playable-actions-fast-candidate-r23.service` on GPU 0
- `vista-sunshine.service`
- `vista-sunshine-x11-input-relay.service`

Live project:

`/data/sysx/vista-world/runs/vista-action-world-r1/vista-playable-actions-fast-candidate-20260901b/project`

Sunshine remains available through the Tailnet at:

`https://100.114.80.121:47990`

The runtime uses the `realistic_interior_r2` camera profile and the
`citysample_crowd_visual_demo_v1` human-operated visual provider. It is a
private visual demo only; the City Sample/MetaHuman material is not dataset,
AI/VLM training, evaluation, or review authority.

Checkpoint frame:

`/data/sysx/tmp/vista-playable-actions-r2/r23-demo-checkpoint-20260901.png`

Frame SHA-256:

`3d6fd46816b08703ab9a44aa8ecdb16033e3617e633a7802eaa90cdb914f7541`

Do not restart the four services immediately before the demo. The UE service is
a transient user unit; this document plus the append-only authority is the
recovery checkpoint if it is stopped later.

## Short demo controls

- Use third person for visible full-body actions; press `V` to toggle view.
- Move with `WASD`; look with the mouse.
- Face the pot until the HUD presents `[F] Pick Up Pot`.
- Press `F` once, then remain still for about 2.5 seconds.
- Move to a valid counter, stove, or table placement anchor.
- Cycle with `R` only if Place is not already selected.
- When the HUD presents `[F] Place Pot`, press `F` once and remain still for
  about 2.5 seconds.
- `Q` is animated Drop, not anchored Place; do not use it for this short path.

## Acceptance boundary at checkpoint

Cold authoring and package verification passed for the fresh R18 asset set, and
the replacement runtime reached the playable map with the City Sample visual
provider active. A new end-to-end live pickup, held-object, and anchored-place
recording had not yet completed at the instant this checkpoint was written.
Do not present the external host receipt alone as proof of smooth hand contact,
successful physical attachment, or successful placement.

## Why this motion work is difficult

The visible person and the animation authority are separate systems: the
photoreal City Sample body is driven from a hidden Manny-compatible animation
source. Every action therefore has to keep skeleton identity, retarget chains,
montage slots, frame timing, body scale, and visual contact aligned.

Pickup and place are also transactions, not video clips. At the contact/release
notify the runtime must atomically change collision and physics, attach or
detach the object, preserve the correct transform, update inventory and anchor
state, and still be able to roll everything back if any gate fails. A visually
plausible animation can therefore fail because one attachment/socket/transform
invariant is wrong; conversely, a logically successful transaction can still
look bad because the hand misses the object or the body intersects furniture.

The immediate failure took longer to isolate because the HUD reported the
secondary rollback failure (`ACTION_ROLLBACK_FAILED`) instead of preserving the
original initiating error. We then found that the running project had copied a
quarantined R18 authoring attempt whose montage-slot closure was known to be
invalid. The fresh append-only authority had completed separately, so the safe
fix was to replace only that exact 31-package namespace and restart the isolated
UE runtime while leaving Sunshine and input capture intact.

For general VISTA motion coverage, one fixed clip is insufficient. Different
character proportions, approach angles, counter heights, object sizes, hand
choices, furniture collisions, camera modes, and interruptions need either
motion warping plus hand/foot IK or a family of authored variants. The semantic
VISTA event must also remain synchronized with the physical state change and be
deterministic enough to replay and evaluate. Those are the main gaps between a
single demo animation and a robust GTA-like interaction system.
