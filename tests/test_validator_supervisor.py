"""Bounded external-supervisor regressions; no Bun, models or platform checkout required."""
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'tools'))
from validator_supervisor import run

class ValidatorSupervisorTests(unittest.TestCase):
    def test_normal_exited_leader_still_cleans_closed_pipe_child(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp);marker=folder/'child.pid';script=folder/'fork.py'
            script.write_text('import os,signal,time,pathlib\n'
                'child=os.fork()\n'
                'if child:\n'
                f' while not pathlib.Path({str(marker)!r}).exists():time.sleep(.01)\n'
                ' os._exit(0)\n'
                'signal.signal(signal.SIGTERM,signal.SIG_IGN)\n'
                f'pathlib.Path({str(marker)!r}).write_text(str(os.getpid()))\n'
                'os.close(0);os.close(1);os.close(2)\ntime.sleep(30)\n')
            result,_,_=run([sys.executable,str(script)],folder/'evidence',timeout=5)
            self.assertEqual(result['outcome'],'completed');self.assertTrue(result['cleanupConfirmed'])
            self.assertTrue(result['liveBeforeCleanup'])
            pid=int(marker.read_text());stat=Path(f'/proc/{pid}/stat')
            self.assertTrue(not stat.exists() or stat.read_text().rpartition(')')[2].split()[0]=='Z')

    def test_outer_term_int_retain_interruption_and_clean_group(self):
        for sig in [signal.SIGTERM,signal.SIGINT]:
            with self.subTest(signal=sig.name),tempfile.TemporaryDirectory() as temp:
                folder=Path(temp);marker=folder/'child.pid';child=folder/'child.py'
                child.write_text('import os,signal,time,pathlib\n'
                    'if os.fork():\n while True:time.sleep(1)\n'
                    'signal.signal(signal.SIGTERM,signal.SIG_IGN)\n'
                    f'pathlib.Path({str(marker)!r}).write_text(str(os.getpid()))\n'
                    'time.sleep(30)\n')
                wrapper=folder/'supervisor.py'
                wrapper.write_text('import sys\nfrom pathlib import Path\n'
                    f'sys.path.insert(0,{str(Path(__file__).resolve().parents[1]/"tools")!r})\n'
                    'from validator_supervisor import run,install_handlers\ninstall_handlers()\n'
                    f'run([sys.executable,{str(child)!r}],Path({str(folder/"evidence")!r}),timeout=10)\n')
                process=subprocess.Popen([sys.executable,str(wrapper)],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
                pid=None;group=None
                try:
                    deadline=time.monotonic()+5
                    while not marker.exists() and time.monotonic()<deadline:time.sleep(.02)
                    self.assertTrue(marker.exists());pid=int(marker.read_text());group=os.getpgid(pid)
                    process.send_signal(sig);process.communicate(timeout=5)
                    self.assertNotEqual(process.returncode,0)
                    result=json.loads((folder/'evidence/supervision.json').read_text())
                    self.assertEqual(result['outcome'],'interrupted');self.assertTrue(result['cleanupConfirmed'])
                    self.assertEqual(result['error']['type'],'SupervisorInterrupted')
                    stat=Path(f'/proc/{pid}/stat')
                    self.assertTrue(not stat.exists() or stat.read_text().rpartition(')')[2].split()[0]=='Z')
                finally:
                    if group:
                        try:os.killpg(group,signal.SIGKILL)
                        except ProcessLookupError:pass
                    if process.poll() is None:process.kill()
                    process.communicate(timeout=2)
