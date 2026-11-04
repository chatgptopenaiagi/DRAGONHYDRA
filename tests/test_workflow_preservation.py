"""Actual disposable SQLite fixtures; no application/server/provider/job calls."""
import ast
from contextlib import closing
import hashlib
import json
from pathlib import Path
import sqlite3
import tempfile
import threading
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parent / "installation"))
import workflow_preservation as w

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "src/dragonhydra"
JOBS = {"forecast": "2" * 32, "evaluation": "3" * 32}
TARGET = "4" * 64
NAMES = ("frequency", "poisson_goals", "elo", "recency", "ensemble")
NOW = "2026-11-03T10:00:00.000000Z"


def frozen_tree(relative, expected, fixture=None):
    raw = (HERE / fixture if fixture else SOURCE / relative).read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected:
        raise AssertionError("Frozen reference source hash mismatch")
    return ast.parse(raw)


def script_constant(tree, contains):
    matches = [node.args[0].value for node in ast.walk(tree)
               if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
               and node.func.attr == "executescript" and node.args
               and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)
               and contains in node.args[0].value]
    assert len(matches) == 1
    return matches[0]


MARKET_TREE = frozen_tree("market_store.py", "12c31071ef80a8a9422d68a05bbf09978327a4250c525cb8ee7791cd7190ffbc")
MEMORY_TREE = frozen_tree("cognition/memory.py", "d068811c07ea960552800ca8cdee221799813e975bf566e22f65f2f5430f8b8f")
JOBS_TREE = frozen_tree("jobs.py", "bccb8f08caf58df333942bcc5c527def1a18c1acd09cc01f6dadb95565c16296",
                        fixture="fixtures/forecast-preservation/jobs-ed78.py.txt")
MARKET_SQL = script_constant(MARKET_TREE, "CREATE TABLE IF NOT EXISTS acquisitions")
JOBS_SQL = script_constant(JOBS_TREE, "CREATE TABLE IF NOT EXISTS product_jobs")
COGNITIVE_SQL = next(node.value.value for node in MEMORY_TREE.body
                     if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "SCHEMA_SQL" for t in node.targets))
REFERENCE = w.canonical_schema_from_sql(MARKET_SQL, COGNITIVE_SQL)


class CurrentJobSchemaReference(unittest.TestCase):
    def test_current_schema_matches_original_pinned_forecast_reference(self):
        current = ast.parse((SOURCE / "jobs.py").read_bytes())
        self.assertEqual(script_constant(current, "CREATE TABLE IF NOT EXISTS product_jobs"), JOBS_SQL)


def payload_record(kind, name):
    payload = {"run_id": JOBS["forecast"], "model_name": name, "model_version": "football-models/1",
               "input_evidence_ids": ["retained-fixture:0"], "data_origin": "model_state" if kind == "model" else "model_estimate"}
    if kind == "model":
        payload.update(parameters={"workflow": {"match_id": TARGET}, "result": {"available": True}},
                       configuration={"synthetic_fixture": True}, data_cutoff=NOW)
    return payload


def insert_record(db, kind, payload):
    natural = payload["run_id"] + ":" + payload["model_name"]
    raw = w.canonical(payload)
    fingerprint = hashlib.sha256(raw).hexdigest()
    identifier = kind + ":" + hashlib.sha256(w.canonical([kind, natural, fingerprint])).hexdigest()
    db.execute("INSERT INTO cognitive_records VALUES(?,?,?,?,?)", (kind, identifier, natural, fingerprint, raw.decode()))
    db.execute("INSERT INTO cognitive_receipts VALUES(?,?,?,?)", (identifier, NOW, NOW, NOW))
    return {**payload, "record_id": identifier, "record_content_hash": fingerprint,
            "received_at": NOW, "persisted_at": NOW, "usable_at": NOW}


