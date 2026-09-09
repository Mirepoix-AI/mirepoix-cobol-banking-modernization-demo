#!/usr/bin/env python3
"""Verify all bundle files before executing its captured harness; trusted bundles only."""
import argparse
import hashlib
from pathlib import Path, PurePosixPath
import subprocess
import sys


def verify(root):
    entries={}
    for line in (root/'SHA256SUMS').read_text().splitlines():
        digest,name=line.split('  ',1)
        path=PurePosixPath(name)
        if path.is_absolute() or '..' in path.parts or name in entries or len(digest)!=64:
            raise ValueError('invalid checksum manifest entry')
        entries[name]=digest
    files={p.relative_to(root).as_posix() for p in root.rglob('*') if p.is_file() and p!=root/'SHA256SUMS'}
    if any(p.is_symlink() for p in root.rglob('*')) or files!=set(entries):
        raise ValueError('bundle file inventory mismatch')
    for name,digest in entries.items():
        if hashlib.sha256((root/name).read_bytes()).hexdigest()!=digest:
            raise ValueError('checksum mismatch: '+name)
    for required in ['inputs/run.sh','inputs/tools/evidence.py','inputs/tools/evaluate.py','result.json','replay.py']:
        if required not in entries:
            raise ValueError('missing required input: '+required)


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('bundle',type=Path,nargs='?',default=Path(__file__).resolve().parent)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    try:
        root=args.bundle.resolve()
        verify(root)
        raise SystemExit(subprocess.call([sys.executable,'-B',str(root/'inputs/tools/evidence.py'),
                                        '--replay-source',str(root),'--output',str(args.output.resolve())]))
    except (ValueError,OSError) as error:
        print('Replay refused: '+str(error),file=sys.stderr)
        raise SystemExit(2)
