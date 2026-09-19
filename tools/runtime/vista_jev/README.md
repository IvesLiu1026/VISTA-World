# Continuous assistance: real decision replay

This pilot runs observed-state decisions against the existing rule assistant.
The private viewer synchronizes real API responses with an existing native
six-room recording. It **does not claim that the model controlled the recording**.
The human's physical actions were scripted in the original engineering episode.

The September 20 pilot uses **`qwen/qwen3.5-9b` via OpenRouter**, reasoning
disabled. Jev was absent from the OpenRouter model catalog and the user had not
opened a TypeSafe account. The Jev adapter is implemented but has **zero real
requests and no measured Jev performance**. Never substitute Qwen results under
Jev's name.

## Inputs and results

`prepare.py` selects 25 checkpoints from 775 actual observations: cue, human
activity or utterance changes, a 20-second gap, and the final observation. It
also creates 11 explicitly authored control episodes with 19 decision steps.
Labels are stored separately and never copied into API inputs. This is a
development pilot, not a held-out benchmark or an accuracy estimate for the
VISTA/EgoArgus papers.

Both policies receive the same chronological observations and retain their own
notice history. The model memory is built directly from observations, not the
rule policy's priorities or task labels. Hidden events, future schedules,
deadlines, seeds, review state and evaluation labels are rejected by a closed
input schema. Inputs are engine-visible metadata and authored transcripts,
not RGB/audio. A fixture-only compatibility adapter changes the provenance tag
for the unmodified historical rule implementation; models and exported records
retain the explicit fixture provenance.

Recorded results:

| Measure | Result |
| --- | --- |
| Qwen requests / valid decisions | 44 / 43 |
| Invalid response | 1 upstream error/truncated response, retained |
| Authored control steps passed | Qwen 9/19; unchanged rules 19/19 |
| API turnaround p50 / p95 | 2.513 s / 11.551 s |
| Provider-reported decision cost | USD 0.003834 |
| English synthetic narration | 5 Charon clips, USD 0.043271 |
| Total reported API cost | USD 0.047105 |

Qwen missed the first near-rim water cue during a call, warned at the next
running-tap observation, repeated notices, and did not resume the stove reminder
after tap-off. It also inferred resolution from an object leaving the view in
an authored control. All failures are visible; model self-reported confidence
is not a calibrated correctness probability. Rules matching their authored
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
python -m vista_jev.runner --inputs inputs.jsonl --out qwen \
  --provider openrouter --key-file /protected/existing-openrouter-keys.txt --limit 1
```

Run that command through `uv run --offline --no-project` on the remote host.
After inspecting the receipt, resume with `--limit 59`. Completed requests are
reused only when their request hashes match. An unreceipted started request
blocks resubmission. No retries, model fallback or key rotation occur. At most
60 decisions and USD 0.10 conservative request reservations are permitted.

To test actual Jev after TypeSafe access exists, use a fresh output directory,
`--provider jev`, and a protected plain TypeSafe key file or `TYPESAFE_API_KEY`.
The model is pinned to `jev-1.13.0`. Missing credentials produce an explicit
missing-credentials result, never mock successes. An OpenRouter key is not a
TypeSafe credential. The real Jev integration still needs a successful smoke
call before its compatibility is accepted.

## Viewer and video

Copy safe provider receipts back to `<run>/qwen/`. `report.py` produces derived
records, metrics and a report while preserving raw outputs. `narrate.py` makes
five optional, explicitly authorized English synthetic narration requests;
its script describes the measured September 20 result and must be revised
if applied to different results. This narration is postproduction, not model
speech or a cloned human voice.

```sh
PYTHONPATH=tools uv run python -m runtime.vista_jev.report \
  --run /path/to/run --trace /path/to/original-trace.json
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
[OpenRouter API](https://openrouter.ai/docs/api_reference/overview),
[OpenRouter TTS](https://openrouter.ai/docs/guides/overview/multimodal/tts).
Host-local evidence: `runs/jev-demo-20260920-a` and its workspace handoff.
