# Continuous assistance: real decision replay

This pilot runs observed-state decisions against the existing rule assistant.
The private viewer synchronizes real API responses with an existing native
six-room recording. It **does not claim that the model controlled the recording**.
The human's physical actions were scripted in the original engineering episode.

The corrected September 20 pilot uses **`typesafe/jev-1.13` via OpenRouter's
alpha Decisions API**. All 44 real responses identify **TypeSafe** and the
version **`typesafe/jev-1.13-20260917`**. The same OpenRouter key works; a separate
TypeSafe account is not required for this route. The earlier conclusion that
OpenRouter lacked Jev came from an incomplete catalog lookup and was incorrect.
The original **`qwen/qwen3.5-9b`** run, with reasoning disabled, is retained as
a comparison. Its results are never relabeled as Jev.

## Inputs and results

`prepare.py` selects 25 checkpoints from 775 actual observations: cue, human
activity or utterance changes, a 20-second gap, and the final observation. It
also creates 11 explicitly authored control episodes with 19 decision steps.
Labels are stored separately and never copied into API inputs. This is a
development pilot, not a held-out benchmark or an accuracy estimate for the
VISTA/EgoArgus papers.

All policies receive the same chronological observations and retain their own
notice history. The model memory is built directly from observations, not the
rule policy's priorities or task labels. Hidden events, future schedules,
deadlines, seeds, review state and evaluation labels are rejected by a closed
input schema. Inputs are engine-visible metadata and authored transcripts,
not RGB/audio. A fixture-only compatibility adapter changes the provenance tag
for the unmodified historical rule implementation; models and exported records
retain the explicit fixture provenance.

Recorded results:

| Measure | Jev 1.13 | Qwen3.5-9B, earlier frozen run |
| --- | --- | --- |
| Requests / valid decisions | 44 / 44 | 44 / 43 |
| Invalid responses | 0 | 1 upstream error/truncated response, retained |
| Authored control steps passed | 14/19 | 9/19 |
| API turnaround p50 / p95 | 0.450 s / 0.541 s | 2.513 s / 11.551 s |
| Provider-reported decision cost | USD 0.00267582 | USD 0.003834 |

The corrected demo adds five English Charon narration clips for USD 0.040305;
its total Jev-plus-narration cost is USD 0.04298082 (49 generation calls).
The earlier Qwen demo's USD 0.047105 and all original receipts remain separate.

Unchanged rules pass 19/19 authored development checks. The two model runs
share byte-identical frozen observations and labels; each model maintains its
own notice history. Jev receives a typed choice with descriptions, Qwen a JSON
chat response schema. Their substantive policy instructions are unchanged.
This is not a simultaneous randomized latency benchmark.

In the native replay, Jev detects the first near-rim cue during a call and
resumes the stove reminder after visible tap-off. It still repeats notices too
often. Its five failed control steps include interrupting ordinary cooking,
interrupting a call for keys, failing to prioritize water over a pending stove
task, repeating that stove notice, and forgetting an unresolved need outside
the view. This result supports testing Jev as a decision component with explicit
memory and interruption control, not claiming reliable autonomous planning.

Qwen missed the first near-rim water cue during a call, warned at the next
running-tap observation, repeated notices, and did not resume the stove reminder
after tap-off. It also inferred resolution from an object leaving the view in
an authored control. All failures are visible; model self-reported confidence
is not a calibrated correctness probability. Jev returns probabilities and
distribution-derived confidence; calibration was not measured on this sample.
Rules matching their authored
development criteria do not establish general superiority.

Timing is measured on the TST API-caller host, including network and receipt
handling, not GPU inference alone. The replay does not model request queuing,
online action effects or counterfactual outcomes. Video alignment uses recorded
wall timestamps and is not certified frame-exact. HUD/console overlays in the
historical recording were never sent to the model.

## Reproduce a bounded pilot

Use the workspace `bin/uv`, with an isolated source worktree. Generated files
belong in a new `workspace/runs/` directory, not source Git.

```sh
PYTHONPATH=tools uv run python -m runtime.vista_jev.prepare \
  --source /path/to/native-decisions.json --out /path/to/new-run
```

