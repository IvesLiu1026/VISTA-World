# White geometry guide and photographic-person pilot

The user requests a continuous, realistic first-person household video with
objects staying in place while unseen. This experiment separates source-world
validation from generated-video acceptance. A persistent Blender scene is a
reproducible reference; supplying its video to Seedance does **not** impose a
hard geometric constraint on the generated frames.

`build_pilot.py` builds a 12-second route: kitchen → child position → door →
child position → original kitchen view. It freezes the original authored props,
records every camera pose/projected anchor and checks fixed object transforms.
It uses the existing original material recipe and Cycles. The optional `--person`
argument belongs to a rejected single-view compositing probe; omit it for the
white-guide workflow. A photographic cutout is not a freely viewable 3D human.

`white_guide.py` restores the original geometric child proxy and removes the
cutout, strips all appearance to uniform untextured gray, and renders the route
in Workbench. The dummy provides pose and location, not the final character
design. The final human is synthesized by Seedance 2.5, together with the room.

`tools/video/vista_ego_clay_minute/fixed_world_pilot.py` explicitly submits,
polls and downloads a single bounded request. Its inputs are the white guide
and an empty photographic kitchen appearance image. It deliberately does not
send `frame_images`, which would override the multimodal video-reference mode.
Credentials remain in memory on the user's authorized host. A submission marker
prevents silently repeating a request after an unknown network outcome.

The first attempted photographic-person reference was rejected by the provider
as `InputVideoSensitiveContentDetected.PrivacyInformation`. That input was
removed entirely. It was not cropped, reformatted or resubmitted to bypass the
restriction. The next request synthesizes a new fictional child from text.

## Reproduction

Use the workspace's Blender and uv launchers, a fresh output directory, and a
currently available GPU. Do not reuse the shared UE or Sunshine runtime.

1. Run `build_pilot.py --source <original-clay.blend> --out <native-run>` with
   Blender in background mode and `--python-exit-code 1`. `--render none` saves
   the geometry/camera source; `preview` renders five diagnostic poses.
2. Run `white_guide.py --pilot <native-run/fixed_world_pilot.blend>
   --original <original-clay.blend> --out <white-run>` with Blender.
3. Encode the 144 PNGs at 12 fps into `white_guide.mp4`. Use the actual native
   kitchen view as an image-generation edit reference; save the resulting
   `kitchen_photo.png`, its provenance and SHA-256 outside Git.
4. Serve only those two files through the exact-allowlist temporary HTTPS origin.
   Copy source helpers/media to the authorized remote run directory. Call the
   video driver `prepare`, then `submit --reference-base-file <path> --keys
   <remote-key-file>`, and later `poll` / `download`. Never copy the key file.
5. Inspect the real generated output before extending to 60 seconds. Preserve
   failed requests and candidates. Stop the task-owned origin/tunnel afterward.

## Acceptance boundaries

- Source test: fixed transforms and a returned camera pose; compare actual
  before/after rendered pixels as well as the scene-state ledger.
- Generated test: photographic human appearance, continuous camera movement,
  stable room topology and prop identity/placement, correct return views and
  natural urgent Mandarin audio. Review them independently of the source test.
- The optional `matte_person.py` needs `uv run --with 'rembg[cpu]'` and extracts
  a video foreground. It is retained to reproduce a rejected diagnostic, not as
  the production solution for free-view people or body contact.
- No rendered room is a scanned real apartment, no procedural motion is motion
  capture, and no model-assisted transcript is a ground-truth label.

Experiment artifacts: workspace `runs/ego-fixed-world-20260918-a/`. The run's
review and handoff, rather than this source recipe, record the observed result.

## Full-minute continuation

`white_minute.py --source <original-clay.blend> --out <fresh-run>` strips only
appearance from the original 720-frame/12-fps animation. Its geometry, camera,
hands and scripted prop states remain intact. Encode frames 1–360 and 361–720
as two 30-second inputs. The explicit plans live in the sibling video tooling's
`plans/white_minute_part1.json` and `white_minute_part2.json`.

Run each part in its own directory with `fixed_world_pilot.py --plan <plan>`;
include that argument for prepare/submit/poll/download. The second part uses
`anchor_2.png`, extracted from frame 719 of the first generated 24-fps clip,
in addition to its white video and the kitchen image. Its planned boundary is
the empty closed-door view. Inspect the actual frame before using it. This
image is a soft continuation reference, not a hard first-frame constraint.

Copy reviewed outputs as `generated_1.mp4` and `generated_2.mp4`, then run the
video tool `assemble.py --run <run> --durations 30 30 --native-only`. This trims
codec tail frames and straight-concatenates to exactly 60 seconds, without
crossfades, optical interpolation or concealed cut repairs. Check the actual
30-second boundary, prop interactions and return views before claiming success.

## Anatomical white-hand revision

The first 30s extension retained cylindrical fingertips and an incorrect phone
contact. It was rejected before requesting its second half. The short no-contact
pilot's success therefore did not establish interaction quality.

`rigged_white_minute.py --source <original-clay.blend> --character
<retained-companion.blend> --out <fresh-run> --render preview|all|none` replaces
only the rod arms/hands with the retained CC0 MakeHuman-derived skinned hands.
It uses the existing `vista_embodied_r1/build_body.py` arm IK helpers, authored
finger poses and explicit camera reach/bending offsets, recorded per frame in
`hand_receipt.json`. Room geometry and prop paths remain the authored source.
This is neither captured motion nor a physics simulation; wrist target accuracy
does not prove fingertip contact. Inspect the rendered previews independently.

`plans/rigged_phone_test.json` is a bounded 8s phone-grip generation test using
source frames 217–312. The full-minute candidates use separate rigged part plans
and separate output directories. Preserve rejected jobs and media; never reuse
a submission directory or silently retry an ambiguous request.
