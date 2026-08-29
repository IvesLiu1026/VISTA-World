# VISTA Playable Home Runtime

This package owns both the historical game-only Unreal preview and the sealed
Linux Development package used by the current Sunshine application. It does
not modify the existing Blender-world or NLP-demo runtimes.

The preview command deliberately uses `-game` and a visible X11 display; it
does not use `-RenderOffScreen`. GPU 1 and the existing VISTA ports are refused.

Start with the read-only host report:

```bash
uv run --project tools python \
  tools/runtime/vista_playable_home/preflight.py \
  --ue-editor /absolute/Engine/Binaries/Linux/UnrealEditor
```

Before running a real map, inspect the fixed command:

```bash
uv run --project tools python \
  tools/runtime/vista_playable_home/launch.py \
  --workspace /absolute/new-run/ue/attempt-01 \
  --project /absolute/new-run/ue/attempt-01/project/Home.uproject \
  --ue-editor /absolute/Engine/Binaries/Linux/UnrealEditor \
  --map /Game/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome \
  --display :117 --gpu 0 --vista-world-port 55620 --preflight-only
```

The game process binds only its fixed typed `vista_world_action` listener on
the selected loopback port. The launcher refuses ports owned by existing VISTA
runtimes and never exposes a Python, console, or caller-selected command lane.
It remains in `starting` until a non-mutating typed status handshake proves the
exact world revision and initial generation; a merely-live process or occupied
port is never reported as ready.

Each launch is retained under `game-runtime/attempt-<UTC>-<pid>`. A private
`game-runtime/current.json` pointer lets the stop command target only the
current process identity, so a stopped Sunshine application can be launched
again without deleting or overwriting earlier evidence.

For player-eye review without taking over the live `:117` window, the closed
`realistic_interior_r2_isolated_review` profile fixes the same realistic camera
and 1920x1080/60 settings to GPU 0, display `:118`, and loopback port `55621`:

```bash
uv run --offline --no-sync python \
  tools/runtime/vista_playable_home/launch.py \
  --workspace /absolute/new-run/ue/attempt-01 \
  --project /absolute/new-run/ue/attempt-01/project/Home.uproject \
  --ue-editor /absolute/Engine/Binaries/Linux/UnrealEditor \
  --map /Game/VISTA/PlayableHome/vista_playable_home_r1/Maps/VistaPlayableHome \
  --runtime-profile realistic_interior_r2_isolated_review
```

This lane is review-only. It does not create a Sunshine profile and it does not
prove uncontended performance while another process is using GPU 0.

## Human-operated City Sample visual demo

The current private, non-commercial City Sample/MetaHuman visual-demo lane uses
GPU 0 and X11 display `:118`. Sunshine and the virtual-input-to-XTEST relay must
both target that same display. Their host-local unit files, credentials,
pairings, Tailnet address, and all external Unreal assets stay outside Git.

Launch only from a sealed combined receipt:

```bash
PYTHONPATH=. uv run python \
  tools/runtime/vista_playable_home/human_visual_demo_launch.py \
  --combined-receipt /absolute/attempt/human-visual-demo-combined-receipt.json \
  --launch
```

The launcher fixes display `:118`, GPU 0, the map, provider, resolution, and
network-isolation arguments. It does not accept caller overrides for display,
GPU, map, provider, or arbitrary UE arguments. The editor runs in a private
network namespace so its development-only listeners do not reach the host or
Tailnet.

Readiness requires all of the following text/process checks before manual
review:

- the UE process survives the startup grace period;
- a 1920x1080 `VistaPlayableHome` window exists on `:118`;
- the UE log contains `VISTA_CITYSAMPLE_VISUAL_DEMO_ACTIVE` for the sealed
  provider; and
- Sunshine and the XTEST relay are active with `DISPLAY=:118`.

Those checks prove only that the candidate is available for a human-operated
visual demo. They do not accept photorealism, animation quality, controls, or
dataset suitability. A human must review the Moonlight stream and controls.
City Sample/MetaHuman content is excluded from VISTA datasets, databases,
AI/VLM training, testing, evaluation, and review.

`sunshine_app.py` prints a plan by default. `--apply` creates a timestamped
backup before replacing `apps.json`; Sunshine must then be restarted by its
runtime owner. Do not apply the entry until the referenced profile and map
exist.

## Sealed Linux Development package

`packaged_profile.py` accepts only an `accepted` package receipt and re-hashes
the full archive, executable, PAK, pinned UnrealPak and NVIDIA ICD before it
writes a mode-0600 profile. `packaged_entrypoint.py` then launches the packaged
ELF directly. It never invokes UnrealEditor, a `.uproject`, the archive shell
launcher, or `-game`.

