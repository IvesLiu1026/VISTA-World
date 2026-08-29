# VISTA R8 BuildPlugin Authority R1

Status: source reviewed; administrator installation and publication not run
Updated: 2026-08-30

## Fixed reviewed helper trust anchor

The reviewed helper source has this exact record:

```text
relative_path: tools/admin/vista_r8_buildplugin_authority.py
sha256: 9db9ca95ccb4fb8d97e08addafa0b8e85bfd3464644ce8f2907003a5b1544c91
size_bytes: 60785
installed_path: /root/vista-r8-buildplugin-authority-r1/vista_r8_buildplugin_authority.py
installed_owner: root:root
installed_mode: 0500
```

This literal is intentionally outside the helper. A file cannot securely pin
its own digest without a recursive hash cycle. The administrator must obtain
the literal from the reviewed commit or an independent reviewer channel, not by
dynamically assigning `EXPECTED=$(sha256sum mutable-checkout-file)` during the
installation session.

The root helper records its observed digest in the authority receipt but does
not self-authorize it. The authoritative bootstrap gate is the administrator's
post-install comparison of the root-owned installed file against the independent
literal above.

## Administrator boundary

These are future administrator actions. They were not executed by the Codex
implementation lane.

1. Independently copy the expected SHA-256 above from the reviewed commit or
   reviewer handoff.
2. A pre-install checksum of the checkout is useful diagnostics, but is not an
   authority because the same UID can still replace it before `install` reads
   it.
3. Install the helper to the literal root path as root:root mode `0500`.
4. Recompute SHA-256 and byte size from the installed `/root` file and compare
   them to the independent literal. This post-install verification closes the
   checkout precheck-to-install race. Do not execute a mismatch.
5. Require `/data/vista-authorities` itself to be root:root mode `0555`. Do not
   point the helper at an alternate parent.

One possible administrator transcript, after independently fixing `EXPECTED`
to the reviewed literal, is:

```bash
EXPECTED=9db9ca95ccb4fb8d97e08addafa0b8e85bfd3464644ce8f2907003a5b1544c91

sudo install -d -o root -g root -m 0700 \
  /root/vista-r8-buildplugin-authority-r1
sudo install -o root -g root -m 0500 \
  tools/admin/vista_r8_buildplugin_authority.py \
  /root/vista-r8-buildplugin-authority-r1/vista_r8_buildplugin_authority.py

printf '%s  %s\n' "$EXPECTED" \
  /root/vista-r8-buildplugin-authority-r1/vista_r8_buildplugin_authority.py \
  | sudo sha256sum -c -
sudo stat -c '%s %a %U %G %n' \
  /root/vista-r8-buildplugin-authority-r1/vista_r8_buildplugin_authority.py
```

Expected stat fields are `60785 500 root root` and the exact installed path.
The administrator must separately ensure the authority parent exists safely;
the helper refuses to create or relax it.

## Audit, publish, and reconciliation

First run the zero-write audit from the installed helper:

```bash
sudo /usr/bin/python3.10 -I -B \
  /root/vista-r8-buildplugin-authority-r1/vista_r8_buildplugin_authority.py \
  --audit-source
```

It must report `accepted:false`, source projection
`69153cd676ac35579115d1be9c8ced7d86c70beab7f8adb681ad7b8d373ae48e`,
241 files, 32 directories, and 51,661,522 bytes. An existing authority pathname
is reported as observed but unvalidated; audit never claims it is absent or
accepted without observing it.

The closed audit report also records an explicitly unvalidated
`execution_boundary`: the expected installed helper path, the requirement for
an external helper trust anchor, and the pinned interpreter path, SHA-256, and
byte size. `live_interpreter_validated` remains `false` in audit mode because
checkout audit does not invoke the installed-root execution gate. Only
`--publish` or `--reconcile-published` validates the live `/proc/self/exe`
binding after the independent post-install helper check.

Only after the audit and independent installed-helper check may the
administrator choose one fresh publication:

```bash
sudo /usr/bin/python3.10 -I -B \
  /root/vista-r8-buildplugin-authority-r1/vista_r8_buildplugin_authority.py \
  --publish \
  --acknowledgement \
  'I acknowledge one fresh publication of the reviewed VISTA R8 UE 5.7 BuildPlugin authority.'
```

If the command returns
`BUILDPLUGIN_AUTHORITY_PUBLISHED_DURABILITY_UNKNOWN`, rename already succeeded
but the authority-parent fsync did not. The final path may exist. Do not retry
`--publish`, remove the final path, or infer that publication rolled back.
Reconcile the existing immutable tree instead:

```bash
sudo /usr/bin/python3.10 -I -B \
  /root/vista-r8-buildplugin-authority-r1/vista_r8_buildplugin_authority.py \
  --reconcile-published \
  --acknowledgement \
  'I acknowledge reconciliation of the existing VISTA R8 UE 5.7 BuildPlugin authority without republishing it.'
```

Reconciliation regenerates the expected manifest/receipt from the held pinned
source, audits every final byte and mode, revalidates the source namespace,
fsyncs the complete final tree and parent, and reports
`published_buildplugin_authority_durability_reconciled`. It never renames or
republishes the authority.

## Claim boundary and remaining work

This authority proves only that the exact reviewed BuildPlugin package was
copied through the root-owned immutable publication boundary. It does not prove
that UE loaded the plugin, imported the R8 animations, ran pickup/place, passed
two-client testing, or reached human-motion, photoreal, or GTA quality.

After administrator publication, a separate reviewed change must pin the
authority `payload/` projection into the R8 materializer. A separately sealed
UE 5.7 execution authority/runner is still required before any apply or runtime
claim.
