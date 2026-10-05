# Concurrent assistance pilot

Private native prototype: three VISTA-derived needs, an in-world phone call,
causal rules, physical human actions, persistent world state, two fixed views.
See `docs/research/concurrent-assistance.zh-TW.md` for architecture, provenance
and research limits. No model planning, VLM, ASR or assistant manipulation claim.

Compile the supported authoring prompt without starting a simulation:

```sh
uv run --offline --no-project python tools/runtime/vista_concurrent/scenario.py \
  --out /absolute/new/scenario.json
```

This is a bounded catalog compiler, not arbitrary natural-language generation.
The episode runner validates this JSON and executes its event triggers using
`--scenario /absolute/new/scenario.json`. It supports this one catalog
composition and route; it is not yet a generic execution language.

Copy the verified anatomy DEV with `prepare.py`, build its plugin Editor target,
and cache the reviewed 16 English dialogue lines with `speech.py` on the
authorized key host. Keys remain on that host. The speech tool has a 30-call /
USD 0.20 reserve guard, no redirects, no automatic paid retries; resume reuses
completed PCM and rejects ambiguous started requests. Google documents Orus,
Charon and Iapetus as male synthetic presets:
https://docs.cloud.google.com/text-to-speech/docs/gemini-tts

Launch `vista_companion/private_runtime.py` with a private display and
`--ego-sensor`. Set the actual verified graphics adapter; GPU 1 presentation
was not accepted by the previous native workflow. Shared live services are never
restarted. Required source tests and native runtime evidence are separate checks.

```sh
uv run --offline --script tools/runtime/vista_concurrent/episode.py \
  --run /absolute/private-native-run --out /absolute/new/first-episode \
  --speech /absolute/dialogue-cache --view first
```

Repeat with a new output and `--view third`. Private review control uses a
separate session-bound file inbox and only allows walking, smooth gaze,
independent event addition, phone motion and validated cached speech. Native
object actions use the existing generation-checked action bridge. No arbitrary
console execution, reset or viewpoint change is available through that inbox.
Initial setup occurs before recording. Raw video, checks, privileged trace,
public observations, decisions, command receipts and dialogue are retained.

The Python human controller uses privileged state to navigate known routes and
verify actions. Only `Planner.step` sees the public observation, with completed
authored transcripts labeled as such. This interface boundary is not OS isolation.

Package only completed takes. The review builder requires all physical outcome,
fixed-view, continuity and preemption checks, plus identical scenario specifications:

```sh
uv run --offline --no-project python tools/runtime/vista_concurrent/review.py \
  --first /absolute/first-episode --third /absolute/third-episode \
  --out /absolute/new/review-web
uv run --offline --no-project python tools/runtime/vista_concurrent/serve.py \
  --root /absolute/review-web --bind 127.0.0.1 --port 48998
```

For an already authorized remote review, bind the host's verified Tailscale IPv4.
The server exposes five hash-verified media/page assets with byte-range support;
it never exposes privileged traces, speech credentials or runtime controls.
Native captions contain only the current speaker and their dialogue. The two
recordings are independent executions, not synchronized camera feeds.
