# Fine manipulation and real material revision

R3 extends the six-room Home R2 with measured fingertip contact, real CC0
surface imagery and repaired moving hardware. It reuses the fitted 53-bone
MakeHuman character and the existing VISTA action bridge. The frozen house,
46 entity IDs, 40 action IDs, two explicit extensions and seven event
definitions remain in `world_packs/vista_photoreal_home_r2/scene.json`.

The selected native candidate is `build-n` in `project-x`, with `contacts-j`.
Generated assets and native evidence are append-only under
`runs/vista-photoreal-design-r1/home-fidelity-r3-20260907a`. The accompanying
[implementation manifest](implementation-manifest.json) binds the selected source,
map, binaries and reports; earlier failed
attempts remain in that run. An authoring inventory or successful import is
not visual acceptance.

## Contact behavior

Thirty finger joint rest frames and ten distal skin patches are measured from
the fitted source body. Blender bone-local offsets cannot be used directly in
UE: Interchange changes the bone rolls. R3 retargets the source component
frames into the imported reference skeleton and rejects incompatible skeletons.

Thirty-five authored interaction surfaces use triangles extracted from their
actual meshes. A local BVH supports nearest-surface queries. Point controls
require the index finger, narrow grips require index and thumb, and wraps
require index, middle and thumb. The phone additionally solves ring and pinky
contact. Two-hand props check both hands; ladder motion samples both rails.
The player must first reach the control, close the hand and establish the
required contact before the action commits.

Finger refinement runs on the animation proxy's game-thread update after full
arm IK. It preserves bone lengths, restricts interphalangeal corrections to
flexion, allows bounded MCP spread and limits each joint's change from the
authored pose. A swept, bounded wrist adjustment feeds back through the whole
arm solver (at most 2 cm, swept against surrounding geometry). Measurements come from the finalized skeletal pose, including
surface distance and penetration direction. Receipts retain these measurements
separately from wrist error, simulator state and final action outcome.

Keys and a flat phone use opposed contacts from above their support. The phone
also rolls around the index/thumb contact line to bring the shorter fingers
onto the surface without pushing the wrist into the bedside support. The box
uses independently measured side anchors on its tapered scan. The four
wardrobe handles now belong to their respective moving leaves: R2's split had
left them on the stationary carcass. Fridge and wardrobe grips use isolated
handle surfaces and measured curved-handle centers. Looking at a different
object while carrying preserves the held object's hand profile and contact.
Container removal waits for a finalized closed-hand pose before transferring
ownership; assigning the closure target on the current tick is insufficient.

This is a fingertip skin-patch approximation with kinematic finger motion,
not distributed soft-tissue pressure or a force-closure proof. Liquid volume
and spills remain analytic effects; falls remain procedural poses; clothes
and straps do not acquire cloth simulation through this revision.

## Real-world imagery and character

Existing acquisition receipts bind Poly Haven's CC0 white oak and wool
herringbone diffuse, roughness and OpenGL normal maps. Metric UV channel 1
maps those surfaces while preserving the original UVs and source geometry.
Four shared UE materials cover 37 existing furniture parts; five legacy
decorative door labels are correctly absent after R2's operable-door import.
The hardware repair subsequently replaces the carcass and four leaves.

The retained CC0 `cardboard_box_01` supplies UV-mapped photographs, roughness,
normal detail, tape and physical creases. It is fitted to the existing
49 × 28 × 29 cm box and retains the same identity, mass and interaction role.
Its source translation is baked away so the bottom pivot is correct.

Nanite fallback simplification can change collision openings even if the
source geometry is identical. R3 keeps prior Nanite enablement and uses full
triangle fallbacks for 138 native meshes. The 37 material replacements have
zero native bounds difference against their source geometry. This favors
collision fidelity; performance must be measured on the running build.

The pot has a circular collision base matching its 23 cm encapsulated bottom.
Four convex collision volumes are extracted from the existing curved burner
bars, and the pot/lid start 2 cm higher to clear the supports before gravity
settles them. These volumes follow the actual bars; no support plane is added.
Three native resets settled with less than 0.004° tilt and zero reported linear
speed, followed by a verified two-hand pickup. Raising the initial pose alone
and changing the pot base alone did not resolve the issue; those failed
attempts are retained.

The existing CC0 character retains its geometry, weights and pose library.
Skin receives a 2K baked normal from the source skin shader. The eye's original
alpha mask is restored: forcing its outer shell opaque had hidden the iris.
Existing hair and clothing imagery remains available. The hair silhouette,
cloth deformation and hand skin still show the limits of this game asset.
The source facial shapes are not a working runtime facial-animation system.

