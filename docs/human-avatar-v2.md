# Human avatar v2 and anatomical motion fixes

The six-room human is replaced by Microsoft Rocketbox `Male_Adult_10` (MIT,
commit `0943055`), fitted to the unchanged 53-joint VISTA rig. The controller
computes every pose for the existing bind (`EmbodiedR1` reference skeleton and
pose library), so the bind must not change; the new mesh is fitted to it.

## Building the mesh

`tools/blender/vista_companion/build_rocketbox_human.py`:

1. Opens the accepted human blend only for its armature (bind recorded and
   asserted unchanged at the end).
2. Imports the Rocketbox facial FBX, normalises transforms, and poses its Biped
   skeleton onto the VISTA joints. Limb joints (shoulder, elbow, wrist, finger,
   hip, knee, ankle, ball) land exactly on the VISTA pivots: each bone rotates by
   a two-vector frame fit and scales along whichever local axis follows the limb
   (Biped bones run along local X, not Y). Pelvis, spine, neck and head use one
   affine torso fit so the torso keeps natural proportions; the neck keeps its
   natural length and the head only translates and scales.
3. Bakes the fitted basis and all 67 blendshapes (15 visemes, 52 ARKit) through
   the same deformation, and transfers the artist weights by bone
   correspondence (facial and eye bones fold into `head`; four influences).
4. Replaces the low-resolution Rocketbox hand skin (about 420 vertices per
   hand, classified by texture colour so jacket cuffs remain) with the native
   high-resolution hands (about 6.8k vertices each, already bound to the rig
   and calibrated for fingertip contacts), cut inside the cuff and tinted from
   the mean face/hand texture colours.
5. Exports `human.glb` (with blendshapes) and `owner.glb` (no head, hair or
   lashes for first person), front/side/walk renders and a hashed manifest.

`tools/ue/vista_companion/import_avatar_v2.py` imports the textures (normal
maps as BC5, specular as masks), builds four materials (subsurface skin for
face and hands, masked two-sided hair and lashes), imports both meshes, asserts
the bone order, maps the seven face channels to ARKit blendshapes (`JawOpen`,
`EyeBlink*`, `MouthFunnel/Pucker`, `MouthStretch*`, `MouthClose`, `BrowInnerUp`
and `BrowOuterUp*`, `MouthSmile*`) and writes `appearance.json` and
`VistaHumanAppearance.json` in the independent project only.

## Motion fixes (EmbodiedBodyAnimation.cpp)

- **Hinge-consistent arm IK (`SolveArm`).** Swing-only IK kept the upper arm's
  roll from the base pose, so a changed elbow plane bent the forearm sideways
  and twisted the skin. The upper arm now rolls so the elbow flexes in its
  anatomical plane; the forearm takes up to 88 degrees of the pronation the
  hand needs (75% share); the wrist keeps the remainder. Joint positions and
  the hand transform are identical to the previous solver.
- **Elbow swivel search.** Seven candidate elbow planes around the anatomical
  guide are scored for wrist bend beyond 40 degrees, elbow inside a 17 cm torso
  cylinder, and distance from the guide; the existing 150 deg/s swivel rate
  limit still applies.
- **Distributed forward bend.** A reach lean is a hip hinge (32% while foot IK
  re-solves the legs) plus spinal curve (45/32/23% over spine_01..03), not a
  single lumbar fold.
- **Heel raise.** Deep crouches lift the heel around the ball instead of
  folding the ankle past 62 degrees between shin and foot.
- **Seated legs and recline.** Seated feet go under the knees from the leg
  lengths and seat height (the standing stance had straightened the legs into
  a slide off the seat front); the torso reclines about 7 degrees.
- **Pose rate limit.** Per-bone local rotation is limited to 720 deg/s (1500 for
  fingers) and translation to 300 cm/s, except after teleports, so cancelled or
  rolled-back actions blend instead of popping.
- Relaxed idle fingers curl a little more (0.30 instead of 0.16).
- **Phone call (`HomeActionTransactions.cpp`).** The pickup pinch holds the
  handset across its width with the palm over one face, so the old upright
  handset at a fixed actor offset put the palm between phone and cheek, the
  wrist in front of the face and the elbow straight out at shoulder height.
  When a call starts, `SolvePhoneCall` searches handset poses for the grip
  actually held: speaker on the outer ear (`phone_speaker_cm`, measured on the
  Rocketbox head in its bind frame), palm outside, wrist and knuckles clear of
  the jaw, elbow flexion under 150 degrees, and an elbow in front of the chest
  with the wrist bend within 45 degrees (`PhoneArmCost`). The pose is kept in
  the head frame. A per-tick elbow hint (`ArmElbowHint`) follows the handset
  along its whole path, and the lift arcs in front of the chin; the straight
  chord had passed 10 cm from the shoulder (elbow 155 degrees).

## Review tooling

- `HomeReviewShot yaw distance height elevation`, `HomeReviewFocus bone` and
  `HomeReviewShotOff`: private-review-only spectator camera. Actions read the
  ego sensor and control rotation, so it cannot change any outcome. It stops
  only at static geometry (a held phone used to pull it onto the prop).
- The private motion trace records all 53 finalized bones.
- `tools/runtime/vista_character_motion/joint_sanity.py` flags hinge joints
  bending the wrong way or sideways, wrist/forearm/neck/spine excess, limbs
  inside the torso, finger hyperextension/overflexion, segment stretch and
  rotation pops, per action window.
