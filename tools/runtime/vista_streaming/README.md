# Continuous household assistance — development slice

The controlled character is the human who needs help. The separate blue-vest
companion follows and speaks. This slice adds independent event lifecycles, phone
motion, authored Chinese speech, visible symbolic observations, and a transparent
priority/memory baseline. It is not autonomous VLM planning or assistant object
manipulation.

Use an independent `six-room-companion-dev-stream-* / payload` project. Never
modify a frozen release. `prepare_project.py` installs the scoped source/config;
build its Editor and Game targets before native review. `build_props.py`,
`dress_rooms.py`, and `settle_props.py` create/import/place the additional props.
The material and model payloads remain outside Git. The workspace handoff records
exact paths, hashes, build commands and validation receipts.

`prepare_speech.py` uses the already installed local VoiceStudio/CosyVoice model
and a bounded owned service to prepare six cached phrases. It does not call a
remote model, run ASR, or synthesize new planner-generated sentences.

Start a bounded private runtime with `vista_companion/private_runtime.py` using
its own run directory and display. Then, from this worktree:

```sh
uv run --offline --script tools/runtime/vista_streaming/native_slice.py \
  --run /absolute/path/to/private-native-run \
  --out /absolute/path/to/new-audit-run --mode audit
uv run --offline --script tools/runtime/vista_streaming/native_slice.py \
  --run /absolute/path/to/private-native-run \
  --out /absolute/path/to/new-episode-run --mode episode
```

The episode drives the human through actual XTest movement and the native action
executor. It uses a reset and starting fixture before the continuous section;
thereafter it walks through doors and stairs, picks up the phone, adds events
without resetting, puts the phone down, and operates the faucet. Each check is
based on the actual native result. A failed reach, collision, placement or timeout
fails the run and preserves its evidence; do not substitute forced transforms.

The reviewer has privileged `state.json` for verifying outcomes and steering the
scripted human. `policy.py` only receives the separate `observation.json` and an
explicitly authored human transcript. Symbolic cues are filtered by camera view
and line of sight; they are still engine metadata, not visual recognition. The
policy and reviewer are not OS-isolated processes.

Outputs include native video/audio, observations and decisions, issued notices,
action timeline, privileged trace and checks. The video contains console/HUD
authoring information and is an engineering demonstration, not benchmark RGB.
The main continuous slice checks an urgent water reminder during a phone call,
actual human resolution and retention of the earlier stove need. It does not
claim that the companion physically closed the faucet or finished every task.

Development console commands: `HomeEventAdd mmg_001`, `HomeEventAdd mmg_021`,
`HomeEventAdd mmg_044`, `HomePhone 1/0`, `HomeHumanSay human_call/human_request`,
and allowlisted `HomeNotice water/stove/keys/resume/quiet`. `HomePhone 1` requires
the physical phone to be held. Other hand actions require it to be lowered first.
Events with conflicting initial writes or objects in use are rejected; completed
templates can recur with distinct instance IDs. Legacy `HomeEvent` still resets.

For paper-oriented research questions, controls and metrics, see
`docs/research/ego-streaming-assistance.md`.
