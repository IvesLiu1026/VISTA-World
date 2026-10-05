# Live six-room assistance

Natural-language scene + human acting is available at `/director`. See
[the scenario director report](../../../docs/research/20260921-scenario-director.md)
for supported skills, evidence, model roles and research limitations.
`/director/compile`, `/director/play` and `/director/stop` use the same web token
boundary as the existing controls. `--paused` starts a test service without
background assistant inference; starting a performance temporarily enables it.

For anticipatory walking, open-topic Q&A, turn memory and conversation interrupted
by concurrent events, see [CONVERSATION.md](CONVERSATION.md).

This is an interactive extension of the concurrent home demo. A person can move
freely in Unreal while an independent service observes, asks actual TypeSafe Jev
for an intervention decision, plays English speech inside the engine, and keeps
unresolved tasks across room changes. The human is the person receiving help;
the second embodied character is the assistant.

## Responsibilities and evidence

1. `HomeStreaming.cpp` exports the human's visible object/cue metadata and held-key
   proprioception. It uses the human ego sensor in both presentation views.
2. `policy.py` keeps last-seen cues, sourced human utterances, goals and pending
   needs. Jev selects wait, observe, stove reminder, urgent bath reminder or key
   reminder. Guards reject unsupported observations and preserve urgency:
   water, stove, keys. Leaving a room does not resolve a need.
   These public-evidence guards also determine which intervention choices are
   offered to Jev. Wait/observe remain available; a known-off tap is excluded even
   while near-rim water is still visible. This is constrained action selection,
   not an unguarded model accuracy benchmark. Raw subset probabilities are retained.
3. `provider.py` calls OpenRouter's actual `alpha/decisions` API with
   `typesafe/jev-1.13`; dated returned versions are checked. It also uses Jev for
   typed intent and furnishing-preset selection. No simulated Jev fallback exists.
4. `qwen/qwen3.5-35b-a3b` compiles NL authoring and produces bounded plans. Plans
   preserve Jev's first task, cannot control the person's body, and cannot authorize
   a physical manipulation. A rejected plan is shown as an error.
5. Native English male warning clips start before slow generative planning.
   Novel responses use `google/gemini-3.1-flash-tts-preview` (Charon assistant,
   Orus human, Iapetus phone), cached after generation. Unreal plays PCM, mouth
   motion and captions. Recordings capture that engine audio; there is no ADR.
6. An explicit human request can trigger a nearby stove/tap turn-off. Native
   code sweeps the body approach, checks support and line of sight, rotates the
   existing arm chain, and requires index-finger contact before committing state.
   A committed/blocked receipt produces the completion/failure response.

Scene authoring and assistant observation are separate. The assistant never gets
the director prompt, event schedule, evaluator state, hidden entity list, gold
labels or route. Typed messages are labelled typed input. Authored human speech
becomes evidence only after native playback has completed; an interrupted line
is not recorded as fully heard. The service has no ASR or RGB/VLM perception.

## Current scope

- All six existing furnished rooms remain traversable. NL selects a starting
  room, one of everyday/workday/evening, and any subset of stove (`mmg_001`),
  running bath (`mmg_021`) and key search (`mmg_044`), each delayed 0–300 seconds.
- Workday stacks one existing book at a verified office support; evening also
  enables the warm lamp. These are asset-library presets, not new generated
  buildings, arbitrary geometry or arbitrary object arrangements.
- Optional male phone dialogue is an authored audible stimulus; it does not put
  a phone in the person's hand. In play, pick up the phone and use the contextual
  Answer/End action with E. The review script does this with real contextual input.
- Physical assistant skills are follow, wait and nearby contact-checked turn-off.
  Generated `check`/`ask` steps are guidance. The assistant does not yet grasp and
  deliver keys or execute arbitrary multi-room manipulation plans.
- Contact is kinematic fingertip proximity, not a force-based robotics simulation.
  Long-range navigation, complex crowds and general motion synthesis are outside
  this implementation. Body motion retains the existing skeleton; limb lengths
  are not stretched to reach a target.