```bash
ATT=/absolute/package-linux-development/attempt-01
PROFILE="$ATT/sunshine-profile-packaged-accepted.json"

uv run --offline --project tools python \
  tools/runtime/vista_playable_home/packaged_profile.py \
  --package-attempt "$ATT" \
  --package-receipt-sha256 <receipt-sha256> \
  --nvidia-icd /usr/share/vulkan/icd.d/nvidia_icd.json \
  --output "$PROFILE"

PROFILE_SHA=$(sha256sum "$PROFILE" | awk '{print $1}')
/usr/bin/python3 \
  tools/runtime/vista_playable_home/packaged_entrypoint.py \
  --profile "$PROFILE" --profile-sha256 "$PROFILE_SHA"
```

The packaged supervisor fixes GPU 0, display `:117`, loopback port `55620`,
the r1 map and 1280x720 at 60 FPS. It re-hashes the archive immediately before
spawn and again after typed `READY`, proves that the listener belongs to its
owned process group, and records an immutable launch attempt beneath the
package's `game-runtime/` directory.

## Observed renderer acceptance (realistic r2)

The VisualProfile, generated `DefaultEngine.ini`, UE build result, and Linux
package receipt deliberately remain `renderer_runtime_observation: pending`.
They describe requested settings and cannot prove that the active RHI applied
them. After the exact r2 runtime and its loopback adapter are live, seal one
read-only observation into the current runtime attempt:

```bash
WORKSPACE=/absolute/r2/ue/attempt-01
PACKAGE=/absolute/package-linux-development/attempt-01/package-receipt.json
PACKAGE_ATTEMPT="${PACKAGE%/package-receipt.json}"
STATE="$PACKAGE_ATTEMPT/game-runtime/attempt-<utc>-<pid>/runtime-state.json"
OUTPUT="${STATE%/*}/renderer-acceptance-final.json"

uv run --offline --project tools python \
  tools/runtime/vista_playable_home/renderer_acceptance.py \
  --workspace "$WORKSPACE" \
  --repo-root "$PWD" \
  --package-receipt "$PACKAGE" \
  --output "$OUTPUT" \
  --runtime-state-sha256 "$(sha256sum "$STATE" | awk '{print $1}')" \
  --build-result-sha256 "$(sha256sum "$WORKSPACE/result-receipt.json" | awk '{print $1}')" \
  --package-receipt-sha256 "$(sha256sum "$PACKAGE" | awk '{print $1}')" \
  --source-commit "$(git rev-parse HEAD)"
```

`renderer_status` accepts only an operation and fresh command ID. The UE game
thread reads the active UE version, RHI, feature level, shader platform, and a
closed allowlist of Lumen, reflection, VSM, TSR, Nanite, exposure, streaming,
screen-percentage, and scalability CVars. Missing or non-finite values fail
closed. The host rejects duplicate keys, unknown fields/schemas, replayed
command IDs, multiple JSON responses, stale evidence, and any mismatch with
the pinned `observation_contract`. It also proves immediately before and after
the exchange that the loopback listener is still the exact packaged-game
process-group listener recorded at readiness. Only the exclusive mode-0600
renderer receipt says `observed_accepted`; no earlier request/build/package
receipt is rewritten or promoted.

Install the package-bound Sunshine entry with a dry run first, followed by the
same command plus `--apply`:

```bash
uv run --offline --project tools python \
  tools/runtime/vista_playable_home/sunshine_app.py \
  --apps "$HOME/.config/sunshine/apps.json" \
  --python /usr/bin/python3 \
  --launcher "$PWD/tools/runtime/vista_playable_home/packaged_entrypoint.py" \
  --profile "$PROFILE" --profile-sha256 "$PROFILE_SHA" \
  --exit-timeout 90 --working-dir "$PWD"
```

The historical packaged profile in this section uses `DISPLAY=:117`. The
human-operated City Sample lane above instead uses `DISPLAY=:118`; Sunshine and
the XTEST relay must always agree with the selected lane. Linger must be
enabled. Moonlight video and NVENC can be ready while control remains blocked:
keyboard/mouse require writable `/dev/uinput`, and gamepads also require
writable `/dev/uhid`. Treat root-only devices as view-only, never as a
successful remote-control setup.

On the accepted host the service name is `vista-sunshine.service`. Stop only
the currently owned packaged world without stopping Sunshine or touching other
UE sessions:

```bash
uv run --offline --project tools python \
  tools/runtime/vista_playable_home/stop.py \
  --workspace "$ATT"
```