Transfer **only** `inputs.jsonl` and the package's `__init__.py`, `protocol.py`
and `runner.py` to the authorized credential-owning host. Keep all labels and
the native reviewer trace on the evaluation side. The initial smoke call is:

```sh
python -m vista_jev.runner --inputs inputs.jsonl --out jev \
  --provider openrouter-jev --key-file /protected/existing-openrouter-keys.txt \
  --limit 1 --budget 0.05
```

Run that command through `uv run --offline --no-project` on the remote host.
After inspecting the receipt, resume with `--limit 43`. Completed requests are
reused only when their request hashes match. An unreceipted started request
blocks resubmission. No retries, model fallback or key rotation occur. At most
60 decisions and USD 0.10 conservative request reservations are permitted.

`--provider openrouter-jev` posts `state` and typed `questions` to
`https://openrouter.ai/api/alpha/decisions`, pinned to `typesafe/jev-1.13` with
fallback routing disabled. It verifies the returned model family and preserves
the response, all five probabilities, confidence, cost and generation ID.
Do not send this model to `/chat/completions`.

The separate `--provider jev` adapter posts to TypeSafe's direct
`/v1/systemone` endpoint and requires a TypeSafe key; that direct transport has
not been measured here. `--provider openrouter` retains the earlier Qwen chat
adapter. Missing credentials produce an explicit result, never mock successes.

## Viewer and video

Copy safe provider receipts back to `<run>/jev/`. `report.py` produces derived
records, metrics and a report while preserving raw outputs. `narrate.py` makes
up to five optional, explicitly authorized English synthetic narration requests;
pass a reviewed `--script` JSON list of `at_s`/`text` entries describing the
actual results (at most 140 words). It uses the male Charon preset. Keep narration
billing separate from decision costs. This narration is postproduction, not model
speech or a cloned human voice.

```sh
PYTHONPATH=tools uv run python -m runtime.vista_jev.report \
  --run /path/to/jev-run --trace /path/to/original-trace.json \
  --provider jev --comparison-run /path/to/frozen-qwen-run
PYTHONPATH=tools uv run python -m runtime.vista_jev.render \
  --run /path/to/run --native /path/to/original-native.mp4
python tools/runtime/vista_jev/serve.py --root /path/to/run/web \
  --bind YOUR_TAILSCALE_IPV4 --port 48997
```

The native image sequence stays continuous at 1280×720, 20 fps, 174.9 seconds;
original Mandarin audio is replaced with English narration, and actual decision
captions are burned in. The viewer has play/pause, scrubbing, chapter buttons,
speed, sound, fullscreen and per-step inspection. It serves only six inventoried
assets, supports byte-range playback, and has no inference or credential endpoint.
Do not expose remote keys, raw auth headers, full run directories or datasets.

The live Moonlight/UE/input/companion/gallery services are separate and unchanged.
No new autonomous navigation, manipulation, animation or native scene deployment
is implied by this replay demo.

## Validation

```sh
PYTHONPATH=tools uv run python -m unittest \
  tools.tests.test_jev_demo tools.tests.test_streaming_policy \
  tools.tests.test_vista_playable_home_contracts \
  tools.tests.test_vista_playable_home_compiler
git diff --check
```

Official contracts checked September 20, 2026:
[TypeSafe API](https://docs.typesafe.ai/api),
[TypeSafe models](https://docs.typesafe.ai/models),
[OpenRouter Jev model](https://openrouter.ai/typesafe/jev-1.13),
[OpenRouter Decisions API](https://openrouter.ai/docs/api/api-reference/alphadecisions/submit-a-decisions-questions-and-answers-request),
[OpenRouter API](https://openrouter.ai/docs/api_reference/overview),
[OpenRouter TTS](https://openrouter.ai/docs/guides/overview/multimodal/tts).
Host-local evidence: corrected `runs/jev-openrouter-20260920-b` and preserved
`runs/jev-demo-20260920-a`, with their workspace handoffs. The Decisions API is
alpha and may change; the executed source and raw requests are retained.
