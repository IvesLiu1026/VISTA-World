# Shoulder calibration and Korean 3:7 hair

The measured CMU walk permanently raised the fitted avatar's shoulders by
6.73 cm (left) and 7.40 cm (right), measured relative to the thorax. Retargeting
had aimed the target clavicle along the source Shoulder-to-Arm offset. That
offset describes a different subject's shoulder girdle and is not the arm's
T-pose/A-pose correction. Idle did not contain the offset.

`build_walk_cycle.py`, `retarget_mocap.py` and the Epic directional
`build_motion.py` now calibrate limb directions without recalibrating the
clavicle toward that source offset. The retained local clips can be repaired
without reacquiring source mocap: `shoulder.repair_gait` aligns the mean local
girdle orientation to the fitted rig's rest, retains frame-to-frame residuals,
and reconstructs descendant positions while retaining their measured global
rotations. Local translations and bone lengths stay fixed. For directional
clips this deliberately removes the clip's mean shoulder posture, including
any real postural bias; it is a locomotion correction, not a universal retargeter.
Jump, fall and landing are retained verbatim by `repair_directional.py`.

## Anatomy and actual scope

The shoulder connects the thorax, clavicle, scapula and humerus through coupled
SC, AC and GH motion. Arm elevation involves upward rotation and other rotations
of the shoulder girdle; permanently freezing it would also produce poor reach.
See [Teece et al., 2008](https://pmc.ncbi.nlm.nih.gov/articles/PMC2759875/) and
[Crosbie et al., 2008](https://pubmed.ncbi.nlm.nih.gov/17981379/). These are the
anatomical rationale, not a source of hard universal joint limits or fitted
parameters for this specific avatar.

The **53 deform joints and their bind matrices remain unchanged**. The current
clavicle joint approximates the girdle; this revision does not add a separately
skinned scapula, twist bones, muscles, or a full biomechanical human. The
`raised_arm` authoring control allows progressively more shoulder elevation
during a high reach, independently of humeral elevation. Its curves are artistic
settings, not population measurements. Keep task/hand IK separate from this pose
probe. This is useful animation authoring, not a physically balanced humanoid
policy or evidence of autonomous grasping.

`hair.py` replaces the straight fringe and scalp with a deterministic mesh groom:
an off-center part, broad swept fringe, fitted crown and short sides. All hair
vertices are weighted to the actual head. It is 3D geometry, not a generated
portrait pasted onto the model. Existing face morphs, glasses, outfit and
first-person head exclusion are retained. Close-up strand/clump quality remains
an authored approximation, not a scanned groom.

## Reproduce

From a workspace worktree, use fresh output paths:

```sh
../../bin/blender --background --threads 12 --python-exit-code 1 \
  --python tools/blender/vista_avatar_anatomy/build.py -- \
  --source ../../runs/six-room-companion-face-b/companion.blend \
  --motion ../../projects/six-rooms-agent-r1/payload/Content/VISTA/VillaR1/mocap.json \
  --out ../../runs/avatar-anatomy-build-NEXT
```

Run `repair_directional.py --source NEW/character.blend --motion
PROJECT/Content/VISTA/AlpineR3/locomotion.json --out NEW_DIRECTIONAL`, then
`validate.py --source ORIGINAL_MOCAP --candidate NEW --directional NEW_DIRECTIONAL
--out NEW_VALIDATION`. `audit.py` measures and optionally renders an input without
changing it. `validate.py` rejects the original shrug as a negative control,
checks the actual head deformation, and saves `authoring-rig.blend` with editable
corrected walk / left reach / right reach actions. The walk retains its original
1.10-second timing; reach examples run two seconds. Runtime GLBs are exported
without these review actions and use the accompanying JSON motion libraries.

Import into a **fresh** `six-room-companion-dev-anatomy-*` project using
`tools/ue/vista_companion/import_anatomy.py` with `VISTA_ANATOMY_SOURCE`,
`VISTA_ANATOMY_DIRECTIONAL`, and `VISTA_ANATOMY_IMPORT_OUT`. It checks source hashes,
native joint order and all seven face morph groups before binding the new
world/owner meshes, companion, and both motion libraries. It retains the project
scene/task configuration. No frozen project or live selection is edited.

For native input use `private_runtime.py --motion-proof`, `review_anatomy.py`,
and `analyze_anatomy.py` in `tools/runtime/vista_companion/`. Pass absolute DDC paths
or let the launcher resolve them. The analysis uses finalized Unreal transforms.
Inspect **observed clips and run blend**, not merely the requested key: the
current indoor Explorer Shift binding did not activate the run controller in
the recorded test. Running clips are covered by asset-level validation only.

Isaac export uses `tools/isaac/export_avatar.py`; `avatar_probe.py --compare-with
ORIGINAL_USD` renders both actual assets. The preview is baked animation, not
Isaac motor control. `make_shoulder_review.py` labels these camera frames and
adds the local synthetic male English narration produced by
`prepare_anatomy_speech.py`. First/last-frame holds are recorded explicitly.

## Evidence on server5090, 2026-09-16

- Source baseline: 28 tests; supervisor regression: 6 tests.
- `runs/avatar-anatomy-validation-b`: 42 passing asset/pose checks. Maximum local
  translation error 0.000000552 m; head-attached hair error 0.000000254 m. These
  small errors establish invariants, not perceptual realism.
- `runs/avatar-anatomy-isaac-a`: 8 native compatibility/shoulder checks pass.
  Minimum vertical neck-to-shoulder gap in this replay is 8.29 cm.
- `runs/avatar-anatomy-native-check-a`: 22 room/input/transaction checks and 41
  finalized-bone checks pass. Forward walking shoulder excursion was -1.76 to
  +1.66 cm about the fitted rest, rather than a fixed 6.7–7.4 cm lift.
- `runs/avatar-anatomy-review-a`: 12.5-second native before/after video with English
  male narration and labels, plus two matching Blender comparison stills.
- Independent project: `projects/six-room-companion-dev-anatomy-a`. The live
  Moonlight Six Rooms AI project was not replaced. No GPU 1 or service changes.

The native pickup/drop transaction passed; this is not validation of every
finger, cup silhouette or clothing contact. The test frame still warrants a
separate close review of cup/hand presentation. This task does not establish
universal collision correctness, naturalness of all actions, or GTA-level skin
and cloth quality. Baked walking/reach tests are not paper benchmark outcomes.
