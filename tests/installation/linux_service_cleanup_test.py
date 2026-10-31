"""Exercise actual package postrm with isolated fake service-manager helpers.

No real systemctl, package manager, service, credential or database is touched.
The child PATH contains only these recording stubs; the real script runs through
/bin/sh. Native package lifecycle acceptance remains a separate test category.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import io
import json
import os
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = Path(__file__).resolve().parents[2]
POSTRM = ROOT/'packaging/linux-native/postrm'
EVIDENCE = ROOT/'build/linux/native-kernel-20261031/service-cleanup-regression'
SCRATCH = ROOT/'runtime/scratch/linux-service-cleanup'


@unittest.skipUnless(platform.system() == 'Linux', 'Native /bin/sh required')
class CleanupTests(unittest.TestCase):
    def setUp(self):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix='case-', dir=SCRATCH)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bin = self.root/'bin'
        self.bin.mkdir()
        self.log = self.root/'calls.jsonl'
        self.bookkeeping = self.root/'bookkeeping'
        self.bookkeeping.mkdir()
        (self.bookkeeping/'dragonhydra-api.service.link').write_text('owned helper state')
        (self.bookkeeping/'unrelated.service.link').write_text('preserve another service')
        for relative, body in {
            'state/core.sqlite3': b'representative committed bytes\x00\xff',
            'state/raw/capture.json': b'{"fixture":"retained"}',
            'config/api.env': b'DRAGONHYDRA_PORT=18743\n',
            'state/local-session.json': b'{"token":"labelled-synthetic-test-value"}',
        }.items():
            path = self.root/relative
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
        self.protected = {path.relative_to(self.root).as_posix(): path.read_bytes()
                          for top in ('state','config') for path in (self.root/top).rglob('*') if path.is_file()}
        stub = '''#!/usr/bin/python3
import json,os,sys
from pathlib import Path
name=Path(sys.argv[0]).name
with Path(os.environ['DH_TEST_CALLS']).open('a') as output:
    output.write(json.dumps({'name':name,'args':sys.argv[1:]})+'\\n')
code=int(os.environ.get('DH_TEST_HELPER_EXIT' if name=='deb-systemd-helper' else 'DH_TEST_SYSTEMCTL_EXIT','0'))
if code:raise SystemExit(code)
if name=='deb-systemd-helper':
    if sys.argv[1:]!=['purge','dragonhydra-api.service']:raise SystemExit(91)
    (Path(os.environ['DH_TEST_BOOKKEEPING'])/'dragonhydra-api.service.link').unlink(missing_ok=True)
elif name=='systemctl':
    if sys.argv[1:]!=['daemon-reload']:raise SystemExit(92)
else:raise SystemExit(93)
'''
        for name in ('deb-systemd-helper','systemctl'):
            path = self.bin/name
            path.write_text(stub)
            path.chmod(0o755)

    def hook(self, *arguments, isolated_root=False, helper_exit=0, systemctl_exit=0):
        env = {**os.environ, 'PATH': str(self.bin), 'DPKG_ROOT': str(self.root/'isolated-root') if isolated_root else '/',
               'DH_TEST_CALLS': str(self.log), 'DH_TEST_BOOKKEEPING': str(self.bookkeeping),
               'DH_TEST_HELPER_EXIT': str(helper_exit), 'DH_TEST_SYSTEMCTL_EXIT': str(systemctl_exit)}
        result = subprocess.run(['/bin/sh',str(POSTRM),*arguments],env=env,cwd=self.root,
                                capture_output=True,text=True,timeout=5)
        for name, body in self.protected.items():
            self.assertEqual((self.root/name).read_bytes(),body,'Retained data changed: '+name)
        self.assertEqual((self.bookkeeping/'unrelated.service.link').read_text(),'preserve another service')
        return result

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def expected(self):
        calls = [{'name':'deb-systemd-helper','args':['purge','dragonhydra-api.service']}]
        if Path('/run/systemd/system').is_dir():
            calls.append({'name':'systemctl','args':['daemon-reload']})
        return calls

    def test_isolated_dpkg_root_never_manages_host(self):
        for action in ('remove','purge','upgrade','failed-upgrade'):
            with self.subTest(action=action):
                result = self.hook(action,isolated_root=True)
                self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(self.calls(),[])
        self.assertTrue((self.bookkeeping/'dragonhydra-api.service.link').is_file())

    def test_upgrade_and_failed_upgrade_do_not_change_enablement(self):
        for action in ('upgrade','failed-upgrade','abort-install','abort-upgrade','disappear'):
            with self.subTest(action=action):
                result = self.hook(action,'0.4.0-old')
                self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(self.calls(),[])
        self.assertTrue((self.bookkeeping/'dragonhydra-api.service.link').is_file())

    def test_missing_action_is_a_noop(self):
        result = self.hook()
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(self.calls(),[])

    def test_remove_clears_only_exact_unit_bookkeeping(self):
        result = self.hook('remove')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(self.calls(),self.expected())
        self.assertFalse((self.bookkeeping/'dragonhydra-api.service.link').exists())

    def test_purge_clears_only_exact_unit_bookkeeping(self):
        result = self.hook('purge')
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(self.calls(),self.expected())
        self.assertFalse((self.bookkeeping/'dragonhydra-api.service.link').exists())

    def test_repeated_remove_and_purge_are_idempotent(self):
        for action in ('remove','remove','purge','purge'):
            result = self.hook(action)
            self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(self.calls(),self.expected()*4)
        self.assertFalse((self.bookkeeping/'dragonhydra-api.service.link').exists())

    def test_helper_failure_propagates_without_false_reload_or_cleanup(self):
        result = self.hook('remove',helper_exit=17)
        self.assertEqual(result.returncode,17)
        self.assertEqual(self.calls(),[{'name':'deb-systemd-helper','args':['purge','dragonhydra-api.service']}])
        self.assertTrue((self.bookkeeping/'dragonhydra-api.service.link').is_file())

    @unittest.skipUnless(Path('/run/systemd/system').is_dir(), 'Daemon reload branch requires systemd marker')
    def test_daemon_reload_failure_is_not_reported_as_success(self):
        result = self.hook('remove',systemctl_exit=23)
        self.assertEqual(result.returncode,23)
        self.assertEqual(self.calls(),self.expected())


if __name__=='__main__':
    if EVIDENCE.exists():
        raise SystemExit('Evidence directory already exists; retain previous results')
    EVIDENCE.mkdir(parents=True)
    before = hashlib.sha256(POSTRM.read_bytes()).hexdigest()
    started = datetime.now(timezone.utc).isoformat()
    log = io.StringIO()
    result = unittest.TextTestRunner(stream=log,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(CleanupTests))
    after = hashlib.sha256(POSTRM.read_bytes()).hexdigest()
    (EVIDENCE/'unittest.log').write_text(log.getvalue())
    report = {'schema_version':1,'started_at':started,'finished_at':datetime.now(timezone.utc).isoformat(),
              'command':[sys.executable,'-B','tests/installation/linux_service_cleanup_test.py'],
              'environment':{'platform':platform.platform(),'python':sys.version,'executable':sys.executable},
              'tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),
              'skipped':[{'test':str(case),'reason':reason} for case,reason in result.skipped],
              'postrm_sha256_before':before,'postrm_sha256_after':after,
              'harness_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'passed':result.wasSuccessful() and before==after,
              'scope':'Actual postrm through native /bin/sh with fake recording helpers only; no actual services/package manager or user data touched'}
    report['exit_code']=0 if report['passed'] else 1
    (EVIDENCE/'verification.json').write_text(json.dumps(report,indent=2)+'\n')
    print(log.getvalue(),end='')
    print(json.dumps(report,indent=2))
    raise SystemExit(report['exit_code'])
