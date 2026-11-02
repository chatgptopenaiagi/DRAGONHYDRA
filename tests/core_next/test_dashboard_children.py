"""Actual dashboard child normalization and standings render regressions, no browser claim."""
import json
from pathlib import Path
import subprocess
import unittest

ROOT = Path(__file__).resolve().parents[2]
NODE = Path('C:/Program Files/nodejs/node.exe')
FIXTURE = ROOT / 'tests/core_next/dashboard_children.cjs'
ASSETS = [ROOT/'src/dragonhydra/resources/web/app.js', ROOT/'client/desktop/web/app.js']


@unittest.skipUnless(NODE.is_file(), 'Existing recorded Node runtime required')
class DashboardChildrenTests(unittest.TestCase):
    def test_real_server_and_desktop_renderers_preserve_dom_children_and_zeros(self):
        for asset in ASSETS:
            with self.subTest(asset=asset.relative_to(ROOT).as_posix()):
                run = subprocess.run([str(NODE),str(FIXTURE),str(asset)],capture_output=True,text=True,timeout=15)
                report=json.loads(run.stdout)
                self.assertEqual(run.returncode,0,report)
                self.assertTrue(report['passed'])
                self.assertEqual(len(report['checks']),6)

    def test_browser_and_packaged_desktop_share_identical_dashboard_source(self):
        self.assertEqual(ASSETS[0].read_bytes(),ASSETS[1].read_bytes())


if __name__=='__main__': unittest.main()
