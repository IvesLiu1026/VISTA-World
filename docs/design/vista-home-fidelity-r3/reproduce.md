# Reproduction inputs

Run from the R3 worktree. Use a fresh output for each attempt; accepted R1/R2
and failed R3 attempts are read-only. Runtime, Blender and UE outputs stay
outside Git. Python commands use `uv`; Blender scripts use the retained
4.5.8 authority with `--background --python-exit-code 1 --python SCRIPT -- ARGS`.

| Stage | Script under `tools/blender/vista_home_fidelity_r3/` | Selected output |
| --- | --- | --- |
| Source inventory | `inspect_source.py` | `inventory/character.json`, `inventory/cardboard.json` |
| Metric material UVs | `build_material_revision.py` | `materials-b/materials.json` |
| Eye/skin material source | `build_character_revision.py` | `character-b/character.json` |
| Fitted photo box | `build_box_revision.py` | `box-b/parts.json` |
| Moving handles | `build_hardware_revision.py` | `hardware-a/parts.json`, `hardware-a/contacts.json` |
| Hardware PBR revision | `build_material_revision.py` | `materials-c/materials.json` |
| Finger frames/contact triangles | `build_contact_revision.py` | `contacts-j/fine-contacts.json` |
| Existing curved burner supports | `build_support_revision.py` | `supports-a/parts.json` |

The material stage merges the whole-home R1 manifest and R2 `model-c`/`model-d`
manifests, using the retained Poly Haven acquisition receipt. The hardware
stage uses R2's `home-actions.blend` and the R1/R2 manifests. Contact authoring
uses the fitted `embodied-r1-20260907a/model/body-b/body-grip-authoring.blend`,
the accepted cup GLB and the merged manifests, with `box-b` and `hardware-a`
last. Pass `--contact-overrides hardware-a/contacts.json` to use isolated
handle surfaces. All these inputs are hash-bound in the selected artifacts.

`tools/runtime/vista_home_fidelity_r3/verify_assets.py --materials PLAN --out
FRESH_REPORT` checks triangle equality, UVs, material identity and image hashes.
Source bounds for UE use the glTF-to-UE coordinate map `(x, z, y) * 100`.

Build the plugin in a network namespace:

```sh
/usr/bin/bwrap --unshare-net --die-with-parent --dev-bind / / -- \
  /mnt/NAS2/yhliu/UE_5.7.3_prebuilt/Engine/Build/BatchFiles/RunUAT.sh BuildPlugin \
  -Plugin="$PWD/unreal_plugins/VistaPhotorealReview/VistaPhotorealReview.uplugin" \
  -Package=/absolute/fresh/build -TargetPlatforms=Linux -Rocket
```

Prepare a fresh project with `tools/ue/vista_home_fidelity_r3/prepare_project.py`
and `--source`, `--out`, `--plugin`, `--contract`, `--contacts`. This inherits
assets, binds the contract hash and installs the privileged contact file in
`Config/VistaFineContacts.json`.

UE import scripts in `tools/ue/vista_home_fidelity_r3/` take a JSON configuration
path through the following environment variables. Retain the selected configs
as examples, then change asset namespace and result paths for a new attempt.

| Script | Variable | Selected configuration/report |
| --- | --- | --- |
| `import_material_revision.py` | `VISTA_HOME_FIDELITY_CONFIG` | `import-materials-d-config.json`, `import-materials-d.json` |
| `import_character_revision.py` | `VISTA_HOME_CHARACTER_CONFIG` | `import-character-h-config.json`, `import-character-h.json` |
| `import_prop_revision.py` | `VISTA_HOME_PROP_CONFIG` | `import-box-m-config.json`, `import-box-m.json` |
| `import_material_revision.py` | `VISTA_HOME_FIDELITY_CONFIG` | `import-hardware-n-config.json`, `import-hardware-n.json` |
| `repair_resting_pose.py` | `VISTA_HOME_RESTING_CONFIG` | `repair-resting-x-config.json`, `repair-resting-x.json` |
| `import_support_revision.py` | `VISTA_HOME_SUPPORT_CONFIG` | `import-supports-x-config.json`, `import-supports-x.json` |

