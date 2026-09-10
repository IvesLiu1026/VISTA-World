# Portable lab workstation demos

This release moves seven existing human-demo environments onto the dual RTX 5090
workstation without replacing the source demo, shared Unreal installation, or the
workstation's existing streaming application. Payloads contain 14,132 files
(13,276,824,154 bytes); the catalog binds every included file by SHA-256.

## Release and commands

The runtime account owns `~/vista-world-5090/releases/20260910a`. Use that account
for these commands. The administrator who installs device permissions may be a
different account; `enable-input.sh` resolves the owner of its tools directory.

```sh
release="$HOME/vista-world-5090/releases/20260910a"
"$release/tools/uv" run --offline --no-project --python python3 python \
  "$release/tools/select_demo.py" --environment alpine-villa-r3 --gpu 0
```

| Environment | `--environment` |
| --- | --- |
| Alpine Villa R3 | `alpine-villa-r3` |
| Original VISTA World | `vista-world` |
| Photoreal Kitchen | `photoreal-kitchen` |
| Photoreal Home | `photoreal-home` |
| Home R5 | `home-r5` |
| Villa R1 | `villa-r1` |
| Villa R2 | `villa-r2` |

The interactive release currently accepts `--gpu 0` only. A physical GPU 1 test
reached Vulkan initialization but stalled before presenting to this Xvfb display;
it is not accepted as a working second interactive slot. Both adapters remain
installed and other jobs are preserved. This is one interactive scene at a time;
it does not combine GPU memory or split one Unreal frame across both adapters.
The selector operates only on `vista-5090-game.service` and
`vista-5090-input.service`, with a lock around changes. `--stream` waits for the
new session selection before remaining alive for Sunshine's application slot.
Disconnecting a client leaves the scene available on the dedicated display.

The compact Sunshine menu contains Desktop, Alpine Villa R3, and VISTA World.
The other archived revisions remain selectable with the command above, then
viewable through Desktop. Each release preserves its original controls; R3
uses WASD, Shift, Space, Tab, E, P, F and R.

## Reproduce the transfer

1. Read the `nlplab-admin` skill and current lab workstation document. Confirm
   the target's GPUs, disk, matching UE build, displays, ports and existing jobs.
   `transport.py` resolves the workstation row at execution time, uses existing
   SSH trust with `StrictHostKeyChecking=yes`, and sanitizes textual output.
   Never put endpoint, account or credential values into this repository.
2. Create the owned remote release directory and copy a reviewed static `uv`
   executable into `tools/uv`; no global Python installation is required.
   Supply an app-list snapshot containing the seven source profile commands to
   `export_bundle.py --apps ... --output ...`. It validates source-profile
   digests and excludes payload-root Saved, Intermediate, DerivedDataCache and
   Git directories. Reject rather than silently dereference payload symlinks.
3. Copy payloads with `transport.py send --directory-contents --exclude-runtime`.
   Create each destination `environments/<environment-id>/payload` directory
   inside the owned release before starting a transfer.
   There is no rsync deletion. Keep catalogs and binary assets outside Git.
   This release's final catalog is `catalog-r2.json`, SHA-256
   `0ad1548e0dba0a786f3273521c2038e8af1bfeabc65da7c9dd5409a4b75d118b`.
   A different catalog requires an explicit review/update of the selector's pin.
4. Copy these helpers and the reviewed relay dependency into the remote tools
   directory. The relay source is VISTA-World commit
   `55b4f1d809fa3d7a59f26102a26ca53c4a5b36f6`, file
   `tools/runtime/input_relay/sunshine_x11.py`, deployed as `input_relay.py`.
   Its required SHA-256 is
   `6c54a2c636de8d5e8cc6959c742c3f46350265e72bc095930290ef812e3970e0`.
5. Run `launch_bundle.py --action verify` for every catalog entry, then remove
   write bits only within those verified payload directories. Runtime files,
   input state and caches live outside the payloads. Verify again after testing.
6. An administrator reviews and runs `sudo sh /absolute/release/tools/enable-input.sh`.
   The root script grants an additive `vista-streaming` ACL to virtual input
   devices and preserves the distribution's input group. It upgrades only the
   exact earlier VISTA rule digest or an identical current rule. It does not
   restart a desktop, GPU process, display manager or user service manager.
7. Check that the dedicated display and configured alternative stream port
   range are available. Run `configure_streaming.py` once, then start/enable
   `vista-5090-sunshine.service`. It requires the dedicated authenticated Xvfb
   display. An existing VISTA config or unit causes the installer to stop for
   review instead of overwriting it. Existing default Sunshine config stays intact.

The service binds only the current private Tailscale IPv4 resolved in memory;
UPnP is off. Its new port range is separate from the pre-existing streaming
service. Obtain the host and configured port from the live environment rather
than copying infrastructure endpoints into notes. Use a fresh Sunshine admin
account and fresh Moonlight pairing; no source credentials, certificates or
paired-client state are copied. Passwords and pairing PINs stay in the private UI.

