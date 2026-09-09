#!/usr/bin/env python3
"""Replay a trusted local integration bundle after complete integrity checks."""
import argparse
from pathlib import Path
import subprocess
import sys

# Verification must not mutate the evidence by creating import bytecode.
sys.dont_write_bytecode=True
root=Path(__file__).resolve().parent
sys.path.insert(0,str(root/'base/inputs'))
from replay import verify as verify_base,verify_inventory

def verify(root):
    entries=verify_inventory(root)
    verify_base(root/"base")
    for required in ["result.json","replay.py","platform/packages/validate/src/index.ts",
                     "base/inputs/tools/validator_evidence.py","base/inputs/tools/validator_suite.py",
                     "base/inputs/tools/validator_worker.ts"]:
        if required not in entries:raise ValueError("missing integration input: "+required)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path,required=True);parser.add_argument('--bun',required=True)
    args=parser.parse_args()
    try:verify(root)
    except Exception as error:
        print(f'integrity refused: {error}',file=sys.stderr);raise SystemExit(2)
    raise SystemExit(subprocess.call([sys.executable,'-B',str(root/'base/inputs/tools/validator_evidence.py'),
                                     '--replay-root',str(root),'--output',str(args.output),'--bun',args.bun]))
