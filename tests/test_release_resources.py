"""Packaging contracts that prevent absent or drifting installed resources."""
import hashlib
import json
from pathlib import Path
import unittest

from dragonhydra import build_meta, product

ROOT = Path(__file__).resolve().parents[1]
RESOURCES = ROOT / 'src' / 'dragonhydra' / 'resources'


class ReleaseResourcesTests(unittest.TestCase):
    def test_dashboard_mirror_is_exact(self):
        for name in ('app.js', 'index.html', 'style.css'):
            self.assertEqual((ROOT/'client/desktop/web'/name).read_bytes(), (RESOURCES/'web'/name).read_bytes())

    def test_vetted_public_samples_match_original_receipts(self):
        for path in (RESOURCES/'data/raw').glob('*.receipt.json'):
            receipt = json.loads(path.read_text(encoding='utf-8-sig'))
            data = path.with_name(path.name.removesuffix('.receipt.json')).read_bytes()
            self.assertEqual(hashlib.sha256(data).hexdigest(), receipt['sha256'])
            self.assertEqual(len(data), receipt['bytes'])
            self.assertTrue(receipt['source_url'].startswith(('https://raw.githubusercontent.com/openfootball/', 'https://www.football-data.co.uk/')))

    def test_version_matrix_matches_python_and_service(self):
        mapping = json.loads((ROOT/'packaging/release/version.json').read_text())
        self.assertEqual(product.VERSION, mapping['product_version'])
        self.assertEqual(build_meta.PYTHON_VERSION, mapping['python_version'])
        self.assertEqual(build_meta.info()['api_namespace'], mapping['api_namespace'])
