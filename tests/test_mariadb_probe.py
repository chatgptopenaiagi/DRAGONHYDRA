import unittest

from dragonhydra.integration.mariadb_probe import MariaDBJoomlaProbe, run_probe


class LiveMariaDBTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = run_probe()

    def test_live_select_aggregates(self):
        counts = self.result["aggregates"]
        self.assertGreater(counts["table_count"], 0)
        self.assertGreater(counts["extension_count"], 0)
        self.assertGreaterEqual(counts["published_content_count"], 0)
        self.assertGreaterEqual(counts["user_count"], 0)
        self.assertEqual(set(counts), {"table_count", "extension_count", "published_content_count", "user_count"})

    def test_readonly_account_write_rejected_by_privileges(self):
        self.assertTrue(self.result["write_rejected_with_error_1142"])
        self.assertTrue(self.result["select_only_grants"])

    def test_zero_row_probe_did_not_change_aggregate_counts(self):
        self.assertTrue(self.result["aggregate_counts_unchanged"])

    def test_uses_dedicated_identity(self):
        self.assertEqual(self.result["account"], "dragonhydra_probe@localhost")
        self.assertTrue(self.result["passed"])


if __name__ == "__main__":
    unittest.main()
