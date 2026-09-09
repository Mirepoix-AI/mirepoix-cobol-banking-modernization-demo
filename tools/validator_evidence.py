#!/usr/bin/env python3
"""Capture and execute a local, pinned real-validator integration bundle."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import evidence

ROOT=Path(__file__).resolve().parents[1]

def identity(repository):
    def git(*args):return subprocess.check_output(['git','-C',str(repository),*args],text=True,timeout=10).strip()
    return dict(commit=git('rev-parse','HEAD'),dirty=bool(git('status','--porcelain','--untracked-files=all')))

def capture_platform(source,target):
    target.mkdir()
    for relative in ['packages/validate/src','packages/validate/package.json','packages/validate/LICENSE','adrs/ADR-018-multi-language-execution-allowlist.md']:
        src=source/relative;dst=target/relative;dst.parent.mkdir(parents=True,exist_ok=True)
        if src.is_dir():shutil.copytree(src,dst)
        else:shutil.copy2(src,dst)
    dependency=source/'packages/validate/node_modules/zod'
    shutil.copytree(dependency,target/'node_modules/zod')
    return dict(**identity(source),dependency=dict(name='zod',version=json.loads((dependency/'package.json').read_text())['version']))

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--platform',type=Path);parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--bun',default=shutil.which('bun'));parser.add_argument('--replay-root',type=Path)
    args=parser.parse_args()
    if not args.bun:parser.error('--bun or Bun on PATH is required')
    if not args.platform and not args.replay_root:parser.error('--platform is required for a new run')
    output=args.output.resolve();output.mkdir(parents=True,exist_ok=True)
    if any(output.iterdir()):parser.error('output must be empty')
    started=time.time();metadata=dict(schemaVersion=3,kind='mirepoix-validator-integration',state='incomplete',startedAt=started)
    try:
        if args.replay_root:
            old=args.replay_root.resolve();parent=json.loads((old/'result.json').read_text())
            source=old/'base/inputs';demo=parent['demo']
            metadata.update(parentEvidence=evidence.digest(old/'SHA256SUMS'),platform=parent['platform'])
        else:
            source=ROOT;demo=identity(ROOT)
        metadata['demo']=demo
        if evidence.run(output/'base',source,demo,sys.argv[1:])!=0:raise RuntimeError('base workload did not verify')
        shutil.copy2(output/'base/inputs/tools/replay_validator.py',output/'replay.py')
        if args.replay_root:shutil.copytree(old/'platform',output/'platform')
        else:metadata['platform']=capture_platform(args.platform.resolve(),output/'platform')
        if any(p.is_symlink() for p in output.rglob('*')):raise ValueError('integration snapshot symlink refused')
        version=subprocess.Popen([args.bun,'--version'],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True)
        evidence.ACTIVE=version
        version_out,version_err=version.communicate(timeout=10)
        evidence.stop_active()
        if version.returncode!=0:raise RuntimeError('Bun version probe failed: '+version_err)
        metadata['bun']=dict(path=args.bun,version=version_out.strip())
        command=[sys.executable,'-B',str(output/'base/inputs/tools/validator_suite.py'),'--base',str(output/'base'),
                 '--platform',str(output/'platform'),'--output',str(output),'--bun',args.bun]
        metadata['command']=command
        with (output/'driver.stdout').open('w') as stdout,(output/'driver.stderr').open('w') as stderr:
            process=subprocess.Popen(command,stdout=stdout,stderr=stderr,start_new_session=True)
            evidence.ACTIVE=process
            process.wait(timeout=600)
        evidence.stop_active()
        result=json.loads((output/'validator-result.json').read_text());metadata['evaluation']=result
        if process.returncode==0 and result['state']=='verified':metadata['state']='verified'
        elif result['state']=='failed':metadata['state']='failed'
    except BaseException as error:
        metadata['error']=dict(type=type(error).__name__,message=str(error))
    finally:
        try:evidence.stop_active()
        except Exception as error:metadata['state']='incomplete';metadata['cleanupError']=str(error)
    try:evidence.finalize(output,metadata,started)
    except InterruptedError as error:
        metadata.update(state='incomplete',error=dict(type=type(error).__name__,message=str(error)))
        evidence.finalize(output,metadata,started)
    print(f"{metadata['state'].upper()} validator evidence={output} bundle={output}.tar.gz")
    return 0 if metadata['state']=='verified' else 1

if __name__=='__main__':raise SystemExit(main())
