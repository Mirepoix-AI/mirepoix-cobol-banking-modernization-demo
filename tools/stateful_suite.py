"""Bounded real-process state/restart acceptance, archived by the main harness."""
import copy
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys
from stateful import initial,expected_step,validate_state,encode,canonical


class StatefulFailure(AssertionError):
    """A witnessed contract mismatch, distinct from an uncertain execution."""


def suite(root,output,execute):
    fixture=json.loads((root/'fixtures/stateful.json').read_text())
    expected=[initial(fixture)]
    for record in fixture['records']:expected.append(expected_step(expected[-1],record))
    folder=output/'stateful'
    folder.mkdir()
    (folder/'expected-states.json').write_text(json.dumps(expected,indent=2)+'\n')
    results=[]
    def command(binary,case,extra=(),fixture_path=None):
        argv=[sys.executable,'-B',str(root/'tools/stateful.py'),'--fixture',str(fixture_path or root/'fixtures/stateful.json'),
              '--binary',str(binary),'--state',str(case),*extra]
        observation=execute(argv,30)
        results.append(dict(command=argv,observation=observation))
        (folder/'invocations.json').write_text(json.dumps(results,indent=2)+'\n')
        return observation
    def read(case):return json.loads((case/'checkpoint.json').read_text())
    def require(condition,reason,expected=True,actual=False):
        if not condition:
            failure=dict(reason=reason,expected=expected,actual=actual,
                         invocation=results[-1] if results else None)
            (folder/'failing-cases.json').write_text(json.dumps([failure],indent=2)+'\n')
            raise StatefulFailure(str(reason))
    def equal(actual,expected,reason):
        require(actual==expected,reason,expected,actual)
    def completed(observation,expected_exit=0):
        if observation['exit']!=expected_exit:
            raise RuntimeError('stateful execution incomplete: '+json.dumps(observation))
    for language in ['cobol','rust']:
        binary=output/'build'/('stateful-'+language)
        case=folder/(language+'-normal')
        observation=command(binary,case,['--initialize'])
        completed(observation)
        equal(read(case),expected[-1],'full final state')
        for index in range(len(fixture['records'])):
            equal(json.loads((case/f'committed-{index}.json').read_text()),expected[index+1],'intermediate state')
        for hook in ['before','after']:
            for offset in range(len(fixture['records'])):
                case=folder/f'{language}-{hook}-{offset}'
                observation=command(binary,case,['--initialize','--hook',hook,'--offset',str(offset)])
                completed(observation,75)
                committed=offset if hook=='before' else offset+1
                equal(read(case),expected[committed],'interrupted durable state')
                (case/'interrupted-state.json').write_text(canonical(read(case))+'\n')
                observation=command(binary,case)
                completed(observation)
                equal(read(case),expected[-1],'restart full state')
        case=folder/(language+'-broken-restart')
        completed(command(binary,case,['--initialize','--hook','after','--offset','0']),75)
        before=read(case)
        broken=command(binary,case,['--broken'])
        require(broken['exit']!=0,'broken restart survived','nonzero exit',broken['exit'])
        equal(read(case),before,'broken restart published')
        results[-1]['requiredMutantKilled']=True
        for fault in ['write','dirsync']:
            case=folder/f'{language}-publication-{fault}'
            observation=command(binary,case,['--initialize','--publication-fault',fault,'--offset','0'])
            require(observation['exit']!=0,'publication error reported success')
            equal(read(case),expected[0 if fault=='write' else 1],'publication failure disk boundary')
            (case/'interrupted-state.json').write_text(canonical(read(case))+'\n')
            completed(command(binary,case))
            equal(read(case),expected[-1],'publication recovery')
        for fault in ['missing','malformed','cursor','ids','balance','changed-input']:
            case=folder/f'{language}-checkpoint-{fault}'
            case.mkdir()
            state=copy.deepcopy(expected[1])
            if fault=='cursor':state['next']=2
            if fault=='ids':state['acceptedIds']=[]
            if fault=='balance':state['balances']['A']='666.00'
            if fault=='changed-input':state['inputHash']='0'*64
            if fault!='missing':(case/'checkpoint.json').write_text('{' if fault=='malformed' else canonical(state))
            before=(case/'checkpoint.json').read_bytes() if (case/'checkpoint.json').exists() else None
            require(command(binary,case)['exit']!=0,'bad checkpoint accepted')
            after=(case/'checkpoint.json').read_bytes() if (case/'checkpoint.json').exists() else None
            equal(after.decode() if after else None,before.decode() if before else None,'bad checkpoint changed')
    # Adverse actual processes produce valid-looking output but must never publish
    # unless the process itself completed cleanly. Both language coordinators use
    # this common supervision boundary; each scenario starts from the same state.
    for fault in ['nonzero','stderr','truncated','timeout']:
        case=folder/('process-'+fault);case.mkdir()
        (case/'checkpoint.json').write_text(canonical(expected[0])+'\n')
        wrong=folder/('process-'+fault+'.py')
        valid=encode(expected[1],fixture['records'][1]).split('RECORD|')[0]+'END\n'
        source='#!/usr/bin/python3\nimport os,sys,time,signal\n'
        if fault=='timeout':
            source+='signal.signal(signal.SIGTERM,signal.SIG_IGN)\n'
            source+=f'open({str(case/"pid")!r},"w").write(str(os.getpid()))\ntime.sleep(30)\n'
        else:
            source+='sys.stdout.write('+repr(valid if fault!='truncated' else valid[:-4])+')\n'
            if fault=='stderr':source+='sys.stderr.write("unexpected diagnostic")\n'
            if fault=='nonzero':source+='sys.exit(1)\n'
        wrong.write_text(source);wrong.chmod(0o755)
        require(command(wrong,case)['exit']!=0,'bad process accepted')
        equal(read(case),expected[0],'bad process published candidate')
        if fault=='timeout':
            pid=int((case/'pid').read_text());stat=Path(f'/proc/{pid}/stat')
            require(not stat.exists() or stat.read_text().split()[2]=='Z','timed-out process survives')
    (folder/'invocations.json').write_text(json.dumps(results,indent=2)+'\n')
    return dict(state='verified',records=len(fixture['records']),accounts=len(fixture['accounts']),
                invocations=len(results),interruptionCases=2*2*len(fixture['records']),
                brokenRestartMutantsKilled=2,fullFinalState=expected[-1])
