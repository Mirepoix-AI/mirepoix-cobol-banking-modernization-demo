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
        outcome=case/'outcome.json'
        if outcome.exists():outcome.unlink()
        observation=execute(argv,30)
        try:observation['execution']=json.loads(outcome.read_text())
        except (OSError,ValueError):observation['execution']=None
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
    def witnessed(condition,reason):
        if not condition:raise RuntimeError('adverse execution unconfirmed: '+reason)
    def completed(observation,expected_exit=0):
        if observation['exit']!=expected_exit:
            raise RuntimeError('stateful execution incomplete: '+json.dumps(observation))
        execution=observation.get('execution') or {}
        witnessed(execution.get('schemaVersion')==1 and execution.get('outcome')==('completed' if expected_exit==0 else 'injected-interruption'),
                  'completion/interruption protocol')
        witnessed(not observation['stderr'],'unexpected coordinator diagnostic')
    def rejected(observation,phase,error_type,message):
        if observation['exit']==0:completed(observation)
        require(observation['exit']!=0,'expected rejection reported success','nonzero exit',observation['exit'])
        execution=observation.get('execution') or {}
        error=execution.get('error') or {}
        witnessed(observation['exit']==1 and not observation['stdout'] and execution.get('schemaVersion')==1 and execution.get('outcome')=='incomplete'
                  and execution.get('phase')==phase and error.get('type')==error_type
                  and (message is None or error.get('message')==message)
                  and observation['stderr']==f"{error_type}: {error.get('message')}\n",'expected rejection cause')
        return execution
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
                witnessed(observation['execution'].get('hook')==dict(name=hook,offset=offset), 'interruption hook')
                witnessed(observation['execution'].get('phase')==('before-rename' if hook=='before' else 'committed'), 'interruption phase')
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
        if broken['exit']==0:
            completed(broken)
            require(False,'broken restart survived','nonzero exit',0)
        execution=rejected(broken,'candidate-validate','ValueError','balance chain')
        mutated=copy.deepcopy(before)
        mutated['next']-=1;mutated['journal']=mutated['journal'][:-1];mutated['acceptedIds']=[]
        witnessed(execution.get('mutation')==dict(name='replay-without-commit-identity',before=before,after=mutated),'recovery mutation did not execute')
        witnessed(execution.get('candidate')==expected_step(mutated,fixture['records'][mutated['next']]),'mutated transition candidate')
        attempt=execution.get('attempt') or {}
        witnessed(attempt.get('observation',{}).get('exit')==0 and attempt.get('cleanupConfirmed') is True,'mutated transition completion/cleanup')
        equal(read(case),before,'broken restart published')
        results[-1]['requiredMutantKilled']=True
        for fault in ['write','dirsync']:
            case=folder/f'{language}-publication-{fault}'
            observation=command(binary,case,['--initialize','--publication-fault',fault,'--offset','0'])
            rejected(observation,'injected-write-failure' if fault=='write' else 'injected-directory-sync-failure',
                     'OSError','injected pre-rename write failure' if fault=='write' else 'injected directory-fsync failure after rename')
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
            phase='checkpoint-decode' if fault=='malformed' else 'checkpoint-load' if fault=='missing' else 'checkpoint-validate'
            error_type='JSONDecodeError' if fault=='malformed' else 'ValueError'
            message=dict(missing='restart checkpoint is missing',malformed=None,cursor='journal/cursor mismatch',
                         ids='accepted IDs disagree with journal',balance='final balance chain',
                         **{'changed-input':'changed input identity'})[fault]
            rejected(command(binary,case),phase,error_type,message)
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
        observation=command(wrong,case)
        execution=rejected(observation,'execute','RuntimeError' if fault=='timeout' else 'ValueError',
                           'transition timeout' if fault=='timeout' else 'missing output terminator' if fault=='truncated' else 'transition process failed')
        attempt=execution.get('attempt') or {}
        expected_observation=dict(exit=-signal.SIGKILL if fault=='timeout' else 1 if fault=='nonzero' else 0,
                                  stdout='' if fault=='timeout' else valid[:-4] if fault=='truncated' else valid,
                                  stderr='unexpected diagnostic' if fault=='stderr' else '')
        witnessed(attempt.get('observation')==expected_observation and attempt.get('cleanupConfirmed') is True,
                  'adverse transition observation/cleanup')
        witnessed(bool(attempt.get('timedOut'))==(fault=='timeout'),'transition timeout attribution')
        equal(read(case),expected[0],'bad process published candidate')
        if fault=='timeout':
            pid=int((case/'pid').read_text());stat=Path(f'/proc/{pid}/stat')
            require(not stat.exists() or stat.read_text().split()[2]=='Z','timed-out process survives')
    (folder/'invocations.json').write_text(json.dumps(results,indent=2)+'\n')
    return dict(state='verified',records=len(fixture['records']),accounts=len(fixture['accounts']),
                invocations=len(results),interruptionCases=2*2*len(fixture['records']),
                brokenRestartMutantsKilled=2,fullFinalState=expected[-1])
