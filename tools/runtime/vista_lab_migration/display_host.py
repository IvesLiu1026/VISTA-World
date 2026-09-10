"""Start only the dedicated authenticated VISTA X11 display."""
from __future__ import annotations

import os
from pathlib import Path
import secrets
import subprocess


def main() -> None:
    root = Path(__file__).resolve().parents[3]
    if root.name != 'vista-world-5090':
        raise SystemExit('Unexpected migration root')
    if Path('/tmp/.X11-unix/X119').exists() or Path('/tmp/.X119-lock').exists():
        raise SystemExit('Display is occupied; refusing to replace another session')
    auth = root / 'runtime/Xauthority'
    auth.parent.mkdir(mode=0o700, exist_ok=True)
    if not auth.exists():
        fd = os.open(auth, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        os.close(fd)
        subprocess.run(['xauth', '-f', str(auth)], text=True, check=True,
                       input='add :119 . ' + secrets.token_hex(16) + '\n', capture_output=True)
    auth.chmod(0o600)
    command = ['/usr/bin/Xvfb', ':119', '-screen', '0', '1920x1080x24',
               '-nolisten', 'tcp', '-noreset', '-auth', str(auth)]
    os.execv(command[0], command)


if __name__ == '__main__':
    main()
