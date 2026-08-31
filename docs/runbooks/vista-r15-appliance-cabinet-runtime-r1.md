# VISTA R15 Appliance and Cabinet Runtime R1

## Scope

This milestone connects the fixed R15 source gestures to the existing
rollback-safe semantic action executor without changing EventSpec v3 action
meaning:

- stove and faucet `turn_on` / `turn_off` select the R15 rotary gestures;
- washer `turn_on` and `press` select the R15 button gesture while the action
  receipt remains `turn_on` or `press` respectively;
- cabinet `open` / `close` select the R15 cabinet gestures;
- refrigerator `open` / `close` remains bound to the R14 refrigerator clips;
- successful terminal transactions continue to call
  `RecordSuccessfulInteraction` with the logical affordance.

Appliance controls and cabinet handles are project-authored scene components.
TCP, NLP, and EventSpec inputs cannot provide montage paths or interaction
points. Container state changes now require the shared action executor and use
reservation, contact commit, rollback, and release.

## Source verification

From the repository root:

```bash
PYTHONPATH=. uv run pytest -q \
  tools/tests/test_vista_playable_home_r15_runtime_binding.py \
  tools/tests/test_vista_playable_home_appliance_actions_p0.py \
  tools/tests/test_vista_playable_home_semantic_action_executor.py \
  tools/tests/test_vista_playable_home_makehuman_cc0_animation_runtime_integration.py \
  tools/tests/test_vista_playable_home_action_executor.py

uv run ruff check \
  tools/tests/test_vista_playable_home_r15_runtime_binding.py \
  tools/tests/test_vista_playable_home_appliance_actions_p0.py \
  tools/ue/vista_playable_home/compose_home_commandlet.py
```

Observed before commit: `49 passed`; Ruff passed.

## UE 5.7 compile evidence

A fresh append-only `BuildPlugin` run compiled Editor, Development, and
Shipping targets successfully:

```text
root=/data/sysx/vista-world/runs/vista-action-world-r1/
     playable-actions-r2-plugin-build-r19-20260901a
tree_sha256=53742f9a250a5ada8e46c16f54c79f97fbab4ffc8a96d72f52529ae11867fdd7
file_count=261
total_bytes=58226688
result=BUILD SUCCESSFUL
```

The package was built before the Git commit containing this runbook. A later
R15 import or runtime acceptance run must build and pin a fresh package from
the exact committed source; this package is compile evidence, not an immutable
runtime authority.

## Non-claims

- The R15 FBX files have not yet been imported into the candidate UE project.
- No NullRHI transaction automation has run for these new bindings.
- No GPU runtime, Sunshine, or human visual review has passed this milestone.
- The static HSSD cabinet shell is not claimed to have physical articulation.
- Sit, seated idle, stand, and pour remain source motions pending their own
  posture and two-object transaction implementations.
- This milestone does not claim GTA quality or production readiness.

## Integrated R20 evidence

After the import bridge and EventSpec v3 preflight were merged, commit
`9b860626bbdfbfa9b9838e6a23dd70c4d81a6759` produced a fresh plugin:

```text
root=/data/sysx/vista-world/runs/vista-action-world-r1/
     playable-actions-r2-plugin-build-r20-20260901a
tree_sha256=7f6bc56e078ab50f18ce699b73762630aead69a45219e82572544912bbfea94b
file_count=266
total_bytes=59666177
result=BUILD SUCCESSFUL
```

The pinned CPU-only import completed at:

```text
/data/sysx/vista-world/runs/vista-action-world-r1/
makehuman-cc0-detail-actions-r15-ue57-dev-r1-20260901b
status=r15_detail_action_dev_import_complete_unaccepted_nonpromotable
host_content_digest=4cf524c0123b3567aaed24c3e6e0e351a0b6fcdc55623fd337244469a565c30b
commandlet_receipt_sha256=edd4c1fb700dc65eb4b06f471cf4d18d4afc3630f09cf9051d4816751553df07
package_count=18
gpu_used=false
network_available=false
```

The first EventSpec preflight automation attempt used the minimal import
project and passed the test with three missing-skeletal-mesh warnings; it is
retained as rejected evidence. Fresh attempt B used the complete prior proof
project with the exact R20 plugin:

```text
/data/sysx/vista-world/runs/vista-action-world-r1/
event-v3-queue-preflight-ue-automation-r20-20260901b
test=VISTA.PlayableHome.EventV3.QueuePreflightReadOnly
state=Success
succeeded=1
succeeded_with_warnings=0
failed=0
warnings=0
errors=0
```

The installed UE launcher still exits status 1 after the automation report is
written and prints its known missing project game-binary-directory message;
the same launcher behavior is present in the earlier R18 accepted proof. This
milestone claims the exact Automation report only, not a clean host-process
exit or runtime acceptance.
