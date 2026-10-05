# Bath outcome pilot

Open `/bath` on the existing **research** live service. Three reference
conditions validate the world before a separate model rollout. All use event
`mmg_021`, a phone-holding person at the reviewed bathroom anchor, native time,
and a 140-second evaluation horizon after event start. Preparation is additional.
Use the existing scene/actor ownership, explicit user authorization for inference,
and local TTS. No native payload change is required on responsive-a.

| Condition | Warning | Controller |
|---|---|---|
| control | none | no intervention; zero model calls |
| timely | t >= 12 s | reference controller |
| late | t >= 100 s | same reference controller |
| model | chosen by the model from t >= 12 s | existing research policy, at most 8 requests |

The person responds only after accepted, relevant assistant speech finishes
native playback. After two native seconds it says `Please turn off the bath tap
now.` Both controllers use that delivered current request and native contact
guards. The listener is deliberately limited to English water-warning patterns;
negations and unrelated messages are unmatched and logged. This is a controlled
actor, not a general semantic human model. Model warnings are not supplied by the
reference controller. Interrupted or stale speech cannot grant permission.

The prelude and closing call are fixed. After an actual committed operation the
person resumes the phone conversation. No intervention means no permission branch.
Call continuation is a bounded scripted proxy, not proof of arbitrary human-goal
completion. The model receives only the existing closed ego RGB / completed
utterance / own-action / memory packet. Evaluator water state, future script,
reference timing and third-person images stay outside that packet.

`/bath/play` accepts `condition` and `view` (`first` or `third`); `/stop` interrupts
the owned episode. Other scene jobs are mutually exclusive. Manual dialogue is
refused during a controlled bath run. At completion inference pauses. Keyboard
or external native changes can invalidate a comparison; inspect the trace.

Each `BACKEND/bath/RUN_ID` contains protocol, initial state, sampled native trace,
delivered events and results. Sampling is approximately 150 ms wall time; report
actual native sampling intervals. `tap_off` requires both committed receipt and
final off state. `overflow_ever` is historical, including overflow followed by
shutoff. Scores are recomputable with:

```sh
PYTHONPATH=tools uv run python -m runtime.vista_live.bath_audit \
  --root BACKEND/bath --out bath-audit.json
```

The audit compares t=1..10 native seconds, with preselected .005 normalized-level
and 2 cm person-position tolerances. It checks a common protocol, completed
horizons, causal speech/request/commit ordering, preserved stove state and
reference outcomes. It reports all attempts; latest completed runs supply the
pilot comparison. Failed attempts must remain disclosed. Model success is
reported separately, never required for world validation.

`bath_review.py` records through the same API using an explicitly owned private
runtime or selected development game. Record each condition separately. Retain
same-run ego captures alongside the third-person film. Publish reviewed recordings
as `BACKEND/media/bath-{control,timely,late,model}.mp4`; media paths use existing
range-serving protections. `/bath/results` exposes evaluator-only records.

For the meeting: 30 seconds setup, two minutes A/B/C recordings, one to two
minutes real-model evidence, one minute outcome table. Show one live replay if
time permits. Pre-recordings are labeled and preserve unsuccessful model runs.
This pilot covers direct state and temporal consequences plus one controlled
human branch. It does not establish multi-scenario benchmark performance, coupled
consequences, spill cleanup, fluid volume, or general physical fidelity.
