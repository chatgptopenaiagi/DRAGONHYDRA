"""Contract checks independent of drivers, services, credentials and database state."""

from dataclasses import FrozenInstanceError, asdict, replace
from datetime import datetime, timezone
import unittest

from dragonhydra.storage.contracts import (
    CapabilityReport, ConnectionDiagnostic, DatabaseEngineIdentity,
    DatabaseHealth, ReadOnlyQueryResult,
)


class DatabaseContractTests(unittest.TestCase):
    def setUp(self):
        self.identity = DatabaseEngineIdentity(
            "mariadb", "10.4.32", "127.0.0.1", 3306, "joomla_codex_lab",
            "PyMySQL", "1.2.3",
        )
        self.health = DatabaseHealth("healthy", True, 2.5, datetime.now(timezone.utc))
        self.result = ReadOnlyQueryResult(
            "controlled_joomla_aggregates", (("table_count", 76), ("published_count", 0)),
            "joomla_codex_lab",
        )
        self.diagnostic = ConnectionDiagnostic("tcp", None, None, ("TLS_STATE_NOT_MEASURED",))
        self.report = CapabilityReport(
            self.identity, self.health, True, False, True, True,
            self.result, self.diagnostic,
        )

    def test_result_supports_zero_counts_without_losing_provenance(self):
        self.assertEqual(dict(self.result.counts)["published_count"], 0)
        self.assertEqual(self.result.source_database, self.identity.database)

    def test_all_report_contracts_are_frozen(self):
        for record, attribute in (
            (self.identity, "engine"), (self.health, "status"),
            (self.result, "operation"), (self.diagnostic, "transport"),
            (self.report, "read"),
        ):
            with self.subTest(record=type(record).__name__), self.assertRaises(FrozenInstanceError):
                setattr(record, attribute, None)

    def test_ports_reject_boolean_fraction_and_out_of_range(self):
        for port in (True, 0, 65536, 1433.5, "1433"):
            with self.subTest(port=port), self.assertRaises(ValueError):
                replace(self.identity, port=port)

    def test_endpoint_and_driver_identity_must_be_explicit(self):
        for field in ("engine", "version", "host", "database", "driver", "driver_version"):
            with self.subTest(field=field), self.assertRaises(ValueError):
                replace(self.identity, **{field: " "})

    def test_unknown_engine_rejected(self):
        with self.assertRaises(ValueError):
            replace(self.identity, engine="unbounded")

    def test_latency_is_finite_and_nonnegative(self):
        for latency in (-1, float("inf"), float("nan"), True, "fast"):
            with self.subTest(latency=latency), self.assertRaises(ValueError):
                replace(self.health, latency_ms=latency)
        self.assertEqual(replace(self.health, latency_ms=0).latency_ms, 0)

    def test_measurement_requires_timezone(self):
        for measured_at in (datetime(2026, 9, 24), "2026-09-24T00:00:00Z"):
            with self.subTest(measured_at=measured_at), self.assertRaises(ValueError):
                replace(self.health, checked_at=measured_at)

    def test_health_requires_real_boolean_and_consistent_status(self):
        for change in ({"connected": 1}, {"connected": False}, {"status": "assumed"}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                replace(self.health, **change)

    def test_counts_reject_duplicates_negatives_boolean_and_mutability(self):
        for counts in (
            (), [("count", 1)], (["count", 1],), (("count", -1),),
            (("count", True),), (("count", 1.5),),
            (("count", 1), ("count", 2)), (("", 0),),
        ):
            with self.subTest(counts=counts), self.assertRaises(ValueError):
                replace(self.result, counts=counts)

    def test_unknown_tls_state_is_not_claimed_unencrypted(self):
        self.assertIsNone(self.report.diagnostic.encrypted)
        self.assertIsNone(self.report.diagnostic.certificate_validated)

    def test_validated_certificate_requires_verified_encryption(self):
        for encrypted in (False, None):
            with self.subTest(encrypted=encrypted), self.assertRaises(ValueError):
                replace(self.diagnostic, encrypted=encrypted, certificate_validated=True)
        self.assertTrue(replace(self.diagnostic, encrypted=True, certificate_validated=True).encrypted)

    def test_diagnostic_rejects_mutable_or_duplicate_reasons_and_nonbooleans(self):
        for changes in (
            {"reason_codes": ["UNVERIFIED"]}, {"reason_codes": ("A", "A")},
            {"reason_codes": ("",)}, {"encrypted": 1}, {"certificate_validated": "yes"},
        ):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(self.diagnostic, **changes)

    def test_cross_database_result_cannot_be_attributed_to_endpoint(self):
        with self.assertRaises(ValueError):
            replace(self.report, result=replace(self.result, source_database="other_database"))

    def test_denied_write_cannot_claim_write_capability(self):
        with self.assertRaises(ValueError):
            replace(self.report, write=True)

    def test_capabilities_require_verified_connection(self):
        with self.assertRaises(ValueError):
            replace(self.report, health=replace(self.health, status="unavailable", connected=False))

    def test_capability_flags_reject_truthy_values(self):
        for field in ("read", "write", "transaction", "write_rejected"):
            with self.subTest(field=field), self.assertRaises(ValueError):
                replace(self.report, **{field: 1})

    def test_report_requires_nested_contract_types(self):
        for field in ("identity", "health", "result", "diagnostic"):
            with self.subTest(field=field), self.assertRaises(ValueError):
                replace(self.report, **{field: {}})

    def test_report_serializes_without_driver_or_credential_objects(self):
        report = asdict(self.report)
        self.assertEqual(set(report), {
            "identity", "health", "read", "write", "transaction", "write_rejected",
            "result", "diagnostic",
        })
        self.assertEqual(report["identity"]["port"], 3306)
        self.assertNotIn("password", repr(report).lower())


if __name__ == "__main__":
    unittest.main()
