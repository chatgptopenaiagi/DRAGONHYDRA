"""Regression for the managed Linux package's persistent loopback address.

Runs only on Linux using project-owned scratch directories. It never reads
credentials or invokes systemd, a package manager, or the application API.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import platform
import socket
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
HELPER = ROOT / 'packaging/linux-native/managed_endpoint.py'
SCRATCH = ROOT / 'runtime/scratch/linux-managed-endpoint'
EVIDENCE = ROOT / 'build/linux/native-kernel-20261031/managed-endpoint-regression'
SPEC = importlib.util.spec_from_file_location('managed_endpoint_under_test', HELPER)
MANAGED = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MANAGED)


class ManagedEndpointTests(unittest.TestCase):
    def setUp(self):
        SCRATCH.mkdir(parents=True, exist_ok=True)
        temporary = tempfile.TemporaryDirectory(prefix='state with spaces Fußball-', dir=SCRATCH)
        self.addCleanup(temporary.cleanup)
        self.state = Path(temporary.name)
        self.environment = patch.dict(os.environ, {'DRAGONHYDRA_MANAGED_ENDPOINT': '1'})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def arguments(self, *extra):
        return MANAGED.managed_arguments(['--state', str(self.state), '--port', '0', *extra])

    def test_port_survives_endpoint_file_removal_and_repeated_start_arguments(self):
        first = self.arguments()
        port = int(first[-1])
        self.assertEqual(first[-2], '--port')
        self.assertGreater(port, 0)
        self.assertLessEqual(port, 65535)
        cache = (self.state / MANAGED.CACHE).read_bytes()
        endpoint = self.state / 'endpoint.json'
        endpoint.write_text(json.dumps({'url': 'http://127.0.0.1:' + str(port), 'pid': 123}))
        endpoint.unlink()  # The original R4 shutdown deletes this readiness file.
        for _ in range(5):
            self.assertEqual(self.arguments(), first)
            self.assertEqual((self.state / MANAGED.CACHE).read_bytes(), cache)
        self.assertIn('Fußball', str(self.state))

    def test_plain_cli_port_zero_does_not_create_managed_state(self):
        unused = self.state / 'ordinary CLI child'
        argv = ['--state', str(unused), '--port', '0']
        with patch.dict(os.environ, {'DRAGONHYDRA_MANAGED_ENDPOINT': '0'}):
            self.assertEqual(MANAGED.managed_arguments(argv), argv)
        self.assertFalse(unused.exists())

    def test_explicit_port_and_information_commands_have_no_managed_side_effects(self):
        unused = self.state / 'explicit port child'
        for argv in (
            ['--state', str(unused), '--port', '18743'],
            ['--state', str(unused), '--port=18743'],
            ['--state', str(unused), '--port', '0', '--build-info'],
            ['--state', str(unused), '--port', '0', '--help'],
            ['--state', str(unused), '--port', '0', '-h'],
        ):
            with self.subTest(argv=argv):
                self.assertEqual(MANAGED.managed_arguments(argv), argv)
                self.assertFalse(unused.exists())

    def test_equals_and_duplicate_port_arguments_resolve_to_one_cached_port(self):
        original = ['--state=' + str(self.state), '--port=18743', '--port=0']
        result = MANAGED.managed_arguments(original)
        self.assertEqual(result[:-2], original)
        self.assertEqual(int(result[-1]), MANAGED.read_cache(self.state))
        self.assertEqual(MANAGED.managed_arguments(original), result)

    def test_invalid_cache_is_rejected_without_overwriting_committed_bytes(self):
        valid = {'schema_version': 1, 'host': '127.0.0.1', 'port': 18000}
        invalid = [
            [], None, {}, {**valid, 'port': True}, {**valid, 'port': '18000'},
            {**valid, 'port': 0}, {**valid, 'port': 65536}, {**valid, 'port': -1},
            {**valid, 'schema_version': True}, {**valid, 'schema_version': 2},
            {**valid, 'host': '0.0.0.0'}, {**valid, 'host': '::1'},
            {**valid, 'additional': 'not supported'},
        ]
        destination = self.state / MANAGED.CACHE
        for value in invalid:
            with self.subTest(value=value):
                before = json.dumps(value).encode()
                destination.write_bytes(before)
                with self.assertRaises(ValueError):
                    self.arguments()
                self.assertEqual(destination.read_bytes(), before)
        for before in (b'{invalid-json', b' ' * 1025):
            with self.subTest(raw_length=len(before)):
                destination.write_bytes(before)
                with self.assertRaises(ValueError):
                    self.arguments()
                self.assertEqual(destination.read_bytes(), before)

    def test_symlink_cache_and_lock_fail_without_touching_the_target(self):
        target = self.state / 'existing committed target.json'
        original = b'{"keep":"this committed UTF-8 payload: Fu\xc3\x9fball"}\n'
        target.write_bytes(original)
        destination = self.state / MANAGED.CACHE
        destination.symlink_to(target)
        with self.assertRaises(OSError):
            self.arguments()
        with self.assertRaises(ValueError):
            MANAGED.write_cache(self.state, 18000)
        self.assertTrue(destination.is_symlink())
        self.assertEqual(target.read_bytes(), original)
        destination.unlink()
        lock = self.state / 'managed-port.lock'
        lock.unlink(missing_ok=True)
        lock.symlink_to(target)
        with self.assertRaises(OSError):
            self.arguments()
        self.assertTrue(lock.is_symlink())
        self.assertEqual(target.read_bytes(), original)
        self.assertFalse(destination.exists())

    def test_atomic_replacement_failure_preserves_old_port_and_cleans_temporary(self):
        MANAGED.write_cache(self.state, 18000)
        destination = self.state / MANAGED.CACHE
        before = destination.read_bytes()
        with patch.object(MANAGED.os, 'replace', side_effect=OSError('injected replacement failure')):
            with self.assertRaisesRegex(OSError, 'injected replacement failure'):
                MANAGED.write_cache(self.state, 18001)
        self.assertEqual(destination.read_bytes(), before)
        self.assertEqual(MANAGED.read_cache(self.state), 18000)
        self.assertEqual(list(self.state.glob('.managed-port-*.tmp')), [])

    def test_cache_permission_is_private_when_filesystem_enforces_posix_modes(self):
        probe = self.state / 'permission probe'
        probe.write_bytes(b'not a credential')
        probe.chmod(0o600)
        actual = stat.S_IMODE(probe.stat().st_mode)
        if actual != 0o600:
            self.skipTest('Project filesystem reports ' + oct(actual) + '; native state permissions are covered by systemd installation acceptance.')
        MANAGED.write_cache(self.state, 18000)
        self.assertEqual(stat.S_IMODE((self.state / MANAGED.CACHE).stat().st_mode), 0o600)
        with MANAGED.locked_state(self.state):
            self.assertEqual(stat.S_IMODE((self.state / 'managed-port.lock').stat().st_mode), 0o600)

    def test_parallel_launchers_share_one_committed_selection(self):
        gate = self.state / 'start gate'
        code = (
            'import importlib.util,json,sys,time;from pathlib import Path;'
            's=importlib.util.spec_from_file_location("managed",sys.argv[1]);'
            'm=importlib.util.module_from_spec(s);s.loader.exec_module(m);'
            'gate=Path(sys.argv[3]);deadline=time.monotonic()+10;'
            '\nwhile not gate.exists():\n'
            ' if time.monotonic()>deadline:raise TimeoutError("start gate")\n'
            ' time.sleep(.01)\n'
            'print(json.dumps(m.managed_arguments(["--state",sys.argv[2],"--port","0"])))'
        )
        children = []
        try:
            for _ in range(6):
                children.append(subprocess.Popen(
                    [sys.executable, '-I', '-S', '-B', '-c', code, str(HELPER), str(self.state), str(gate)],
                    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                    env={**os.environ, 'DRAGONHYDRA_MANAGED_ENDPOINT': '1'},
                ))
            gate.write_bytes(b'go')
            results = []
            for child in children:
                stdout, stderr = child.communicate(timeout=20)
                self.assertEqual(child.returncode, 0, stderr)
                results.append(json.loads(stdout))
            self.assertEqual(len({result[-1] for result in results}), 1)
            self.assertEqual(int(results[0][-1]), MANAGED.read_cache(self.state))
            self.assertEqual(list(self.state.glob('.managed-port-*.tmp')), [])
        finally:
            for child in children:
                if child.poll() is None:
                    child.kill()
                child.communicate(timeout=5)

    def test_cached_port_is_not_silently_changed_when_another_listener_occupies_it(self):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(('127.0.0.1', 0))
            listener.listen(1)
            port = listener.getsockname()[1]
            MANAGED.write_cache(self.state, port)
            before = (self.state / MANAGED.CACHE).read_bytes()
            result = self.arguments()
            self.assertEqual(int(result[-1]), port)
            self.assertEqual((self.state / MANAGED.CACHE).read_bytes(), before)
            self.assertEqual(listener.getsockname()[1], port)


if __name__ == '__main__':
    if platform.system() != 'Linux':
        raise SystemExit('Run with the verified WSL Ubuntu-26.04 Python3.14 interpreter.')
    if EVIDENCE.exists():
        raise SystemExit('Evidence already exists; preserve this completed regression run.')
    EVIDENCE.mkdir(parents=True)
    started = datetime.now(timezone.utc).isoformat()
    helper_before = hashlib.sha256(HELPER.read_bytes()).hexdigest()
    stream = io.StringIO()
    result = unittest.TextTestRunner(stream=stream, verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ManagedEndpointTests))
    output = stream.getvalue()
    (EVIDENCE / 'unittest.log').write_text(output)
    report = {
        'schema_version': 1, 'started_at': started,
        'finished_at': datetime.now(timezone.utc).isoformat(),
        'environment': {'platform': platform.platform(), 'python': sys.version, 'executable': sys.executable},
        'command': [sys.executable, '-B', str(Path(__file__).relative_to(ROOT))],
        'tests_run': result.testsRun, 'failures': len(result.failures), 'errors': len(result.errors),
        'skipped': [{'test': str(test), 'reason': reason} for test, reason in result.skipped],
        'passed': result.wasSuccessful(), 'exit_code': 0 if result.wasSuccessful() else 1,
        'helper_sha256_before': helper_before,
        'helper_sha256_after': hashlib.sha256(HELPER.read_bytes()).hexdigest(),
        'harness_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'scope': 'Project scratch files and ephemeral loopback sockets only; no service/database/package mutations.',
    }
    (EVIDENCE / 'verification.json').write_text(json.dumps(report, indent=2) + '\n')
    print(output, end='')
    print(json.dumps(report, indent=2))
    raise SystemExit(report['exit_code'])
