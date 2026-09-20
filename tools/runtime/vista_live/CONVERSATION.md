# Open-topic conversation during household activity

Every new typed message and every completed, explicitly assistant-addressed
authored human line goes through actual Jev intent classification. Jev remains
the fast typed decision model; `qwen/qwen3.5-35b-a3b` generates free-form answers
and relevant follow-up questions. No topic menu, prerecorded assistant dialogue,
or template matching replaces these calls. The human review lines are explicitly
authored stimuli, and must not be reported as microphone recognition or autonomous
human behavior.

`Conversation` retains the last 16 turns from both speakers with provenance.
Native caption acknowledgements are recorded separately from completed audio.
An answer can therefore appear in-world while its English male voice is being
prepared. A new input invalidates pending generation/queued audio. Stop or pause
does not silently retry a failed model request. Failed and interrupted requests
remain in the evidence log and durable budget.

Ordinary exchanges respond immediately after the human's turn. Each response
answers the actual question before offering at most one relevant follow-up. The
assistant waits for the human's answer; it never fabricates that answer or
repeatedly asks an unanswered question merely to inflate interaction frequency.
Physical requests are classified even while casual conversation is suspended,
so asking for help can resolve the situation that interrupted the conversation.

An observed urgent water/stove need or an active phone-at-ear interaction suspends
casual generation. The fast warning path remains independent of text generation
and TTS. After observed resolution/phone end, the companion reconnects to the
actual preceding topic with a fresh public observation. Low-priority key finding
can coexist with conversation. Requests to stop talking and the chat-pause button
stop casual speech while retaining hazard monitoring.

The conversation generator has a separate closed, speech-only schema. It cannot
issue engine operations. Physical execution still requires an explicit human
request, current visible evidence, an allowed native skill, collision/reach checks
and a native contact receipt. Topics are open, but there is no live web retrieval,
ASR, RGB perception, or unrestricted arbitrary engine control.

## Walking

Both private human routes and live companion following preview bends before
arriving at the waypoint. Shortcuts require a full swept capsule plus sampled,
supported floor; stairs/ledges retain the recorded route. Narrow corners keep
their waypoint until the next full chord is clear. A forward probe reduces speed
before contact, and supported short side corrections help with door posts.
The original CharacterMovement collision capsule remains authoritative, including
slow tangential passage at narrow frames. No collision disabling, body teleport,
or hidden ground-truth planner is used to demonstrate ordinary walking.

The manual player's WASD direction is still under the human's control. Route
steering affects the authored human review route and the companion's following,
not an unwanted automatic turn of manually controlled input. This is a local
route-steering improvement, not a trained navigation or motion-matching system.

## Isolated review

Use a new `six-room-companion-dev-natural-*` project, an unused display, and
distinct native/backend ports. `private_runtime.py --live-port 49113` connects the
native panel to the private backend. `service.py --port 49113 --web-port 49000
--bridge PRIVATE_RUN/bridge` never selects the live runtime. The private audio
launcher verifies/moves only its own UE process's sink-input because SDL stream
restore may override `PULSE_SINK`.

Prepare `conversation_speech.py --out SPEECH --provider LOOPBACK_PROVIDER` once;
it creates human-only English male stimuli and refuses ambiguous paid retries.
Run `conversation_review.py --workspace WORKSPACE --run PRIVATE_RUN --out NEW_OUT
--view first|third --port 49113`. Both recordings retain a continuous fixed view,
native in-world audio and captions. The companion's answers, prioritization and
contact actions come from the separate live service. The review checks drink and
music recall, topic change, conversational suspension, three native event
outcomes, movement continuity and anticipatory corners.

New task allowances are explicitly configurable on the provider. Once stored in
the task SQLite ledger, restarting with different limits/cap is rejected; request
counts, ambiguous reservations and prior evidence cannot silently reset. Different
tasks use different named ledgers with separately recorded authorization.