def baseline(path, existing_memory=False):
    with closing(sqlite3.connect(path)) as db:
        db.executescript(JOBS_SQL)
        db.executescript("""
        CREATE TABLE raw_sources(source_hash TEXT PRIMARY KEY, bytes BLOB NOT NULL);
        CREATE TABLE public_fixture_records(id TEXT PRIMARY KEY,home TEXT,away TEXT,home_goals INTEGER,away_goals INTEGER,marker BLOB,nullable TEXT,numeric);
        CREATE TABLE connector_settings(provider TEXT PRIMARY KEY,config TEXT,interval_seconds INTEGER,next_due REAL);
        CREATE TABLE connector_observations(seq INTEGER PRIMARY KEY AUTOINCREMENT, record TEXT);
        """)
        db.executemany("INSERT INTO raw_sources VALUES(?,?)", [("a" * 64, b"retained source A"), ("b" * 64, b"retained source B")])
        db.executemany("INSERT INTO public_fixture_records VALUES(?,?,?,?,?,?,?,?)",
                       [(str(i), "Home" + str(i), "Away", 0 if i % 2 else None, 0, b"\x00\xff", None, 1) for i in range(760)])
        db.execute("INSERT INTO connector_settings VALUES(?,?,?,?)", ("api-football", '{"fixture_only":"FAKE_SECRET_CANARY"}', 0, 0.0))
        db.execute("INSERT INTO connector_observations(record) VALUES(?)", ("unchanged",))
        db.execute("INSERT INTO product_jobs(id,owner,kind,payload,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                   ("1" * 32, "local:owner", "import_public", "{}", "succeeded", NOW, NOW))
        for n in range(6):
            db.execute("INSERT INTO product_updates(topic,payload,committed_at) VALUES(?,?,?)", ("baseline", json.dumps({"step": n}), NOW))
        db.executemany("INSERT INTO product_bridge_nonces VALUES(?,?)", [("fixture-nonce-" + str(i), 1.0) for i in range(7)])
        if existing_memory:
            db.executescript(MARKET_SQL)
            db.executescript(COGNITIVE_SQL)
            old = payload_record("model", "old-model")
            old["run_id"] = "0" * 32
            insert_record(db, "model", old)
        db.commit()


def append_workflow(path):
    with closing(sqlite3.connect(path)) as db:
        db.executescript(MARKET_SQL)
        db.executescript(COGNITIVE_SQL)
        models, predictions = [], []
        for name in NAMES:
            model = insert_record(db, "model", payload_record("model", name))
            prediction = payload_record("prediction", name)
            prediction["model_run_id"] = model["record_id"]
            prediction["probabilities"] = {"home": "0.4", "draw": "0.3", "away": "0.3"}
            models.append(model)
            predictions.append(insert_record(db, "prediction", prediction))
        results = {"forecast": {"status": "persisted", "available": True, "model_runs": models, "predictions": predictions},
                   "evaluation": {"status": "pending", "available": False, "reason": "LATER_RETAINED_OUTCOME_UNAVAILABLE"}}
        for kind, identifier in JOBS.items():
            db.execute("INSERT INTO product_jobs(id,owner,kind,payload,status,result,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                       (identifier, "local:owner", kind, json.dumps({"match_id": TARGET}), "succeeded", json.dumps(results[kind]), NOW, NOW))
            for status in ("queued", "running", "succeeded"):
                db.execute("INSERT INTO product_updates(topic,payload,committed_at) VALUES(?,?,?)", ("job", json.dumps({"id": identifier, "status": status}), NOW))
            db.execute("INSERT INTO product_updates(topic,payload,committed_at) VALUES(?,?,?)", ("data", json.dumps({"job_id": identifier, "kind": kind}), NOW))
        db.executemany("INSERT INTO product_bridge_nonces VALUES(?,?)", [("fixture-new-nonce-" + str(i), 2.0) for i in range(7)])
        db.commit()
    return [row["record_id"] for row in models + predictions]


class PreservationTests(unittest.TestCase):
    def setUp(self):
        scratch = HERE / "scratch"
        scratch.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(prefix="sqlite-fixture-", dir=scratch)
        self.root = Path(self.temp.name).resolve()
        self.assertEqual(self.root.parent, scratch.resolve())
        self.before, self.after = self.root / "before.sqlite3", self.root / "after.sqlite3"
        baseline(self.before)
        self.copy(self.before, self.after)
        self.ids = append_workflow(self.after)

    def tearDown(self):
        self.assertEqual(self.root.parent, (HERE / "scratch").resolve())
        self.temp.cleanup()

    def copy(self, source, target):
        with closing(sqlite3.connect(source.as_uri() + "?mode=ro", uri=True)) as a, closing(sqlite3.connect(target)) as b:
            a.backup(b)

    def audit(self):
        return w.audit_workflow_preservation(self.before, self.after, approved_job_ids=JOBS,
                                              approved_cognitive_ids=self.ids, expected_schema=REFERENCE)

    def mutate(self, sql, args=()):
        with closing(sqlite3.connect(self.after)) as db:
            db.execute(sql, args)
            db.commit()

    def codes(self, report):
        return {item["code"] for item in report["errors"]}

    def test_original_first_use_six_tables_twenty_seven_objects(self):
        report = self.audit()
        self.assertTrue(report["passed"], report)
        self.assertEqual(report["counts"]["added_schema_objects"], 27)
        self.assertEqual(report["counts"]["new_cognitive_records"], 10)
        self.assertEqual(report["counts"]["new_cognitive_receipts"], 10)
        self.assertEqual(report["counts"]["new_events"], 8)
        self.assertEqual(report["counts"]["auth_bookkeeping"]["product_bridge_nonces"], {"before": 7, "after": 14})

    def test_existing_store_and_old_records_preserved(self):
        self.before.unlink()
        self.after.unlink()
        baseline(self.before, existing_memory=True)
        self.copy(self.before, self.after)
        self.ids = append_workflow(self.after)
        report = self.audit()
        self.assertTrue(report["passed"], report)
        self.assertEqual(report["counts"]["added_schema_objects"], 0)

    def test_idempotent_existing_run_has_no_new_rows_or_events(self):
        self.before.unlink()
        self.copy(self.after, self.before)
        report = self.audit()
        self.assertTrue(report["passed"], report)
        self.assertEqual(report["counts"]["new_jobs"], 0)
        self.assertEqual(report["counts"]["new_events"], 0)

    def test_retained_field_change_detected_without_values(self):
        self.mutate("UPDATE public_fixture_records SET home=? WHERE id='0'", ("FAKE_SECRET_CANARY",))
        report = self.audit()
        self.assertFalse(report["passed"])
        self.assertIn({"code": "PROTECTED_ROWS_CHANGED", "table": "public_fixture_records", "fields": ["home"]}, report["errors"])
        self.assertNotIn("FAKE_SECRET_CANARY", json.dumps(report))

    def test_raw_blob_mutation_detected_even_if_lengths_equal(self):
        # The new immutable triggers prevent UPDATE. A simulated foreign writer
        # has to remove one, and both its DDL and row mutation must be rejected.
        self.mutate("DROP TRIGGER raw_immutable_update")
        self.mutate("UPDATE raw_sources SET bytes=? WHERE source_hash=?", (b"retained source Z", "a" * 64))
        report = self.audit()
        self.assertIn("PROTECTED_ROWS_CHANGED", self.codes(report))
        self.assertIn("CANONICAL_FIRST_USE_SCHEMA_MISMATCH", self.codes(report))

    def test_provider_configuration_change_detected(self):
        self.mutate("UPDATE connector_settings SET config=?", ('{"private":"FAKE_SECRET_CANARY"}',))
        report = self.audit()
        self.assertIn("PROTECTED_ROWS_CHANGED", self.codes(report))
        self.assertNotIn("FAKE_SECRET_CANARY", json.dumps(report))

    def test_other_internal_sequence_row_is_not_exempt(self):
        self.mutate("UPDATE sqlite_sequence SET seq=100 WHERE name='connector_observations'")
        self.assertIn("OTHER_SEQUENCE_ROW_CHANGED", self.codes(self.audit()))

    def test_event_sequence_must_equal_maximum(self):
        self.mutate("UPDATE sqlite_sequence SET seq=100 WHERE name='product_updates'")
        self.assertIn("PRODUCT_UPDATES_SEQUENCE_MAX_MISMATCH", self.codes(self.audit()))

    def test_unrelated_ddl_is_rejected(self):
        self.mutate("CREATE TABLE unknown_extension(id INTEGER)")
        self.assertIn("UNAPPROVED_SCHEMA_ADDITION", self.codes(self.audit()))

    def test_replaced_canonical_trigger_is_rejected(self):
        self.mutate("DROP TRIGGER raw_immutable_update")
        self.mutate("CREATE TRIGGER raw_immutable_update BEFORE UPDATE ON raw_sources BEGIN SELECT 1; END")
        self.assertIn("CANONICAL_FIRST_USE_SCHEMA_MISMATCH", self.codes(self.audit()))

    def test_preexisting_ddl_cannot_be_replaced(self):
        self.mutate("ALTER TABLE connector_settings ADD COLUMN foreign_column TEXT")
        self.assertIn("PREEXISTING_SCHEMA_OBJECT_CHANGED", self.codes(self.audit()))

    def test_old_job_mutation_is_rejected(self):
        self.mutate("UPDATE product_jobs SET progress=99 WHERE id=?", ("1" * 32,))
        self.assertIn("OLD_WORKFLOW_ROW_CHANGED", self.codes(self.audit()))

    def test_old_cognitive_payload_cannot_change_under_valid_schema(self):
        self.before.unlink()
        self.after.unlink()
        baseline(self.before, existing_memory=True)
        self.copy(self.before, self.after)
        self.ids = append_workflow(self.after)
        self.mutate("DROP TRIGGER cognitive_records_no_update")
        self.mutate("UPDATE cognitive_records SET payload='{}' WHERE natural_key=?", ("0" * 32 + ":old-model",))
        self.mutate(REFERENCE["trigger:cognitive_records_no_update"]["sql"])
        self.assertIn("OLD_WORKFLOW_ROW_CHANGED", self.codes(self.audit()))

    def test_old_event_mutation_is_rejected(self):
        self.mutate("UPDATE product_updates SET payload='{}' WHERE seq=1")
        self.assertIn("OLD_WORKFLOW_ROW_CHANGED", self.codes(self.audit()))

    def test_unowned_job_is_rejected(self):
        self.mutate("INSERT INTO product_jobs(id,owner,kind,payload,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?)",
                    ("8" * 32, "other", "forecast", "{}", "succeeded", NOW, NOW))
        self.assertIn("UNAPPROVED_JOB_DELTA", self.codes(self.audit()))

    def test_unowned_cognitive_row_is_rejected(self):
        with closing(sqlite3.connect(self.after)) as db:
            extra = payload_record("model", "unowned")
            insert_record(db, "model", extra)
            db.commit()
        self.assertIn("UNAPPROVED_COGNITIVE_DELTA", self.codes(self.audit()))

    def test_new_auxiliary_table_must_be_empty(self):
        self.mutate("INSERT INTO acquisitions VALUES(?,?,?,?,?,?)", ("x", "y", "f", "a" * 64, "{}", None))
        self.assertIn("UNAPPROVED_NEW_TABLE_DATA", self.codes(self.audit()))

    def test_approved_cognitive_hash_cannot_hide_payload_tampering(self):
        self.mutate("DROP TRIGGER cognitive_records_no_update")
        self.mutate("UPDATE cognitive_records SET payload='{}' WHERE record_id=?", (self.ids[0],))
        self.assertIn("COGNITIVE_CONTENT_HASH_BINDING_INVALID", self.codes(self.audit()))

    def test_receipt_must_equal_official_job_readback(self):
        self.mutate("DROP TRIGGER cognitive_receipts_no_update")
        self.mutate("UPDATE cognitive_receipts SET usable_at='2026-11-03T11:00:00Z' WHERE record_id=?", (self.ids[0],))
        self.assertIn("COGNITIVE_JOB_RESULT_RECEIPT_MISMATCH", self.codes(self.audit()))

    def test_record_bindings_match_exact_frozen_official_pure_functions(self):
        # Extract only these two pure functions, not a module import or schema/
        # application operation. The entire source file's SHA is pinned above.
        funcs = [node for node in MEMORY_TREE.body if isinstance(node, ast.FunctionDef) and node.name in {"_canonical", "_hash"}]
        self.assertEqual(len(funcs), 2)
        namespace = {"json": json, "hashlib": hashlib}
        exec(compile(ast.Module(body=funcs, type_ignores=[]), "frozen-memory-pure-functions", "exec"), namespace)
        with closing(sqlite3.connect(self.after.as_uri() + "?mode=ro", uri=True)) as db:
            for kind, identifier, natural, fingerprint, payload in db.execute("SELECT * FROM cognitive_records"):
                raw = namespace["_canonical"](json.loads(payload))
                self.assertEqual(namespace["_hash"](raw), fingerprint)
                self.assertEqual(kind + ":" + namespace["_hash"](namespace["_canonical"]([kind, natural, fingerprint])), identifier)

    def test_event_not_linked_to_approved_job_rejected(self):
        self.mutate("UPDATE product_updates SET payload=? WHERE seq=7", (json.dumps({"id": "9" * 32, "status": "queued"}),))
        self.assertIn("UNAPPROVED_EVENT_DELTA", self.codes(self.audit()))

    def test_actual_integer_real_storage_change_is_detected(self):
        self.mutate("UPDATE public_fixture_records SET numeric=CAST(1 AS REAL) WHERE id='0'")
        with closing(sqlite3.connect(self.after)) as db:
            self.assertEqual(db.execute("SELECT typeof(numeric) FROM public_fixture_records WHERE id='0'").fetchone()[0], "real")
        self.assertIn("PROTECTED_ROWS_CHANGED", self.codes(self.audit()))

    def test_page_growth_and_freelist_do_not_fail_logical_preservation(self):
        self.mutate("CREATE TABLE temporary_pages(data BLOB)")
        self.mutate("INSERT INTO temporary_pages VALUES(zeroblob(300000))")
        self.mutate("DROP TABLE temporary_pages")
        report = self.audit()
        self.assertTrue(report["passed"], report)

    def test_row_insertion_order_does_not_change_logical_comparison(self):
        # Rebuild the protected table in reverse order with precisely the same
        # stored schema SQL and values, preserving its semantic data and types.
        with closing(sqlite3.connect(self.after)) as db:
            ddl = db.execute("SELECT sql FROM sqlite_master WHERE name='public_fixture_records'").fetchone()[0]
            rows = db.execute("SELECT * FROM public_fixture_records ORDER BY id DESC").fetchall()
            db.execute("DROP TABLE public_fixture_records")
            db.execute(ddl)
            db.executemany("INSERT INTO public_fixture_records VALUES(?,?,?,?,?,?,?,?)", rows)
            db.commit()
        self.assertTrue(self.audit()["passed"])

    def test_concurrent_protected_writer_in_workflow_window_detected(self):
        # Simulate a second writer between forecast completion and the after
        # snapshot. Snapshot isolation alone must not exempt its retained change.
        def writer():
            with closing(sqlite3.connect(self.after)) as db:
                db.execute("UPDATE public_fixture_records SET away_goals=2 WHERE id='1'")
                db.commit()
        worker = threading.Thread(target=writer)
        worker.start()
        worker.join(timeout=5)
        self.assertFalse(worker.is_alive())
        self.assertIn("PROTECTED_ROWS_CHANGED", self.codes(self.audit()))

    def test_unknown_reference_schema_cannot_authorize_extra_object(self):
        bad = dict(REFERENCE)
        bad["table:extra"] = {"type": "table", "name": "extra", "tbl_name": "extra", "sql": "CREATE TABLE extra(x)"}
        report = w.audit_workflow_preservation(self.before, self.after, approved_job_ids=JOBS,
                                               approved_cognitive_ids=self.ids, expected_schema=bad)
        self.assertEqual(self.codes(report), {"EXACT_27_OBJECT_REFERENCE_REQUIRED"})

    def test_partial_preexisting_cognitive_schema_is_not_silently_repaired(self):
        # Absent is a supported first use. Partially initialized is a different
        # failure, even when this candidate would add a missing immutable trigger.
        with closing(sqlite3.connect(self.before)) as db:
            db.executescript(COGNITIVE_SQL)
            db.execute("DROP TRIGGER cognitive_records_no_update")
            db.commit()
        self.assertIn("BASELINE_FIRST_USE_SCHEMA_PARTIAL", self.codes(self.audit()))

    def test_sequence_gap_not_hidden_by_equal_maximum(self):
        self.mutate("UPDATE product_updates SET seq=15 WHERE seq=14")
        self.mutate("UPDATE sqlite_sequence SET seq=15 WHERE name='product_updates'")
        self.assertIn("PRODUCT_UPDATES_SEQUENCE_DELTA_MISMATCH", self.codes(self.audit()))

    def test_wal_writer_during_read_is_detected_not_mixed_into_snapshot(self):
        with closing(sqlite3.connect(self.after)) as db:
            db.execute("PRAGMA journal_mode=WAL")
        original = w._fetch_rows
        written = []
        def fetch(db, name):
            filename = db.execute("PRAGMA database_list").fetchone()[2]
            if Path(filename) == self.after and name == "public_fixture_records" and not written:
                def writer():
                    with closing(sqlite3.connect(self.after)) as other:
                        other.execute("UPDATE public_fixture_records SET away_goals=3 WHERE id='2'")
                        other.commit()
                    written.append(True)
                thread = threading.Thread(target=writer)
                thread.start()
                thread.join(timeout=3)
                self.assertFalse(thread.is_alive())
            return original(db, name)
        with patch.object(w, "_fetch_rows", side_effect=fetch):
            report = self.audit()
        self.assertTrue(written)
        self.assertIn("SNAPSHOT_CHANGED_DURING_AUDIT", self.codes(report))

    def test_audit_does_not_modify_snapshot_files(self):
        hashes = [hashlib.sha256(p.read_bytes()).hexdigest() for p in (self.before, self.after)]
        self.assertTrue(self.audit()["passed"])
        self.assertEqual(hashes, [hashlib.sha256(p.read_bytes()).hexdigest() for p in (self.before, self.after)])


if __name__ == "__main__":
    unittest.main(verbosity=2)
