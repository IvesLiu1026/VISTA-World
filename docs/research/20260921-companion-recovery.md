# Cooperative recovery and cancellation

An assistant previously rejected a request when the human blocked the narrow
bathroom approach, even if the human subsequently stepped aside. A separate
reproduction showed that asking the assistant to wait changed its following
flag but did not stop its ongoing manipulation: it still closed the tap.
Both baseline recordings are retained against deployed source `adc730b`.

## Behavior

The motor controller first searches for a route with normal capsule and floor
checks. If no route exists, a direct capsule sweep must hit the human, and the
same supported chord without that human must be clear, before classifying the
corridor as temporarily human-blocked. This second query is diagnostic only;
it never becomes an executable path. Available detours are still preferred.

Human-blocked routes now use the existing cooperative wait: ask for space,
stop moving, check again every 0.75 seconds, and stop after eight seconds
without clearance. Movement resumes only after a fresh collision-checked route
exists. Target state still changes only after the actual fingertip/contact
guard. The local 350 cm, same-floor scope and kinematic contact limits remain.

An explicit follow/wait request cancels manipulation before applying the new
following flag. This ordering also prevents the cancelled action's saved follow
mode from overwriting the latest user request. It applies to the native UI and
typed requests that resolve to these skills.

Each accepted manipulation now returns its native action ID. Generated intention
speech stays bound to that acceptance, not a later snapshot of another action.
The service drops obsolete work before a planning request, after its response,
and before queued speech playback. The engine rechecks the action ID/target or
feedback status on its game thread before starting audio, covering the gap
between the service check and native execution. A late cancellation cannot
recover a provider request already sent, but it prevents subsequent voice work
and obsolete playback. An utterance already playing is not retroactively erased.

## Evidence and interpretation

Local evidence is under `workspace/runs/companion-recovery-20260921-a`;
the independent payload is `projects/six-room-companion-dev-director-c`.
Native build 2 succeeds; all 61 plugin source files match the payload. Binary
SHA-256: `d0a7da82b4aaee1edc7ebd99db0b8df3610ab5e1fc59f358cc955c9e6de0ec3d`.
The local suite passes 153 tests, including five new delayed/cancelled-request
regressions. Frozen dependency sync and source whitespace checks pass.

| Native control | Result |
| --- | --- |
| Human yields from blocked corridor, fixed first and third views | Wait, approach, reach, commit; tap off in both |
| Human does not yield | Bounded `blocked_clearance`; tap stays on |
| Cancel during corridor wait | Cancelled; tap stays on |
| Wait here during approach | Cancelled; tap stays on |
| Follow me during approach | Cancelled; tap stays on; following resumes |
| Closed bathroom door | `blocked_approach`; no false request for human clearance |
| Clear stove approach | Commit; stove off |
| Speech transport, replacement and cancellation | Three valid starts and five stale rejections |

All nine motor recordings pass actual state, fixed-view, continuous root motion
and sampled human capsule separation checks. Successful interventions satisfy
the existing <=3 cm fingertip guard. The yielding cases now complete where the
same old-binary fixture rejected immediately. All nine videos decode completely.
The preliminary build-1 acceptance is retained separately from final build-2
evidence; baseline failures are never relabelled as successes.

The cached ten-step phone/bath scenario also completes through the normal
Director API in both fixed perspectives (`home-final-first`, `home-final-third`).
Native durations are 65.38 and 65.39 seconds. Both independently record an
actual companion tap shutoff. The concurrently active stove remains on; these
are not all-hazards-resolved episodes. The existing clear human viewing position
is unchanged from the previous accepted staging, not newly learned behavior.

All 34 assistant requests from these replays pass a recursive key audit for
hidden geometry and future scripts. The nine motor tests consume no new model
or TTS requests. The two full replays use 30 decision/intent calls, four plans
and one new TTS call; the prior durable US$2 provider cap and remaining allowance
are reused. No automatic paid retry, fallback or new allowance is introduced.

The motor reviews directly issue an assistance command. They establish motion,
cancellation and transport behavior, **not learned-policy success**. In
`speech_guard`, a cached clip is deliberately injected to test native speech
acceptance/refusal; that recording is not an autonomous dialogue demo.
Authored human routes are test stimuli. Fixed-view full scenario replays use
the normal Director and assistant service separately from these controls.

Assistant input remains visible engine metadata and completed in-world speech.
Controller geometry and diagnostic paths are evaluator-only, not model inputs.
This is not RGB perception, ASR, force-based manipulation, a general navigation
solution or a held-out paper benchmark. Sampled capsule/root checks do not prove
the absence of all mesh penetration or human-rated motion naturalness.

## Reproduce

Only use a private runtime accepted by `input_probe.py`; wait for fresh native
state and service readiness before running. The motor review restores the
previous following flag afterward. Use a fresh output directory each time.

```sh
uv run --offline tools/runtime/vista_live/approach_review.py \
  --workspace "$WORKSPACE" --run "$PRIVATE_RUN" --out "$FRESH_OUT" \
  --view first --case corridor_yield --port 49117
```

Additional controls: `corridor_wait`, `corridor_cancel`, `hold_position`,
`follow_instead`, `closed_door`, and `speech_guard --speech "$CACHED_CLIP"`.
The earlier endpoint-occupancy, clear, stove and far cases remain available.

## GitHub CI usage

This iteration requests **zero additional GitHub Actions runs**. Required
dependency/contract checks, focused behavioral tests, native builds, recorded
acceptance, source/binary matching and secret scans run locally. Changes are
batched before publication to a feature branch targeting the existing World
integration branch. The repository's existing CI triggers apply to `main`
pushes/PRs and manual dispatch; no workflow or required check is disabled.

Do not dispatch during intermediate commits or repeat a successful unchanged
head. When remote validation is needed for a later merge, inspect existing runs
and use one final-head run instead of duplicate dispatches. Previous run
`35596484446` passed for base `adc730b` only; it is not CI evidence for this
changed source. The workspace CI ledger records the new run count separately
from local verification and makes no estimate of remaining billed minutes.

The next research step is a held-out set of cooperative and uncooperative
human behaviors: measure when to ask for clearance, abandon or retry an action,
and return control. Score physical outcomes, interruption burden and recovery
separately from plausible plan text.
