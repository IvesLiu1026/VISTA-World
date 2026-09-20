# Ten themes and small-room recipe generation

This experiment extends the six-room live assistant with ten authored topics:
breakfast, work, departure, reading, movies, fitness, chores, visitors, travel,
and evening astronomy. These are distinct conversation/memory stimuli and
combinations of the existing stove, water and misplaced-key events; they are
not ten new physical skills or ten new hazard categories.

| Topic | Starting room | Concurrent physical events |
|---|---|---|
| Breakfast and coffee | Kitchen | Stove, misplaced keys |
| Work and technology | Office | Running water, misplaced keys |
| Departure and time planning | Entry | Stove, misplaced keys, running water |
| Reading and stories | Living room | Running water, misplaced keys |
| Movies and music | Living room | Running water, stove |
| Exercise conversation | Bedroom | Running water, misplaced keys |
| Chores and organization | Bathroom | Running water, stove |
| Visitors and hospitality | Kitchen | Stove, running water |
| Travel and packing conversation | Bedroom | Misplaced keys, stove, running water |
| Evening astronomy | Bedroom | Running water, misplaced keys |

Every review also includes an actual handset pickup and phone exchange. Topic
names describe conversation stimuli; exercise and travel do not add new exercise
animations or a physical suitcase-packing skill.

The human opening and follow-up are authored English male speech stimuli. The
assistant classifies the actual heard input with Jev and generates prose with
Qwen. Urgency and phone state suspend casual speech; an actual follow-up checks
whether the earlier topic detail survived the interruption. Typed free-topic
input remains available. Engine-visible metadata is the observation interface,
not camera perception or microphone transcription.

The existing review policy also recognizes the three known authored goal
phrases by exact string and registers their goals. Jev is still called for
each heard input; arbitrary typed input uses Jev's goal interpretation. These
authored videos therefore do not isolate Jev's intent-recognition ability.
Intervention choices also pass eligibility and urgency guards. A later intent
or unconstrained-planning benchmark must separate and ablate these helpers.

The recording driver introduces events at authored route milestones; interactive
theme cards use saved seeded time schedules. Both use the same native event
contracts. A recording is a separate authored take, not a replay of a particular
manual-play session. Responses can still repeat questions or make awkward
transitions; the recall and physical checks do not score every aspect of language
naturalness.
General-knowledge and travel claims in casual replies are not independently
fact-checked here; remembering the user's detail is not a factual-QA score.

## What Jev can build

