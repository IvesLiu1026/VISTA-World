# Native human materials and motion refinement

The six-room human uses the MakeHuman CC0 `young_asian_male` skin and `short04`
authored hair mesh. The downloaded hair is fitted to the existing head, tinted
dark and weighted to its head joint. An opaque scalp layer and a two-sided
masked strand material prevent bright gaps and missing backfaces. Dark glasses
frames retain the reference outfit. The same skin material is assigned to the
world body and first-person owner body.

The 53-joint bind hierarchy, clothes and seven facial morph groups are retained.
This is an asset/material revision, not a new motion-capture set or a full
character replacement. It does not establish GTA-quality realism. Microsoft
Rocketbox Male_Adult_09 was also downloaded as a candidate, with its MIT license;
it is not the deployed human and is not used to supply the existing face morphs.

## Reproduce

1. Download the MakeHuman system archive identified by
   `assets/manifests/human-polish-cc0.json`. Verify its SHA-256 and extract the
   listed files into a separate external asset directory.
2. Run Blender's `tools/blender/vista_companion/polish_human.py` with `--source`
   pointing to the accepted expressive human blend, `--motion` to the villa
   mocap JSON, `--assets` to the extracted archive, and a fresh `--out` directory.
3. Inspect front/side renders, exported GLB materials, unchanged bone order and
   morph targets. Set `VISTA_HUMAN_SOURCE` to that output and
   `VISTA_HUMAN_IMPORT_OUT` to a fresh receipt directory. Run
   `tools/ue/vista_companion/import_polished_human.py` in the independent
   `six-room-companion-dev-natural-c` project with the Python commandlet/null RHI.
4. Build the scoped native plugin and run the actual GPU scene privately before
   selecting the new project. Import success alone is not rendering acceptance.

The importer uses direct automated Interchange for textures and meshes.
AssetTools texture imports can invoke Slate notifications and crash a headless
commandlet. Existing asset packages are never overwritten. `HumanPolishR2` is a
fresh namespace; an earlier failed import's unused R1 texture is retained only
in the private project.

## Motion changes

- Camera mode changes fade the neck correction instead of abruptly bypassing it.
- Brief stops during direction reversals retain the support-foot phase and blend
  heading. An actual return to rest can initialize a fresh stride.
- The explorer's indoor Shift key now reaches the existing jog controller.
  Opening a menu or releasing Shift clears that controller. Existing speed and
  interaction constraints remain in the HomeActions layer.

`test_vista_body_look` compiles the same angle update as the engine and checks
wrapping, pitch/yaw limits, view blend continuity and stalls. The private native
`review_human_polish.py` exercises real keys and measures finalized bone poses.
It rejects missing traces, a head jump on view switching, and a nonfunctional
indoor jog. `review_anatomy.py` covers six rooms, both views, directional movement
and pickup/release; `analyze_anatomy.py` checks bind/limb/shoulder/neck invariants.
`review_ground_motion.py` checks routes in fixed views and physical assistant
contacts without calling a model.

## Measured scope

On the same host at a 30 FPS private target, a short repeated view-toggle probe
reduced the largest adjacent head rotation from 65.68 to 12.99 degrees. The
rapid direction-reversal probe's largest joint step changed from 28.63 to
19.71 degrees. Indoor Shift reached 225 cm/s and a nonzero run blend (0.625).
These are bounded native input probes; neither complete action coverage nor
universal collision/biomechanical correctness follows from them.

The authored groom has 9,694 vertices versus the prior 937,200 fiber vertices.
The corresponding human GLB is 18.5 MB versus 78.6 MB. These are asset counts,
not a measured live FPS/VRAM improvement. Preview and live game lighting differ;
judge the actual native view for presentation quality.

Source/license details: [MakeHuman system assets](https://static.makehumancommunity.org/assets/assetpacks/makehuman_system_assets.html),
[CC0](https://creativecommons.org/publicdomain/zero/1.0/),
[Microsoft Rocketbox](https://github.com/microsoft/Microsoft-Rocketbox).
External models, textures, generated packages and recordings remain outside Git.
