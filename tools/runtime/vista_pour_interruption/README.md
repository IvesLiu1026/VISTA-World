# Interruptible Villa pouring

The Villa carafe now supports a stop request while pouring. Press **P** to start
while holding the carafe near the mug; press **P** again to stop. The explicit
`VillaStopPour` console action is idempotent, including during the return motion.
The character straightens the carafe around its measured lip position over
0.7 seconds, then withdraws it to the carry position over 0.65 seconds. The
physics handle and hand IK remain engaged throughout. Automatic completion uses
the same return path after 4.5 seconds. **E** places the returned vessel; **R**
is an explicit scene reset, with separate before/after records.

The motor controller uses the measured vessel tilt to reduce outflow during
straightening. Already emitted parcels and visual streams keep moving. A stop
does not restore actor transforms or undo transferred/spilled water. The motor
trajectory is procedural; it is not motion capture or a learned human response.

## Initial conditions and records

Optional launch arguments `-VistaJugInitialMl=600` and `-VistaMugInitialMl=160`
set initial liquid volumes. Jug bounds are 0–600 mL and mug bounds are 0–260 mL,
matching this scene's authored reservoirs. Defaults remain 600 and 0 mL.
Invalid or non-finite values prevent scene readiness. Reset reapplies these
configured volumes. Capacity is fixed to the authored 260 mL mug.

Each actor session writes a uniquely named JSONL file under
`Saved/VillaPourActions/`. `vista.pour-action/v1` events include an action ID,
simulation time, action time, initial volumes, current source/receiver/spill/
airborne volumes and mass residual. Events distinguish start, stop request,
automatic return, return completion, settled flow, grip loss, reset and shutdown.
They are privileged diagnostic state and must not be supplied to a restricted
assistant or mixed into model observations.

Volume comes from a conservative reservoir/flight ledger. Vessel surfaces
visualize that ledger; Niagara provides coarse water effects independently.
Neither particle counts nor screenshots measure solver mass. The ledger's hit
classification uses the observed mouth alignment at emission; it does not solve
moving receivers, arbitrary splashes or fully coupled fluid dynamics.

## Native engineering probe

Build this plugin with the scene's UE 5.7.3 engine into a fresh package. Use
`RunUAT.sh BuildPlugin` with `-NoTargetPlatforms` for the editor plugin and
`-TargetPlatforms=Linux` for Editor/Game Development/Shipping compilation. Copy
the reviewed plugin into a fresh materialized `alpine-villa-r3` project. Do not
modify the selected Sunshine project or frozen source assets.

The runner expects a `VistaPourCache` DDC graph in that private project's engine
configuration: an engine pack, an optional read-only donor, and a private writable
cache. It uses a private Xvfb display, GPU 0, and the current host's established
`r.Shadow.Virtual.Cache=0` workaround. Virtual shadows remain enabled. This host
does not support the runbook's unprivileged network namespace, so the receipt
explicitly records that this is not a sealed evaluation environment.

From the writing worktree, with absolute project/engine/output paths:

```sh
uv sync --frozen
PYTHONPATH=tools uv run python -m unittest \
  tools.tests.test_vista_playable_home_contracts \
  tools.tests.test_vista_playable_home_compiler \
  tools.tests.test_villa_liquid_ledger \
  tools.tests.test_villa_pour_control \
  tools.tests.test_villa_motion_curves -v
uv run python -m tools.runtime.vista_pour_interruption.run_native \
  --project "$POUR_PROJECT" --engine "$POUR_ENGINE" --out "$POUR_RUN"
uv run python -m tools.runtime.vista_pour_interruption.verify \
  --run "$POUR_RUN" --out "$POUR_VALIDATION"
```

`-VistaPourProof` runs six scripted cases: 160 mL initial mug with no stop,
stop at 1.7 s, stop at 3.6 s; empty mug with no stop or stop at 1.7 s; and a
repeat of the 160 mL timely stop. All times are relative to pour start. Each case
physically picks up and places the carafe. Duplicate stop requests exercise
idempotency. First-person pickup/pour/place and third-person straightening/return
screenshots accompany dense post-animation joint/object measurements.

The verifier checks conservation, surface/ledger agreement, action cardinality,
motion continuity, wrist contact, arm lengths, upright return, complete pickup/
place, different consequences and comparable pre-interruption samples. The
predeclared prefix bounds are 0.5 cm object/actor position and 0.25 mL liquid
difference; these are engineering tolerances, not an exact physics snapshot.
Visual review is still required after numeric checks. Fixed 1/30-second steps
measure motion correctness; wall time under shared GPU load is not real-time FPS.
Add `--video` to record the private display to `native-review.mp4` for human
motion review. Its playback follows wall time, including loading and capture
stalls. The runner does not record the shared Sunshine display.

The initial native review still shows a stiff, generic finger grasp and limited
visibility of the water stream from directly above the carafe. A zero wrist-to-IK
goal error does not establish fingertip skin contact. Improving the carafe-specific
grip and measuring fingertip-to-glass contact remains a separate animation task.

## Research scope

These are scripted motor interruption checks, not model accuracy, causal human
warning efficacy, or a benchmark result. The stop schedule directly requests a
motor action. A later study must specify the mapping from an assistant warning
to a person's reaction, restrict observations to the past, hold scene/evidence
prefixes fixed, and measure unnecessary-interruption cost as well as spill
reduction. The benign condition here exposes reduced delivered water; it does
not establish human annoyance or task failure.

The retained character/motion assets currently carry a local human-review scope.
Do not publish them as model inputs or benchmark media without resolving the
asset provenance and intended distribution. This change does not connect the
separate HomeActions bridge to Villa or authorize a model/API evaluation run.
