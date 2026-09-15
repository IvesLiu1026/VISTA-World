# R25 character motion repair

This continues the playable R25 material release in an isolated project. It does
not edit R25 maps, appearance assets, recorded source motions or the live stream.

The existing 53-bone skin and hierarchy match the runtime reference. The reported
defects arise after animation loading:

- Wrapped look angles jumped from one clamped neck extreme to the other. A
  persistent, rate-limited gaze is now bounded relative to the **animated torso**.
  It replaces the free recorded head turn and distributes one rotation over the
  neck/head. Active hand contacts retain their established pose.
- Rapid mouse changes crossed directional blends fast enough to move the pelvis
  by 39 degrees in one 30 Hz simulation step. The circular blend coordinate now
  turns continuously at a bounded rate.
- Contact weights were ahead of the filtered pose. World foot anchors then
  distorted the correctly alternating FK gait. Contacts now share the pose's
  filter; anchor corrections have continuous weight and a 6 cm horizontal bound.
  Ground height remains authoritative and the knee pole follows the recorded bend.

The terrain correction deliberately permits some sliding rather than letting an
anchor drag a leg beyond reach. This is not a new mocap library, physical footstep
planner, full-body IK system, or evidence of GTA-level animation quality.

## Native evidence

`run_native.py` requires a private `character-motion-*` project and a separate X11
display. It uses real SDL mouse/key input, fresh native state, actual GPU identity,
normal process shutdown, and a native video capture. The opt-in C++ trace writes
both motion FK and **finalized** bone transforms. These are privileged engineering
measurements, not model observations.

Run the motion suite under `xvfb-run` with `--project`, `--engine`, `--out` and
`--ddc` paths. The default uses a fixed 1/30-second simulation step; video capture
uses wall time, so it is not a timing benchmark. `--suite regression --realtime`
records normal presentation speed and checks vehicles, six room identities,
table/floor pickup, sitting and standing. Every output directory must be new.

`analyze.py RUN` measures rig binding, anatomical gaze, limb lengths, adjacent
rotations and same-side hand/foot opposition along the movement axis.
`verify.py RUN` rejects incomplete input evidence and the original defects.
Inspect the native presentation as well; these checks do not certify zero sliding
or animation quality for every interaction.

The original R25 baseline fails the regression checks. Final evidence paths,
build/source hashes and the actual live selection belong in the workspace
character-motion handoff. Never describe a private fix as already live.

## Verified delivery on server5090

- Linux Editor and Game Development builds: `runs/character-motion-build-e`.
- 37 source tests, including the portable C++ gaze update.
- `runs/character-motion-fixed-d`: 3,210 finalized frames; all 57 checks pass.
  The fast stationary mouse case dropped from a 162.6-degree adjacent head
  rotation to 6.0 degrees. Forward hand/foot correlation changed from
  -0.053/-0.356 after the old IK to -0.988/-0.993 after repair.
- `runs/character-motion-regression-a`: normal-speed input and all 23 vehicle,
  six-room, pickup/contact and seat checks pass; clean exit 0.
- `runs/character-motion-preview-a`: 14-second native preview with Chinese labels,
  1080p H.264/yuv420p/30 fps, fully decoded and sampled visually.
- `projects/campus-motion-r25-1`: 4,855 inventoried files, manifest SHA-256
  `48a33ae652ca6cb197f404bf3ae23b3ac284bda839e5b63d3f26eea2d196abc5`.
  All non-plugin scene files are byte-identical to the frozen R25 inventory;
  launcher preflight passes. `freeze.py` enforces the scene boundary and the
  native evidence's plugin binary hash before making this copy.

Streaming promotion is separate from these receipts. Check the current workspace
handoff and runtime selection before telling a user which revision is live.
