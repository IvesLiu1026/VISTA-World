# Reachable companion interventions

The previous concurrent phone/bath episode completed its human acting steps,
but the companion returned `blocked_approach` and left the bath tap running.
This change makes a requested low-control interaction executable when there is
physical space, and reports obstruction separately from the actor's completion.

## Controller and feedback

- The native motor controller samples supported operating positions, checks
  the full standing capsule, arm length and upper-body clearance, and chooses
  a clear approach. A bounded 24 cm same-floor A* grid is available when the
  direct chord is blocked. This is local navigation within 350 cm, not a
  general stair/multi-room navmesh planner.
- Low controls use at most 25 degrees of waist rotation. Arm segment lengths,
  bone translations and planted feet are preserved. Approach time no longer
  consumes the hand's separate four-second settling window; the body recovers
  smoothly after completion or cancellation.
- A human occupying an otherwise usable operating position produces
  `waiting_clearance`. The companion asks for space, checks again every 0.75 s,
  and stops after eight seconds without clearance. Candidate classification
  may ignore the human diagnostically; an actual route never does.
- The existing commit guard still requires fingertip error <=3 cm, unobstructed
  reach, current active target and <=85 cm horizontal distance. Contact remains
  kinematic, not force/torque simulation. A failure leaves the target active.
- Native action speech is tied to action ID/status, including queued playback.
  An obsolete request to move aside cannot play after cancellation or completion.
- Scenario Studio distinguishes human acting completion from actual companion
  approach/wait/reach/commit/failure. Outcomes come from native feedback, never
  from a generated plan's assertion of success.

The reviewed bathroom viewing stop moves from `(1245,-1015)` to `(1285,-1100)`
through collision-checked walking. This keeps the tap's operating area free.
That is an explicit **human staging change**, not evidence that the assistant
learned to solve the original occupied pose without cooperation.

## Native evidence

Local evidence root: `workspace/runs/companion-reach-20260921-a`.
Independent payload: `projects/six-room-companion-dev-director-b`.
GPU 0 RTX 5090, private display `:129`, native build 5; 61 plugin source files
match the payload. Binary SHA-256:
`cf976926a662f9b7658718620ca4146d4618df1ba490656b4b524fb59b331551`.

| Case | Observed result |
| --- | --- |
| Original occupied bath position, no yielding | Wait, bounded `blocked_clearance`; tap remains on |
| Human moves aside during that wait | Continuous approach and fingertip commit; tap turns off |
| Human starts at the clear viewing position | Actual native commit and tap off |
| Cancel while waiting | Cancelled; tap remains on |
| Cancel during approach | Cancelled; tap remains on |
| Stove with operating space available | Actual native commit and stove off |
| Bath request from another floor | Rejected; tap remains on |
| Human blocks narrow approach corridor | Search examines 68 nodes and rejects; tap remains on |

These direct `assist` cases are **motor engineering tests**, not model-policy
success rates. Their sampled traces check fixed perspective, continuous root
movement, human capsule separation and actual entity state. They do not prove
arbitrary layouts, complete mesh nonpenetration or naturalness across all motion.
The obstructed corridor still needs the human to move; a general bypass route
is not claimed.

The cached ten-step phone/bath scenario was also replayed through the same web
Director API in `home-e2-first` and `home-e-third`. Both complete all human steps,
keep one fixed perspective, and independently record a committed tap shutoff
with native `active=false`. Native durations are 65.39 and 65.59 s. Approach to
commit takes about 2.2 s in these two staged examples, excluding model/voice
latency. This is not a latency benchmark. The concurrent stove stays active:
the human asked for the bath tap, so these are not all-hazards-resolved episodes.

The final local suite passes 148 tests. Browser checks at 390 and 1280 px verify
separate actor/intervention labels without horizontal overflow or console errors.

Retained unsuccessful investigations include `baseline-first`, `space-b`,
`space-b2`, `probe-c2` and `home-e-first`. The latter failed at the bathroom door
because an isolated motor test had left following disabled; normal following
was restored before the accepted full replays. An early review launch before
native readiness also remains recorded. Failures were not relabelled as success.

## Reproduce and interpret

Run only on a private runtime accepted by `input_probe.py`, never on the live
Moonlight display. The motor review temporarily freezes following and restores
its previous value afterward. It does not generate assistant policy decisions.

```sh
uv run --offline tools/runtime/vista_live/approach_review.py \
  --workspace "$WORKSPACE" --run "$PRIVATE_RUN" --out "$FRESH_OUT" \
  --view first --case yield --port 49117

uv run --offline tools/runtime/vista_live/director_review.py \
  --workspace "$WORKSPACE" --run "$PRIVATE_RUN" --out "$FRESH_OUT" \
  --scenario "$PREPARED_SCENARIO_ID" --view third --port 49117 \
  --require-off faucet
```

Other motor cases: `clear`, `no_yield`, `cancel_wait`, `cancel_move`, `stove`,
`far`, `obstacle`. See `motor-summary.json`, `end-to-end-audit.json`,
`source-inventory.json`, native action receipts, videos and per-case traces.

Assistant input remains visible engine metadata and completed in-world speech,
not RGB perception or ASR. Seventy-three recorded assistant requests passed a
recursive key audit for hidden geometry, future events and scripts; private
planning diagnostics are evaluator-only. This audit is not sealed benchmark
isolation. Provider ledger/caps and existing English male voice roles remain
unchanged. No new model training or arbitrary text-to-mesh generation is claimed.

Next research work should use held-out cooperative and obstructed layouts,
record physical execution failure separately from planning intent, and measure
when the assistant should ask for cooperation, retry, or return control. Add
causal visual/audio perception before making a visually grounded paper claim.
