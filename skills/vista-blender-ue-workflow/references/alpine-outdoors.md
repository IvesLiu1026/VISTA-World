# Alpine outdoors: reproducible implementation and failure checks

These entry points target UE 5.7.3 / Blender 4.5.8 in VISTA-World. Resolve the
current delivery manifest first. R3 writing worktree:
`/data/sysx/vista-world/worktrees/vista-alpine-world-r3`; evidence root:
`/data/sysx/vista-world/runs/vista-villa-r3-20260910a`.

## Preserve identity and inputs

Copy the accepted frozen R2 Content, Config and plugin into a **fresh** authoring
project. R1, R2 and R3 share the Villa map package name; verify the project path,
plugin, map, both motion JSONs and appearance JSON. A map name alone is ambiguous.
Leave live Sunshine/input services alone during private verification.

`tools/runtime/vista_alpine_r3/acquire_sources.py --out <fresh>` plans a bounded
publisher batch; `--download` executes it within existing user authorization.
It verifies sizes and publisher MD5, records SHA256 and uses at most three
downloads / one GiB per batch. The recorded Poly Haven models/maps are CC0.
`--only-hdri --hdri-resolution 8k` obtains the photographic distant skyline.
Do not call paid providers merely to make a terrain or retarget an existing clip.

## Build in metres; prove exported attributes

Under `tools/blender/vista_alpine_r3`:

1. `build_landscape.py --out <fresh>` uses `layout.py` for terrain, lake basin,
   connected trails, terrace, real garden door opening, instance placement and
   cameras. Exported Blender `(x,y,z)` metres become UE `(100x,-100y,100z)` cm.
   Every placement must use the same height function. Near/far grid edges match.
2. `export_nature.py` extracts complete named publisher variants. Inspect its
   CLI before use; retain source hashes, UVs, material names and pivot offsets.
   Some publisher `UVMap` attributes are **CORNER FLOAT_VECTOR**, not Blender UV
   layers. Convert XY into a real UV layer after evaluating with all data layers
   preserved. Confirm every textured GLB primitive has `TEXCOORD_0`.
3. Ground tree pivots from the trunk's bottom vertices. Retain the publisher's
   partly buried rock origin. A bounding-box-min pivot can make a sloping rock
   float. Do not assume variant object offsets are already baked.
4. `refine_character.py` retains the 53-bone fitted body. Split shirt/trousers
   by connected geometry, not a global Z threshold. Inspect photographed UV
   regions before diagnosing a white patch as a missing material: R3's shoe
   texture included a gray sock whose geometry protruded through the trousers.

Primitive cubes may already have UV layers. Creating a second layer does not
guarantee it becomes glTF `TEXCOORD_0`. Check the exported channel, or deliberately
use world-space texture coordinates for large architectural surfaces.

## Retarget complete motion, then couple it to physical movement

`tools/ue/vista_alpine_r3/inspect_sources.py` extracts local Epic mannequin clips
at 30 Hz. The receipt names source packages and hashes; keep that content within
its UE license scope, outside benchmark/model prediction inputs.
`build_motion.py --source <extraction> --base <accepted-R2-mocap> --out <new-json>`
runs through Blender Python. It uses the same 53 bone names, calibrated limb
directions, full temporally ordered cycles and measured root displacement.

The R3 library has eight walking directions, eight running directions, jump,
fall and land. Keep the accepted R2 lowered-arm idle. Blend direction and speed;
drive phase from **distance travelled**, and shorten stride distance and foot
excursion together. Running enables ordinary CharacterMovement acceleration;
jumping uses its actual gravity/collision arc. Disable ground IK while airborne,
release stance anchors, then reset them on landing. Do not stretch bone lengths
to hit a foot target or replace jumping with a teleported animation.

Inspect where the retargeted foot lands relative to the moving capsule. A path
centred too far behind the hip forces the pelvis to drop, then reaches the leg's
IK limit and slips at toe-off. Calibrate the whole swing/landing path; do not
move an existing support anchor or widen the verifier's drift tolerance. R3's
measured correction reduced the 18 cm pelvis excursion as well as foot sliding.

## Native authoring and visual iteration