## Run

Use workspace `bin/uv`. Source is deployed in an isolated worktree and prepared
into an independent `six-room-companion-dev-live-a` project using `prepare.py`.
Compile the project plugin with the project's UE 5.7.3 Editor target. Preserve
the donor project and external asset/license scope.

On the authorized key host, run `python -m runtime.vista_live.provider --root
EVIDENCE --key-file AUTHORIZED_FILE --port 49112`. Bind stays loopback; connect via
an SSH loopback tunnel. The key never leaves that host and is not logged. Start
the local service with `--root EVIDENCE --workspace WORKSPACE --speech CLIP_DIR`.
`--bridge PRIVATE_RUN/bridge` targets isolated review; omit it for the selected
live project. The web UI defaults to loopback port 48999; a host-local deployment
can bind it to its private Tailscale address. The native endpoint stays loopback
49111. No API keys go into the browser or Unreal project.

The launcher detects `Config/VistaLive.json` and enables live/ego-sensor flags.
It checks the local service before replacing the user's game. Other projects
retain their earlier assistant behavior. Select the previous project and host
profile to roll back; preserve Sunshine credentials and paired clients.

Controls: WASD, mouse, E contextual action, T assistant panel, Tab perspective.
The web UI accepts Chinese scene descriptions and typed requests. Start with:

> 工作日的家。我準備出門找鑰匙，爐火還開著；30 秒後浴缸開始放水，
> 同時接到電話。從廚房開始。

Generate, review the proposal, then apply. Unsupported requests are rejected
before changing the world. Applying resets the current scene and pending tasks.
Stop cancels speech, manipulation and outstanding model results while the physical
events continue. Pause disables proactive decisions; explicit requests remain
available. Stale generation/observation replies cannot act on a newer scene.

## Limits and accounting

The persistent SQLite guard reserves at most 1,000 decision/intent/layout calls,
60 plan/author calls, 30 new TTS clips and USD 2 of conservative request reserves.
The guard uses provider-reported charges after successful responses and retains
full reservations for pending, failed, ambiguous or unpriced (including TTS)
requests. Reconciliation never resets request counts or erases the original
reservations. Reserves are not reported actual spend. Failed/ambiguous calls still count; no
automatic retry, key rotation or provider/model fallback. A provider failure or
exhausted budget shows an error; local movement remains responsive. Inspect
receipts before manually reopening a provider circuit.

Jev latency is decision API time, not microphone-to-speech latency. Cached native
warnings and newly generated dialogue have different latency paths. Native action
completion is measured separately. Do not claim general planning accuracy from
the authored demo or confuse visible engine metadata with video understanding.

Choice validation follows the [TypeSafe response contract](https://docs.typesafe.ai/primitives/choice):
the returned choice must have maximal probability. An observed upstream response
violated this condition during development; it was retained and rejected, and the
UI required explicit recovery. Do not relax the validator to hide failed trials.

## Validation and recordings

`tools.tests.test_vista_live` covers observation boundaries, causality, urgency,
resolution, delayed replies, cancellation, delivered speech, strict contracts and
durable budgets. Run the repository contract/compiler baseline, Jev/concurrent
regressions and workspace launcher tests as well. Compile evidence and actual
native evidence are separate checks.

`review.py` drives an authored human route/dialogue only. The separate live service
makes all assistant decisions; the recording harness cannot inject an assistant
warning. Capture uses continuous native first or third person, X11 plus Pulse audio,
and retains event/contact/view/teleport checks. Failed trials remain separate.
The live presentation hides the VSM overflow screen banner only; rendering settings,
diagnostic logs and sampled frame times remain available for performance review.
The `/demo` page serves only the two explicitly published MP4/JPEG pairs under
the local service root's `media` directory. No evidence directory listing is exposed.

Host-specific hashes, native results, timings, deployment and rollback are recorded
in the workspace handoff, outside source Git. External assets and media are not
committed. This is an engineering research prototype, not a completed benchmark.
