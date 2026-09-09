#!/usr/bin/env python3
"""Synthetic checkpoint coordinator, independent state oracle and wire framing."""
import argparse
import copy
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import sys
import time
from fractions import Fraction
from numeric import oracle, classify
from processes import finish

ACTIVE=None
STOPPING=False
LIMIT=Fraction('999999999.99')
ROW_KEYS={'offset','id','account','rate','disposition','reason','opening','interest','closing'}
STATE_KEYS={'schemaVersion','inputHash','next','balances','acceptedIds','journal'}


def canonical(value):
    return json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=True)


def money(value):
    cents=int(value*100)
    return ('-' if cents<0 else '')+f'{abs(cents)//100}.{abs(cents)%100:02}'


def valid_money(text):
    return (isinstance(text,str) and re.fullmatch(r'-?(0|[1-9][0-9]{0,8})\.[0-9]{2}',text)
            and text!='-0.00' and abs(Fraction(text))<=LIMIT)


def require(condition,message):
    if not condition:raise ValueError(message)


def validate_fixture(fixture):
    require(set(fixture)=={'schemaVersion','accounts','records'} and type(fixture['schemaVersion']) is int and fixture['schemaVersion']==1,'fixture schema')
    require(isinstance(fixture['accounts'],list) and len(fixture['accounts'])<=8,'accounts bound')
    require(isinstance(fixture['records'],list) and len(fixture['records'])<=32,'records bound')
    def identifier(text):return isinstance(text,str) and re.fullmatch(r'[A-Za-z0-9-]{1,12}',text)
    seen=set()
    for account in fixture['accounts']:
        require(set(account)=={'id','balance'} and identifier(account['id']) and valid_money(account['balance']),'opening account')
        require(account['id'] not in seen,'duplicate opening account')
        seen.add(account['id'])
    for record in fixture['records']:
        require(set(record)=={'id','account','rate'} and identifier(record['id']) and identifier(record['account']),'record schema')
        rate=record['rate']
        require(isinstance(rate,str) and rate.isascii() and len(rate)<=64 and not any(c in rate for c in '\0\n\t'),'record rate framing')


def initial(fixture):
    validate_fixture(fixture)
    return dict(schemaVersion=1,inputHash=hashlib.sha256(canonical(fixture).encode()).hexdigest(),next=0,
                balances={a['id']:a['balance'] for a in fixture['accounts']},acceptedIds=[],journal=[])


def expected_step(state, record):
    """Acceptance oracle only; never used to replace a program's candidate."""
    out=copy.deepcopy(state)
    row=dict(offset=state['next'],**record,disposition='REJECTED',reason=None,opening=None,interest=None,closing=None)
    if record['id'] in state['acceptedIds']:
        row.update(disposition='DUPLICATE',reason='ACCEPTED_ID')
    elif record['account'] not in state['balances']:
        row['reason']='UNKNOWN_ACCOUNT'
    else:
        opening=state['balances'][record['account']]
        row.update(opening=opening,closing=opening)
        error,_=classify(record['rate'],4)
        if error:row['reason']='RATE_OVERFLOW' if error=='OVERFLOW' else 'INVALID_INPUT'
        else:
            result=oracle([opening,record['rate']])
            if result['exit']:row['reason']='INTEREST_OVERFLOW'
            else:
                interest=result['stdout'].strip().split('\t')[1]
                row['interest']=interest
                closing=Fraction(opening)+Fraction(interest)
                if abs(closing)>LIMIT:row['reason']='BALANCE_OVERFLOW'
                else:
                    row.update(disposition='APPLIED',closing=money(closing))
                    out['balances'][record['account']]=row['closing']
                    out['acceptedIds'].append(record['id'])
    out['next']+=1
    out['journal'].append(row)
    return out


