# Local Isaac research pilot

Read `docs/research/isaac-sim-pilot.md` for evidence, failed cases and boundaries.
These scripts are tested with Isaac Sim **5.1.0.0**, Python **3.11**, Blender
**4.5.8**, and the current server5090 NVIDIA driver. This is not a 6.1 skills test.

From the source worktree, use the workspace tools and a dedicated interpreter:

```sh
../../bin/uv venv --python 3.11 ../../services/isaac-pilot/venv
../../bin/uv pip install --python ../../services/isaac-pilot/venv/bin/python \
  --extra-index-url https://pypi.nvidia.com 'isaacsim[all,extscache]==5.1.0'
```

Do not recreate an existing environment to rerun the experiment. The complete
installed-version receipt is in `runs/isaac-pilot-setup-a/installed-packages.txt`.
Isaac's NumPy 1.26 environment is separate from VISTA's NumPy 2 contract tooling.

For each run, choose a **new** output name. Example (from this worktree):

```sh
../../bin/uv run --offline python tools/isaac/run_bounded.py \
  --python ../../services/isaac-pilot/venv/bin/python \
  --output ../../runs/isaac-pilot-physics-next --timeout 300 -- \
  tools/isaac/physics_probe.py --output ../../runs/isaac-pilot-physics-next/data
```

`run_bounded.py` is a server5090 supervisor: explicit GPU 0, one NVIDIA Vulkan
ICD, no display, a timeout and whole-GPU memory ceiling. It kills only its own
child process group. Inspect the live GPU workload before a new run; the memory
limit is a backstop, not resource reservation. No system driver changes occur.
Its result checker expects `<output>/data/results.json`, nonempty `checks`, and
no `error.txt`; scientific criteria can fail even when Kit exits 0.

Use `manipulation_probe.py --repeats 2` in place of `physics_probe.py` to run the
six trials. The pause-height check is currently expected to fail: the controller
phase reaches carry before the physical arm finishes rising. Keep that result;
it is not permission to lower the criterion. `make_review.py --data ... --output
NEW_DIR` renders the native camera comparison, explicitly labeling this failure.

For the actual VISTA humanoid, export an independent USD:

```sh
../../bin/blender --background --python tools/isaac/export_avatar.py -- \
  --source ../../runs/six-room-companion-face-b/companion.blend \
  --motion ../../projects/six-rooms-agent-r1/payload/Content/VISTA/VillaR1/mocap.json \
  --output ../../runs/isaac-pilot-avatar-export-next
```

Then use `avatar_probe.py --asset /absolute/path/to/avatar.usdc --output
NEW_RUN/data` through the same supervisor. `make_avatar_review.py` makes its
English-labeled silent video. It is baked animation compatibility, not physics
locomotion. Validate the native images in addition to skeleton/skin metadata.

No helper changes Sunshine, UE, network configuration, credentials, scene
selection or published datasets. Model inference, IRA navigation, humanoid
training and UE ↔ Isaac online synchronization are not implemented here.