The [official TypeSafe system-one documentation](https://docs.typesafe.ai/concepts/system-one)
describes typed decisions over text/JSON, not generative prose, code, meshes,
textures or image/video inputs. The [OpenRouter compile example](https://openrouter.ai/labs/jev/compile)
uses a generative model to prepare questions and Jev to make subsequent choices.
A [community game demo](https://typesafe-ai-playground.vercel.app/doom) supplies
structured state and allowed game actions. Its existing game world is not
evidence of Jev generating realistic 3D assets.

Here Jev chooses `support`, `family`, `palette`, and `lighting`. The native engine
assembles reviewed existing furniture and photographic PBR materials inside a
bounded 6 × 5.2 × 2.9 metre room. Three furniture families, three palettes, two
lighting settings and three arrangements make 54 combinations. Seeds beyond
those arrangements do not invent additional geometry. Unsupported requirements
such as pools or disabled collision are rejected. Batch generation prepares up
to ten recipes; entering one explicitly applies it to the game. Stopping a
batch preserves the in-flight receipt and prevents subsequent calls.

The palette changes the floor: `walnut` is a darker tint of the existing oak
material, not a separate scanned walnut asset. Furniture retains its original
materials. A generated room does not imply newly generated textures or meshes.

Geometry is owned by trusted engine code. It stages a candidate away from the
current room, checks the supported floor and capsule corridor, and commits
only a valid candidate. Opaque walls have thickness and a real bounded window
opening. Loose props are packed on verified mesh surfaces rather than on the
maximum bounds of furniture that may include lamps or monitors. Returning to
the original house restores original entity bindings.

## Paired recipe pilot

Evidence: `runs/scenario-forge-20260921-a/benchmark-b/` in the host workspace.
Thirteen hand-authored requests cover the ten themes, an unsupported pool,
disabling collision and a negated warm-light request. Both models receive only
the request and the same four-field choice space. Local expected answers are
not sent to either model. Call order alternates; there is no automatic retry.
The recorded model IDs are `typesafe/jev-1.13-20260917` and
`qwen/qwen3.5-35b-a3b`, accessed through the existing authorized OpenRouter
provider on 2026-09-21 (Asia/Taipei). Preserve individual provider/model receipts
when repeating the experiment; the alias alone does not establish an immutable
backend implementation.

| Model | Valid recipes | Expected matches | API p50 | API p95 |
|---|---:|---:|---:|---:|
| Jev | 13/13 | 12/13 | 436.54 ms | 876.3 ms |
| Qwen | 13/13 | 13/13 | 891.81 ms | 1298.07 ms |

P95 uses the nearest-rank empirical percentile (the maximum for 13 samples).

Jev selected daylight instead of warm lighting for the visitor request. This
failure is retained. These are small, manually authored engineering checks,
not an unbiased general capability benchmark. Network/API time, native
assembly, shader/texture warm-up and visible interaction readiness are
different measurements. Millisecond geometry assembly is not a claim of
millisecond photorealistic asset generation.

All nine furniture-family/arrangement cases passed an authored perimeter walk
in both views, a real third-person handset pickup, and a return to the house
while carrying it (`micro-acceptance.json`). The accepted cases are split across
`micro-walk-m` and `micro-walk-m2`; failed approaches are retained. This checks
one route and grasp stance per case, not arbitrary navigation or all possible
approaches. Native assembly took 3.34–7.89 ms with the engine and assets already
loaded. That timer ends before rendering and is not first-frame readiness.

A browser smoke test accepted a Chinese warm/dark-study description and received
the native applied-scene receipt about 1.02 seconds after clicking. An unrelated
typed rainbow question produced an actual completed in-world spoken answer.
An unsupported pool request stopped after one call and preserved the existing
room. Real keyboard walking after web entry and clearing stale authoring state
after an external room reset are verified separately. These are single warm
interactive checks, not latency distributions.

Semantic review also matters: the first work-topic pair passed every mechanical
check but one response suggested programming music while the human was looking
for keys. Those unpublished takes remain in `themes-g/semantic-review.json`.
Practical requests now use the current observation without unrelated casual
history; assistant task replies keep their purpose and are excluded from later
casual resumption. The corrected native work trial acknowledged that keys were
not visible, then returned to the Python/music conversation after the phone and
water interruption. This fixes a context-routing defect, not general language
model reliability or all repetition.

The first departure take (`themes-h/departure/first`) also retained a real
`blocked_approach`: the human stood in the companion's stove approach lane and
the companion asked for space. A private physics check moved the human to the
free side at approximately (1295,-1030) cm and the unchanged contact guards then
committed the stove turn-off. Later authored takes leave that lane open before
requesting help. This cooperative staging is not evidence of general autonomous
obstacle planning.

An earlier fitness take (`themes-i/fitness/first`) stopped when the TTS provider
returned HTTP 400. The original response body was not retained, so its exact
upstream cause is unknown. Provider failures now preserve bounded, key-redacted
status/body receipts. A regression verifies that the same failed request ID
cannot trigger another API call and its conservative reservation stays charged
against the allowance. The later fitness trial is a new recorded attempt, not
an automatic replay or proof that every upstream voice request will succeed.

Recipe API timing is also distinct from spoken conversational responsiveness.
The review's `wall_seconds` runs from starting the authored human stimulus until
the assistant finishes speaking; it includes both utterances and is not
time-to-first-token or time-to-first-audio. Cached urgent warnings and newly
synthesized casual replies have different latency paths.

A separate third-person fitness take was rejected by the original fixed
65 cm inter-sample displacement check. Native video showed continuous stair
descent: 60.44 cm horizontal and 33.74 cm vertical over 0.404 engine seconds.
The walk-only audit now uses the native 150 cm/s horizontal limit with 3 cm
tolerance, a 22 cm step plus stair slope envelope, and at least two engine
samples per second. Negative tests reject fast jumps, vertical discontinuity,
clock reversal, frozen-time movement and session changes. Existing accepted
traces also pass this check. Original failed results remain unchanged; the
third-person take is re-recorded. This corrects an evaluation error and does
not modify the engine's collision or locomotion limits.

The earlier third-person travel take (`themes-l/travel/third`) retained an
upstream decision timeout. Jev had correctly recorded `leave_find_keys`; a
subsequent decision call timed out, making the service visibly unavailable
and preventing the later key reminder. The original request ID and failure
receipt remain preserved. No automatic retry, allowance reset or substitute
model was used; a later trial starts a fresh scene and new requests after the
provider health check. Successful takes do not establish outage resilience.

## Accepted recordings and implementation checks

The final set has 20 separate fixed-view takes, two per theme, totaling
4204.03 seconds (70.07 minutes). Each take lasts 170.07–239.70 seconds and
passes nine checks covering fixed perspective, sampled walking continuity,
opening/follow-up, actual-detail recall, physical-event completion,
interruption/resumption, anticipatory corners and resolved observed needs.
All 20 unchanged 1920×1080/30 H.264/AAC captures fully decode and contain
non-silent native audio. Captions and role speech are produced in the engine;
there is no narrator or post-dubbed assistant track.

`media-audit-final.json`, `semantic-accepted.json` and `audio-checks.json` are
the evidence indexes. Accepted recordings are selected from `themes-d`,
`themes-h`, `themes-i`, `themes-j`, `themes-k`, `themes-l`, `themes-m` and
`themes-n`; prior failed takes and their receipts remain untouched. These are
selected engineering demonstrations, not a report of 100% trial success.
Breakfast was captured on an earlier build before the final micro-room/menu
fixes; the other final theme videos use build 14. All accepted traces also pass
the final time-aware walking audit.

The final functional regression set has 128 passing tests. Native build 14
has 59 matching source files and binary SHA-256
`c44f7ff026d404b551a083556a3faec704c725822a161a03b68e1ba93570f006`.
During private capture alongside the previous live instance, sampled engine
frame-time medians were approximately 33.33 ms; per-take p95 was
33.33–33.67 ms. The private game was capped at 30 fps. These are server-side
samples, not measured Mac/Windows Moonlight latency or client frame rate.

## Research use

Useful next experiments compare constrained recipe selection, generative JSON
planning and retrieval on held-out prompts; report semantic match, traversable
space, supported and usable objects, material readiness and end-to-end latency.
For assistance, hold layouts and human stimuli constant while varying event
overlap, speech interruption and observation delay. Measure warning latency,
missed urgent events, unnecessary interruptions, task completion and actual
conversation recall. Preserve seed, recipe, model receipt, native state and
separate continuous first/third-person recordings per trial.

The minutes-long authored takes do not establish long-horizon performance.
Current conversation memory is the last 16 turns, not durable personal memory.
Longer held-out streams, observation noise and unseen event combinations remain
necessary before drawing paper-level conclusions about assistant planning.

Current visual fidelity is asset-library prototype quality. A plausible room
with working interactions is useful evidence; it is not yet a photorealistic
scene-generation or human-motion result suitable for an unqualified paper claim.

## Reproduction

Use an owned private project and display. Do not run the review driver against
the shared Moonlight display. A separate provider service holds credentials
and a durable bounded allowance; evidence and generated media stay outside Git.

```sh
PYTHONPATH=tools uv run --offline python -m runtime.vista_live.forge_benchmark --help
uv run --offline tools/runtime/vista_live/micro_review.py --help
uv run --offline tools/runtime/vista_live/theme_suite.py --help
PYTHONPATH=tools uv run --offline python -m runtime.vista_live.theme_audit --help
```

`micro_review` exercises nine family/arrangement combinations, both view modes,
actual capsule walking, phone pickup and reset while carrying. `theme_suite`
runs the selected themes and fixed perspectives sequentially, records native
audio/video, preserves all receipts and stops on failure. A new output directory
is required for each attempt. It never silently retries a failed paid call.
The lamp-bearing bedside table holds a phone and keys; the larger lounge and
study tables additionally hold a cup. Generated furniture is decorative; only the reviewed portable object skills
are exposed there. Full-house seating, device actions and concurrent events
continue to use their original scene contracts.

`theme_audit` checks accepted-capture hashes and media streams, optionally fully
decodes them, extracts actual played dialogue and reports sampled frame times.
Its numerical checks do not replace viewing the footage and reviewing meaning.
`theme_media` publishes accepted videos unchanged, including their native audio,
and extracts posters. The theme page provides one-click entry, separate fixed
view recordings, free-text room descriptions and a bounded variant queue.
