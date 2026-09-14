# Six-room audit and reference avatar

This workflow reads the retained Home and Villa maps and builds a locally
reviewable utility outfit on the existing CC0 body. Generated assets, photos,
engine logs and previews stay outside source Git. It does not select or restart
the shared Sunshine/game slot.

The accompanying Chinese design document is
`docs/design/vista-reference-avatar/rooms-and-cases.zh-TW.md`.
Its new cases are proposals, not completed experiments.

## Inputs and stages

Use a materialized, isolated project whose directory is exactly
`projects/villa-reference-avatar/payload/PhotorealHome.uproject`, and a fresh output
directory for each attempt. Keep the original photo local; no script reads or
uploads it. Use the workspace's Blender and uv wrappers.

1. Run `tools/ue/vista_reference_avatar/inspect_sources.py` using UE's Python
   commandlet with `VISTA_AVATAR_INSPECT_OUT`. It saves `maps.json` before trying
   the skeletal FBX exports, then writes export digests and material bindings.
   FBX skeletal export needs **Vulkan + AllowCommandletRendering** on this host;
   NullRHI hits `GetCPUSkinnedVertices` assertions. `FbxMaterialBakeMode.DISABLED`
   alone does not fix that. The successful export attempt later crashed during
   engine teardown: inspect artifact digests and parse the FBX independently.
2. Run `tools/blender/vista_reference_avatar/inspect_fbx.py` with
   `VISTA_AVATAR_FBX` and fresh `VISTA_AVATAR_BLENDER_OUT`. This imports the world
   FBX, reports geometry/bones/materials and saves `source.blend`.
3. Run `tools/ue/vista_reference_avatar/export_preview_textures.py` with fresh
   `VISTA_AVATAR_TEXTURE_OUT`. NullRHI is sufficient. On-disk material dependencies
   locate the existing texture sources when compiled shader texture lists are
   unavailable. Exports include original digests.
4. Run `tools/blender/vista_reference_avatar/build_avatar.py` using Blender
   `--background --threads 8 --python-exit-code 1 --python SCRIPT`, with:
   - `VISTA_AVATAR_BLEND`: inspected `source.blend`;
   - `VISTA_AVATAR_TEXTURES`: texture export directory;
   - `VISTA_AVATAR_MOTION_CONTRACT`: retained `Content/VISTA/VillaR1/mocap.json`;
   - `VISTA_AVATAR_OUT`: fresh output directory.
5. Run `verify_asset.py --asset OUTPUT --motion-contract MOCAP --out NEW_JSON`.
   This parses both real GLBs, verifies the 53 joint set, finite data, normalized
   weights, joint indices and export hashes. Merely counting bones is insufficient
   to establish animation compatibility.
6. Run `tools/ue/vista_reference_avatar/import_avatar.py` in the private project
   with `VISTA_AVATAR_SOURCE`, fresh `VISTA_AVATAR_IMPORT_OUT`, and a new
   `VISTA_AVATAR_REVISION` (namespace below `/Game/VISTA/ReferenceAvatar/`).
   It preserves old appearance paths in its receipt and only updates the private
   appearance file after both meshes match the exact native motion bone order.
7. Run `run_native.py --project PROJECT --engine UE_ROOT --out NEW_DIR --ddc CACHE`.
   It captures the existing 12-case Villa motion probe, reports actual GPU UUID,
   uses a private X display, and cleans only its own processes. Review the pixels.
   `capture_complete` is a capture status, **not** visual acceptance.
   `--probe alpine` additionally exercises the existing outdoor walk/run/jump and
   garden-door probe, useful for inspecting dark cloth under outdoor lighting.

## Bone conversion and rendering requirements

Blender's FBX importer represents native `root` as the armature object, leaving
52 explicit bones. Its displayed axes also differ from the runtime reference
pose. Adding the missing root alone passes the name check but deforms badly
under existing animation. The build restores root, bakes unit conversion and
reconstructs all local reference transforms from the existing motion contract.
It checks retained joint world positions within 0.01 mm and preserves body weights.

The motion contract here is an internal rig reference used in asset engineering.
It is not copied into the output GLBs as animation clips, used as model input,
or claimed as newly licensed training/evaluation data.

On this RTX 5090 host, native validation uses Vulkan, `graphicsadapter=0` and
`r.Shadow.Virtual.Cache=0`. Existing scoped GPU probes found the virtual-shadow
cache path can stall or lose the device. Fixed 30 Hz is simulation timing, not
a measured rendering frame rate. These are local engineering probes; they are
not isolated model-evaluation jobs.

Use `-noexceptionhandler -NoAnalytics -notraceserver` for owned UE commandlets and
probes. The earlier `-nocrashreports` flag did not prevent the engine crash handler
from invoking CrashReportClient; that failed attempt's diagnostic upload is
recorded in the local handoff. The portrait is never a commandlet input.

## Remaining limits

The photo provides only one view. Face likeness is approximate. The new pocket
flaps are skinned geometry, with no cloth dynamics or functional item container.
The inherited hand grasp, finger contact and locomotion need separate quality
work. Native preview is required before selecting this avatar for a user session.
No source binaries, model experiment results or new six-room runtime actions are
included in this change.
