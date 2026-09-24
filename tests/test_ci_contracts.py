"""Portable comparison of a schema published for the canonical Windows lab."""

import copy
import json
import unittest

from dragonhydra.config import PROJECT_ROOT
from dragonhydra.handoff.contracts import SCHEMA


class PortablePublishedSchemaTests(unittest.TestCase):
    def test_published_schema_matches_except_explicit_deployment_root(self):
        published = json.loads(
            (PROJECT_ROOT / "config/browser-handoff-envelope.schema.json").read_text(encoding="utf-8")
        )
        # The published Desktop contract belongs to the owner's Windows lab.
        # Runtime validation must still bind every envelope to its actual root.
        self.assertEqual(published["properties"]["project_root"], {
            "const": r"C:\xampp\DRAGONHYDRA", "type": "string",
        })
        self.assertEqual(SCHEMA["properties"]["project_root"], {
            "const": str(PROJECT_ROOT), "type": "string",
        })
        relocated = copy.deepcopy(SCHEMA)
        relocated["properties"]["project_root"]["const"] = r"C:\xampp\DRAGONHYDRA"
        self.assertEqual(relocated, published)