def validate_state(state,fixture):
    base=initial(fixture)
    require(set(state)==STATE_KEYS and type(state['schemaVersion']) is int and state['schemaVersion']==1,'checkpoint schema')
    require(state['inputHash']==base['inputHash'],'changed input identity')
    require(type(state['next']) is int and 0<=state['next']<=len(fixture['records']),'cursor bounds')
    require(isinstance(state['balances'],dict) and set(state['balances'])==set(base['balances']),'account set')
    require(all(valid_money(v) for v in state['balances'].values()),'balance encoding')
    require(isinstance(state['journal'],list) and len(state['journal'])==state['next'],'journal/cursor mismatch')
    require(isinstance(state['acceptedIds'],list),'accepted IDs')
    balances=base['balances'].copy();accepted=[]
    for offset,row in enumerate(state['journal']):
        record=fixture['records'][offset]
        require(set(row)==ROW_KEYS and type(row['offset']) is int and row['offset']==offset,'journal offset/schema')
        require(all(row[k]==v for k,v in record.items()),'journal input identity')
        disposition=row['disposition'];reason=row['reason']
        if record['id'] in accepted:
            require(disposition=='DUPLICATE' and reason=='ACCEPTED_ID','duplicate policy')
            require(all(row[k] is None for k in ['opening','interest','closing']),'duplicate nullability')
        elif record['account'] not in balances:
            require(disposition=='REJECTED' and reason=='UNKNOWN_ACCOUNT','unknown account policy')
            require(all(row[k] is None for k in ['opening','interest','closing']),'unknown nullability')
        else:
            require(row['opening']==balances[record['account']] and valid_money(row['closing']),'balance chain')
            error,_=classify(record['rate'],4)
            if error:
                require(disposition=='REJECTED' and reason==('RATE_OVERFLOW' if error=='OVERFLOW' else 'INVALID_INPUT'),'rate rejection policy')
                require(row['interest'] is None and row['closing']==row['opening'],'rate rejection amounts')
            elif disposition=='APPLIED':
                require(reason is None and valid_money(row['interest']),'applied fields')
                require(Fraction(row['opening'])+Fraction(row['interest'])==Fraction(row['closing']),'balance addition')
                balances[record['account']]=row['closing'];accepted.append(record['id'])
            else:
                require(disposition=='REJECTED' and reason in ['INTEREST_OVERFLOW','BALANCE_OVERFLOW'],'rejection reason')
                require(row['closing']==row['opening'],'rejected balance change')
                if reason=='INTEREST_OVERFLOW':require(row['interest'] is None,'interest overflow null')
                else:
                    require(valid_money(row['interest']),'closing overflow interest')
                    require(abs(Fraction(row['opening'])+Fraction(row['interest']))>LIMIT,'closing overflow bound')
    require(state['acceptedIds']==accepted,'accepted IDs disagree with journal')
    require(state['balances']==balances,'final balance chain')


def encode(state,record):
    lines=[f"STATE|{state['next']}|{state['inputHash']}"]
    lines += [f'ACCOUNT|{key}|{value}' for key,value in state['balances'].items()]
    lines += ['ACCEPTED|'+key for key in state['acceptedIds']]
    for row in state['journal']:
        lines.append('JOURNAL|'+'|'.join(str(row[k]) if row[k] is not None else '~' for k in ['offset','id','account'])+'|'+row['rate'].encode().hex().upper()+'|'+'|'.join(row[k] if row[k] is not None else '~' for k in ['disposition','reason','opening','interest','closing']))
    lines += ['RECORD|'+record['id']+'|'+record['account']+'|'+record['rate'].encode().hex().upper(),'END']
    return '\n'.join(lines)+'\n'


def decode(text):
    lines=text.splitlines()
    require(lines and lines[-1]=='END','missing output terminator')
    head=lines[0].split('|');require(len(head)==3 and head[0]=='STATE','state header')
    state=dict(schemaVersion=1,inputHash=head[2],next=int(head[1]),balances={},acceptedIds=[],journal=[])
    for line in lines[1:-1]:
        fields=line.split('|')
        if fields[0]=='ACCOUNT':
            require(len(fields)==3 and fields[1] not in state['balances'],'account wire')
            state['balances'][fields[1]]=fields[2]
        elif fields[0]=='ACCEPTED':
            require(len(fields)==2,'accepted wire');state['acceptedIds'].append(fields[1])
        elif fields[0]=='JOURNAL':
            require(len(fields)==10,'journal wire')
            row=dict(zip(['offset','id','account','rate','disposition','reason','opening','interest','closing'],fields[1:]))
            row['offset']=int(row['offset']);row['rate']=bytes.fromhex(row['rate']).decode('ascii')
            for key in ['reason','opening','interest','closing']:
                if row[key]=='~':row[key]=None
            state['journal'].append(row)
        else:raise ValueError('unexpected output row')
    return state


def interrupted(signum,_frame):
    global STOPPING
    if STOPPING:return
    STOPPING=True
    if ACTIVE is not None:finish(ACTIVE)
    raise InterruptedError(signal.Signals(signum).name)


def transition(binary,state,record,log):
    global ACTIVE
    started=time.time()
    process=subprocess.Popen([str(binary)],stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,start_new_session=True)
    ACTIVE=process
    try:
        stdout,stderr=process.communicate(encode(state,record).encode(),timeout=3)
        finish(process)
        observation=dict(exit=process.returncode,stdout=stdout.decode(),stderr=stderr.decode())
        log.update(observation=observation)
        require(process.returncode==0 and not stderr,'transition process failed')
        return decode(stdout.decode())
    except subprocess.TimeoutExpired:
        stdout,stderr=finish(process)
        log.update(observation=dict(exit=process.returncode,stdout=stdout.decode(errors='replace'),
                                    stderr=stderr.decode(errors='replace')),timedOut=True)
        raise RuntimeError('transition timeout')
    finally:
        try:
            finish(process)
            log['cleanupConfirmed']=True
        finally:ACTIVE=None;log.update(startedAt=started,endedAt=time.time())


