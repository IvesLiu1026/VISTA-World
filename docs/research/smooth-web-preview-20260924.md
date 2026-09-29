# Continuous web preview

The research page previously updated two PNG screenshots once per second.
Their native source produces two synchronized evidence pairs per second. That
transport cannot display continuous walking even when the game renders normally.
This change adds an independent human-viewing stream at the existing demo URL.

The default **即時畫面** tab shows the current game viewport at960x540 with a
30FPS target. **省流量** sends at most15FPS from the same encoder. The original
paired first/third screenshots remain under **雙視角觀測**, with the same
low-frequency evidence semantics and existing archive hashes. The main preview
follows the game's selected camera; it is not two simultaneous30FPS cameras.
Completed recordings and offline downloads are unchanged. Free movement, view
switching and live audio remain in Moonlight; the MJPEG preview carries images.

`--web-preview` enables an on-demand local FFmpeg window capture. It checks the
selected project, GPU0/display119 identity, Unreal process, native window PID
and class. Only that window is captured; window or selection changes invalidate
the current source. The producer checks ownership while consuming frames.
Preview pixels may contain game HUD and third-person content and must never be
used as policy evidence. The clean ego-RGB contract/capture path is unchanged.

All viewers share one CPU encoder. A bounded latest-frame slot, frame size limit,
four-viewer cap, finite socket writes and disconnect cleanup prevent a slow
reader from queuing stale frames or blocking the producer. Switching tabs or
hiding/leaving the browser disconnects its stream. The encoder stops after two
seconds without viewers and restarts on demand. The15FPS option reduces network
traffic, not the shared encoder's capture rate. No new dependencies or model
requests are required. Existing local FFmpeg, xwininfo and xprop are used.

Validation on the host's actual VISTA window measured30.002 encoded frames/s.
A headless Chromium canvas sampled148 distinct decoded frames in4.996seconds
(about29.6 updates/s) while the page displayed the live stream. A deliberately
stalled HTTP viewer disconnected while a second viewer continued at30.10FPS,
maximum sampled gap34.7ms and zero observed latest-frame backlog. These are
host-local checks, not a claim about the user's Mac/network performance.
The tested detailed scene uses approximately13.4Mbit/s at30FPS; MJPEG is less
bandwidth-efficient than Moonlight's video codecs. Use15FPS on a slower link.

139 focused/live/research/Director/baseline tests passed, including split JPEG
framing, bounded memory, shared encoder reuse, ownership revocation, idle cleanup,
reconnect, viewer limits, and preserved research input/permission behavior.
No native source, assets, model, ledger cap or GitHub workflow changes. The
existing inherited broader native-camera assertion is outside this patch; the
full suite and remote Actions were not rerun for this web-only change.

Host evidence, browser screenshots, final cadence, deployment/rollback and
limitations are in `runs/smooth-web-preview-20260924-a` and the workspace handoff.
