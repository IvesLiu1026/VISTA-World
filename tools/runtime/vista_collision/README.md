# Indoor repair and continuous recording

User preferences, 2026-09-16: new demonstration videos use **English male speech
and English captions**. Deliver **two separate uninterrupted videos**, one always
first person and one always third person. Walk through the connecting spaces;
no room teleport, viewpoint switch, console/menu footage or montage during a take.

`six_rooms.json` defines a shared route. `ExplorerWalkthrough` is a scripted HUMAN
controller available only with `-VistaPrivateReview`; it applies movement input
through the normal character movement/collision and animation pipeline. Camera
turns have bounded angular speed. It stops on blockage or changed view. It never
claims learned planning or assistant manipulation. Separate takes share a route,
but are not frame-synchronous recordings of the same simulation episode.

`review.py` runs native camera/wall/backpack checks and records either fixed view.
Use the existing `vista_companion/private_runtime.py` on an isolated project and
X display, then pass that process receipt via `--run`; live displays are refused.
Before a take, install `six_rooms.json` as `Config/VistaWalkthrough.json` and prepare
the English phrases with `vista_streaming/prepare_speech.py`. That tool now uses
the bundled synthetic male US news anchor reference; it stores the reference
hash with each clip. The live conversational service keeps its existing defaults
until separately updated; changing the recording voice does not change it.

The scene repair script moves the backpack, peg and all corresponding interaction
anchors together to a supported mount on the bedroom east wall. It replaces the
unbound floating electrical decorations with plates on the living-room partition.
No frozen map or donor asset is edited. The camera uses a 3-cm local near plane
and a collision sphere covering all its corners, including initial penetration
handling; companion capsules also block the human capsule. The third-person boom
is 260 cm with a 35 cm-high anchor and 45 cm shoulder offset, giving the follower
more clearance on stairs. Camera collision evidence is sampled after resolution
of the current camera, not from the previous-frame camera cache during actor Tick.
Recordings retain the existing private runtime's disabled virtual-shadow cache;
enabling it caused a Vulkan device loss on this host. Engine warning messages are
not suppressed. A non-Nanite shadow queue warning remains a renderer limitation.

`clear_office.py` moves the study desk, chair, screen and desk props together by
50 cm, updating their task anchors. This recovers a passage around the open door.
Following retains three-dimensional breadcrumbs across walls and stairs. When a
human reverses toward the companion, it samples supported, collision-clear
positions and walks aside to let them pass. This is a local follower heuristic,
not a general navigation planner. The take checks retain the actual capsule gap
and final three-dimensional distance as evidence.

`build_review.py` accepts only two takes with all seven native checks passing,
preserves an inventoried earlier gallery, and creates a two-video landing page.
The gallery uses the existing private, allowlisted review server; it does not
publish runtime state, hidden event data or source files.

Native screenshots and checks, source/build logs, route traces, generated speech
and videos belong in new workspace run directories, outside Git. Validate actual
view, collision, map continuity, audio and movement before delivery. A successful
walk is limited to the tested route; it does not establish universal contact,
door, finger, or navigation correctness.
