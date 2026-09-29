# Multi-stage embodied research scenarios

This extension adds changing plans, delayed reminders, simultaneous walking and
speech, and interrupted assistance to the existing six-room research demo.
It does not train an assistant or introduce a benchmark success-rate claim.
The human stimulus is controlled; the accompanying assistant's responses and
physical operations are decided live from public observations.

## Two reviewed starter cases

- **行程更改 × 延後提醒**: a notebook reminder and casual presentation discussion;
  stove and bath water overlap; a phone call changes ten/lab/printed notes to
  eleven/library/USB; the human replaces the notebook reminder with a laptop;
  the assistant must recall the earlier request, accept corrections and answer
  the departure question. Actual stove/tap shutoffs are separately audited.
- **暫停恢復 × 通話界線**: the caller requests bath shutoff without authorizing the
  assistant. The human declines action, then requests help from the doorway,
  pauses assistance, moves aside, renews the request and asks the assistant to
  follow again. Blocking, waiting, renewed permission and actual completion
  have separate receipts. The doorway staging does not guarantee an outcome.

`runtime.vista_live.complex_examples` installs these **curated human stimuli**.
They do not contain assistant answers and are not labeled NL-generated. The
same runner also executes actual model-compiled scenarios.

## Natural-language authoring

On the research page, expand **用自然語言建立新情境**, select **多階段情境** and enter,
for example:

> 在六個房間裡，先提醒我出門帶筆電，邊走去臥室邊聊研究。接電話後對方改了會面時間；
> 浴室的水同時開著。我先要求助理等一下，之後讓路再請它關水，最後追問會面資訊。
> 只有人物和電話對話，不要替助理寫答案，也不要旁白。

This explicitly selects `vista.scenario/v2`: at most 48 actor steps, 16 short
English spoken lines, 300 seconds of explicit waits, and existing events whose
onset is within 600 seconds. The runner has a 900-second game-time bound. These
are maximum capabilities, not a claim that every combination was tested.
Legacy unversioned scenarios keep their original 16-step/six-line bounds.
Unsupported skills and objects still fail validation.

`walk_say` starts a reviewed collision-aware path, speaks using native male
playback, and waits for **both** arrival and speech completion. Its `seconds`
field is additional listening time afterwards. Walking toward an unknown point,
phone speech without an answered call, blocked arrival and a scene change are
rejected. `bathroom_doorway` is one reviewed home-only destination, not free
coordinates. Existing kinematic locomotion/contact limitations remain.

The large model compiles the actor script and retains the final assistant
semantic/planning decision. TypeSafe Jev selects bounded asset-library recipes;
it does not override that assistant or generate new meshes or materials.

Consecutive phone-directed utterances are coalesced across a one-second quiet
window, retaining every completed turn. Direct requests, periodic visual scans
and native completion feedback bypass that delay. This reduces obsolete calls
without changing the assistant's semantic decisions. The long author reserves
USD 0.04 per request within the unchanged plan allowance; shorter requests keep
their original reservations.

## Repeatable episode initialization

A new explicit scene reset restores the companion as well as the human and
objects. Old wait/follow state, reach pose, path, action identity and speech are
cleared. Ground, capsule clearance and visibility checks select a valid initial
position next to the newly placed human; failure is reported, not called ready.
This setup relocation happens before the episode. It is not recovery teleportation
during a blocked action. Continuous in-episode motion remains separately audited.

## Selective verbatim memory

With `--research --research-memory`, the public packet uses
`vista.research-observation/v2`. Its only additions are up to eight previously
selected **verbatim human/phone utterances** and a short tentative agenda.
The model selects IDs from evidence it already received. The application copies
original text, speaker, audience, source and clock; it never synthesizes facts
from hidden scene state or the future actor script. Recent dialogue remains
bounded to 16 turns and prior decisions to six. Memory clears on scene identity
change. Late stale responses cannot update it.

Recalled dialogue can support a factual answer but cannot renew physical
permission. Every manipulation, wait, follow or cancellation must cite a recent
unconsumed direct human turn, at most 45 seconds old. A caller request, an old
reminder or a visible hazard alone does not grant that permission. Determining
what a direct utterance means remains the model's responsibility; the adapter
checks provenance, age and one-time use. Native collision/contact guards remain.

Provider raw replies are archived before strict validation. Two documented,
semantics-preserving compatibility normalizations are bounded: duplicate valid
memory IDs become one selection, and exactly two identical complete JSON texts
become one decision. Unknown IDs, conflicting objects, duplicate keys and extra
prose remain errors. Neither normalization changes an action or invents consent;
there is no automatic paid retry or provider fallback.

## Validation and research use

