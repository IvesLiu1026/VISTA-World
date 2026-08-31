# R15 detail-action UE asset-contract automation

## Status and scope

`VISTA.PlayableHome.R15DetailActions.AssetContract` is an Editor automation
proof for a project that already contains the quarantined R15 detail-action
assets. The proof is source-only until an authorized UE run compiles it and
executes it against those assets. It does not accept motion quality, authorize
runtime execution, or promote any package to production.

The test owns no runtime behavior. It only reads assets and verifies:

- an exact cold on-disk inventory of 9 `AnimSequence` + 9 `AnimMontage`
  packages under `/Game/VISTA/MakeHumanCC0/R15/DetailActions`;
- exact object paths and exact R6 skeleton identity;
- 30 fps, each clip's closed frame range, 53 named source bone tracks, forced
  reference-pose root lock, disabled root motion, and zero root-track delta at
  every source frame;
- one default slot, one segment, and one montage iteration for every clip,
  including `seated_idle_loop` (repeat policy remains a runtime concern); and
- all 16 per-clip typed notify occurrences: the closed vocabulary contains 14
  unique signal names, with the two shared contact signals checked at both of
  their clip-specific frame times.

## Cold-load precondition

Run this automation test first in a fresh UnrealEditor-Cmd process. Before the
test loads an object, it requires all 18 R15 object paths to be absent from the
UObject table, synchronously scans the namespace from disk, checks the exact
class/path inventory, and confirms that the registry scan itself did not warm
the assets. An interactive Editor session or an earlier test that loaded any
R15 asset intentionally fails the cold-load precondition.

The R6 skeleton may already be loaded because it is outside the R15 namespace;
its exact object identity is still required for every sequence and montage.

## Authorized future execution

Use the real project containing the imported R15 packages and a plugin build
that includes this commit. Preserve stdout, stderr, Engine log, exit code, and
the project/plugin input digests in a fresh append-only evidence directory.
The intended CPU-only invocation shape is:

```sh
UnrealEditor-Cmd /absolute/project.uproject \
  -ExecCmds="Automation RunTests VISTA.PlayableHome.R15DetailActions.AssetContract;Quit" \
  -unattended -nop4 -nosplash -nullrhi -stdout -FullStdOutLogOutput
```

Do not reuse a mutable project as evidence and do not infer success from exit
code alone; retain the automation completion line showing zero failed tests.
This source milestone deliberately did not start UE, compile the plugin, use a
GPU, or modify any live service.

## Explicit target-aware limitation

The R15 `AnimSequence` and `AnimMontage` assets encode skeletal motion and typed
signal timing, but they do not encode a scene entity path, target transform,
contact-height band, IK goal, or Motion Warping target. Therefore this test
does not prove target-aware IK, Motion Warping, or scene-target paths. Exact
sequence/montage object paths prove clip asset identity only.

Target/contact descriptors remain in the sealed R15 source profile, while
scene-target selection and alignment belong to a separately owned runtime
contract. Adding a target-aware assertion here without project-owned metadata
on the inspected assets would be a false claim and would require changing
shared runtime files, which is outside this milestone.

## Focused source validation

The repository-side test parses the compiled C++ clip table, compares all nine
paths, frame counts, and notify pairs to the sealed R15 Python import contract,
and checks that the implementation contains each cold-load, skeleton, track,
root, slot, and typed-notify gate. Its mutation cases must reject path, notify,
bone-count, disk-inventory, and loop-count drift:

```sh
uv run --python 3.11 pytest -q \
  tools/tests/test_vista_playable_home_r15_detail_action_asset_contract_automation.py
```
