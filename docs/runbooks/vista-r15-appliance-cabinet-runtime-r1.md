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
