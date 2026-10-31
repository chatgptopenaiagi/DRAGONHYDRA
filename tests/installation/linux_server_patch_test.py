"""Regression for the exact frozen Linux package's listener repair."""
from __future__ import annotations

import ast
import base64
import csv
import hashlib
import importlib.util
import io
from pathlib import Path
import platform
import socket
import tempfile
from types import SimpleNamespace
import unittest
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location('linux_server_patch', ROOT/'packaging/linux-native/server_patch.py')
PATCH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PATCH)
WHEEL = ROOT/'build/linux/prep-20261031-r2/dragonhydra-linux-dev-9f3d6e5ab108/dragonhydra-0.4.0a1-py3-none-any.whl'
SCRATCH = ROOT/'runtime/scratch/linux-server-patch'
SCRATCH.mkdir(parents=True, exist_ok=True)


class ListenerPatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='case-', dir=SCRATCH)
        self.addCleanup(self.temp.cleanup)
        self.site = Path(self.temp.name)
        self.wheel_sha = hashlib.sha256(WHEEL.read_bytes()).hexdigest()
        with ZipFile(WHEEL) as archive:
            for name in (PATCH.TARGET, PATCH.RECORD):
                path = self.site/name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(archive.read(name))

    def listener_factory(self):
        """Execute the actual transformed socket statements, not a copied fix."""
        PATCH.apply_server_patch(self.site)
        tree = ast.parse((self.site/PATCH.TARGET).read_text())
        main = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'main')
        start = next(index for index, node in enumerate(main.body)
                     if isinstance(node, ast.Assign) and isinstance(node.targets[0], ast.Name) and node.targets[0].id == 'listener')
        selected = main.body[start:start+3]
        self.assertIsInstance(selected[1], ast.If)
        self.assertIsInstance(selected[2], ast.Try)
        body = selected+[ast.Return(value=ast.Name(id='listener', ctx=ast.Load()))]
        fn = ast.FunctionDef(name='listener_factory', args=ast.arguments(posonlyargs=[], args=[ast.arg(arg='args')],
            kwonlyargs=[], kw_defaults=[], defaults=[]), body=body, decorator_list=[])
        module = ast.fix_missing_locations(ast.Module(body=[fn], type_ignores=[]))
        namespace = {'os': SimpleNamespace(name='posix'), 'sys': SimpleNamespace(platform='linux'), 'socket': socket}
        exec(compile(module, str(self.site/PATCH.TARGET), 'exec'), namespace)
        return namespace['listener_factory']

    def test_exact_patch_and_record_integrity(self):
        receipt = PATCH.apply_server_patch(self.site)
        body = (self.site/PATCH.TARGET).read_bytes()
        self.assertEqual(receipt['base_sha256'], PATCH.BASE_SERVER_SHA256)
        self.assertEqual(receipt['transformed_sha256'], hashlib.sha256(body).hexdigest())
        self.assertNotEqual(receipt['transformed_sha256'], receipt['base_sha256'])
        rows = list(csv.reader(io.StringIO((self.site/PATCH.RECORD).read_text())))
        entry = next(row for row in rows if row[0] == PATCH.TARGET)
        expected = 'sha256='+base64.urlsafe_b64encode(hashlib.sha256(body).digest()).decode().rstrip('=')
        self.assertEqual(entry, [PATCH.TARGET, expected, str(len(body))])
        self.assertEqual(hashlib.sha256(WHEEL.read_bytes()).hexdigest(), self.wheel_sha)

    def test_source_drift_rejected_without_record_or_source_write(self):
        target = self.site/PATCH.TARGET
        target.write_bytes(target.read_bytes()+b'\n# newer unrelated source\n')
        before = {p: p.read_bytes() for p in (target, self.site/PATCH.RECORD)}
        with self.assertRaisesRegex(ValueError, 'Unexpected frozen'):
            PATCH.apply_server_patch(self.site)
        for path, body in before.items():
            self.assertEqual(path.read_bytes(), body)

    def test_inconsistent_record_rejected_before_writing_source(self):
        target, record = self.site/PATCH.TARGET, self.site/PATCH.RECORD
        before = target.read_bytes()
        record.write_bytes(record.read_bytes().replace(b'dragonhydra/server.py,sha256=', b'dragonhydra/server.py,sha512=', 1))
        invalid = record.read_bytes()
        with self.assertRaisesRegex(ValueError, 'RECORD'):
            PATCH.apply_server_patch(self.site)
        self.assertEqual(target.read_bytes(), before)
        self.assertEqual(record.read_bytes(), invalid)

    def test_windows_exclusive_branch_is_unchanged_and_no_reuseport(self):
        original = (self.site/PATCH.TARGET).read_text()
        PATCH.apply_server_patch(self.site)
        transformed = (self.site/PATCH.TARGET).read_text()
        def exclusive(text):
            tree = ast.parse(text)
            for node in ast.walk(tree):
                if isinstance(node, ast.If) and ast.unparse(node.test) == "os.name == 'nt'":
                    if any('SO_EXCLUSIVEADDRUSE' in ast.unparse(item) for item in node.body):
                        return ast.dump(ast.Module(body=node.body, type_ignores=[]))
            self.fail('Windows exclusive branch absent')
        self.assertEqual(exclusive(original), exclusive(transformed))
        tree = ast.parse(transformed)
        self.assertFalse(any(isinstance(node, ast.Attribute) and node.attr == 'SO_REUSEPORT' for node in ast.walk(tree)))

    @unittest.skipUnless(platform.system() == 'Linux', 'Actual Linux socket semantics required')
    def test_graceful_connected_listener_rebinds_immediately(self):
        factory = self.listener_factory()
        first = factory(SimpleNamespace(host='127.0.0.1', port=0))
        self.addCleanup(first.close)
        port = first.getsockname()[1]
        first.settimeout(3)
        first.listen(1)
        with socket.create_connection(('127.0.0.1', port), timeout=3) as client:
            accepted, _ = first.accept()
            with accepted:
                accepted.sendall(b'HTTP/1.0 200 OK\r\nContent-Length: 2\r\n\r\nOK')
                accepted.shutdown(socket.SHUT_WR)
                while client.recv(4096):
                    pass
        first.close()
        replacement = factory(SimpleNamespace(host='127.0.0.1', port=port))
        self.addCleanup(replacement.close)
        replacement.listen(1)
        self.assertEqual(replacement.getsockname(), ('127.0.0.1', port))

    @unittest.skipUnless(platform.system() == 'Linux', 'Actual Linux socket semantics required')
    def test_live_listener_conflict_rejected_with_original_errno(self):
        factory = self.listener_factory()
        first = factory(SimpleNamespace(host='127.0.0.1', port=0))
        self.addCleanup(first.close)
        first.listen(1)
        port = first.getsockname()[1]
        with self.assertRaises(SystemExit) as failure:
            factory(SimpleNamespace(host='127.0.0.1', port=port))
        import errno
        self.assertIn('[errno='+str(errno.EADDRINUSE)+']', str(failure.exception))
        with socket.create_connection(('127.0.0.1', port), timeout=3):
            pass
        self.assertEqual(first.getsockname()[1], port)


if __name__ == '__main__':
    unittest.main(verbosity=2)
