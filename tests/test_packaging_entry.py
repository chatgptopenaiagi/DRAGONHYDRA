"""Packaging entrypoint checks without touching the operational database."""
import contextlib
import io
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

from dragonhydra import cli, packaging_entry, watch
from dragonhydra.cognition import runtime


ROOT = Path(__file__).resolve().parents[1]


class PackagingEntryTests(unittest.TestCase):
    def test_checkout_discovery_from_nested_workspace(self):
        previous=Path.cwd()
        self.addCleanup(os.chdir,previous)
        os.chdir(ROOT / 'runtime')
        with patch.dict(os.environ,{},clear=False):
            os.environ.pop('DRAGONHYDRA_HOME',None)
            self.assertEqual(packaging_entry.workspace(),ROOT)

    def test_read_only_score_and_explicit_workspace(self):
        previous=(cli.ROOT,cli.DEFAULT_DB,watch.ROOT,runtime.ROOT)
        def restore():
            cli.ROOT,cli.DEFAULT_DB,watch.ROOT,runtime.ROOT=previous
        self.addCleanup(restore)
        output=io.StringIO()
        with patch.dict(os.environ,{'DRAGONHYDRA_HOME':str(ROOT)},clear=False), \
             patch.object(sys,'argv',['dragon','score']), contextlib.redirect_stdout(output):
            result=packaging_entry.main()
        self.assertEqual(result,0)
        self.assertEqual(cli.ROOT,ROOT)
        self.assertEqual(watch.ROOT,ROOT)
        self.assertEqual(runtime.ROOT,ROOT)
        self.assertIn('SYNTHETIC CHRONOLOGICAL SCORING',output.getvalue())


if __name__=='__main__':
    unittest.main()
