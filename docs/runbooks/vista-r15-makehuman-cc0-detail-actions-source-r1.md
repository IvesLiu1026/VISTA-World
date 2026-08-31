# VISTA R15 MakeHuman CC0 detail-action source authority

R15 adds nine fresh, project-authored numeric motions on the existing 53-bone
MakeHuman CC0 rig:

1. `rotary_turn_on_right` for stove or faucet controls
2. `rotary_turn_off_right` for stove or faucet controls
3. `button_press_right` for a washer start button
4. `cabinet_drawer_open_right`
5. `cabinet_drawer_close_right`
6. `sit_down_chair`
7. `seated_idle_loop`
8. `stand_up_chair`
9. `pour_right`

This lane is a source authority, not a runtime acceptance. Its closed profile,
plans, and worker receipts keep all of these values false:

```json
{
  "accepted": false,
  "runtime_execution_authorized": false,
  "human_reviewed": false
}
```

Every motion has its own numeric recipe and armature-only FBX. No R8 or R14
motion bytes are copied. Root animation channels are prohibited. The seated
idle begins and ends on the same exact numeric pose. Counter, waist, and seat
height bands are explicit, as are `hand_r` or `pelvis` contact bones.

## Runtime-signal boundary

Only the following source clips reference typed signals that already exist in
`UVistaAnimationComponent`:

| Clip | Contact | Completion |
| --- | --- | --- |
| rotary on | `vista_appliance_power_contact` | `vista_appliance_turn_on_completed` |
| rotary off | `vista_appliance_power_contact` | `vista_appliance_turn_off_completed` |
| button press | `vista_appliance_button_contact` | `vista_appliance_press_completed` |

This does not authorize these FBXs for execution; UE import, montage creation,
target alignment, and live observation remain undone.

Cabinet/drawer, sitting, seated idle, standing, and pouring are marked
`source_only_unimplemented`. Their `vista_cabinet_*`, `vista_chair_*`,
`vista_sit_*`, `vista_seated_idle_*`, `vista_stand_*`, and `vista_pour_*`
signals are R15 source-contract names only. They do not claim a C++ backend.

## Read-only validation

```bash
cd /home/yhliu/VISTA-World-worktrees/vista-detail-actions-r15-r1

PYTHONPATH=. uv run python -m \
  tools.animation.vista_playable_home_cc0_detail_actions_r15.plan \
  > /tmp/vista-r15-detail-actions-dry-run.json

PYTHONPATH=. uv run pytest -q \
  tools/tests/test_vista_playable_home_makehuman_cc0_detail_actions_r15.py

uv run ruff check \
  tools/animation/vista_playable_home_cc0_detail_actions_r15 \
  tools/blender/vista_playable_home_makehuman_cc0_detail_actions_r15 \
  tools/tests/test_vista_playable_home_makehuman_cc0_detail_actions_r15.py
```

The focused suite includes negative gates for acceptance escalation, false
runtime-backend claims, contact-bone drift, root motion, broken loop seams,
R8/R14 recipe reuse, duplicate JSON keys, and non-finite numbers.

The final worker was also exercised with a self-digested plan that changed the
typed rotary clip to a source-only backend. Blender exited with code 1 before
writing a receipt: `WorkerError: runtime/source-only binding differs`.

## Reproducible headless generation

Use a new destination for every attempt. Never reuse a partial or failed root.
Generated Blend, FBX, PNG, logs, plans, and receipts stay outside Git.

```bash
DEST=/data/sysx/vista-world/runs/vista-action-world-r1/\
makehuman-cc0-detail-actions-r15-source-r1-YYYYMMDDa
PLAN=/tmp/vista-r15-detail-actions-execute-YYYYMMDDa.json
SOURCE=/data/sysx/vista-world/runs/vista-action-world-r1/\
makehuman-cc0-smoke-r6/vista_cc0_hero.blend
BLENDER=/data/vista-authorities/blender-4.5.8-r1/distribution/blender

test ! -e "$DEST"
test ! -e "$PLAN"

PYTHONPATH=. uv run python -m \
  tools.animation.vista_playable_home_cc0_detail_actions_r15.plan \
  --mode execute --destination-root "$DEST" > "$PLAN"

mkdir -m 700 "$DEST" "$DEST/artifacts" "$DEST/evidence" "$DEST/runtime"
mkdir -m 700 \
  "$DEST/runtime/home" "$DEST/runtime/config" \
  "$DEST/runtime/cache" "$DEST/runtime/tmp"
install -m 600 "$PLAN" "$DEST/evidence/execution-plan.json"

env \
  HOME="$DEST/runtime/home" \
  XDG_CONFIG_HOME="$DEST/runtime/config" \
  XDG_CACHE_HOME="$DEST/runtime/cache" \
  TMPDIR="$DEST/runtime/tmp" \
  CUDA_VISIBLE_DEVICES="" \
  HIP_VISIBLE_DEVICES="" \
  "$BLENDER" --background --disable-autoexec "$SOURCE" \
  --python-exit-code 1 \
  --python \
    tools/blender/vista_playable_home_makehuman_cc0_detail_actions_r15/blender_worker.py \
  -- \
  --plan "$PLAN" \
  --artifacts-root "$DEST/artifacts" \
  --receipt "$DEST/evidence/worker-receipt.json" \
  > "$DEST/evidence/blender-worker.log" 2>&1
```

