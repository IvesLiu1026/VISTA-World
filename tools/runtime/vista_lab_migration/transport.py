"""Use the lab device document and existing SSH trust without saving endpoints."""
from __future__ import annotations

import argparse
import ipaddress
import json
from pathlib import Path, PurePosixPath
import re
import shlex
import subprocess
from urllib.request import urlopen

DOCUMENT = 'https://hackmd.io/@GLuZ0xa3SHOywVxhNCl8mQ/Sy2_CZ3Ozx/download'


def target() -> tuple[str, str]:
    with urlopen(DOCUMENT, timeout=20) as response:
        document = response.read().decode()
    rows = [line for line in document.splitlines()
            if '5090' in line and line.lstrip().startswith('|')]
    if len(rows) != 1:
        raise ValueError('The target workstation row is missing or ambiguous')
    columns = [item.strip().strip('`') for item in rows[0].split('|')]
    addresses = [item for item in columns
                 if re.fullmatch(r'(?:\d{1,3}\.){3}\d{1,3}', item)]
    if len(addresses) != 1:
        raise ValueError('The target address is missing or ambiguous')
    host = str(ipaddress.IPv4Address(addresses[0]))
    port = columns[columns.index(host) + 1]
    if not port.isdigit() or not 0 < int(port) < 65536:
        raise ValueError('Invalid target SSH port')
    return host, port


def ssh_options(port: str) -> list[str]:
    return ['ssh', '-o', 'BatchMode=yes', '-o', 'ConnectTimeout=10',
            '-o', 'ConnectionAttempts=1', '-o', 'StrictHostKeyChecking=yes',
            '-p', port]


def redact(text: str, host: str) -> str:
    text = text.replace(host, '<TARGET>').replace(str(Path.home()), '<USER_HOME>')
    text = text.replace(Path.home().name, '<USER>')
    return re.sub(r'\b(?:\d{1,3}\.){3}\d{1,3}\b', '<ADDRESS>', text)


def destination(value: str) -> str:
    path = PurePosixPath(value)
    if (path.is_absolute() or '..' in path.parts or
            not re.fullmatch(r'[A-Za-z0-9._/-]+', value) or
            not value.startswith('vista-world-5090/')):
        raise ValueError('Destination must remain in the owned migration root')
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='action', required=True)
    remote = sub.add_parser('run')
    remote.add_argument('--script', type=Path, required=True)
    remote.add_argument('--timeout', type=int, default=120)
    send = sub.add_parser('send')
    send.add_argument('--source', type=Path, required=True)
    send.add_argument('--destination', required=True)
    send.add_argument('--directory-contents', action='store_true')
    send.add_argument('--exclude-runtime', action='store_true')
    send.add_argument('--dry-run', action='store_true')
    receive = sub.add_parser('receive')
    receive.add_argument('--source', required=True)
    receive.add_argument('--destination', type=Path, required=True)
    args = parser.parse_args()
    host, port = target()
    if args.action == 'receive':
        source = destination(args.source)
        if args.destination.exists():
            raise ValueError('Refusing to replace existing local evidence')
        # Single file, with strict SSH trust and an exclusive local destination.
        result = subprocess.run(ssh_options(port) + [host, 'cat -- ' + shlex.quote(source)],
                                capture_output=True, timeout=60)
        if result.returncode:
            raise SystemExit(redact(result.stderr.decode(errors='replace'), host))
        with args.destination.open('xb') as output:
            output.write(result.stdout)
        print(json.dumps({'received_bytes': len(result.stdout)}))
        return
    if args.action == 'run':
        result = subprocess.run(ssh_options(port) + [host, 'sh -s'],
                                input=args.script.read_text(), capture_output=True,
                                text=True, timeout=args.timeout)
        print(redact(result.stdout, host), end='')
        if result.stderr:
            print(redact(result.stderr, host), end='', file=__import__('sys').stderr)
        raise SystemExit(result.returncode)
    source = args.source.resolve(strict=True)
    target_path = destination(args.destination)
    if args.directory_contents and not source.is_dir():
        raise ValueError('Directory contents require a directory')
    command = ['rsync', '-a', '--no-owner', '--no-group', '--safe-links',
               '--protect-args', '--info=progress2', '--no-inc-recursive',
               '-e', shlex.join(ssh_options(port))]
    if args.dry_run:
        command.append('--dry-run')
    if args.exclude_runtime:
        for directory in ('Saved', 'Intermediate', 'DerivedDataCache', '.git'):
            command.append('--exclude=/' + directory + '/***')
    command.extend([str(source) + ('/' if args.directory_contents else ''),
                    host + ':' + target_path])
    proc = subprocess.Popen(command, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, text=True, bufsize=1)
    assert proc.stdout
    previous = None
    for line in proc.stdout:
        match = re.search(r'(\d+)%\s+([\d.]+[kMGT]?B/s)', line)
        if match:
            percent = int(match[1])
            bucket = percent // 10
            if bucket != previous:
                print(json.dumps({'transfer_percent': percent, 'speed': match[2]}), flush=True)
                previous = bucket
        elif line.strip():
            print(redact(line, host).strip(), flush=True)
    code = proc.wait()
    print(json.dumps({'transfer_exit_code': code}), flush=True)
    raise SystemExit(code)


if __name__ == '__main__':
    try:
        main()
    except subprocess.TimeoutExpired:
        raise SystemExit('Transport timed out; inspect owned remote state before retrying') from None
