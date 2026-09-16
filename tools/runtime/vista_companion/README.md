# Six-room humanoid companion

The indoor Home map gains a separate humanoid companion, a Traditional Chinese
dialogue panel, VoiceStudio speech, audio-driven facial morphs, and collision-aware
following. The existing player, motion library, room interactions, and campus
entry remain separate. `Config/VistaCompanion.json` enables the feature only in
the new private/frozen companion project.

## Use

Moonlight entry: **VISTA Six Rooms AI**. Start in the living room. **T** opens
dialogue; type a question and press Enter, or select a Chinese quick button.
Follow/wait/stop are explicit buttons. **Esc** closes dialogue or opens the six
room selector; **Q** offers existing object actions and activities; **E** performs
the available object action; **Tab** changes camera view.

This version accepts text/button input and replies with speech and subtitles.
Microphone recognition is not implemented. It cannot operate objects for the
player. The follower traces the player's path with swept character movement;
blocked paths can require the player to lead it around an obstacle. Explicit room
selection places the following companion at a checked nearby floor position.
Waiting companions stay in their room. This is not a navigation/planning benchmark.

## Local models and upstream source

Use `workspace/bin/uv` and a dedicated Python 3.10 environment at
`workspace/services/six-room-companion/venv`. Install `requirements.lock` with
`uv pip install --python <venv>/bin/python -r requirements.lock`, using the
official PyTorch cu128 index for the locked `+cu128` Torch wheels.

External source trees (kept outside this repository):

| Tree | Public upstream | Revision |
| --- | --- | --- |
| VoiceStudio | https://github.com/debpalash/VoiceStudio | `4e55180f700e2ce1b39195ec7377b9b3da8e20b2` |
| CosyVoice | https://github.com/FunAudioLLM/CosyVoice | `074ca6dc9e80a2f424f1f74b48bdd7d3fea531cc` |
| CosyVoice/third_party/Matcha-TTS | https://github.com/shivammehta25/Matcha-TTS | `dd9105b34bf2be2230f4aa1e4769fb586a3c824e` |

`acquire_models.py --service <service directory>` downloads pinned public
Qwen3-4B-Instruct-2507 and Fun-CosyVoice3-0.5B-2512 files without authentication,
and records per-file hashes in `models.json`. Inference uses only these local
weights on GPU 0. VoiceStudio's unmodified CosyVoice subprocess entry point runs
through its real framed JSON protocol; the full VoiceStudio desktop UI is not
required. The default voice is CosyVoice's upstream sample prompt, not the user's
voice. VoiceStudio is AGPL-3.0; CosyVoice/Qwen are separately licensed upstream
components. Source/model license files remain with their external trees.

The reviewed VoiceStudio requirements were insufficient for the pinned CosyVoice
tree: `gdown`, `wget`, `pyarrow`, and `pyworld` were also needed. Transformers is
pinned to **4.51.3** (the CosyVoice upstream version); 5.10.1 caused a mixed-dtype
inference failure. Initial Qwen2.5-1.5B transport tests succeeded but its scene
answers invented states/capabilities, so it is not used in the demo.

The provided user systemd unit binds **127.0.0.1:49010** and is started by the
companion launcher before replacing a current game. It is installed without
enabling automatic startup at login. Existing launcher behavior changes only
when a valid companion config is present: enable game sound, publish companion
proof, and check the local service before scene selection. No cloud model API or
credential is used.

## Observation and animation contracts

`AHomeActionsCharacter::CompanionObservation` builds an independent observable
view: room, line-of-sight/FOV-filtered public object display names, focused object,
and public task description. It does not serialize entity state, event IDs,
evaluation conditions, future events, seeds, or the proof bridge. Opening dialogue
captures this view before turning toward the companion; the request includes
observation age. Known public display labels are translated without adding state.
Dialogue history is bounded to two prior exchanges. Model answers can still make
mistakes: this is a demo, not evidence of perfect grounding or task success.

`build_face.py` keeps the 53-bone body contract and adds seven facial shape
families. `import_companion.py` validates bone order, maps Interchange's generated
per-mesh morph names back to those families, and duplicates materials with morph
usage enabled. Without that flag UE substitutes a gray default skin material.
The player's material assets are not modified. A soft portrait fill keeps the
companion visible in backlit rooms.

Following uses the existing 61-frame walk and actual traveled distance. Root
rotation is bounded, head gaze is limited, and only initial/explicit room travel
uses placement. Facial motion uses 50 Hz PCM energy/spectral proxies and Unreal's
consumed-audio clock. It is **not phoneme alignment or facial performance capture**;
audio device buffering can add delay. Stop/cancel clears the voice, releases the
mouth, cancels inference, and rejects late HTTP replies.

## Reproduction and verification

1. Make an independent authoring copy of frozen `campus-motion-r25-1`; use the
   `six-room-companion-dev-*` project prefix. Copy this plugin's source there.
2. Run `tools/blender/vista_companion/build_face.py` with workspace Blender against
   the retained R25 `character.blend`; output a new run directory.
3. Build editor and game plugin targets with the recorded UE 5.7.3 engine. Run
   `tools/ue/vista_companion/import_companion.py` as a null-RHI Python commandlet
   with `VISTA_COMPANION_SOURCE` and `VISTA_COMPANION_IMPORT_OUT`. Set
   `VISTA_COMPANION_REVISION` to a fresh asset root for every import.
4. `private_runtime.py` launches on its own X display and audio sink. It explicitly
   disables crash upload, analytics, trace server, and UDP messaging. It cleans up
   its processes and sink when stopped. Never use the live `:119` display here.
5. Run `check_native.py`, `check_speech.py`, `check_cancel.py` against the private
   process, and `check_service.py` against the local service. Inspect captures and
   review the generated dialogue; transport success alone is not a semantic pass.
6. Stop the private process. `freeze.py` requires passing native evidence, matching
   plugin/config/service hashes, and unchanged pre-existing scene bytes. It omits
   rejected morph imports, build caches, and host build receipts from the frozen
   payload. The existing manifest launcher performs another preflight.

Service logs, exact text/observable-context requests, audio cache, models, rendered
assets, and proof videos stay in workspace service/run/project directories, never
in Git. Canonical VISTA datasets and papers are not modified by this prototype.
