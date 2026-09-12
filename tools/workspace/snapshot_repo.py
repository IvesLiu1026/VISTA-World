"""Create a pinned shallow Git checkout using objects, never the dirty worktree.

Only an explicitly supplied credential-free GitHub origin is retained. Source
Git configuration, hooks, untracked files, environments, and credential stores
are never copied. Sparse exclusions affect the working tree, not Git objects.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import subprocess

EXCLUSIONS = [
    '.env', '.env.*', '*.pem', '*.key', '*.p12',
    '**/Saved/**', '**/Intermediate/**', '**/DerivedDataCache/**',
    '**/__pycache__/**', '**/node_modules/**', '**/.venv/**',
    '*.aux', '*.blg', '*.fdb_latexmk', '*.fls', '*.log', '*.out', '*.pid',
    '/notes/', '/runs/', '/runtime/', '/outputs/', '/experiments/', '/meetings/', '/archive/',
    '/benchmarks/**/canonical/datasets/', '/benchmarks/**/teacher_sources_*/',
]


def git(root: Path, *args: str) -> str:
    result = subprocess.run(['git', '-C', str(root), *args], capture_output=True,
                            text=True, check=True)
    return result.stdout.strip()


def snapshot(source: Path, revision: str, output: Path, origin: str, branch: str) -> dict:
    if not re.fullmatch(r'https://github.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?', origin):
        raise ValueError('Use an explicit credential-free GitHub origin')
    if not re.fullmatch(r'codex/[a-z0-9-]+', branch):
        raise ValueError('Use an isolated codex branch')
    sha = git(source, 'rev-parse', '--verify', revision + '^{commit}')
    # Refuse credential files even when sparse checkout would hide them: their
    # objects would still be transferred. Public env templates remain reviewed inputs.
    rows = git(source, 'ls-tree', '-r', sha).splitlines()
    symlinks = []
    for row in rows:
        meta, path = row.split('\t', 1)
        if Path(path).suffix in {'.pem', '.key', '.p12'} or Path(path).name in {'id_rsa', 'id_ed25519', '.env'}:
            raise ValueError('Credential-like tracked file requires source review: ' + path)
        if meta.startswith('120000'):
            symlinks.append(path)
    output.mkdir(parents=True, exist_ok=False)
    git(output, 'init', '--quiet')
    git(output, 'fetch', '--quiet', '--depth=1', '--no-tags', str(source.resolve()), sha)
    git(output, 'config', 'core.sparseCheckout', 'true')
    git(output, 'config', 'core.sparseCheckoutCone', 'false')
    patterns = ['/*'] + ['!' + pattern for pattern in EXCLUSIONS]
    patterns += ['!/' + p for p in symlinks]
    patterns.append('**/.env.example')
    (output / '.git/info/sparse-checkout').write_text('\n'.join(patterns) + '\n')
    git(output, 'switch', '--quiet', '-c', branch, 'FETCH_HEAD')
    git(output, 'remote', 'add', 'origin', origin)
    # FETCH_HEAD records the local transfer path and is not required after checkout.
    (output / '.git/FETCH_HEAD').unlink()
    if git(output, 'status', '--porcelain'):
        raise ValueError('Exported checkout is unexpectedly dirty')
    if git(output, 'rev-parse', 'HEAD') != sha:
        raise ValueError('Exported revision differs')
    return {'schema': 'vista.source-snapshot/v1', 'origin': origin, 'commit': sha,
            'branch': branch, 'shallow': True, 'source_worktree_copied': False,
            'excluded_worktree_patterns': patterns[1:],
            'note': 'Sparse exclusions do not remove tracked content from the shallow Git objects.'}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--revision', required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--origin', required=True)
    p.add_argument('--branch', default='codex/5090-development')
    p.add_argument('--receipt', type=Path, required=True)
    a = p.parse_args()
    if a.receipt.exists():
        raise ValueError('Receipt already exists')
    result = snapshot(a.source, a.revision, a.output, a.origin, a.branch)
    with a.receipt.open('x') as f:
        json.dump(result, f, indent=2)
        f.write('\n')
    print(json.dumps({'exported_commit': result['commit'], 'clean': True}))


if __name__ == '__main__':
    main()
