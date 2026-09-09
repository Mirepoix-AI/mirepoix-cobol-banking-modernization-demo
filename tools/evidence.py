#!/usr/bin/env python3
"""Snapshot first; retain success, failure and incomplete evidence for replay."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import signal
import subprocess
import sys
import tarfile
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
FILES = ['run.sh','replay.py','README.md','PROVENANCE.md','LICENSE']
DIRECTORIES = ['src','fixtures','tools','tests','docs','upstream','.github']


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def capture(source, target):
    target.mkdir()
    for name in FILES:
        shutil.copy2(source/name, target/name)
    for name in DIRECTORIES:
        if (source/name).exists():
            shutil.copytree(source/name, target/name,
                            ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    if any(p.is_symlink() for p in target.rglob('*')):
        raise ValueError('snapshot symlinks are unsupported')


def git_identity():
    def git(*args):
        return subprocess.check_output(['git','-C',str(ROOT),*args],text=True).strip()
    return dict(commit=git('rev-parse','HEAD'),dirty=bool(git('status','--porcelain','--untracked-files=all')),
                status=git('status','--porcelain','--untracked-files=all'))


def run(output, source, identity, invocation, parent=None):
    output=output.resolve()
    output.mkdir(parents=True,exist_ok=True)
    if any(output.iterdir()):
        raise ValueError('output directory must be empty')
    started=time.time()
    metadata=dict(schemaVersion=2,state='incomplete',demo=identity,invocation=invocation,
                  startedAt=started,platform=platform.platform(),python=sys.version,
                  parentEvidence=parent,toolchains={},
                  environment={key:os.environ.get(key) for key in ['LANG','LC_ALL','COB_CFLAGS','COB_LDFLAGS','COB_CONFIG_DIR','COB_COPY_DIR']})
    try:
        capture(source,output/'inputs')
        shutil.copy2(output/'inputs/replay.py',output/'replay.py')
        for tool, flags in [('cobc',['-V']),('rustc',['-Vv']),('gcc',['--version'])]:
            resolved=shutil.which(tool)
            metadata['toolchains'][tool]=dict(path=resolved)
            if resolved:
                version=subprocess.run([resolved,*flags],capture_output=True,text=True,timeout=10)
                metadata['toolchains'][tool].update(exit=version.returncode,stdout=version.stdout,stderr=version.stderr)
        env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'}
        with (output/'harness.stdout').open('w') as stdout,(output/'harness.stderr').open('w') as stderr:
            process=subprocess.Popen([sys.executable,str(output/'inputs/tools/evaluate.py'),
                                    '--root',str(output/'inputs'),'--output',str(output)],
                                   env=env,stdout=stdout,stderr=stderr,start_new_session=True)
            try:
                process.wait(timeout=300)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid,signal.SIGKILL)
                    process.wait()
                raise RuntimeError('evaluator exceeded 300 seconds')
        evaluation=json.loads((output/'evaluation.json').read_text())
        metadata.update(evaluation=evaluation)
        if process.returncode==0 and evaluation['state']=='verified':
            metadata['state']='verified'
        elif evaluation['state']=='failed':
            metadata['state']='failed'
    except Exception as error:
        metadata['error']=f'{type(error).__name__}: {error}'
    metadata.update(endedAt=time.time(),elapsedSeconds=time.time()-started)
    (output/'result.json').write_text(json.dumps(metadata,indent=2)+'\n')
    paths=sorted(p for p in output.rglob('*') if p.is_file())
    (output/'SHA256SUMS').write_text(''.join(f'{digest(p)}  {p.relative_to(output).as_posix()}\n' for p in paths))
    with tarfile.open(str(output)+'.tar.gz','w:gz') as bundle:
        bundle.add(output,arcname=output.name)
    print(f"{metadata['state'].upper()} evidence={output} bundle={output}.tar.gz")
    return 0 if metadata['state']=='verified' else 1


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--output',type=Path)
    parser.add_argument('--mutation',action='store_true',help='Compatibility option: all checks still run')
    parser.add_argument('--replay-source',type=Path,help=argparse.SUPPRESS)
    args=parser.parse_args()
    output=args.output or Path(tempfile.mkdtemp(prefix='carddemo-evidence-'))
    if args.replay_source:
        parent=json.loads((args.replay_source/'result.json').read_text())
        identity=parent['demo']
        return run(output,args.replay_source/'inputs',identity,sys.argv[1:],digest(args.replay_source/'SHA256SUMS'))
    return run(output,ROOT,git_identity(),sys.argv[1:])


if __name__=='__main__':
    raise SystemExit(main())
