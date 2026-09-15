# Campus demo

This demo combines the six restored indoor spaces with approximate Guangfu campus,
north gate and Daxue Road scenes. It uses the existing car/scooter gameplay and
procedural entry, driving, riding and exit animations.

The visual finish adds photographed broadleaf trees, masked leaves and grass PBR
maps from Poly Haven. The portable source/license/digest record is
`campus-demo-sources.json`; the earlier building/road/vehicle source record remains
`campus-pbr-sources.json`. Original outdoor meshes and collision are retained;
old tree rendering is replaced by instanced trees at the original trunk locations.
Windowed background buildings and perimeter barriers close the demonstration area.
Ambient fill improves readability under canopies. These are authored lighting
and city context, not measured campus illumination or surveyed building geometry.

## Reproduce and validate

Use `acquire_demo_sources.py`, `export_demo_tree.py` and `finish_demo.py` with new
output directories and a fresh Unreal asset namespace. Set the matching revision
in `tools/runtime/vista_campus/layout.py`. Use the project only after its authoring
commandlet has exited; do not run authoring and native rendering concurrently.

Read saved assets with `verify_demo.py`, `verify_saved.py` and `verify_surfaces.py`.
Run all six suites in `run_native.py`: surfaces, tour, vehicles, crossing, home and
animations. Native checks reject failed material compilation and missing material
usage flags in the selected revision; imported asset existence alone is insufficient.
Inspect actual captures and continuous vehicle videos as well as the checks.

Keep a single directional sun in this host's demo. The attempted four extra
directional fill lights stalled/failed inside Vulkan/Lumen's lighting work; the
final author uses real-time sky capture and post-process ambient fill instead.
Retain failed-run diagnostics separately from accepted evidence.

`tools/workspace/freeze_campus_demo.py` requires successful native receipts matching
the current maps, config and binary before making an independent copy. It refuses
to overwrite a project or copy from a running authoring project. The output contains
an inventory plus an explicit campus runtime map, which avoids inheriting the donor
villa's map from workspace scene metadata.

`dev_stream.py --mode preflight` checks the frozen inventory before lifecycle changes.
Register a scoped Sunshine app named **VISTA Campus Demo** using `--mode stream`.
Keep existing apps and authentication files. Select the reviewed project only in
the owned VISTA slot after checking active users; verify the actual GPU, map, input
delivery, and that a second launch resumes the unchanged payload.

## Presenter controls

| Input | Action |
| --- | --- |
| Esc | Click a scene or view the controls |
| WASD + mouse | Move/look; accelerate, reverse and steer while riding |
| E | Perform the visible primary action; enter or exit a stopped vehicle |
| Q | Click contextual actions, room destinations or indoor activities |
| Tab | Switch first/third person |
| Space | Jump on foot; brake on a vehicle |

Windows and macOS both use Moonlight. Obtain the host's current Tailscale address
from the host-local connection guide. Create the Sunshine administrator in its
private web UI, add `HOST:48989` in Moonlight, and submit each client's PIN at
`https://HOST:48990/pin`. Account credentials and pairing secrets stay out of Git
and chat. Client pairing/streaming requires an actual client check; a local renderer
or HTTP response is not evidence that a remote user can see or control the demo.

## Limits

This is a functional research demonstration with approximate architecture and
procedural character animation. It is not GTA-level art, a surveyed NYCU digital
twin, validated vehicle physics, or a completed model benchmark. Scene travel
resets exploration. Persistent cross-map tasks, full controller support and a fully
Traditional Chinese interface remain future work. The barriers bound the authored
area; they do not establish a complete general-purpose respawn system.