def publish(directory,state,fault=None,before=None,phase=lambda value:None):
    candidate=directory/'candidate.json'
    phase('write')
    if fault=='write':
        phase('injected-write-failure')
        raise OSError('injected pre-rename write failure')
    with candidate.open('w') as stream:
        stream.write(canonical(state)+'\n');stream.flush();os.fsync(stream.fileno())
    phase('before-rename')
    if before:before()
    os.replace(candidate,directory/'checkpoint.json')
    phase('renamed-directory-sync-pending')
    if fault=='dirsync':
        phase('injected-directory-sync-failure')
        raise OSError('injected directory-fsync failure after rename')
    fd=os.open(directory,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)
    phase('committed')


def run_batch(fixture,binary,directory,initialize=False,hook=None,offset=None,publication_fault=None,broken=False,report=None):
    if report is None:report={}
    report['phase']='fixture-validate'
    validate_fixture(fixture)
    directory.mkdir(parents=True,exist_ok=True)
    checkpoint=directory/'checkpoint.json'
    report['phase']='checkpoint-load'
    if initialize:
        require(not checkpoint.exists(),'checkpoint already exists')
        publish(directory,initial(fixture))
    else:require(checkpoint.is_file(),'restart checkpoint is missing')
    raw=checkpoint.read_text()
    report['phase']='checkpoint-decode'
    state=json.loads(raw)
    report['phase']='checkpoint-validate'
    validate_state(state,fixture)
    candidate=directory/'candidate.json'
    if candidate.exists():candidate.unlink()
    if broken and state['next']:
        # Deliberately broken recovery loses commit identity and reapplies a
        # committed prefix on already-updated balances; checks must reject it.
        original=copy.deepcopy(state)
        state['next']-=1
        state['journal']=state['journal'][:-1]
        state['acceptedIds']=[]
        report['mutation']=dict(name='replay-without-commit-identity',before=original,after=copy.deepcopy(state))
    def injected_exit(name,index):
        report.update(outcome='injected-interruption',hook=dict(name=name,offset=index))
        (directory/'outcome.json').write_text(json.dumps(report,indent=2)+'\n')
        os._exit(75)
    while state['next']<len(fixture['records']):
        index=state['next'];record=fixture['records'][index]
        evidence=dict(offset=index,phase='execute')
        report.update(phase='execute',attempt=evidence)
        try:
            proposed=transition(binary,state,record,evidence)
            report.update(phase='candidate-validate',candidate=proposed)
            validate_state(proposed,fixture)
            require(proposed['next']==index+1 and proposed['journal'][:-1]==state['journal'],'candidate progression')
            (directory/f'candidate-{index}.json').write_text(canonical(proposed)+'\n')
            (directory/'last-attempt.json').write_text(json.dumps(evidence,indent=2)+'\n')
            def phase(value):
                evidence['phase']=value
                report['phase']=value
                (directory/'last-attempt.json').write_text(json.dumps(evidence,indent=2)+'\n')
            publish(directory,proposed,publication_fault if index==offset else None,
                    (lambda:injected_exit('before',index)) if hook=='before' and index==offset else None,phase)
            evidence['phase']='committed'
            (directory/f'committed-{index}.json').write_text(canonical(proposed)+'\n')
            (directory/'last-attempt.json').write_text(json.dumps(evidence,indent=2)+'\n')
            if hook=='after' and index==offset:injected_exit('after',index)
            state=proposed
        except Exception as error:
            evidence['error']=f'{type(error).__name__}: {error}'
            raise
        finally:
            (directory/'last-attempt.json').write_text(json.dumps(evidence,indent=2)+'\n')
    return state


if __name__=='__main__':
    signal.signal(signal.SIGTERM,interrupted);signal.signal(signal.SIGINT,interrupted)
    parser=argparse.ArgumentParser()
    parser.add_argument('--fixture',type=Path,required=True);parser.add_argument('--binary',type=Path,required=True)
    parser.add_argument('--state',type=Path,required=True);parser.add_argument('--initialize',action='store_true')
    parser.add_argument('--hook',choices=['before','after']);parser.add_argument('--offset',type=int)
    parser.add_argument('--publication-fault',choices=['write','dirsync']);parser.add_argument('--broken',action='store_true')
    args=parser.parse_args()
    report=dict(schemaVersion=1,outcome='incomplete',phase='fixture-load')
    exit_code=1
    try:
        result=run_batch(json.loads(args.fixture.read_text()),args.binary,args.state,args.initialize,args.hook,args.offset,args.publication_fault,args.broken,report)
        report.update(outcome='completed',phase='complete')
        print(canonical(result))
        exit_code=0
    except Exception as error:
        report['error']=dict(type=type(error).__name__,message=str(error))
        print(f'{type(error).__name__}: {error}',file=sys.stderr)
    try:
        args.state.mkdir(parents=True,exist_ok=True)
        (args.state/'outcome.json').write_text(json.dumps(report,indent=2)+'\n')
    except Exception as error:
        print(f'outcome retention failed: {error}',file=sys.stderr)
        exit_code=1
    raise SystemExit(exit_code)