Run the baseline contract/compiler tests and focused tests including
`tools.tests.test_vista_long_scenarios`. Use `director_review` with an explicit
owned selected project, fixed view and a sufficient `--duration-limit`, then:

```sh
PYTHONPATH=tools uv run python -m runtime.vista_live.research_audit \
  --episode /path/to/take --backend /path/to/backend --require-off faucet
PYTHONPATH=tools uv run python -m runtime.vista_live.complex_audit \
  --case permission --episode /path/to/take --backend /path/to/backend
```

The first audit binds inputs to archived first-person pixels, verifies recalled
turn provenance, continuous motion, actual state transitions/committed receipts,
and measured movement during speech. The second checks case-specific authority,
pause/resume and selected factual-answer keywords. It includes the actual
completed dialogue for human review; keyword checks are not a semantic judge.
Third-person images, actor scripts and target state remain evaluator-only.

Fixed first/third recordings are separate executions, not identical trajectories
or matched counterfactuals. Speech is native in-world playback, not a later
response track. Dialogue input currently comes from completed authored playback
and typed input, not microphone ASR. Model/TTS latency and rejected/stale calls
must remain visible in reports. Development failures must be retained.

## Recorded development outcomes, 2026-09-22

Evidence is outside source Git at `workspace/runs/complex-scenarios-20260922-a/`.
The four native recordings match code `1603ef1`; subsequent release changes add
the bounded reply-tail drain and explicit recording limitation labels.

| Case / fixed view | Sampled seconds | Model responses | Provider p50 / p95 | Outcome |
| --- | ---: | ---: | ---: | --- |
| Plans / first | 326.2 | 20 | 4.86 / 6.95 s | Both shutoffs and complete corrected recap |
| Plans / third | 336.2 | 20 | 5.06 / 7.01 s | Both shutoffs and complete corrected recap |
| Permission / first | 191.1 | 13 | 4.57 / 5.95 s | Physical/authority checks pass; final casual reply outlasts recording |
| Permission / third | 185.6 | 12 | 5.43 / 8.93 s | Physical/authority checks pass; retrospective account is incorrect |

All four pass the closed-input, fixed-view, continuous-human-motion, actual
shutoff and concurrent speech/movement audits. These checks do **not** establish
semantic success. Plans carry an earlier original utterance beyond the 16-turn
window in eight and three requests respectively; this is not a memory ablation.
The permission third-person reply says an earlier tap shutoff succeeded although
that approach was rejected. This error remains after prompt clarification.
Its native clip is published as a labeled failure example, not a corrected answer.
The first-person clip also retains its original ending and is labeled accordingly.

The released runner now waits up to 45 seconds for existing final response work,
native playback and its completed-turn callback. It does not submit another
model request. Two regression tests cover delayed playback/callback and takeover;
a targeted native test waits 9.24 seconds around an 8.28-second cached voice and
a simulated completion callback, using zero provider calls. The full episodes
have not been re-recorded after this fix.

A separate actual Chinese NL compilation includes a three-to-four-o'clock,
office-to-library correction and a folder reminder. Its 156.6-second native
no-intervention run completes with zero policy calls and both devices still on.
The first compilation omitted caller facts despite passing the schema; it is
retained along with the reviewed second compilation. This is not an assisted
success or a guarantee of NL semantic coverage.

Local final checks include 148 focused tests, the 28 contract/compiler baseline,
an Editor build with 62 matching native source files, seven home-room resets
and three micro-room resets. The broader suite retains an inherited camera-source
assertion failure in unchanged `VistaPlayableHomeCharacter.cpp`; do not call the
whole suite green. No GitHub Actions run is requested for this iteration.

The task allowance retains 13/160 plan requests after development and recordings;
reported provider cost is USD 0.571659 plus USD 0.06 reserved for failed requests,
within the unchanged USD 2 cap. The earlier teacher allowance remains untouched.
Movies and local male voice playback consume no model allowance. These are task
limits, not account balance; full plans took 20 calls, so prefer recordings and
short live questions at handoff. There is no automatic allowance rollover.

These results are an engineering review of selected cases. Independent human
ratings, broader semantic evaluation and end-to-end latency comparisons remain
future work. Offline ASR is only an audio inspection aid: it can hallucinate
speech over silence, as the retained third-person plans tail demonstrates.

This provides controlled stimuli for future memory, correction, interruption and
permission ablations. A defensible paper still needs frozen versions, held-out
scenarios, multiple seeds, stronger baselines, matched conditions and reporting
of all outcomes. It does not yet demonstrate optimal scheduling, subsecond
reaction, force-valid human interaction or general photorealistic NL generation.
