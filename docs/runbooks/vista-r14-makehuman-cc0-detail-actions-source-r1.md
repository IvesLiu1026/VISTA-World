# VISTA R14 MakeHuman CC0 detail-action source slice

This is a fresh, animation-source-only lane for three right-hand interactions:

- `fridge_open_right`
- `fridge_close_right`
- `object_inspect_right`

Every clip is authored from project-owned numeric keyframes at 30 fps on the
existing 53-bone MakeHuman CC0 rig. Root motion is forbidden. The fridge clips
carry typed handle-contact and completion signals; inspect carries an explicit
completion signal. Each recipe includes separate anticipation, engagement,
follow-through, completion, and recovery poses.

The source namespace is `vista.makehuman-cc0-detail-actions/r14`; planned UE
content is isolated under `/Game/VISTA/MakeHumanCC0/R14/DetailActions`. No R8
motion artifact is copied or modified, and pickup/place clips are not used as
stand-ins. Character and motion provenance remain `CC0-1.0`; generated Blend
and FBX files must remain outside Git.

## Safe validation

The default planner is read-only and does not launch Blender:

```bash
cd /home/yhliu/VISTA-World-worktrees/vista-playable-actions-r2
PYTHONPATH=. uv run python -m \
  tools.animation.vista_playable_home_cc0_detail_actions_r14.plan \
  > /tmp/vista-r14-detail-actions-dry-run.json

PYTHONPATH=. uv run pytest -q \
  tools/tests/test_vista_playable_home_makehuman_cc0_detail_actions_r14.py
```

Expected result: one sealed `dry_run` plan, three distinct numeric recipe
digests, and all focused tests passing.

## Candidate generation (not performed by this change)

Generation is a separate, explicitly approved state-changing step. Choose a
fresh append-only destination outside Git, write an `execute` plan while the
destination does not exist, then invoke pinned Blender 4.5.8 on the sealed CC0
source Blend:

```bash
DEST=/data/vista-published/vista-action-world-r1/makehuman-cc0-detail-actions-r14-candidate-YYYYMMDDa
PLAN=/tmp/vista-r14-detail-actions-execute.json
test ! -e "$DEST"

PYTHONPATH=. uv run python -m \
  tools.animation.vista_playable_home_cc0_detail_actions_r14.plan \
  --mode execute --destination-root "$DEST" > "$PLAN"

mkdir -p "$DEST/artifacts" "$DEST/evidence"
/data/vista-authorities/blender-4.5.8-r1/distribution/blender \
  --background --disable-autoexec \
  /data/sysx/vista-world/runs/vista-action-world-r1/makehuman-cc0-smoke-r6/vista_cc0_hero.blend \
  --python-exit-code 1 \
  --python tools/blender/vista_playable_home_makehuman_cc0_detail_actions_r14/blender_worker.py \
  -- --plan "$PLAN" --artifacts-root "$DEST/artifacts" \
  --receipt "$DEST/evidence/worker-receipt.json"
```

The worker writes one animation library Blend, three armature-only FBXs, and a
fail-closed receipt after exact 53-bone/root-static FBX round-trip checks.

## Remaining gates

Blender pose markers and action metadata preserve the typed-notify authority,
but this slice does not create Unreal `AnimSequence`, `AnimMontage`, or UE
notifies. UE import, montage notify materialization, hand/handle IK alignment,
runtime event binding, collision/door synchronization, visual review, and human
motion acceptance all remain explicitly false until separately implemented and
observed.
