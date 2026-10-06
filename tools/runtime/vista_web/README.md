# Browser access to the existing Unreal environment

This endpoint streams the selected VISTA native game window and its audio. Browser
input operates that same character, object state, menu and assistant runtime.
It does not export, decimate or replace any meshes, hair, materials or animation.
It supersedes the rejected lightweight reconstruction in `web/demo`.

## Run privately

Use the workspace `uv` entrypoint and a separate environment (put dependencies on
NAS scratch if the root disk is low). No Unreal rebuild is required.

```sh
uv venv /path/to/native-web-venv --python 3.12
uv pip install --python /path/to/native-web-venv/bin/python \
  -r tools/runtime/vista_web/requirements.txt
PYTHONPATH=tools /path/to/native-web-venv/bin/python -m runtime.vista_web.server \
  --workspace /path/to/workspace --project six-room-companion-dev-natural-b \
  --bind TAILSCALE_IP --port 49240 --origin http://TAILSCALE_IP:49240
```

Requires system ffmpeg with x11grab, PulseAudio and h264_nvenc support, the selected
GPU0/:119 Unreal game, its Xauthority and `vista_live_audio.monitor`. The existing
`WindowSource` validates selection, native PID, executable, display and window
class. No desktop capture, extra renderer, external service, model inference or
cloud TTS is started. Video capture/NVENC and monitor recording run on demand and
stop after the last viewer disconnects. The configured origin must exactly match
the URL used to open the page. Bind only on an authorized private interface.

Choose **Enter environment**. WASD moves, drag looks, Shift jogs, Space jumps;
**Switch view** changes first/third person. **Rooms** opens the *native* six-room
menu; click a room in the streamed picture. **Actions** opens the native activity
menu, **Interact / E** executes the visible action and G puts an object down.
Menu clicks account for video letterboxing. The touch pad provides movement on
small screens. Sound may require a second click because of browser autoplay rules; the picture
then plays muted rather than paused.
Pointer lock/fullscreen are optional; drag works when insecure-origin browser
restrictions prevent pointer lock.

## Transport and input invariants

- One server-rendered world, up to three viewers and one browser input controller.
  Other viewers can take control only after release/expiry. Moonlight shares this
  world and is not part of the browser lease; avoid operating both simultaneously.
- Actual 1920x1080, 30 Hz H.264/NVENC with a one-second keyframe interval; mono
  48 kHz Opus audio comes from the existing native VISTA audio monitor. Configure
  H.264 preferences **before** remote SDP negotiation; packet passthrough must not
  be mislabeled as VP8. aiortc is pinned because its packet/relay internals are used.
- Encoded interframes are buffered in order, never discarded with a latest-only
  relay. Disconnect a viewer exceeding 60 queued video packets, instead of growing
  latency/memory without bound or silently corrupting prediction frames.
- A controller sends full key snapshots every 50 ms with increasing sequence
  numbers. An input gap of 1.2 seconds releases held keys but keeps the controller,
  so a relay hiccup (Tailscale starts on DERP before its direct path) cannot hand
  the world away; the next fresh snapshot presses what is still held. Eight
  seconds without input ends the lease. Stale messages cannot renew a lease or
  press keys, including after the same viewer re-claims. Blur only lifts held keys;
  a hidden page, leave and disconnect release ownership.
- The page re-claims on a game key, a click in the picture or a toolbar action,
  and on returning to the tab or after its lease lapsed unless the viewer chose
  Release control. A claim never overrides another controller; `/health` records
  `input_stalled`, `control_expired` and `claim_rejected` for diagnosis.
  Channel close tears down the peer immediately; a crashed viewer missing all
  heartbeats is removed after ten seconds even if ICE still reports connected.
- Only reviewed game keys and bounded relative mouse motion / viewport clicks are
  accepted. No console, command execution, clipboard, filesystem or arbitrary
  native bridge operation is exposed. Each input checks the selected native window.
- Offers require the configured same origin and JSON content type. Only four
  explicit static files are served; no state folders, assets or credentials are
  exposed. `/context` is small privileged **human UI** metadata, never policy input.
- A browser running on the server must play audio to a separate test sink or stay
  muted to prevent feeding the received audio back into the native monitor.

## Validation

```sh
PYTHONPATH=tools python -m unittest tools.tests.test_vista_web_control -v
# Requires this module's pinned requirements, no native game or GPU:
PYTHONPATH=tools python -m unittest runtime.vista_web.test_server -v
```

The first suite covers input stalls, lease expiry, disconnect-equivalent release,
exclusive ownership, stale and replayed packets, native selection changes, key
validation and viewport bounds. The second exercises HTTP origin/schema/file guards and real WebRTC offer
negotiation, asserting that only H.264 is negotiated for packet passthrough.

Actual browser acceptance must additionally check decoded frames, native movement
and rotation, both views in all six rooms, native menu clicks and object actions,
native speech reaching the remote audio track, a paused input producer, tab close,
and capture teardown after the last viewer. Use a cached native speech clip to
verify audio without making a provider call; label this as a transport test.
Frame rate from a same-host browser is not a WAN latency or Mac/Safari result.

## Remaining deployment boundaries

This is a private Tailscale/LAN browser entry, **not a completed public website
deployment**. ICE uses host candidates; no STUN/TURN, public session authentication,
queue or per-visitor Unreal instance is provisioned. A static Cloudflare upload
cannot host this GPU-backed process. Public `ivesliu.org` integration still needs
an authenticated signaling route and reachable media/TURN, followed by a real
off-network test. Existing Cloudflare Access and DNS are unchanged.

The original research authoring/chat service remains separate. This transport does
not add a new language-model policy or expose arbitrary chat text entry through
the native keyboard allowlist. Existing native clipping, camera and motion defects
are not fixed by streaming; they remain visible exactly as in the source game.
