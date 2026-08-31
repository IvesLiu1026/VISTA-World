# VISTA R8 BuildPlugin Authority R1

Status: source reviewed; administrator installation and publication not run
Updated: 2026-08-30

## Fixed reviewed helper trust anchor

The reviewed helper source has this exact record:

```text
relative_path: tools/admin/vista_r8_buildplugin_authority.py
sha256: 1e699c84d025dfa73872b20eb035610b2dc85074fa28f716a48ae34f324cfca2
size_bytes: 80566
installed_path: /root/vista-r8-buildplugin-authority-r1/vista_r8_buildplugin_authority.py
installed_owner: root:root
installed_mode: 0500
```

This literal is intentionally outside the helper. A file cannot securely pin
its own digest without a recursive hash cycle. The administrator must obtain
the literal from the reviewed commit or an independent reviewer channel, not by
dynamically assigning `EXPECTED=$(sha256sum mutable-checkout-file)` during the
installation session.

The root helper records its observed digest but does not self-authorize it. The
authoritative bootstrap gate is the separately reviewed initial R8 one-shot,
which consumes the sealed core-review audit and copies the exact reviewed bytes
through held descriptors. It also installs the distinct BuildPlugin admin
authority and its closed receipt.

## Administrator boundary

These are future administrator actions. They were not executed by the Codex
implementation lane.

1. Complete the two-commit R8 review sequence and freeze the engine source pin,
   BuildPlugin helper/admin candidate, and canonical zero-write core audit.
2. Independently review the later literal-pinned initial one-shot bootstrap.
   It must publish the BuildPlugin helper root as root:root `0555` with exact
   sole file `vista_r8_buildplugin_authority.py:0500`.
3. The same append-only bootstrap publishes a separate root:root `0555` admin
   authority with exact
   `{publish-reconcile-buildplugin:0500, receipt.json:0444}`. The receipt binds
   the helper, pinned Python, admin script, and core-review provenance.
4. Never directly install or execute a checkout or `/tmp` wrapper. Operationally,
   privileged helper modes are entered only after a trusted root process opens
   and passes the fixed admin-launcher FD. This is an exact live-validation gate,
   not a claim that root is structurally unable to construct such an FD. Require
   `/data/vista-authorities` itself to be root:root `0555`; the helper refuses to
   create or relax it.

## Audit, publish, and reconciliation

The zero-write source audit remains available before privileged publication:

```bash
/usr/bin/python3.10 -I -B tools/admin/vista_r8_buildplugin_authority.py \
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

Only after the audit, four-root bootstrap, and parent seal may the administrator
choose one fresh publication. The generated admin is never directly/shebang
invoked; use fixed `env -i` system bash. It holds its own FD, and the helper
cross-checks that FD against the immutable sibling receipt before any write:

The resulting BuildPlugin authority receipt uses
`vista.r8-buildplugin-authority-receipt/v2`. Its closed `admin_publication`
record binds the fixed admin root/mode, launcher name/path/pin/mode, sibling
receipt name/path/pin/mode/schema/content digest, bootstrap provenance, and
`admin_launcher_fd_required:true`. Runtime consumers rehash that fixed admin
authority; v1, omitted, unknown, tampered, or rebound bindings fail closed.
The root-side R2 loader and terminal executor also re-open the publisher helper
authority as exact root:root `0555` inventory
`{vista_r8_buildplugin_authority.py:0500}`, require one single-link helper, and
rehash it against `receipt.publisher.helper`. The BuildPlugin publisher
interpreter pin must equal the root policy's live Python pin; runtime publication
provenance separately rehashes the same fixed `/usr/bin/python3.10` bytes before
the complete terminal authority set is accepted.

```bash
sudo /usr/bin/env -i PATH=/usr/bin:/bin /usr/bin/bash \
  /root/vista-r8-buildplugin-admin-r1/publish-reconcile-buildplugin \
  publish-buildplugin \
  'I acknowledge one fresh publication of the reviewed VISTA R8 UE 5.7 BuildPlugin authority.'
```

If the command returns
`BUILDPLUGIN_AUTHORITY_PUBLISHED_DURABILITY_UNKNOWN`, rename already succeeded
but the authority-parent fsync did not. The final path may exist. Do not retry
`--publish`, remove the final path, or infer that publication rolled back.
Reconcile the existing immutable tree instead:

```bash
sudo /usr/bin/env -i PATH=/usr/bin:/bin /usr/bin/bash \
  /root/vista-r8-buildplugin-admin-r1/publish-reconcile-buildplugin \
  reconcile-buildplugin \
  'I acknowledge reconciliation of the existing VISTA R8 UE 5.7 BuildPlugin authority without republishing it.'
```

Reconciliation regenerates the expected manifest/receipt from the held pinned
source, audits every final byte and mode, revalidates the source namespace,
fsyncs the complete final tree and parent, and reports
`published_buildplugin_authority_durability_reconciled`. It never renames or
republishes the authority.

## Claim boundary and remaining work

Once successfully published, this authority would prove only that the exact
reviewed BuildPlugin package was copied through the root-owned immutable
publication boundary. It would not prove that UE loaded the plugin, imported
the R8 animations, ran pickup/place, passed two-client testing, or reached
human-motion, photoreal, or GTA quality.

After administrator publication, a separate reviewed change must pin the
authority `payload/` projection into the R8 materializer. A separately sealed
UE 5.7 execution authority/runner is still required before any apply or runtime
claim.
