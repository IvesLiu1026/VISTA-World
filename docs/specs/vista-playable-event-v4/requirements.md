# VISTA Playable Event v4 Requirements

## Context

EventSpec v3 is the frozen authority for seven verified VISTA-derived safe-remediation
queues. It intentionally rejects posture and liquid-transfer actions. The R15 source
profile now describes candidate Sit, Stand, and Pour clips, but no Unreal adapter or
visual acceptance receipt exists. V4 must expose those actions to offline planning
without changing any v1-v3 authority or claiming runtime readiness.

## Goals

- Define a closed, digest-bound EventSpec v4 that derives from an exact validated v3
  event and preserves every v3 queue action as an exact prefix.
- Add wire actions `sit`, `stand`, and two-target `pour`.
- Make `pour.target_id` the exact primary/source entity and
  `pour.secondary_target_id` the exact receiver entity.
- Compile validated events into source-only action plans and closed dispatcher
  envelopes with typed identities.
- Keep all acceptance and runtime authorization fields false until independent UE
  adapter and visual evidence exists.
- Specify an NLP boundary that can emit only a closed ActionPlan candidate which must
  pass the same schema, identity, sequence, and digest validation before compilation.

## Non-goals

- No UE plugin, player, HUD, composer, R5 projection, service, GPU, or Sunshine work.
- No runtime dispatch, animation acceptance, liquid simulation, arbitrary command,
  shell, filesystem path, object path, or free-form tool execution from NLP.
- No edits or resealing of any v1-v3 artifact.
- No claim that R15 source clips are visually or operationally accepted.

## Functional requirements

### REQ-001 — immutable v3 derivation

The system shall validate the exact source v3 event through the existing v3 contract,
bind its content digest in v4, and require each source queue to be an exact prefix of
the corresponding v4 queue.

Acceptance criteria:

- Removing, reordering, or changing any inherited action fails closed.
- Adding fields to inherited actions fails because equality is byte-structural.
- V1-v3 files and digests remain unchanged.

### REQ-002 — closed action grammar

The v4 JSON Schema shall keep every object closed and add exactly these shapes:

- `{"action":"sit","target_id":"<seat semantic id>"}`
- `{"action":"stand","target_id":"<same seat semantic id>"}`
- `{"action":"pour","target_id":"<held source semantic id>",
  "secondary_target_id":"<receiver semantic id>"}`

Acceptance criteria:

- Missing, unknown, malformed, or extra keys fail schema validation.
- Source and receiver IDs must differ and both resolve exactly in the bound house.

### REQ-003 — typed sequence preflight

The preflight shall track one actor posture/seat claim and one held-item slot per NPC.
Sit requires a seat target and standing state; Stand requires the same active seat;
Pour requires the exact primary source to occupy the held slot and a distinct exact
receiver. These are contract checks only and do not imply UE capability.

### REQ-004 — action catalog v4 overlay

The v4 action catalog shall bind the exact reviewed r3 digest, preserve all 38 action
semantics and ordering, and add the exact R15 profile as an unaccepted candidate for
`sit_down`, `seated_idle`, `stand_up`, and `pour`.

Acceptance criteria:

- No semantic action is added, removed, or redefined.
- No readiness layer is `verified`; evidence digests remain null.
- `runtime_acceptance` remains `blocked` for every action.

### REQ-005 — compiler and dispatcher envelope

The compiler shall emit deterministic source-only plans. Each action includes its
canonical ID, backend action, runtime type, closed parameters, readiness, and false
acceptance/authorization flags. Dispatcher envelope construction shall preserve typed
primary and secondary identity roles and shall not perform network or UE execution.

### REQ-006 — closed NLP boundary

An NLP system may propose only JSON matching the ActionPlan/EventSpec v4 grammar.
Free-form text is never executable. Proposed IDs must resolve against an enumerated,
digest-bound entity set and the result must pass schema validation and preflight before
it can reach the compiler. Any unknown intent, key, ID, or path is rejected.

## Quality requirements

- Deterministic canonical JSON and SHA-256 content sealing.
- Negative tests for extra keys, source/receiver reversal hazards, same-target Pour,
  unheld Pour, Stand-before-Sit, seat mismatch, v3 drift, forged acceptance, and
  arbitrary NLP/shell-shaped keys.
- Tests run locally through `uv run pytest`; no GitHub Actions dependency is required.

## Readiness truth

This milestone is contract/source-only. `accepted=false` and
`runtime_execution_authorized=false` are invariant. Live composition, UE adapter
support, contact semantics, liquid-state effects, and visual acceptance remain pending.

## Approval

The coordinator explicitly authorized requirements, design, implementation, tests,
documentation, and a local commit in one bounded task. This records the combined phase
gate for this isolated branch; it does not authorize runtime deployment or service work.
