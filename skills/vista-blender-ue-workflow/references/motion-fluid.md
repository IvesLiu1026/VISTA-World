# Natural interactions and real liquid prototypes

Use a fitted/rigged character and suitable clips for locomotion. Motion Matching
selects from a database; it does not supply missing finger manipulation clips.
Retarget and check root motion, feet, turning, stopping and stairs. Epic's Game
Animation Sample is a candidate reference, not an installed dependency.

Layer gaze, torso reach, arm IK, wrist alignment and staggered finger closure
over the base motion, then verify contact before committing an action. Keep foot
support stable. Sine-wave walking and smoother interpolation are procedural
components, not a complete high-quality motion library.

The shared clamped quintic blend is `10t³−15t⁴+6t⁵`. Verify monotonicity and zero
endpoint velocity/acceleration. This formula alone does not establish naturalness.

Keep owner/world meshes synchronized with one world skeleton. Test first/third
person switching empty, carrying, near a wall and during approach. Looking down
should show body surfaces without stretching bones. Frustum landmarks alone can
pass while clothing occludes feet; also check rendered surface visibility.

Use observable phases: approach → align → reach → contact → attach/operate →
release → settle. Verify target identity, reachability, grip pose, fingertip
distance and unchanged arm lengths. Run real pickup/drop transactions and inspect
receipts. Preserve cancellation/reset. Never attach early just to hide a gap.

## Liquids

Use UE Niagara Fluids 3D FLIP for an interactive prototype, Blender Mantaflow for
a baked physical shot (label playback), and rigid-body physics for solid objects.
Inspect a solver's actual parameters first. Local UE 5.7 Pool/Hose/Splash templates
do not expose all nozzle controls as `User.*` variables. Unknown keys may silently
do nothing. `HomeFluidAuthoring` rejects unknown keys and type/range mismatches
atomically. Internal rapid-iteration constants are not per-component controls.

Validate scale, gravity, timestep, resolution, boundaries, obstacle collisions,
particles and surface rendering in a small lab. Stop a source while keeping old
water moving; do not translate the domain with a nozzle or erase water on tap-off.
Inspect before/during/after frames. Estimated particle counts alone do not prove
visible water or correct collision.

Volume coupling requires initial water + inflow − outflow − retained − lost water
accounting with units and tolerance. Overflow needs a rim-crossing condition.
Scripted milliliters are not solver measurements. Keep visual effects and event
quantities distinct until their correspondence is validated.

VISTA authors/audits scenarios; EgoArgus controls evidence relations and evaluates
assistance. The proposed extension compares consequences from a common world
state. A physical demo alone is not that experiment. Keep labels, hidden state,
seeds, scripts and future outcomes out of restricted assistant inputs. Distinguish
changing dialogue evidence from changing the intervention in a fixed world.
