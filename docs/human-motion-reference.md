# Reference-based human motion

The six-room native environment mixes a measured CMU forward walk with its
existing directional/run animations. Previously, the CMU library was loaded but
the directional animation path replaced it during normal gameplay. This change
uses the capture in actual final poses, including measured arm swing. It does
not implement Epic Pose Search/Motion Matching or reproduce every GTA action.

## Capture and retarget

Use [CMU Graphics Lab](https://mocap.cs.cmu.edu/) clip 07_01 from the pinned
[BVH conversion mirror](https://github.com/una-dinosauria/cmu-mocap). Provenance,
license and exclusions are in `assets/manifests/human-motion-reference-cmu.json`.
Frame 0 is a synthetic T-pose, and finger motion/ground forces were not captured.
The fitted target retains its 53-joint hierarchy, calibrated neutral shoulders,
segment lengths, facial morphs, skin, hair and clothes.

The Blender builder selects a complete ordered gait cycle. Foot support is
estimated from captured foot/toe height and world foot speed, rather than a fixed
stance clock. The runtime aligns the left-foot rear extrema between animation
sources, then blends the pose, support weights and travelled distance together.
Forward walking uses the capture; it fades toward existing directional and run
clips away from forward/at higher speeds. Floor IK preserves target leg lengths.

Build into a fresh directory with `--python-exit-code 1`, then copy the JSON to an
independent development project. Unlink a hardlinked inherited JSON before
replacing it. Keep BVH/Blender/UE assets and generated media outside Git.

## Reaching and gripping

The arm IK starts from the current recorded elbow plane. It progressively adds
a torso-relative anatomical guide as reach weight rises. This avoids switching
to a fixed mesh-space pole on the first tiny reach weight. The forearm takes a
share of axial grip rotation before the wrist is restored to its exact contact
orientation. Endpoints and segment lengths remain unchanged; actual contact
gates and object state transactions still decide success.

The pole also follows the desired palm longitudinal axis to reduce wrist bend.
Its signed angular change is bounded in the current reach plane and retained in
torso coordinates, preventing near-straight/antipodal elbow flips during turns.
These constraints supplement the captured pose; they are not captured task clips.

Held posture uses a continuous height/distance transition. The former threshold
changed torso lean by 85% in one frame during handset lift/return. The handset
now gathers toward the chest, turns upright and rises to the ear over a bounded
transition. A position-only elbow solve cannot repair every handset orientation.
The phone controller therefore projects the physical prop orientation into a
palm/forearm cone calculated from the fitted arm lengths and relative grip; it
recomputes the wrist offset after each orientation correction. This preserves
the physical grip and exact contact authority. It uses a 50-degree engineering
bend target, not a universal anatomical limit. The same path reverses on hang-up.
The return gesture keeps the held upright posture and bounds its animation clock
advance after release, so a render hitch cannot skip its visible transition.
The audit includes every adjacent recorded pose, including hitch intervals; it
reports timing separately rather than discarding the slow frames.

## Native acceptance

`review_reference_motion.py` sends real keyboard/mouse input only to a recorded
private display and records separate fixed first/third-person silent clips.
`analyze_reference_motion.py` reads finalized native transforms and checks bone
lengths, neck orientation, elbow/wrist geometry, camera continuity and actual
capture use. Its thresholds are bounded engineering acceptance, not clinical
anatomical limits or a complete naturalness score. The older baseline wrist
geometry is reconstructed from its final wrist plus the unchanged rig-local
metacarpal offset; the newer trace directly includes that finalized bone.

Run `review_anatomy.py`/`analyze_anatomy.py` for all rooms, directions, jogging and
pickup/release, `review_phone_motion.py` for holding/answering/hanging up a phone,
and `review_ground_motion.py` for continuous routes and assistant device contacts.
These reviews use no model endpoint or cloud speech quota. A saved movie or a
compiled plugin alone is insufficient acceptance.

## Remaining work

Capture or license task-specific reference clips for low/high reaches, turning,
sitting, two-handed manipulation and conversational gestures. Retarget them in
the same calibrated basis, preserve physical contact and validate transitions.
Hand pose authoring/contact IK is still required because CMU has no finger data.
More motions, collision cases and human preference studies are needed before
claiming comprehensive naturalness; actor appearance and cloth deformation also
remain separate from this motion iteration.

Engineering phone tests explicitly stage within reach beside the table; this
does not establish autonomous approach. Picking up a fallen phone can still
return an unreachable-hand rejection. Preserve that failure and solve approach,
grasp/posture and crouch/kneel references before expanding action claims.
