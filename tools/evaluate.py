#!/usr/bin/env python3
"""Compile captured sources and compare exact process observations to an oracle."""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import time
from numeric import corpus, oracle, SEED, GENERATED
from processes import finish
from stateful_suite import StatefulFailure, suite

MUTANTS = ['one_cent', 'rounding', 'sign', 'divisor', 'range']
ACTIVE = None
STOPPING = False


def interrupted(_signum, _frame):
    global STOPPING
    if STOPPING:return
    STOPPING=True
    if ACTIVE is not None:
        finish(ACTIVE,grace=1.3,timeout=1.8)
    raise RuntimeError('evaluation interrupted')

signal.signal(signal.SIGTERM, interrupted)
signal.signal(signal.SIGINT, interrupted)


def execute(argv, timeout=20):
    global ACTIVE
    process = subprocess.Popen(argv, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               start_new_session=True)
    ACTIVE = process
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        finish(process,grace=1.3,timeout=1.8)
        raise RuntimeError(f'command timed out: {argv[0]}')
    finish(process)
    ACTIVE = None
    return dict(exit=process.returncode, stdout=stdout.decode(), stderr=stderr.decode())


def evaluate(root, output):
    build = output/'build'
    build.mkdir()
    cases = corpus(root)
    (output/'cases.json').write_text(json.dumps(dict(seed=SEED, generated=GENERATED, cases=cases), indent=2)+'\n')
    commands = [['cobc','-x','-free','-Wall','-o',str(build/'cobol'),str(root/'src/carddemo-interest.cob')]]
    for variant in ['rust'] + MUTANTS:
        command = ['rustc','--edition=2021','-D','warnings','-C','overflow-checks=yes','-C','strip=symbols']
        if variant != 'rust':
            command += ['--cfg','carddemo_mutation' if variant == 'one_cent' else 'mutation_'+variant]
        commands.append(command+['-o',str(build/variant),str(root/'src/carddemo-interest.rs')])
    commands += [
        ['cobc','-x','-free','-Wall','-o',str(build/'stateful-cobol'),str(root/'src/stateful.cob')],
        ['rustc','--edition=2021','-D','warnings','-C','overflow-checks=yes','-C','strip=symbols',
         '-o',str(build/'stateful-rust'),str(root/'src/stateful.rs')],
    ]
    (output/'commands.json').write_text(json.dumps(commands, indent=2)+'\n')
    for index, command in enumerate(commands):
        result = execute(command, 90)
        (build/f'compile-{index}.json').write_text(json.dumps(result, indent=2)+'\n')
        if result['exit']:
            raise RuntimeError(f'compiler failed: {command[0]}, see build/compile-{index}.json')
    mismatches = []
    kills = {name: [] for name in MUTANTS}
    with (output/'observations.jsonl').open('w') as observations:
        for case in cases:
            expected = oracle(case['args'])
            actual = {name: execute([str(build/name),*case['args']], 3) for name in ['cobol','rust']+MUTANTS}
            failures = [name for name in ['cobol','rust'] if actual[name] != expected]
            if 'committed' in case and case['committed'] != expected:
                failures.append('committed-fixture')
            if failures:
                mismatches.append(dict(case=case, expected=expected, failed=failures, actual=actual))
            for name in MUTANTS:
                if actual[name] != expected:
                    kills[name].append(case['id'])
            observations.write(json.dumps(dict(caseId=case['id'], expected=expected, actual=actual))+'\n')
            observations.flush()
    (output/'failing-cases.json').write_text(json.dumps(mismatches, indent=2)+'\n')
    (output/'mutations.json').write_text(json.dumps(kills, indent=2)+'\n')
    return dict(cases=len(cases), seed=SEED, generated=GENERATED,
                baseline='EQUIVALENT' if not mismatches else 'DIVERGENT',
                failedCases=len(mismatches), killed={name:len(ids) for name,ids in kills.items()},
                survived=[name for name,ids in kills.items() if not ids])


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result = dict(state='incomplete', startedAt=time.time())
    try:
        result.update(evaluate(args.root,args.output))
        result['stateful']=suite(args.root,args.output,execute)
        result['state']='verified' if result['baseline']=='EQUIVALENT' and not result['survived'] else 'failed'
    except StatefulFailure as error:
        result.update(state='failed',stateful=dict(state='failed',
                      failureEvidence='stateful/failing-cases.json'),error=str(error))
    except Exception as error:
        result['error']=str(error)
    result['endedAt']=time.time()
    (args.output/'evaluation.json').write_text(json.dumps(result,indent=2)+'\n')
    raise SystemExit(0 if result['state']=='verified' else 1)
