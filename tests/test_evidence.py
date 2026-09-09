"""Real compiler adverse/replay tests; no models, network or live bb state."""
import json
import os
from pathlib import Path
import shutil
import signal
import time
import subprocess
import tempfile
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]

class EvidenceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='cobol-evidence-tests-')
        cls.work=Path(cls.temp.name)
        cls.good=cls.work/'good'
        cls.invoke(ROOT/'run.sh','--output',cls.good,expected=0)

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    @staticmethod
    def invoke(*args,expected):
        p=subprocess.run([str(a) for a in args],capture_output=True,text=True,timeout=120)
        if p.returncode!=expected:raise AssertionError((p.returncode,p.stdout,p.stderr))
        return p

    def copy_source(self,name):
        source=self.work/name
        shutil.copytree(ROOT,source,ignore=shutil.ignore_patterns('.git','__pycache__','evidence'))
        subprocess.run(['git','init','-q',str(source)],check=True)
        subprocess.run(['git','-C',str(source),'add','.'],check=True)
        subprocess.run(['git','-C',str(source),'-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','fixture'],check=True)
        return source

    def test_clean_replay_without_checkout(self):
        copied=self.work/'unpacked'
        shutil.copytree(self.good,copied)
        self.invoke('python3',copied/'replay.py','--output',self.work/'replayed',expected=0)
        result=json.loads((self.work/'replayed/result.json').read_text())
        self.assertEqual(result['state'],'verified')
        self.assertEqual(result['demo'],json.loads((copied/'result.json').read_text())['demo'])
        self.assertTrue(result['parentEvidence'])

    def test_bad_fixture_retains_failure(self):
        source=self.copy_source('bad-fixture')
        path=source/'fixtures/cases.tsv'
        path.write_text(path.read_text().replace('zero\tzero\t0.00\t0.00\t0\tOK\t0.00','zero\tzero\t0.00\t0.00\t0\tOK\t9.99'))
        out=self.work/'bad-fixture-evidence'
        self.invoke(source/'run.sh','--output',out,expected=1)
        result=json.loads((out/'result.json').read_text())
        self.assertEqual(result['state'],'failed')
        self.assertTrue(result['demo']['dirty'])
        self.assertTrue(json.loads((out/'failing-cases.json').read_text()))
        self.assertTrue(Path(str(out)+'.tar.gz').is_file())
        self.invoke('python3',out/'replay.py','--output',self.work/'failed-replay',expected=1)

    def test_compile_failure_retains_diagnostics(self):
        source=self.copy_source('compile-failure')
        (source/'src/carddemo-interest.rs').write_text('this cannot compile')
        out=self.work/'compile-evidence'
        self.invoke(source/'run.sh','--output',out,expected=1)
        self.assertEqual(json.loads((out/'result.json').read_text())['state'],'incomplete')
        self.assertNotEqual(json.loads((out/'build/compile-1.json').read_text())['exit'],0)
        self.assertTrue((out/'SHA256SUMS').is_file())

    def test_tampered_input_refused_before_execution(self):
        out=self.work/'tampered'
        shutil.copytree(self.good,out)
        with (out/'inputs/src/carddemo-interest.rs').open('a') as stream:stream.write('\n// tampered\n')
        self.invoke('python3',out/'replay.py','--output',self.work/'must-not-exist',expected=2)
        self.assertFalse((self.work/'must-not-exist').exists())

    def test_root_signals_stop_compiler_and_retain_incomplete(self):
        for sig in [signal.SIGTERM,signal.SIGINT]:
            with self.subTest(signal=sig.name):
                folder=self.work/sig.name
                folder.mkdir()
                compiler=folder/'cobc'
                marker=folder/'compiler.pid'
                compiler.write_text('#!/usr/bin/python3\nimport os,sys,time,signal,pathlib\n'
                    'if "-V" in sys.argv: print("slow fixture compiler");sys.exit(0)\n'
                    'signal.signal(signal.SIGTERM,signal.SIG_IGN)\n'
                    f'pathlib.Path({str(marker)!r}).write_text(str(os.getpid()))\n'
                    'time.sleep(60)\n')
                compiler.chmod(0o755)
                out=folder/'evidence'
                process=subprocess.Popen([str(ROOT/'run.sh'),'--output',str(out)],
                    env={**os.environ,'PATH':str(folder)+':'+os.environ['PATH']},
                    stdout=subprocess.PIPE,stderr=subprocess.PIPE)
                child=None
                try:
                    for _ in range(200):
                        if marker.exists():break
                        time.sleep(.025)
                    self.assertTrue(marker.exists(),'compiler did not start')
                    child=int(marker.read_text())
                    evaluator=int(Path(f'/proc/{child}/stat').read_text().split()[3])
                    process.send_signal(sig)
                    process.communicate(timeout=10)
                    self.assertNotEqual(process.returncode,0)
                    for pid in [child,evaluator]:
                        stat=Path(f'/proc/{pid}/stat')
                        self.assertTrue(not stat.exists() or stat.read_text().split()[2]=='Z')
                    result=json.loads((out/'result.json').read_text())
                    self.assertEqual(result['state'],'incomplete')
                    self.assertIn(sig.name,result['error'])
                    self.assertTrue(Path(str(out)+'.tar.gz').exists())
                    sys.path.insert(0,str(ROOT))
                    from replay import verify
                    verify(out)
                finally:
                    if process.poll() is None:process.kill();process.wait()
                    if child:
                        try:os.killpg(child,signal.SIGKILL)
                        except ProcessLookupError:pass

    def test_version_probe_cleans_child_after_leader_exit(self):
        folder=self.work/'probe-orphan'
        folder.mkdir()
        compiler=folder/'cobc'
        marker=folder/'child.pid'
        compiler.write_text('#!/usr/bin/python3\nimport os,signal,time,pathlib\n'
            'child=os.fork()\n'
            'if child: os._exit(0)\n'
            'signal.signal(signal.SIGTERM,signal.SIG_IGN)\n'
            f'pathlib.Path({str(marker)!r}).write_text(str(os.getpid()))\n'
            'time.sleep(60)\n')
        compiler.chmod(0o755)
        out=folder/'evidence'
        process=subprocess.Popen([str(ROOT/'run.sh'),'--output',str(out)],
            env={**os.environ,'PATH':str(folder)+':'+os.environ['PATH']},
            stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        child=None
        try:
            process.communicate(timeout=18)
            self.assertNotEqual(process.returncode,0)
            child=int(marker.read_text())
            stat=Path(f'/proc/{child}/stat')
            self.assertTrue(not stat.exists() or stat.read_text().split()[2]=='Z')
            self.assertEqual(json.loads((out/'result.json').read_text())['state'],'incomplete')
            self.assertTrue((out/'SHA256SUMS').exists())
        finally:
            if process.poll() is None:process.kill();process.wait()
            if marker.exists():
                try:os.kill(int(marker.read_text()),signal.SIGKILL)
                except ProcessLookupError:pass

    def test_root_signals_stop_nested_stateful_transition(self):
        for sig in [signal.SIGTERM,signal.SIGINT]:
            with self.subTest(signal=sig.name):
                source=self.copy_source('stateful-'+sig.name)
                folder=self.work/('nested-'+sig.name);folder.mkdir()
                marker=folder/'child.pid'
                binary=folder/'transition'
                binary.write_text('#!/usr/bin/python3\nimport os,signal,time,pathlib\n'
                    'child=os.fork()\n'
                    'if child: os._exit(0)\n'
                    'signal.signal(signal.SIGTERM,signal.SIG_IGN)\n'
                    f'pathlib.Path({str(marker)!r}).write_text(str(os.getpid()))\n'
                    'time.sleep(60)\n')
                binary.chmod(0o755)
                (source/'tools/stateful_suite.py').write_text(
                    'import sys\nclass StatefulFailure(AssertionError):pass\n'
                    'def suite(root,output,execute):\n'
                    '    return execute([sys.executable,str(root/"tools/stateful.py"),'
                    '"--fixture",str(root/"fixtures/stateful.json"),"--binary",'
                    +repr(str(binary))+',"--state",str(output/"stateful"),"--initialize"],30)\n')
                out=folder/'evidence'
                process=subprocess.Popen([str(source/'run.sh'),'--output',str(out)],
                    stdout=subprocess.PIPE,stderr=subprocess.PIPE)
                child=None
                try:
                    deadline=time.monotonic()+30
                    while not marker.exists() and time.monotonic()<deadline:time.sleep(.025)
                    self.assertTrue(marker.exists(),'transition did not start')
                    child=int(marker.read_text())
                    process.send_signal(sig)
                    process.communicate(timeout=10)
                    self.assertNotEqual(process.returncode,0)
                    stat=Path(f'/proc/{child}/stat')
                    self.assertTrue(not stat.exists() or stat.read_text().split()[2]=='Z','nested child survives')
                    result=json.loads((out/'result.json').read_text())
                    self.assertEqual(result['state'],'incomplete')
                    sys.path.insert(0,str(ROOT))
                    from replay import verify
                    verify(out)
                    checkpoint=json.loads((out/'stateful/checkpoint.json').read_text())
                    self.assertEqual(checkpoint['next'],0)
                    self.assertEqual(checkpoint['journal'],[])
                finally:
                    if process.poll() is None:process.kill();process.wait()
                    if child:
                        try:os.kill(child,signal.SIGKILL)
                        except ProcessLookupError:pass

    def test_stateful_behavioral_mismatch_is_failed_and_replays_failed(self):
        source=self.copy_source('stateful-behavioral-mismatch')
        path=source/'src/stateful.rs'
        original=path.read_text()
        changed=original.replace('let delta=balance*rate/120000;', 'let delta=balance*rate/120000+1;')
        self.assertNotEqual(original,changed)
        path.write_text(changed)
        out=self.work/'stateful-mismatch-evidence'
        self.invoke(source/'run.sh','--output',out,expected=1)
        for evidence in [out,self.work/'stateful-mismatch-replayed']:
            if evidence!=out:self.invoke('python3',out/'replay.py','--output',evidence,expected=1)
            result=json.loads((evidence/'result.json').read_text())
            self.assertEqual(result['state'],'failed')
            self.assertEqual(result['evaluation']['stateful']['state'],'failed')
            failure=json.loads((evidence/'stateful/failing-cases.json').read_text())[0]
            self.assertEqual(failure['invocation']['observation']['exit'],0)
            self.assertNotEqual(failure['expected']['balances'],failure['actual']['balances'])
            self.assertIn('journal',failure['actual'])

    def test_surviving_restart_mutant_is_failed(self):
        source=self.copy_source('restart-mutant-survivor')
        path=source/'tools/stateful.py'
        original=path.read_text()
        changed=original.replace("if broken and state['next']:", 'if False:')
        self.assertNotEqual(original,changed)
        path.write_text(changed)
        out=self.work/'restart-survivor-evidence'
        self.invoke(source/'run.sh','--output',out,expected=1)
        result=json.loads((out/'result.json').read_text())
        self.assertEqual(result['state'],'failed')
        failure=json.loads((out/'stateful/failing-cases.json').read_text())[0]
        self.assertEqual(failure['reason'],'broken restart survived')
        self.assertEqual(failure['actual'],0)
        self.assertEqual(failure['expected'],'nonzero exit')

    def test_surviving_required_mutant_fails(self):
        source=self.copy_source('survivor')
        path=source/'src/carddemo-interest.rs'
        path.write_text(path.read_text().replace('let monthly_cents = monthly_cents.abs();','let monthly_cents = monthly_cents;'))
        out=self.work/'survivor-evidence'
        self.invoke(source/'run.sh','--output',out,expected=1)
        result=json.loads((out/'result.json').read_text())
        self.assertEqual(result['state'],'failed')
        self.assertIn('sign',result['evaluation']['survived'])

if __name__=='__main__':unittest.main()
