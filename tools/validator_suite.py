"""Real validate() invocations, exact returns and externally supervised adverse cases."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import time
from stateful import encode,canonical
from validator_supervisor import run,install_handlers

class ExperimentFailure(AssertionError):pass


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def suite(base,platform,output,bun):
    cases=json.loads((base/'cases.json').read_text())['cases']
    fixture=json.loads((base/'inputs/fixtures/stateful.json').read_text())
    states=json.loads((base/'stateful/expected-states.json').read_text())
    arithmetic=[dict(id=c['id'],data=json.dumps(dict(args=c['args']))) for c in cases]
    stateful=[dict(id=f'state-{i}',data=json.dumps(dict(wire=encode(states[i],record)))) for i,record in enumerate(fixture['records'])]
    outcomes=[]
    def check(condition,message):
        if not condition:raise RuntimeError(message)
    def variant(name,replacements):
        folder=output/'variants'/name;(folder/'build').mkdir(parents=True)
        roles=['cobol','rust','stateful-cobol','stateful-rust']
        for role in roles:shutil.copy2(replacements.get(role,base/'build'/role),folder/'build'/role)
        (folder/'SHA256SUMS').write_text(''.join(f'{digest(folder/"build"/role)}  build/{role}\n' for role in roles))
        (folder/'derivation.json').write_text(json.dumps(dict(parentManifest=digest(base/'SHA256SUMS'),replacements={role:str(path) for role,path in replacements.items()}),indent=2)+'\n')
        return folder
    def invoke(name,bundle,mode,inputs,timeout=120,cancel=False):
        folder=output/'invocations'/name;folder.mkdir(parents=True)
        spec=lambda language:dict(command=['mirepoix-cobol-demo-v1',str(bundle),digest(bundle/'SHA256SUMS'),mode,language],
                                  cwd=str(base),inputDelivery='stdin',outputCapture='stdout')
        request=dict(originalExec=spec('cobol'),portedExec=spec('rust'),inputs=inputs,tolerance=dict(mode='strict'))
        (folder/'request.json').write_text(json.dumps(request,indent=2)+'\n')
        ready=folder/'child.pid'
        env={**os.environ,'MIREPOIX_DEMO_CHILD_PID_FILE':str(ready)}
        caught=None
        try:
            supervision,stdout,stderr=run([bun,str(base/'inputs/tools/validator_worker.ts'),str(platform)],folder,
                                          json.dumps(request).encode(),timeout,ready if cancel else None,env)
        except BaseException as error:
            caught=error
            supervision=json.loads((folder/'supervision.json').read_text())
            stdout=(folder/'stdout.txt').read_bytes();stderr=(folder/'stderr.txt').read_bytes()
        worker=None
        try:worker=json.loads(stdout)
        except (ValueError,UnicodeDecodeError):pass
        raw=worker.get('rawVerdict') if isinstance(worker,dict) else None
        record=dict(name=name,supervision=supervision,worker=worker,rawVerdict=raw,
                    unresolvedInputs=[r['inputId'] for r in (raw or {}).get('perInput',[]) if r['indeterminate']])
        (folder/'result.json').write_text(json.dumps(record,indent=2)+'\n')
        outcomes.append(record)
        if caught is not None:raise caught
        check(supervision['cleanupConfirmed'],'worker group cleanup unconfirmed')
        if cancel or timeout<120:
            check(ready.exists(),'intended child workload never entered')
            pid=int(ready.read_text());stat=Path(f'/proc/{pid}/stat')
            check(not stat.exists() or stat.read_text().rpartition(')')[2].split()[0]=='Z','child survived supervision')
        return record
    def verdict(record,aggregate,unknown_ids=(),cause=None):
        check(record['supervision']['outcome']=='completed' and record['supervision']['exit']==0,'validator did not complete')
        check(record['rawVerdict'] is not None,'validator return absent')
        if not unknown_ids and record['unresolvedInputs']:raise RuntimeError('unexpected unresolved inputs: '+record['name'])
        if record['rawVerdict']['aggregate']!=aggregate or sorted(record['unresolvedInputs'])!=sorted(unknown_ids):
            raise ExperimentFailure('unexpected raw verdict/unknown set: '+record['name'])
        if cause:
            for item in record['rawVerdict']['perInput']:
                if item['indeterminate']:check(cause in item.get('note',''),'intended tool failure not observed')
    verdict(invoke('arithmetic-equivalent',base,'arithmetic',arithmetic),'EQUIVALENT')
    verdict(invoke('stateful-equivalent',base,'stateful',stateful),'EQUIVALENT')
    mismatch=variant('arithmetic-mutant',{'rust':base/'build/one_cent'})
    verdict(invoke('arithmetic-divergent',mismatch,'arithmetic',arithmetic),'DIVERGENT')
    tools_folder=output/'fault-tools';tools_folder.mkdir()
    source=tools_folder/'stateful-mutant.rs'
    text=(base/'inputs/src/stateful.rs').read_text()
    changed=text.replace('let delta=balance*rate/120000;','let delta=balance*rate/120000+1;')
    check(changed!=text,'stateful mutation did not apply');source.write_text(changed)
    mutant=tools_folder/'stateful-mutant'
    compiled,_,_=run(['rustc','--edition=2021','-C','strip=symbols','-o',str(mutant),str(source)],tools_folder/'compile-stateful',timeout=90)
    check(compiled['outcome']=='completed' and compiled['exit']==0 and compiled['cleanupConfirmed'],'stateful mutation compile failed')
    state_mismatch=variant('stateful-mutant',{'stateful-rust':mutant})
    verdict(invoke('stateful-divergent',state_mismatch,'stateful',stateful),'DIVERGENT')
    c=tools_folder/'fault.c'
    c.write_text('#include <stdio.h>\n#include <stdlib.h>\n#include <string.h>\n#include <signal.h>\n#include <unistd.h>\n'
        'int main(int n,char**v){if(n>1&&(!strcmp(v[1],"hang")||!strcmp(v[1],"orphan"))){if(fork()){if(!strcmp(v[1],"orphan"))_exit(0);for(;;)pause();}signal(SIGTERM,SIG_IGN);'
        'FILE*f=fopen(getenv("MIREPOIX_DEMO_CHILD_PID_FILE"),"w");if(!f)return 8;fprintf(f,"%d",getpid());fclose(f);for(;;)pause();}'
        'if(n>1&&!strcmp(v[1],"fail")){fprintf(stderr,"intentional tool failure\\n");return 7;}'
        'puts("OK\\t0.01");return 0;}\n')
    faulty=tools_folder/'fault'
    compiled,_,_=run(['cc',str(c),'-o',str(faulty)],tools_folder/'compile-fault',timeout=10)
    check(compiled['outcome']=='completed' and compiled['exit']==0 and compiled['cleanupConfirmed'],'fault fixture compile failed')
    # Both sides use an explicitly compiled adverse ELF. Matching infrastructure
    # failures must remain unknown, not equivalent.
    faults=variant('tool-faults',{'cobol':faulty,'rust':faulty})
    failure=[dict(id='tool-failure',data=json.dumps(dict(args=['fail'])))]
    verdict(invoke('tool-indeterminate',faults,'arithmetic',failure),'INDETERMINATE',['tool-failure'],'intentional tool failure')
    mixed=variant('mixed',{'rust':faulty})
    verdict(invoke('mixed-divergent-unknown',mixed,'arithmetic',[
        dict(id='mismatch',data=json.dumps(dict(args=['0.00','0.00']))),*failure]),'DIVERGENT',['tool-failure'],'intentional tool failure')
    orphan=invoke('completed-worker-orphan-cleanup',faults,'arithmetic',[dict(id='orphan',data=json.dumps(dict(args=['orphan'])))])
    verdict(orphan,'INDETERMINATE',['orphan'],'invalid observation')
    check(bool(orphan['supervision']['liveBeforeCleanup']),'orphan fixture did not leave a group member')
    hang=[dict(id='hanging-tool',data=json.dumps(dict(args=['hang'])))]
    for name,cancel,expected_outcome in [('worker-timeout',False,'timed-out'),('worker-cancel',True,'interrupted')]:
        result=invoke(name,faults,'arithmetic',hang,timeout=2,cancel=cancel)
        check(result['supervision']['outcome']==expected_outcome,'intended supervisor event not observed')
        check(result['rawVerdict'] is None,'interrupted worker unexpectedly returned a verdict')
    return dict(state='verified',invocations=outcomes,arithmeticInputs=len(arithmetic),statefulInputs=len(stateful),
                operatorActiveMinutes=None,operatorInterventions=None,modelCost=None,generationTrace=None,
                unavailableReason='No model generation requested; operator effort was not separately timed.')

if __name__=='__main__':
    install_handlers()
    parser=argparse.ArgumentParser();parser.add_argument('--base',type=Path,required=True);parser.add_argument('--platform',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--bun',required=True);args=parser.parse_args()
    result=dict(state='incomplete',startedAt=time.time())
    try:result.update(suite(args.base,args.platform,args.output,args.bun))
    except ExperimentFailure as error:result.update(state='failed',error=dict(type=type(error).__name__,message=str(error)))
    except BaseException as error:result['error']=dict(type=type(error).__name__,message=str(error))
    result['endedAt']=time.time()
    (args.output/'validator-result.json').write_text(json.dumps(result,indent=2)+'\n')
    raise SystemExit(0 if result['state']=='verified' else 1)
