"""Execute the actual server listener statements with real owned loopback sockets."""
import ast
import errno
import os
from pathlib import Path
import socket
import sys
from types import SimpleNamespace
import unittest


class ListenerTests(unittest.TestCase):
    def factory(self):
        from dragonhydra import server
        source = Path(server.__file__)
        tree = ast.parse(source.read_text())
        main = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'main')
        index = next(i for i, node in enumerate(main.body) if isinstance(node, ast.Assign)
                     and isinstance(node.targets[0], ast.Name) and node.targets[0].id == 'listener')
        body = main.body[index:index+3]
        self.assertIsInstance(body[1], ast.If)
        self.assertIsInstance(body[2], ast.Try)
        body = body+[ast.Return(value=ast.Name(id='listener', ctx=ast.Load()))]
        function = ast.FunctionDef(name='factory', args=ast.arguments(posonlyargs=[], args=[ast.arg(arg='args')],
            kwonlyargs=[], kw_defaults=[], defaults=[]), body=body, decorator_list=[])
        module = ast.fix_missing_locations(ast.Module(body=[function], type_ignores=[]))
        namespace = {'os': os, 'sys': sys, 'socket': socket}
        exec(compile(module, str(source), 'exec'), namespace)
        return namespace['factory']

    def test_active_listener_is_not_taken_over_and_bind_failure_retains_errno(self):
        factory = self.factory()
        owner = factory(SimpleNamespace(host='127.0.0.1', port=0))
        self.addCleanup(owner.close)
        owner.listen(1)
        with self.assertRaises(SystemExit) as caught:
            factory(SimpleNamespace(host='127.0.0.1', port=owner.getsockname()[1]))
        self.assertIn('[errno=', str(caught.exception))
        self.assertIn('no unrelated service was stopped', str(caught.exception))
        with socket.create_connection(owner.getsockname(), timeout=2):
            accepted, _ = owner.accept()
            accepted.close()

    @unittest.skipUnless(sys.platform.startswith('linux'), 'Actual Linux TIME_WAIT semantics')
    def test_connected_listener_can_rebind_same_endpoint_after_graceful_close(self):
        factory = self.factory()
        first = factory(SimpleNamespace(host='127.0.0.1', port=0))
        self.addCleanup(first.close)
        endpoint = first.getsockname()
        first.listen(1)
        with socket.create_connection(endpoint, timeout=2) as client:
            accepted, _ = first.accept()
            accepted.shutdown(socket.SHUT_WR)
            accepted.close()
            self.assertEqual(client.recv(1), b'')
        first.close()
        replacement = factory(SimpleNamespace(host=endpoint[0], port=endpoint[1]))
        self.addCleanup(replacement.close)
        replacement.listen(1)
        self.assertEqual(replacement.getsockname(), endpoint)