The worker writes one animation-library Blend, nine armature-only FBXs, and a
900×900 CPU skeletal contact sheet. It then imports every FBX into a factory
scene and verifies exact bone order, frame range, static root, and distinct
semantic pose bytes.

## Verified attempt `20260901b`

Attempt `20260901a` remains unchanged as append-only development evidence.
Attempt `20260901b` is the final source milestone below; it additionally pins
the exact standalone worker source and validates every profile/plan clip
against the worker's closed target, timing, signal, and backend partition.

Artifact root:

```text
/data/sysx/vista-world/runs/vista-action-world-r1/
makehuman-cc0-detail-actions-r15-source-r1-20260901b
```

Authority records:

| Record | SHA-256 |
| --- | --- |
| source Blend, unchanged | `c502ae47ab07d4622bb716f01febfa8df76b2f714260c331dc4eed8e08f1d222` |
| worker source | `8c0be2363f98e9cf1af5f3d7f277a7498fbacc7960f4de15772ddec29d7f66ad` |
| profile content digest | `fb88d2cdfe810226d84b9111cbe99ad7c13842cab0e60c4af48354fe5bc02384` |
| execution plan file | `330ccce36dc491035ed8c8e45ee1af9e3c1e699bc6ea32b7d3fe1a07df2f1e74` |
| execution plan content digest | `424830fc53f6d5a7f01dc1e26a371a7fa147e016174b45c0b25df1b72fcd2ea9` |
| worker receipt file | `6e0eee885f50c9eb8d62de544ec6e4c021c19f5ff84dbc3e43794787ff4b0189` |
| worker receipt content digest | `107a32156ac12422e0899dfac4503518adac1b9a8ce78dde8d79e96ac39847a8` |
| generated Blend | `e5ae72e24a26e3547a77067772ac0c5b50d6a5f2bf24eefc0783c16d96bf0fca` |
| contact sheet | `daf3490bcd758af4d221468bab11a47082591485889ca886aad41467646455d7` |

FBX records:

| Clip | SHA-256 |
| --- | --- |
| button press | `0fc5159249390dca41fd5dc2e9b68cc1aff973230c718a56a4d9869cee5282ee` |
| cabinet/drawer close | `06c7649d3566b63f8052a68f1d60cc11527663987d52e663a764eddc5db45cd2` |
| cabinet/drawer open | `608dfe910c77e370f0caefd36031573bdefb467a346970bdd6f6300867b9eaa0` |
| pour | `ca091c3a4f431beee3bfdf1bb1a31962057a01ea8a23cd1b65be951344a6b1bc` |
| rotary off | `c4d03dfd2509c9061e618c32f9939a850b6a95479b3d11e1c2bf7cca0236c9a1` |
| rotary on | `6561cc420e247a0f77086c083e31ff190766c23df22274a188e27bd337a5aac3` |
| seated idle | `642da601b53f7764a6adf86c0d4d0b37aeaad4ba8a8c8c43cd49062a2ab47eb5` |
| sit down | `6c31b7b5d365e1e46de23a30f40299b1a86d33f4c37b47ba082958d17e4f0511` |
| stand up | `09720198eb77c0a292ab9946eca9ed7580b33525d379195e8747bca1aa5e97ec` |

The contact sheet has 37,747 foreground pixels and is useful for checking pose
separation and contact markers without a GPU. It is schematic evidence, not a
human-motion-quality render.

The numeric recipe digests, round-trip semantic pose digests, and contact-sheet
bytes were identical between the append-only `20260901a` and `20260901b`
attempts. Blender FBX and Blend container hashes changed with the fresh output
root/export metadata, so this lane claims deterministic motion semantics—not
cross-path byte-identical Blender containers.

## Remaining gates

- import into a fresh R15 UE namespace;
- create AnimSequences, montages, and UE notifies;
- build target-aware Motion Warping or Control Rig IK for the three height bands;
- implement stateful cabinet/drawer, chair posture, and pouring backends;
- synchronize hand contact with object state transactions and rollback;
- run isolated UE runtime tests and Sunshine human review;
- correct any foot sliding, penetration, hand offset, or weight-transfer issues;
- only then consider changing any acceptance field.

Until those gates pass, this authority is reproducible source material—not a
playable or GTA-quality runtime claim.
