#!/usr/bin/env python3
"""Replay a trusted local integration bundle after complete integrity checks."""
import argparse
from pathlib import Path
import subprocess
import sys

root=Path(__file__).resolve().parent
sys.path.insert(0,str(root/'base/inputs'))
from replay import verify

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--bun',required=True)
    args=parser.parse_args()
    try:verify(root)
    except Exception as error:
        print(f'integrity refused: {error}',file=sys.stderr);raise SystemExit(2)
    raise SystemExit(subprocess.call([sys.executable,'-B',str(root/'base/inputs/tools/validator_evidence.py'),
                                     '--replay-root',str(root),'--output',str(args.output),'--bun',args.bun]))
