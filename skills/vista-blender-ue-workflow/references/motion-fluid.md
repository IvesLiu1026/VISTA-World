# Natural interactions and real liquid prototypes

Use a fitted/rigged character and suitable clips for locomotion. Motion Matching
selects from a database; it does not supply missing finger manipulation clips.
Retarget and check root motion, feet, turning, stopping and stairs. Epic's Game
Animation Sample is a candidate reference, not an installed dependency.

CMU BVH frame zero may be a synthetic T-pose while the fitted target uses an
A-pose. Calibrate limb directions before applying rotation deltas, preserving
target translations and bone lengths. Otherwise arms can fold behind the hips.
Keep source hashes, license, sampling rate and calibration frame. A selector over
three walk clips is not Epic Pose Search or a complete locomotion database.

Layer gaze, torso reach, arm IK, wrist alignment and staggered finger closure
over the base motion, then verify contact before committing an action. Keep foot
support stable. Sine-wave walking and smoother interpolation are procedural
components, not a complete high-quality motion library.

When a walk looks wrong despite valid bone lengths, trace every layer that owns
the feet and arms. A measured pose followed by unconditional wrist IK can replace
its elbow plane; a second procedural stride can overwrite the recorded gait.
Preserve unoccupied FK arms and apply reach IK only to active hands. Calibrate
hand orientation with the forearm as well as the upper/lower arm directions.

For a small clip library, a temporally ordered full cycle can be more reliable
than selecting a different frame each tick by phase/cost. Derive source-to-target
scale from measured limb lengths, not an assumed BVH unit conversion. Retain the
cycle distance and duration, correct the loop seam without changing local bone
lengths, and advance by actual traveled distance. Phase-based stance weights are
estimates, not captured contact labels; verify the resulting world-space support
feet. Inspect reverse/side steps and turning separately. A warped forward clip
does not establish a complete directional or stair motion library.

Check the transition from standing as well as a settled cycle. An idle support
foot starts beneath the pelvis; beginning a heel-strike phase with that anchor
can outrun the leg before toe-off. Align the initial phase to the standing
support geometry, then verify the first steps without relaxing drift limits.
Use dense fixed simulation steps for motion correctness (this runner uses
`-UseFixedTimeStep -FPS=30`) and record actual sample deltas. A slow shared GPU
can otherwise skip the short interval that contains a contact defect. Fixed-step
proof timing is not evidence of real-time rendering performance.

The shared clamped quintic blend is `10t³−15t⁴+6t⁵`. Verify monotonicity and zero
endpoint velocity/acceleration. This formula alone does not establish naturalness.

Keep owner/world meshes synchronized with one world skeleton. Test first/third
person switching empty, carrying, near a wall and during approach. Looking down
should show body surfaces without stretching bones. Frustum landmarks alone can
pass while clothing occludes feet; also check rendered surface visibility.

Resolve the user's current empty-hand preference before reusing a ready pose.
For naturally lowered hands, disable the camera-ready layer in both views and
calibrate a lightly flexed elbow and neutral wrist. Free look needs a view/body
yaw separation, not a constant full-body turn toward the camera. Derive eyes from
the neck/head pose; if a small inspection-camera lean is used to clear the near
shoulder, record that compromise, bound it, fade it out during contact and retain
eye collision checks. Do not move wrists just to satisfy a frustum test. Capture
neutral, left/right downward looks, straight down, walking, stopping and switching
views; judge the actual visible shoulder, forearm, hand and clothing surfaces.

Use observable phases: approach → align → reach → contact → attach/operate →
release → settle. Verify target identity, reachability, grip pose, fingertip
distance and unchanged arm lengths. Run real pickup/drop transactions and inspect
receipts. Preserve cancellation/reset. Never attach early just to hide a gap.

Sample contact after physics and bone transforms finalize. A pre-animation
snapshot compares the current object with the previous wrist and can report a
false gap. Mark inactive contact as not applicable. Use the actual eye ray for
placement: a fixed actor-height ray misses when an embodied camera leans. Repeat
reset/demo and return inspection cameras to the player when the tour finishes.

## Liquids

Use UE Niagara Fluids 3D FLIP for an interactive prototype, Blender Mantaflow for
a baked physical shot (label playback), and rigid-body physics for solid objects.
Inspect a solver's actual parameters first. Local UE 5.7 Pool/Hose/Splash templates
do not expose all nozzle controls as `User.*` variables. Unknown keys may silently
do nothing. `HomeFluidAuthoring` rejects unknown keys and type/range mismatches
atomically. Internal rapid-iteration constants are not per-component controls.

On a private Hose duplicate, link rate, sphere offset/radius and the velocity
assignment to real user parameters, then remove shadowing literals and compile.
The template may send water horizontally at 150 cm/s. Inspect compiled HLSL for
origin, coordinate space and velocity before treating it as a pouring source.
When extending an authored graph, reuse an identical existing parameter link;
`SetLinkedParameterValueForFunctionInput` asserts if its pin already has a link.

Validate scale, gravity, timestep, resolution, boundaries, obstacle collisions,
particles and surface rendering in a small lab. Stop a source while keeping old
water moving; do not translate the domain with a nozzle or erase water on tap-off.
Inspect before/during/after frames. Estimated particle counts alone do not prove
visible water or correct collision.

Volume coupling requires initial water + inflow − outflow − retained − lost water
accounting with units and tolerance. Overflow needs a rim-crossing condition.
Scripted milliliters are not solver measurements. Keep visual effects and event
quantities distinct until their correspondence is validated.

A useful hybrid combines a conservative milliliter ledger, flight parcels,
receiver capacity and spill/drain destinations with a clipped hydrostatic vessel
surface, a ballistic column for streams narrower than a grid cell, and coarse
GPU FLIP splashes. Advect each emitted slice after source-off; column radius can
follow flow / velocity rather than a decorative constant. Label this hybrid
explicitly and inspect nozzle, basin and receiver at close range. A solid cabinet
behind an otherwise hollow basin can hide all the simulated water. Test the surface's geometric volume at tilted
poses. This does not measure FLIP mass or establish fully coupled CFD accuracy.

VISTA authors/audits scenarios; EgoArgus controls evidence relations and evaluates
assistance. The proposed extension compares consequences from a common world
state. A physical demo alone is not that experiment. Keep labels, hidden state,
seeds, scripts and future outcomes out of restricted assistant inputs. Distinguish
changing dialogue evidence from changing the intervention in a fixed world.