## Rendering and input behavior

The matching shared engine is UE 5.7.3, changelist 50162420. Its executable is
resolved from the runtime account's existing engine location, or from
`VISTA_UNREAL_EDITOR`, and the build is checked. The packaged World retains its
`realistic_interior_r2` camera flag and loopback adapter.

On the target, R3 twice failed on frame 2 in
`Shadow.Virtual.ProcessInvalidations` with `VK_ERROR_DEVICE_LOST`. A pipeline
LRU setting did not resolve it. Setting `r.Shadow.Virtual.Cache=0` for these
launches allowed rendering and native camera/movement checks. Virtual shadows
remain enabled, but their cache is disabled, which may cost performance. This
is a measured workaround, not proof of the underlying driver/engine cause.
Epic documents the cache toggle in its
[Virtual Shadow Maps guide](https://dev.epicgames.com/documentation/unreal-engine/virtual-shadow-maps-in-unreal-engine).
Related RTX 50-series reports appear in this
[Epic support discussion](https://forums.unrealengine.com/t/discussion-of-gpu-crash-in-virtualshadowmappageoverlap-ush/2697770).
Neither the shared engine nor the GPU driver was changed.

Sunshine initializes `h264_nvenc`, limits the stream to 4 Mbps, and advertises
H.264 for the initial Windows compatibility check. Host capture/encoder readiness
does not establish end-to-end client frame rate or latency.

The XTEST relay accepts only one matching, full-display Unreal window.
`stream_host.py` snapshots virtual input devices before starting this Sunshine
instance and pins the three newly created Inputtino devices. Ambiguous creation
fails closed. `input_guard.py` checks those pinned sysfs paths, node identities,
and the tracked Sunshine lifetime before opening a device, so a global udev
symlink changing to a different stream's device does not grant it input access.
The device snapshot is an operational guard, not a boundary against hostile
processes running as the same account.

## Validation and limitations

`native_check.py` selects the scene, waits for the expected X11 window and shader
workers, rejects a black capture, saves screenshots, and matches the actual UE
PID to a physical GPU through NVML output. Optional `--keyboard` injects Tab,
W and R on the dedicated display; inspect the resulting images before accepting
camera or movement behavior. Screenshots taken while shaders are still compiling
must be superseded, not used as visual acceptance. Test receipts identify the
runtime session and explicitly distinguish XTEST from Moonlight client evidence.
`check_virtual_input.py` separately writes bounded camera-toggle presses for
Alpine or forward/back movement for World to the pinned virtual keyboard. This
exercises the live guarded relay rather than injecting XTEST events directly.
Review those images as well; it still does not substitute for a Windows client.
The archived World package did not respond to V-camera toggling in this check;
do not infer that it has every binding present in the latest source tree.

The launcher selects only the installed NVIDIA Vulkan ICD and disables Mesa's
implicit device selection. Loading every installed ICD exposed duplicate GPU
entries on this host, so Vulkan adapter index 1 initially still ran on physical
GPU 0. Never accept the requested index alone as evidence of adapter selection.
With the ICD fixed, physical GPU 1 was selected but presentation did not complete.
The public launcher rejects that selection before stopping a working GPU 0 demo.
NVIDIA's [multi-GPU headless discussion](https://forums.developer.nvidia.com/t/headless-vulkan-with-multiple-gpus/222832?page=2)
describes related virtual-display limitations; resolving a second interactive
slot would require a separate, validated display/container configuration.

This workstation does not currently permit the unprivileged network namespace
used by sealed evaluation profiles. Launches are explicitly `human-demo` with
`network_namespace=false`; they are not benchmark/evaluation acceptance. Analytics,
message transports and ARKit live-link are disabled without changing global
AppArmor, sysctl, drivers, mounts or other users' jobs.

Root permission repair, private admin setup and Windows pairing must each be
verified independently. Do not mark the migration fully accepted merely because
native screenshots or the encoder probe succeed. The machine's existing GTA
stream and the original source-host demo remain separate services.

```sh
uv sync --frozen
PYTHONPATH=tools uv run python -m unittest \
  tools.tests.test_vista_playable_home_contracts \
  tools.tests.test_vista_playable_home_compiler -v
uv run python -m unittest tools.tests.test_vista_lab_migration -v
sh -n tools/runtime/vista_lab_migration/enable-input.sh
git diff --check
```

To stop this release, stop only its `vista-5090-input`, `vista-5090-game` and
`vista-5090-sunshine` user units, then its display; disable only its Sunshine
unit if automatic startup is no longer wanted. Keep assets and evidence for
rollback. Device ACL/rule removal is a separate administrator action and must
preserve the distribution rules and other streaming users.
