# Continuous ego clay-reference minute

An isolated research pilot following the Codex → Blender previsualization →
Seedance workflow in https://x.com/i/article/2099111135169384451.

The authored episode is a parent cooking milk, retrieving a child's toy,
silencing a phone, approaching a ringing door, returning to turn off the stove,
then checking the child. One camera remains in the same apartment for 60 seconds.
The persistent room and prop tracks are procedural; they are not the live UE
environment and are not a physics simulation. The low-detail hand and child
models are motion/reference proxies, not accepted natural-human animation.

## Reproduce the clay reference

```sh
blender --background --threads 6 \
  --python tools/blender/vista_ego_clay_minute/build.py -- \
  --output /absolute/new/run --render all
ffmpeg -framerate 12 -i /absolute/new/run/frames/frame_%04d.png \
  -c:v libx264 -crf 20 -pix_fmt yuv420p -movflags +faststart \
  /absolute/new/run/clay_full_60s.mp4
```

Outputs include the editable `.blend`, sampled state ledger, scene manifest,
and 720 reference frames. Split the reference at 18 and 38 seconds into files
`clay_1.mp4`, `clay_2.mp4`, and `clay_3.mp4` (18, 20, and 22 seconds).

## Generate explicitly

`generate.py prepare --run RUN --segment N` writes a reviewable prompt and
reference hash manifest. `submit`, `poll`, and `download` are separate actions.
API operations read one authorized OpenRouter key from `--keys` in memory on
the user's specified remote host. Keys are never written to receipts or copied
between hosts. The script does not rotate keys, automatically regenerate a
failed clip, or substitute a different model.

The live model catalog is checked before generation. This pilot requests
`bytedance/seedance-2.5`, 720p, 16:9 and native audio. OpenRouter rejected inline
video data with HTTP 400 before generation; references require HTTPS URLs.
`serve_references.py` provides an exact-allowlist localhost origin with a random
path and byte-range support. A temporary HTTPS tunnel may connect the provider
to these reference files; shut down both owned processes after generation.
Never serve the whole run directory, credentials, or the source workspace.

Each subsequent segment requires `previous_N.mp4` (the last 2 seconds of the
prior generated segment) and `anchor_N.png` (its last frame). These are supplied
as references alongside the new clay trajectory. `character_continuity.mp4`
contains two seconds of the first generated child for stable character design.
`environment_kitchen.png` and `environment_living.png` preserve earlier views
of the generated room, with instructions to retain appearance without resetting
the later event state. These are soft references, not a persistent 3D world.
Do not set `frame_images`
without checking current provider behavior: OpenRouter documents that it takes
precedence over `input_references` and changes the generation mode. In reference
mode the tail frame is a soft continuity cue, not a guaranteed boundary constraint.

## Review before accepting

- Check all reference/result durations and a single first-person viewpoint.
- Inspect both segment boundaries for camera, appearance, motion and audio jumps.
- Revisit the kitchen, phone and child: props must preserve identity and state.
- Inspect grasp/release, door remaining closed, milk rise and burner shutoff.
- Check audible events against the timeline, including offscreen persistence.
- Record every candidate and actual cost; do not report only selected successes.
- Generated pixels need their own reviewed timing labels. The authored ledger
  is not automatically ground truth for the generated video.

The first prototype's validation and media live outside Git in the task run.
The existing World contract/compiler baseline remains required for source changes.

The first clip followed the clay motion but retained a stylized 3D child. A
fictional photoreal casting image generated with the built-in image tool was
rejected by Seedance as potentially depicting a real person. That image was not
used or altered to evade the restriction. The pilot continues with its original
stylized character; it does not establish photoreal-human conversion. Preserve
both the original candidate and the rejected request receipt.

`audit_audio.py` optionally sends an extracted WAV to an audio-capable model for
a sound inventory. Its output is an automated review, not human annotation;
record truncation and uncertainty instead of treating the response as labels.

## Observed limitation in this pilot

The first continuation added kitchen cupboards/appliances and failed the phone
lift. One correction made the phone reference upright and more visibly held,
then added both original room images with explicit architecture constraints.
The corrected result did lift the phone, but still added kitchen cupboards and
an extra refrigerator. These failures are retained in the run review. Therefore
the 60-second pilot must not be described as satisfying strict object permanence,
even if camera transitions look continuous. A reproducible clay trajectory does
not guarantee the generated pixels retain its world state.

The completed assembly also fails strict camera continuity: at 38 seconds the
camera jumps from a close cooktop view to a more distant kitchen view. At 18
seconds room framing is similar but the wearer's hands reset. Tail-frame and
prior-tail references did not impose a hard initial state. A simple scene-score
threshold of 0.35 detected neither problem, so an empty cut-detector result is
not acceptance evidence. Final sampled views retain the duplicate refrigerator.
Both delivered editions are exactly 60 seconds / 1440 frames; duration validation
does not change these semantic failures. Four video jobs, including the one
second-segment retry, cost USD 23.80032 in the recorded provider receipts.

`add_event_cues.py --run RUN` authors a separate stereo phone/doorbell Foley
track. `assemble.py --run RUN` conforms the selected 18/20/22-second clips to
1440 frames at 24 fps and produces native-audio and Foley-mixed 60-second files.
It makes straight joins, removes encoder tail padding, and does not use fades,
frame interpolation, speed changes or other edits to hide continuity defects.