UE scripts use `VISTA_ALPINE_CONFIG` JSON and require a private R3 project, fresh
receipt and fresh asset namespace. See existing config receipts for exact keys.
Apply `author_world.py`, `import_character.py`, `polish_world.py`,
`finish_landscape.py`, then `finish_surfaces.py` in the documented order on a
fresh source copy. Finishing scripts assert the previous instance counts; never
repeat a successful scatter pass on the same map.

Use InterchangeManager directly for unattended imports. AssetImportTask can
request Content Browser synchronization and hit a Slate assertion under
NullRHI. Bind native materials by **actual material slot names**, not a zip with
Blender slots: glTF omits unused slots. Construct `CustomInput` without keyword
arguments and set `input_name`; query the TextureSample UV input pin name.
Direct OpenGL normal maps need the UE green-channel flip; masks are linear.

Use the full near-ground triangles for collision; a Nanite fallback can alter
the surface on which feet stand. Tree/leaf rendering uses instancing; separate
trunk cylinders collide, leaves and grass do not. Rocks retain surface collision.
The distant HDR panorama is a background, not a traversable mountain mesh.

Inspect close, far, indoor and outdoor frames. R3's rejected first pass exposed
a yellow repeated ground map, empty tree UVs, overly long walking strides and a
villa sitting in a synthetic pit. Correct source/geometry errors before adding
more lights. Balance directional light and HDR skylight in the same exposure
range. Do not combine kilolux direct light with an almost black environment.
Break distant tiling with rotated/scaled detail and continuous macro colour.
Inspect actual leaf density and shadow detail rather than only instance counts.

The lake uses SingleLayerWater scattering/absorption with small analytic wind
waves. It is an optical surface prototype; do not call it volumetric CFD,
swimming, buoyancy or a coupled VISTA liquid experiment.

## Acceptance and delivery

Build Editor and Linux Game Development/Shipping. Run `run_native.py` from
`tools/runtime/vista_alpine_r3` with fresh output, private Xvfb, explicit NVIDIA
adapter and a 1–900 second bound. Donor DDC nodes stay read-only; writes go to R3.
The launcher cleans only its exact UserDir's residual editor/shader workers.

`--mode alpine --preview` is a 10 Hz **visual iteration**, not movement acceptance.
For acceptance, omit `--preview`, require continuous 1/30-second samples and run
`verify_outdoor.py --proof <AlpineProof/proof.json> --out <fresh>`. It checks actual
door crossing, speed, jump/landing, airborne IK, lowered hands and limb lengths.
A spawn inside a chair caused a 41 cm depenetration step: move the test's initial
position to free floor; never relax the no-teleport threshold to conceal it.

Also run `--mode motion` with the R2 `verify_motion.py` to check settled arms,
turning and support-foot drift, `--mode villa` for kitchen/stairs, and existing
Home pose/interaction cases. Read final saved bindings with `inspect_delivery.py`
(`VISTA_ALPINE_INSPECT_OUT=<fresh>`), and inspect native PNGs. A save receipt plus
a commandlet shutdown crash requires fresh-process readback; preserve both logs.
Shared GPU load and screenshot stalls do not establish live demo frame rate.

Freeze the tested Content/Config/plugin/project into a new `demo-project-*` and
hash **every** file. `launch_demo.py --profile <profile> --action plan` validates
the full inventory and matching native/visual receipts. Register a separate
Sunshine app while the service is free; preserve all older entries. Never select
the new app just to prove registration. Report the app name and controls, actual
acceptance evidence, and remaining visible quality limits without claiming GTA
or AAA production quality from a small prototype.

Unreal's `[VirtualTextureChunkDDCCache]` is separate from the chosen DDC graph
and defaults to `%GAMEDIR%DerivedDataCache/VT`. Redirect its `Path` through an
Engine INI command-line override to the session UserDir. Mount the frozen R3
project read-only in bwrap while keeping UserDir and R3 DDC writable. Otherwise
a successful first launch can add unlisted cache files and block the next
launch's inventory validation. Confirm the external cache in fresh-process
readback and keep this policy scoped to the frozen R3 profile.

`create_delivery.py` freezes only an already reviewed private R3 project and
writes an unselected profile. Supply `--project`, `--out <run/demo-a>`, `--engine`
(the UnrealEditor executable), `--alpine-process`, `--alpine-check`,
`--motion-process`, `--motion-check`, `--native-process`, `--visual-review` and
`--previous-profile`. Visual acceptance must be written after inspecting native
images; the utility never invents it or selects a Sunshine app.