The final pot repair is applied to a fresh copy of verified `project-t`, with
`build-n`. Run `repair_resting_pose.py` with `repair_pot_collision: true`, then
`import_support_revision.py`. The retained `import-resting-supports-x.py`
commandlet wrapper executes this sequence. This changes the pot base collision,
raises only pot/lid initial placement by 2 cm and adds convex physical volumes
for the four original grate bars. It does not add a support plane or change
existing render geometry. The source supports come from R2 `model-c`.

Run every UE commandlet through the same network namespace with
`-run=pythonscript -script=SCRIPT -NullRHI -Unattended -NoAnalytics`, a fresh
`-UserDir`, and `-DDC=VistaHomeActionsCache`. Do not accept a zero Blender exit
without `--python-exit-code 1`, or a saved UE report alone after an engine
shutdown failure. Verify the saved native assets by loading and interacting.

The selected map is `/Game/VISTA/PhotorealHomeR1/Maps/Home`. The inherited
`tools/runtime/vista_home_actions_r2/start_validation.py` starts the owned
validation display `:120`, with fresh user and bridge directories. Never drive
`:119` validation input while the user is connected through Sunshine.

The native checks take `--bridge`, `--user-dir`, `--out`:

```sh
uv run python tools/runtime/vista_home_fidelity_r3/run_native_checks.py --suite details ...
uv run python tools/runtime/vista_home_fidelity_r3/run_native_checks.py --suite sequences --timeouts ...
uv run python tools/runtime/vista_home_fidelity_r3/probe_precision.py ...
uv run python tools/runtime/vista_home_actions_r2/probe_protocol.py ...
uv run python tools/runtime/vista_home_fidelity_r3/review_fine.py ...
uv run python tools/runtime/vista_home_fidelity_r3/probe_motion_contact.py ...
uv run python tools/runtime/vista_home_fidelity_r3/probe_resting_prop.py ...
```

The R3 fixture wrapper verifies actual player position after physics. It fixes
the old living-door fixture, which was displaced by collision, before testing
the real handle. Kitchen-door operation starts on the handle side of the open
leaf; the northern fixture can trap the closing path beside the shoe bench.
The blocked attempt is retained. The wrapper does not teleport an already held prop.

`record_review.py` additionally takes `--candidates` and records the seven
native episodes into opaque review directories. Validate each exported
`restricted_assist_step_input.json` with the inherited
`validate_vista_contract.py --vista-root /home/yhliu/VISTA --input INPUT
--out FRESH_REPORT`, using `uv run --project /home/yhliu/VISTA --no-sync python`
so the actual VISTA dependencies are available. Only the video and selected external dialogue are model
inputs. No model API call is part of this authoring or review workflow.

`collect_evidence.py` binds reports to the running engine process, its project,
bridge, plugin binary, packaged source, contact file and map. Preserve the
complete K/T interaction report separately from the final N/X pot follow-up;
`validation/pot-repair-scope-b.json` records the exact source/content difference.
Do not change the scoped final report's `native_coverage_complete: false` to
imply a repeated full suite.

For the existing development viewer, point the owned
`vista-home-actions-review-r2.service` to `vista-review-candidates-c` with its
existing `tools/native_home_review.py` runner on port 8001. The retained
`validation/viewer-install-a/after-unit.txt` gives the exact command. Do not
restart the production API on port 8000.

The Sunshine installer accepts
`--launcher tools/runtime/vista_home_fidelity_r3/launch_review.py`. Inspect its
dry-run output, then apply only the named **VISTA Photoreal Home** entry with
the new profile. The selected profile is `sunshine-review-profile-n.json` and
the initial installation receipt is `sunshine-entry-final/verification.json`.
Installing the entry leaves the active stream running. This Sunshine version
caches its application list; a direct disk write alone does not establish that
the next client launch uses it. The pinned
[application registry implementation](https://github.com/LizardByte/Sunshine/blob/14ffa6fdaa53f7b51512be2b3d24f3939695403c/src/process.cpp)
and retained connection logs informed the final reload. Verify actual client
disconnects before a reload: a retained Desktop can still report BUSY without
an active connection. `sunshine-entry-final/reload-c.json` records the guarded
reload of the actual `vista-sunshine.service`, followed by `home-start-a.log`
and `live-runtime-a.json` binding the final running Home. No credentials were
changed. An explicit client selection uses
`--action stream` to switch only Home's game/input services to the new project;
manual `--action start` refuses to switch while Sunshine is busy.
