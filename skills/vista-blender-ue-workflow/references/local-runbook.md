# Local entry points — 2026-09-10

Version-specific examples; resolve the current worktree and rules first:

- Source: `/data/sysx/vista-world/worktrees/vista-villa-design-motion-r1`
- Outputs: `/data/sysx/vista-world/runs/vista-villa-r1-20260910a`
- UE 5.7.3: `/mnt/NAS2/yhliu/UE_5.7.3_prebuilt`
- Blender: `/home/yhliu/.local/opt/blender-4.5.8-linux-x64/blender`
- Preserved R5: `/data/sysx/vista-world/runs/vista-home-first-person-r5-20260908a/project-c/PhotorealHome.uproject`

Follow known manifests; do not scan unrelated NAS directories. Verify source hashes.

From the writing worktree:

```sh
uv sync --frozen
PYTHONPATH=tools uv run python -m unittest tools.tests.test_vista_playable_home_contracts tools.tests.test_vista_playable_home_compiler -v
git diff --check
```

`tools/runtime/vista_home_first_person_r5/prepare_project.py` copies a source
project/plugin into a fresh authoring project. Read its CLI/receipt. Replace only
the new copy's plugin after a successful build. Update binary hashes afterward;
the preparation receipt no longer describes replaced binaries.

```sh
/absolute/blender --background --python-exit-code 1 --python tools/blender/vista_villa_r1/build_hero_props.py -- --materials /absolute/materials.json --out /absolute/fresh-assets
```

The prop script verifies CC0 oak maps and vessel geometry, then exports a tray,
mug and carafe. Native import/contact are separate. Retained PBR source:
`/data/sysx/vista-world/runs/vista-home-materials-r4-20260908a/materials-a/materials.json`.

`tools/runtime/vista_villa_r1/design_gallery.py --designs <dir> --out <fresh-dir>`
writes a PNG-validated HTML/Markdown book. Its shot list is specific to one design
batch; adapt it for a different house rather than making placeholder images.

For native builds, use current `RunUAT.sh BuildPlugin`, the source `.uplugin` and
a fresh `-Package=` path. `-NoTargetPlatforms` builds the editor plugin used by
`UnrealEditor -game`; packaged shipping targets require another check. Limit CPU
affinity and use `bwrap --unshare-net` for this local run. Do not modify the shared
engine to fix a private plugin.

For slow cold shader compilation, `tools/runtime/vista_villa_r1/configure_cache.py`
can add a private DDC graph with known donor caches opened read-only and a
separate writable cache. Use `--ddc-graph VistaVillaR1Cache` after that setup.
The runner cleans detached shader workers belonging to its own output directory
after a bounded run; never terminate workers belonging to another demo.

UE Python uses `UnrealEditor-Cmd <new.uproject> -run=pythonscript -script=<script>
-NullRHI -Unattended` with fresh user/DDC paths and disabled messaging.
`tools/ue/vista_villa_r1/inspect_native.py` reads real bindings/parameters; set
`VISTA_VILLA_INSPECT_OUT` to a fresh receipt. `build_fluid_lab.py` creates a
separate map and tests parameter rejection; set `VISTA_VILLA_FLUID_AUTHOR_OUT`.
Check exit status as well as receipts. An editor may save successfully and crash
on shutdown; read back the asset in a fresh process before acceptance.

`tools/runtime/vista_villa_r1/run_native.py --project <new.uproject> --out <fresh>
--engine <engine> --mode poses` runs 12 native pose/interaction cases without a
display. Use `tools/runtime/vista_home_first_person_r5/verify_pose.py` on
`user/Saved/FirstPersonProof/poses.json` and `bridge/`. The separate Blender
`tools/blender/vista_home_first_person_r5/render_pose.py` reconstructs those poses
and checks visible body surfaces; its images are not Unreal screenshots.

For `--mode fluid --gpu <available-index>`, check GPU use first. The local NVIDIA
ICD is `/usr/share/vulkan/icd.d/nvidia_icd.json`; without it this host can select
llvmpipe. This host's driver also requires a DISPLAY for Vulkan: use a temporary
`xvfb-run` display inside the private network namespace, as the runner does.
Verify the actual native device; stop the private probe on fallback. Do not use
the live demo's display/input or restart Sunshine for isolated verification.

Official references, checked against the installed version:

- [Game Animation Sample, UE 5.7](https://dev.epicgames.com/documentation/unreal-engine/game-animation-sample-project-in-unreal-engine?application_version=5.7)
- [Hair rendering](https://dev.epicgames.com/documentation/unreal-engine/hair-rendering-and-simulation-in-unreal-engine)
- [Fluid overview](https://dev.epicgames.com/documentation/en-us/unreal-engine/fluid-simulation-in-unreal-engine---overview)

These document capabilities, not completed installation of motion databases,
grooms, new characters or a volume-coupled Home fluid system.
