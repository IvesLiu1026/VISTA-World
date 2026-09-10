# Moonlight recovery for Alpine Villa R3

On 2026-09-10, the Windows client initially showed black video and disconnected
after roughly ten seconds. A later connection produced an image with severe
frame loss. Capping Sunshine's video encoding bitrate at 4000 Kbps restored
the following client-observed result:

| Windows performance overlay | Before cap | After cap |
| --- | ---: | ---: |
| Incoming / decoded / rendered FPS | 5.59 | 59.38 |
| Frames dropped by network | 92.03% | 0.00% |
| Average network latency | 128 ms | 1 ms |
| Resolution / codec | 1920x1080 / H.264 | 1920x1080 / H.264 |

These readings came from screenshots supplied by the user. The later Sunshine
session began at 18:41:26 Taiwan time, logged a 4000000 bps video bitrate, and
remained connected during the final verification. The selected launcher was
`VISTA Alpine Villa R3`. Keep this session available for the user's demo.

## Retained host configuration

The host uses `vista-sunshine.service` with X11 display `:119` and Sunshine
2026.516.143833. The relevant keys in
`/home/yhliu/.config/sunshine/sunshine.conf` are:

```ini
capture = x11
output_name = 0
encoder = software
sw_preset = ultrafast
sw_tune = zerolatency
hevc_mode = 1
av1_mode = 1
max_bitrate = 4000
```

This is the verified conservative demo setting. Encoding bitrate excludes some
transport, audio and error-correction overhead. At 1080p, fine outdoor details
can show compression; higher-bitrate quality and sustained long-term stability
need a separate client check. Hardware encoding has not been revalidated with
the cap. The active user session was retained instead of changing the encoder.

## Application menu and preservation

The original ten Moonlight entries accumulated as separate historical demo
launchers. The visible menu now contains `Desktop`, `VISTA Alpine Villa R3`,
and `VISTA World`. Each retained application definition matches its original
parsed JSON object. All ten definitions
were backed up before the seven older entries were removed from the menu.
Historical project assets and launch scripts remain available.

The 4 Mbps change restarted only `vista-sunshine.service`. The R3 game and input
services retained PIDs 1717761 and 1719296. The frozen project remains
`/data/sysx/vista-world/runs/vista-villa-r3-20260910a/demo-project-a/PhotorealHome.uproject`.
Authentication, network security settings, the other desktop-streaming service,
research GPU jobs, and production ports were unchanged.

## What the investigation established

- The X11 root image and the same XCB shared-memory capture API used by Sunshine
  both contained rendered scene pixels. This alone did not prove client delivery.
- Both NVENC and a software-encoder trial had black-screen reports. The first
  visible software session still lost 92.03% of video frames. An encoder change
  alone therefore did not establish recovery.
- Metadata captured through Tailscale's supported diagnostic interface showed
  399033 outgoing video packets in the visible, lossy session: 1068-byte IPv4
  packets, without fragmentation, below the interface's 1280-byte MTU. No
  packet-size override or MTU change was applied.
- Sunshine 2026.906.222525 was downloaded and verified against the official
  release SHA-256 during investigation. It was never activated; the global
  Sunshine launcher and other desktop service were untouched.
- The client overlay improved after the 4000 Kbps cap. Excessive network frame
  loss is established; the exact congested hop and the earlier transition from
  black video to a visible image remain unresolved.

## Evidence and recovery procedure

Host-local evidence is append-only under
`/data/sysx/vista-world/runs/vista-moonlight-recovery-20260910a`:

| File | Purpose |
| --- | --- |
| `sunshine.conf.before`, `apps.json.before` | Original configuration and all ten launchers |
| `sunshine.conf.before-bitrate-cap-a` | Software trial before the 4 Mbps cap |
| `software-trial-config.json` | Archived menu entries and initial config hashes |
| `bitrate-cap-a.json` | Scoped change and service PIDs before restart |
| `stream-metadata-d.jsonl` | Selected peer's UDP sizes/directions/fragments; no payloads |
| `user-verified-low-bitrate-a.json` | Before/after Windows readings, screenshot hashes, final config and runtime |
| `verified-session-summary-a.log` | Filtered connection and bitrate log |

Temporary packet capture was stopped after verification. Raw captures, client
screenshots, downloaded binaries, and host configuration backups stay outside Git.

For a recurrence, first collect the Windows performance overlay with
`Ctrl+Alt+Shift+S` and correlate its time with the named Sunshine service log.
Check incoming FPS, network frame loss and latency before changing settings.
Retain the 4 Mbps cap during the immediate demo. Adjust one variable per trial
and obtain client evidence after each change. Preserve the active project and
input service when a Sunshine reload is necessary.

The saved backups support rollback. Compare them with current configuration
first and restore only the intended keys or application definitions, preserving
subsequent edits and authentication. Never replace the shared launcher or
restart the other desktop-streaming service as an incidental repair step.

Primary references: [Moonlight performance overlay](https://github.com/moonlight-stream/moonlight-docs/wiki/Setup-Guide),
[Moonlight's ten-second first-frame timeout](https://github.com/moonlight-stream/moonlight-common-c/blob/master/src/VideoStream.c),
[Sunshine bitrate configuration](https://github.com/LizardByte/Sunshine/blob/14ffa6fdaa53f7b51512be2b3d24f3939695403c/docs/configuration.md),
and [Tailscale packet inspection](https://tailscale.com/docs/reference/troubleshooting/network-configuration/inspect-unencrypted-packets).
