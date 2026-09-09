"""Bounded cleanup of trusted ordinary Linux process groups, including orphans."""
import os
from pathlib import Path
import signal
import subprocess
import time


def members(group):
    live=[]
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():
            continue
        try:
            fields=(entry/'stat').read_text().rpartition(')')[2].split()
        except (FileNotFoundError, ProcessLookupError):
            continue
        if int(fields[2])==group and fields[0] not in ('Z','X'):
            live.append(int(entry.name))
    return live


def send(group, sig):
    try:
        os.killpg(group,sig)
    except ProcessLookupError:
        pass


def finish(process, grace=.1, timeout=1.0):
    # The leader's return code says nothing about surviving members or pipes.
    group=process.pid
    send(group,signal.SIGTERM)
    deadline=time.monotonic()+timeout
    term_deadline=time.monotonic()+grace
    while members(group) and time.monotonic()<term_deadline:
        time.sleep(.01)
    send(group,signal.SIGKILL)
    while members(group) and time.monotonic()<deadline:
        time.sleep(.01)
    if members(group):
        raise RuntimeError('process-group termination remains unconfirmed')
    try:
        return process.communicate(timeout=max(.05,deadline-time.monotonic()))
    except subprocess.TimeoutExpired as error:
        raise RuntimeError('process output drain remains unconfirmed') from error
