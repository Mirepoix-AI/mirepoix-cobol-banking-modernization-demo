#!/usr/bin/env python3
"""Explicit two-repository acceptance: clean replay, tamper refusal, root TERM/INT."""
import argparse
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
import time

parser=argparse.ArgumentParser();parser.add_argument('--bundle',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True);parser.add_argument('--bun',required=True);args=parser.parse_args()
bundle=args.bundle.resolve();output=args.output.resolve();output.mkdir(parents=True)
if any(output.iterdir()):parser.error('output must be empty')
results=[]
def invoke(command,expected):
    started=time.time();p=subprocess.run(command,capture_output=True,text=True,timeout=150)
    results.append(dict(command=command,exit=p.returncode,stdout=p.stdout,stderr=p.stderr,startedAt=started,endedAt=time.time()))
    assert p.returncode==expected,(command,p.returncode,p.stderr,p.stdout)
try:
    replay=output/'replayed'
    invoke([sys.executable,str(bundle/'replay.py'),'--output',str(replay),'--bun',args.bun],0)
    original=json.loads((bundle/'result.json').read_text());actual=json.loads((replay/'result.json').read_text())
    assert actual['state']=='verified' and actual['demo']==original['demo'] and actual['platform']==original['platform']
    tampered=output/'tampered';shutil.copytree(bundle,tampered)
    path=tampered/'platform/packages/validate/src/index.ts';path.write_text(path.read_text()+'\n// tampered\n')
    refused=output/'refused'
    invoke([sys.executable,str(tampered/'replay.py'),'--output',str(refused),'--bun',args.bun],2)
    assert not refused.exists()
    for sig in [signal.SIGTERM,signal.SIGINT]:
        case=output/sig.name
        command=[sys.executable,'-B',str(bundle/'base/inputs/tools/validator_evidence.py'),'--replay-root',str(bundle),'--output',str(case),'--bun',args.bun]
        process=subprocess.Popen(command,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
        groups={process.pid};started=time.time()
        try:
            marker=case/'invocations/worker-timeout/child.pid'
            deadline=time.monotonic()+120
            while not marker.exists() and time.monotonic()<deadline:
                if process.poll() is not None:break
                time.sleep(.02)
            assert marker.exists(),'actual validator child did not start'
            pid=int(marker.read_text());worker=os.getpgid(pid);groups.add(worker)
            driver=int(Path(f'/proc/{worker}/stat').read_text().rpartition(')')[2].split()[1]);groups.add(driver)
            process.send_signal(sig);stdout,stderr=process.communicate(timeout=10)
            assert process.returncode!=0
            result=json.loads((case/'result.json').read_text());assert result['state']=='incomplete'
            interrupted=json.loads((case/'invocations/worker-timeout/result.json').read_text())
            assert interrupted['rawVerdict'] is None
            assert interrupted['supervision']['outcome']=='interrupted' and interrupted['supervision']['cleanupConfirmed']
            for member in [pid,worker,driver]:
                stat=Path(f'/proc/{member}/stat')
                assert not stat.exists() or stat.read_text().rpartition(')')[2].split()[0]=='Z',(sig.name,member)
            results.append(dict(command=command,signal=sig.name,exit=process.returncode,stdout=stdout.decode(),stderr=stderr.decode(),startedAt=started,endedAt=time.time(),cleanupConfirmed=True,rawVerdict=None))
        finally:
            for group in groups:
                try:os.killpg(group,signal.SIGKILL)
                except ProcessLookupError:pass
            process.communicate(timeout=2)
    print('PASS: clean integration replay, tamper refusal, actual root TERM/INT cleanup')
finally:
    (output/'checks.json').write_text(json.dumps(results,indent=2)+'\n')
