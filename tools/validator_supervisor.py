"""External worker boundary; interruption never fabricates a validator return."""
import json
import signal
import subprocess
import time
from pathlib import Path
from processes import finish, members

class SupervisorInterrupted(RuntimeError):pass

ACTIVE=None
STOPPING=False

def interrupted(signum,_frame):
    global STOPPING
    if STOPPING:return
    STOPPING=True
    raise SupervisorInterrupted(signal.Signals(signum).name)

def install_handlers():
    signal.signal(signal.SIGTERM,interrupted)
    signal.signal(signal.SIGINT,interrupted)

def run(argv,folder,stdin=None,timeout=120,cancel_ready=None,env=None):
    global ACTIVE
    folder.mkdir(parents=True,exist_ok=True)
    record=dict(command=[str(a) for a in argv],startedAt=time.time(),outcome='incomplete',cleanupConfirmed=False)
    stdout=b'';stderr=b'';process=None
    try:
        process=subprocess.Popen(argv,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
                                 start_new_session=True,env=env)
        ACTIVE=process
        record['processGroup']=process.pid
        deadline=time.monotonic()+timeout
        first=True
        while True:
            try:
                stdout,stderr=process.communicate(stdin if first else None,timeout=.05)
                record['outcome']='completed'
                break
            except subprocess.TimeoutExpired:
                first=False
                if cancel_ready and cancel_ready.exists() and cancel_ready.read_text().strip().isdigit():
                    record['outcome']='interrupted'
                    record['trigger']='ready-child cancellation'
                    record['readyChild']=int(cancel_ready.read_text())
                    break
                if time.monotonic()>=deadline:
                    record['outcome']='timed-out'
                    break
        record['liveBeforeCleanup']=members(process.pid)
        drained=finish(process,grace=.2,timeout=1)
        if record['outcome']!='completed':stdout,stderr=drained
        record['cleanupConfirmed']=True
        record['exit']=process.returncode
    except BaseException as error:
        record['error']=dict(type=type(error).__name__,message=str(error))
        if isinstance(error,SupervisorInterrupted):record['outcome']='interrupted'
        raise
    finally:
        if process is not None:
            try:
                drained=finish(process,grace=.2,timeout=1)
                if 'error' in record:stdout,stderr=drained
                record['cleanupConfirmed']=True
                record['exit']=process.returncode
            except Exception as error:
                record['cleanupConfirmed']=False;record['outcome']='incomplete'
                record['cleanupError']=str(error)
        ACTIVE=None
        record['endedAt']=time.time()
        record['elapsedSeconds']=record['endedAt']-record['startedAt']
        (folder/'stdout.txt').write_bytes(stdout);(folder/'stderr.txt').write_bytes(stderr)
        (folder/'supervision.json').write_text(json.dumps(record,indent=2)+'\n')
    return record,stdout,stderr