Sources: [Poly Haven CC0 license](https://polyhaven.com/license),
[MakeHuman asset licensing](https://static.makehumancommunity.org/about/license.html).
R6/R23 inventories retain their existing human-review-only scope; no City
Sample or HSSD asset is copied into this VISTA revision.

## VISTA and review

R3 preserves the transactional bridge, cancellation/rollback, event semantics
and restricted-input allowlist from R2. Fine contact geometry, joint frames,
state, receipts, source IDs and review notes are privileged authoring evidence.
Only native video and selected external dialogue enter `MllmEvalInputV1`.
Simulator success does not label assistance need, and exported candidates
remain `needs_review` until the observation cutoff and label are reviewed.

Use Sunshine's **VISTA Photoreal Home** to inspect the selected native build.
The installed entry uses `sunshine-review-profile-n.json`, and R3 is running
on `:119`. Initial installation preserved the running processes. A subsequent
connection-log check established that Sunshine's BUSY status belonged to a
retained **Low Res Desktop** with no connected client. Sunshine was reloaded
only after that check, then the Home game/input services switched to R3.
The other five app entries and the R6/R23 process IDs remain unchanged.
The extra `:120` validation process has been stopped after the final evidence
capture to release its GPU load. First/third/first-person switching and native
living-room/character screenshots also passed on the actual `:119` Home.
The revision-aware launcher selects the requested project when the user opens
the app; preparing a new profile does not interrupt an active stream. Manual
starts require an idle Sunshine server. Other named scenes retain their services.
WASD/mouse move and look; Tab switches first/third person; E or left click
performs the selected action; the wheel changes actions; C crouches; B handles
the backpack; G drops/cancels; 1–6 select rooms while empty-handed; F2 cycles
events; R resets. The prior Home R2 profile is retained for rollback.

The [development review page](http://100.114.80.121:8001/native-home-review)
serves the seven final `vista-review-candidates-c` bundles. Each input passed
the checked-out VISTA `MllmEvalInputV1` and `AgentAssistanceResponse` contracts;
the contract source hash is in `validation/vista-contracts-d/results.json`.
All seven 1080p clips played in Chromium, input downloads returned HTTP 200,
and the catalog rejected zero bundles. Desktop and 390 px mobile captures are
retained with the browser report. The existing review frontend code is unchanged.
The clips include completed actions; a formal assistance observation cutoff
and label still require review. The dialogue is project-authored external text,
not a recording of spoken dialogue. The ladder episode establishes inspected
ladder completion; it does not assert that the character carries a box down it.

No paid model or image/video generation was used. One early UE import crashed
and the engine's automatic crash reporter sent 25,147 bytes to Epic (HTTP 204);
the payload was not independently audited. Subsequent UE import, build and
validation processes run in a network-isolated namespace. The private
`ue-crash-network-note-a.json` records the incident.

## Validation and limits

The complete interaction suite ran on `build-k/project-t`: all 42 action IDs
have successful receipts, and all 35 contact surfaces have mature contact
evidence. The later `build-n/project-x` changes only collision authoring and its
RenderCore dependency; action/animation/bridge source files are byte-identical.
The final map changes the pot's collision, its assembly's initial height, and
adds four support collision actors. All other existing content files are
unchanged. The final resting/pickup check and seven event recordings use X.
This is scoped follow-up verification, not a claim that every suite was repeated
after the pot repair.

| Check | Result |
| --- | --- |
| Contract/compiler, geometry and launcher unit checks | 46 unique tests passed |
| Native room detail cases | 34 passed |
| Native event/interaction sequences, including real-time timeouts | 21 passed |
| Additional precision/control cases | 6 passed |
| Moving-handle continuous contact | 2 passed |
| First/third-person grip views | 2 passed |
| Replay, stale input, cancellation and reset protocol | 14 passed |
| Actual X11 camera/room/pickup controls on `:120` | 13 passed |
| Final pot settling and two-hand pickup | 3 stable resets and pickup passed |
| UE Linux Editor, Game Development and Shipping | Build N succeeded |
| Final VISTA inputs against the actual project contracts | 7 passed, no model calls |
| Browser playback and restricted-input download | 7 passed, 0 rejected bundles |
| Actual Sunshine Home view on `:119` | R3 project/binary verified; camera switching and two native screenshots passed |

Selected detail/sequence reports preserve every attempt's hash and choose the
latest case without discarding failed history. The living-door fixture was
displaced by collision. Kitchen-door closure from the northern approach was
blocked beside the shoe bench. The bed and shoe-bench fixtures also required
clearer standing positions. Corrected fixtures passed on the same K runtime;
collision thresholds and source scene definitions were not relaxed.

The images and clips are native rendered evidence. Hair, garment deformation,
skin rendering and some poses still need artistic refinement. Fine contact is
not a full hand-volume collision, pressure or friction simulation. Native frame
rates are recorded separately from the encoded video rate. The seven final
clips have per-clip median native frame rates of 9.45–10.47 FPS while multiple
UE scenes share the GPU; the capture container is 20 FPS. The performance
report deduplicates repeated native state samples by `clock_s` before taking
the median. This is not a 60 FPS performance acceptance.

After stopping the extra validation runtime, a separate ten-second idle
living-room sample on the actual `:119` Home measured **18.26 FPS** median
from 46 distinct native state updates. This is a scoped idle measurement,
not a whole-house gameplay or connected-client streaming acceptance.
