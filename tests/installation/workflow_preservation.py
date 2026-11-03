"""Narrow, read-only preservation audit for the approved two-job workflow.

Inputs must be independent working copies of preserved SQLite snapshots. SQLite
read-only WAL access can touch SHM bookkeeping, so never pass original forensic
evidence paths. expected_schema is an
independent reference made from the frozen application's DDL, NEVER the candidate
after database. Pairing/configuration, profile/source authorization and network
activity are separate caller gates. No application, provider or job is invoked.
"""
from __future__ import annotations

from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import sqlite3
import time

TABLES = {"acquisitions", "receipts", "quarantine", "quarantine_receipts",
          "cognitive_records", "cognitive_receipts"}
EMPTY_AUXILIARY = TABLES - {"cognitive_records", "cognitive_receipts"}
TRIGGERS = {"quarantine_receipts_no_update", "quarantine_receipts_no_delete",
            "raw_immutable_update", "raw_immutable_delete", "acquisition_immutable_update",
            "acquisition_immutable_delete", "receipt_immutable_update", "receipt_immutable_delete",
            "quarantine_immutable_update", "quarantine_immutable_delete",
            "cognitive_records_no_update", "cognitive_records_no_delete",
            "cognitive_receipts_no_update", "cognitive_receipts_no_delete"}
INDEXES = {"sqlite_autoindex_" + n + "_1" for n in TABLES} | {"sqlite_autoindex_cognitive_records_2"}
CATALOG = {"table:" + n for n in TABLES} | {"trigger:" + n for n in TRIGGERS} | {"index:" + n for n in INDEXES}
AUTH_BOOKKEEPING = {"product_bridge_nonces", "product_sessions"}
WORKFLOW = {"cognitive_records", "cognitive_receipts", "product_jobs", "product_updates"}
REQUIRED_BASE = {"raw_sources", "public_fixture_records", "connector_settings", "product_jobs", "product_updates", "sqlite_sequence"}
MAX_ROWS = 50000
MAX_TABLES = 128


class AuditError(Exception):
    pass


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _need(ok, code):
    if not ok:
        raise AuditError(code)


def _atom(value):
    # SQLite integers and reals (including -0) are distinct; None and BLOBs
    # cannot collide with strings or JSON-shaped application data.
    if value is None:
        return ["null"]
    if type(value) is int:
        return ["integer", str(value)]
    if type(value) is float:
        return ["real", value.hex()]
    if type(value) is str:
        return ["text", value]
    if type(value) is bytes:
        return ["blob", value.hex()]
    raise AuditError("UNSUPPORTED_SQLITE_VALUE_TYPE")


def _encoded(row):
    return canonical([_atom(v) for v in row])


def _same(left, right):
    return _encoded(left) == _encoded(right)


def _schema(db):
    return {kind + ":" + name: {"type": kind, "name": name, "tbl_name": table, "sql": sql}
            for kind, name, table, sql in db.execute("SELECT type,name,tbl_name,sql FROM sqlite_master ORDER BY type,name")}


def canonical_schema_from_sql(market_sql, cognitive_sql):
    """Build an independent in-memory reference from caller-verified frozen DDL.

    This creates NO files. Caller must bind the two supplied SQL constants to
    the intended immutable source. It does not bless arbitrary candidate DDL.
    """
    _need(type(market_sql) is str and type(cognitive_sql) is str, "REFERENCE_DDL_REQUIRED")
    with closing(sqlite3.connect(":memory:")) as db:
        db.executescript(market_sql)
        db.executescript(cognitive_sql)
        objects = _schema(db)
    result = {k: objects[k] for k in CATALOG if k in objects}
    _validate_reference(result)
    return result


def _validate_reference(expected):
    _need(isinstance(expected, dict) and set(expected) == CATALOG, "EXACT_27_OBJECT_REFERENCE_REQUIRED")
    for key, value in expected.items():
        _need(isinstance(value, dict) and set(value) == {"type", "name", "tbl_name", "sql"}, "REFERENCE_OBJECT_SHAPE_INVALID")
        _need(key == value["type"] + ":" + value["name"], "REFERENCE_OBJECT_IDENTITY_INVALID")
        _need(value["tbl_name"] in TABLES | {"raw_sources"}, "REFERENCE_TABLE_BINDING_INVALID")
        _need(value["sql"] is None if value["type"] == "index" else type(value["sql"]) is str,
              "REFERENCE_SQL_SHAPE_INVALID")


def _ordinary(path):
    path = Path(path)
    _need(path.is_file(), "SNAPSHOT_FILE_REQUIRED")
    for candidate in (path, *path.parents):
        _need(not candidate.is_symlink() and not (getattr(candidate.stat(), "st_file_attributes", 0) & 0x400),
              "SNAPSHOT_REPARSE_PATH_REJECTED")
    return path.resolve()


def _fetch_rows(db, name):
    _need(bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", name)), "UNSUPPORTED_TABLE_IDENTIFIER")
    cursor = db.execute('SELECT * FROM "' + name + '"')
    columns = tuple(col[0] for col in cursor.description)
    _need(0 < len(columns) <= 128, "SNAPSHOT_COLUMN_BOUND")
    rows = []
    while batch := cursor.fetchmany(512):
        rows.extend(batch)
        _need(len(rows) <= MAX_ROWS, "SNAPSHOT_ROW_BOUND")
    return {"columns": columns, "rows": tuple(rows)}


def _load(path):
    path = _ordinary(path)
    before_hash = hashlib.sha256(path.read_bytes()).hexdigest()
    with closing(sqlite3.connect(path.as_uri() + "?mode=ro", uri=True, timeout=.2)) as db:
        db.execute("PRAGMA query_only=ON")
        deadline = time.monotonic() + 5
        db.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
        version = db.execute("PRAGMA data_version").fetchone()[0]
        db.execute("BEGIN")
        _need(db.execute("PRAGMA integrity_check").fetchone()[0] == "ok", "SNAPSHOT_INTEGRITY_FAILED")
        objects = _schema(db)
        names = sorted(v["name"] for v in objects.values() if v["type"] == "table")
        _need(len(names) <= MAX_TABLES, "SNAPSHOT_TABLE_BOUND")
        tables = {name: _fetch_rows(db, name) for name in names}
        db.rollback()
        _need(db.execute("PRAGMA data_version").fetchone()[0] == version, "SNAPSHOT_CHANGED_DURING_AUDIT")
    _need(hashlib.sha256(path.read_bytes()).hexdigest() == before_hash, "SNAPSHOT_CHANGED_DURING_AUDIT")
    return {"schema": objects, "tables": tables, "file_sha256": before_hash}


def _objects(table):
    return [dict(zip(table["columns"], row)) for row in table["rows"]]


def _keyed(table, field):
    rows = _objects(table)
    result = {row[field]: row for row in rows}
    _need(len(result) == len(rows), "WORKFLOW_KEY_NOT_UNIQUE")
    return result


def _dict_same(a, b):
    return set(a) == set(b) and all(_same((a[k],), (b[k],)) for k in a)


def _fields(before, after):
    if before["columns"] != after["columns"]:
        return ["<column-layout>"]
    return [col for i, col in enumerate(before["columns"])
            if sorted(_encoded((r[i],)) for r in before["rows"]) != sorted(_encoded((r[i],)) for r in after["rows"])]


def _time(value):
    _need(type(value) is str, "COGNITIVE_RECEIPT_CLOCK_INVALID")
    try:
        result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise AuditError("COGNITIVE_RECEIPT_CLOCK_INVALID") from None
    _need(result.tzinfo is not None and result.utcoffset().total_seconds() == 0, "COGNITIVE_RECEIPT_CLOCK_INVALID")
    return result


def audit_workflow_preservation(before_path, after_path, *, approved_job_ids,
                                approved_cognitive_ids, expected_schema):
    """Return sanitized errors/counters; never emit SQL, row keys or values.

    The exact two auth bookkeeping tables retain the original acceptance's row
    exemption. Their schema remains protected; counts are disclosed separately.
    All old workflow rows are immutable here. Approved IDs already present before
    are replay-only: no duplicate jobs, cognition or events may be added.
    """
    errors = []
    result = {"schema_version": "workflow-preservation/1", "passed": False, "errors": errors,
              "authentication_bookkeeping_row_exemptions": sorted(AUTH_BOOKKEEPING),
              "scope_limits": ["Does not replace configuration/credential fingerprint checks",
                               "Caller binds source/profile, approved IDs and preserved snapshot hashes",
                               "Does not prove network inactivity or model numerical correctness"]}

    def error(code, table=None, fields=None, object_key=None):
        item = {"code": code}
        if table is not None:
            item["table"] = table
        if fields:
            item["fields"] = sorted(fields)
        if object_key:
            item["object_ref"] = hashlib.sha256(object_key.encode()).hexdigest()
        if item not in errors:
            errors.append(item)

    def preserve_old(old, new, table):
        for key in old:
            if key not in new:
                error("OLD_WORKFLOW_ROW_REMOVED", table)
            elif not _dict_same(old[key], new[key]):
                error("OLD_WORKFLOW_ROW_CHANGED", table,
                      [k for k in old[key] if k not in new[key] or not _same((old[key][k],), (new[key][k],))])

    try:
        _validate_reference(expected_schema)
        _need(isinstance(approved_job_ids, dict) and set(approved_job_ids) == {"forecast", "evaluation"}, "EXACT_TWO_JOB_BINDINGS_REQUIRED")
        _need(len(set(approved_job_ids.values())) == 2 and all(type(v) is str and re.fullmatch("[a-f0-9]{32}", v) for v in approved_job_ids.values()),
              "APPROVED_JOB_IDS_INVALID")
        ids = list(approved_cognitive_ids)
        _need(len(ids) == len(set(ids)) == 10 and all(type(v) is str and re.fullmatch(r"(model|prediction):[a-f0-9]{64}", v) for v in ids)
              and sum(v.startswith("model:") for v in ids) == 5, "EXACT_TEN_COGNITIVE_IDS_REQUIRED")
        _need(Path(before_path).resolve() != Path(after_path).resolve(), "DISTINCT_SNAPSHOTS_REQUIRED")
        before, after = _load(before_path), _load(after_path)
        b, a = before["tables"], after["tables"]
        result.update(before_sha256=before["file_sha256"], after_sha256=after["file_sha256"],
                      schema_contract_sha256=hashlib.sha256(canonical(expected_schema)).hexdigest())
        _need(REQUIRED_BASE <= set(b), "BASELINE_TABLES_MISSING")
        cognitive_catalog = {key for key, obj in expected_schema.items() if obj["tbl_name"].startswith("cognitive_")}
        for group in (cognitive_catalog, CATALOG - cognitive_catalog):
            present = group & set(before["schema"])
            if present and present != group:
                error("BASELINE_FIRST_USE_SCHEMA_PARTIAL")
        for key, original in before["schema"].items():
            if key not in after["schema"]:
                error("SCHEMA_OBJECT_REMOVED", object_key=key)
            elif after["schema"][key] != original:
                error("PREEXISTING_SCHEMA_OBJECT_CHANGED", object_key=key)
        additions = set(after["schema"]) - set(before["schema"])
        for key in sorted(additions):
            if key not in expected_schema:
                error("UNAPPROVED_SCHEMA_ADDITION", object_key=key)
        for key, expected in expected_schema.items():
            if after["schema"].get(key) != expected:
                error("CANONICAL_FIRST_USE_SCHEMA_MISMATCH", object_key=key)
        for name in sorted(set(b) | set(a)):
            if name in AUTH_BOOKKEEPING | WORKFLOW | {"sqlite_sequence"}:
                continue
            if name not in b:
                if name not in EMPTY_AUXILIARY or a[name]["rows"]:
                    error("UNAPPROVED_NEW_TABLE_DATA", name if name in TABLES else None)
            elif name not in a:
                error("PROTECTED_TABLE_REMOVED", name)
            elif b[name]["columns"] != a[name]["columns"] or sorted(map(_encoded, b[name]["rows"])) != sorted(map(_encoded, a[name]["rows"])):
                error("PROTECTED_ROWS_CHANGED", name, _fields(b[name], a[name]))
        _need(WORKFLOW | {"sqlite_sequence"} <= set(a), "AFTER_WORKFLOW_TABLES_MISSING")
        keyed = {}
        for name, key in (("product_jobs", "id"), ("product_updates", "seq"),
                          ("cognitive_records", "record_id"), ("cognitive_receipts", "record_id")):
            old = _keyed(b[name], key) if name in b else {}
            new = _keyed(a[name], key)
            preserve_old(old, new, name)
            keyed[name] = old, new
        old_jobs, jobs = keyed["product_jobs"]
        new_jobs = set(jobs) - set(old_jobs)
        approved = set(approved_job_ids.values())
        if not approved <= set(jobs) or new_jobs != approved - set(old_jobs):
            error("UNAPPROVED_JOB_DELTA", "product_jobs")
        _need(approved <= set(jobs), "APPROVED_JOB_ROWS_MISSING")
        targets = []
        for kind, identifier in approved_job_ids.items():
            row = jobs[identifier]
            _need(row["kind"] == kind and row["status"] == "succeeded", "APPROVED_JOB_STATE_INVALID")
            payload = json.loads(row["payload"])
            _need(set(payload) == {"match_id"} and re.fullmatch("[a-f0-9]{64}", payload["match_id"]), "APPROVED_JOB_PAYLOAD_INVALID")
            targets.append(payload["match_id"])
        _need(targets[0] == targets[1] and jobs[approved_job_ids["forecast"]]["owner"] == jobs[approved_job_ids["evaluation"]]["owner"],
              "APPROVED_JOB_SCOPE_MISMATCH")
        forecast = json.loads(jobs[approved_job_ids["forecast"]]["result"])
        evaluation = json.loads(jobs[approved_job_ids["evaluation"]]["result"])
        _need(forecast.get("status") == "persisted" and forecast.get("available") is True,
              "FORECAST_RESULT_NOT_PERSISTED")
        _need(evaluation.get("status") == "pending" and evaluation.get("available") is False
              and evaluation.get("reason") == "LATER_RETAINED_OUTCOME_UNAVAILABLE", "EVALUATION_NOT_EXPECTED_PENDING")
        result_records = list(forecast["model_runs"]) + list(forecast["predictions"])
        expected_records = {r["record_id"]: r for r in result_records}
        _need(len(result_records) == len(expected_records) == 10 and set(expected_records) == set(ids), "FORECAST_RESULT_ID_BINDING_MISMATCH")
        old_records, records = keyed["cognitive_records"]
        old_receipts, receipts = keyed["cognitive_receipts"]
        for table, old, new in (("cognitive_records", old_records, records), ("cognitive_receipts", old_receipts, receipts)):
            if set(new) - set(old) != set(ids) - set(old) or not set(ids) <= set(new):
                error("UNAPPROVED_COGNITIVE_DELTA", table)
        _need(set(ids) <= set(records) and set(ids) <= set(receipts), "APPROVED_COGNITIVE_ROWS_MISSING")
        for identifier in ids:
            row, receipt, reported = records[identifier], receipts[identifier], expected_records[identifier]
            payload = json.loads(row["payload"])
            fingerprint = hashlib.sha256(canonical(payload)).hexdigest()
            _need(row["payload"].encode("utf-8") == canonical(payload) and row["fingerprint"] == fingerprint
                  and identifier == row["kind"] + ":" + hashlib.sha256(canonical([row["kind"], row["natural_key"], fingerprint])).hexdigest(),
                  "COGNITIVE_CONTENT_HASH_BINDING_INVALID")
            _need(payload["run_id"] == approved_job_ids["forecast"] and row["natural_key"] == payload["run_id"] + ":" + payload["model_name"],
                  "COGNITIVE_RUN_BINDING_INVALID")
            _need(all(k in reported and canonical(reported[k]) == canonical(v) for k, v in payload.items())
                  and reported["record_content_hash"] == fingerprint, "COGNITIVE_JOB_RESULT_PAYLOAD_MISMATCH")
            _need(all(receipt[k] == reported[k] for k in ("received_at", "persisted_at", "usable_at")), "COGNITIVE_JOB_RESULT_RECEIPT_MISMATCH")
            _need(_time(receipt["received_at"]) <= _time(receipt["persisted_at"]) == _time(receipt["usable_at"]), "COGNITIVE_RECEIPT_CLOCK_INVALID")
            forecast_job = jobs[approved_job_ids["forecast"]]
            _need(_time(forecast_job["created_at"]) <= _time(receipt["received_at"])
                  and _time(receipt["usable_at"]) <= _time(forecast_job["updated_at"]), "COGNITIVE_RECEIPT_OUTSIDE_JOB_WINDOW")
            if row["kind"] == "prediction":
                _need(payload["model_run_id"] in expected_records and payload["model_run_id"].startswith("model:")
                      and expected_records[payload["model_run_id"]]["model_name"] == payload["model_name"], "PREDICTION_MODEL_BINDING_INVALID")
        old_events, events = keyed["product_updates"]
        new_events = {seq: row for seq, row in events.items() if seq not in old_events}
        if len(new_events) != 4 * len(new_jobs):
            error("UNAPPROVED_EVENT_COUNT", "product_updates")
        event_sets = {job: [] for job in new_jobs}
        for seq, row in sorted(new_events.items()):
            _need(type(seq) is int and seq > max(old_events, default=0), "EVENT_SEQUENCE_INVALID")
            payload = json.loads(row["payload"])
            if row["topic"] == "job" and set(payload) == {"id", "status"} and payload["id"] in new_jobs and payload["status"] in {"queued", "running", "succeeded"}:
                event_sets[payload["id"]].append(payload["status"])
            elif row["topic"] == "data" and set(payload) == {"job_id", "kind"} and payload["job_id"] in new_jobs and payload["kind"] == jobs[payload["job_id"]]["kind"]:
                event_sets[payload["job_id"]].append("data")
            else:
                error("UNAPPROVED_EVENT_DELTA", "product_updates")
        if any(sequence != ["queued", "running", "succeeded", "data"] for sequence in event_sets.values()):
            error("JOB_EVENT_TRANSITION_MISMATCH", "product_updates")
        sequences = []
        for tables in (b, a):
            sequence = _keyed(tables["sqlite_sequence"], "name")
            event_rows = _keyed(tables["product_updates"], "seq")
            _need("product_updates" in sequence and type(sequence["product_updates"]["seq"]) is int,
                  "PRODUCT_UPDATES_SEQUENCE_ROW_MISSING")
            if sequence["product_updates"]["seq"] != max(event_rows, default=0):
                error("PRODUCT_UPDATES_SEQUENCE_MAX_MISMATCH", "sqlite_sequence", ["seq"])
            sequences.append(sequence)
        before_sequence, after_sequence = sequences
        if not _dict_same({k: v["seq"] for k, v in before_sequence.items() if k != "product_updates"},
                          {k: v["seq"] for k, v in after_sequence.items() if k != "product_updates"}):
            error("OTHER_SEQUENCE_ROW_CHANGED", "sqlite_sequence", ["seq"])
        if after_sequence["product_updates"]["seq"] < before_sequence["product_updates"]["seq"]:
            error("PRODUCT_UPDATES_SEQUENCE_REGRESSED", "sqlite_sequence", ["seq"])
        first = before_sequence["product_updates"]["seq"] + 1
        if sorted(new_events) != list(range(first, first + len(new_events))):
            error("PRODUCT_UPDATES_SEQUENCE_DELTA_MISMATCH", "sqlite_sequence", ["seq"])
        result["counts"] = {"added_schema_objects": len(additions), "new_jobs": len(new_jobs),
                            "new_cognitive_records": len(set(records) - set(old_records)),
                            "new_cognitive_receipts": len(set(receipts) - set(old_receipts)),
                            "new_events": len(new_events), "protected_retained_rows": len(b["public_fixture_records"]["rows"]),
                            "auth_bookkeeping": {name: {"before": len(b.get(name, {"rows": ()})["rows"]),
                                                         "after": len(a.get(name, {"rows": ()})["rows"])} for name in sorted(AUTH_BOOKKEEPING)}}
    except AuditError as exc:
        error(str(exc))
    except (sqlite3.Error, OSError):
        error("SNAPSHOT_READ_UNAVAILABLE")
    except Exception:
        error("WORKFLOW_BINDING_SHAPE_INVALID")
    errors.sort(key=lambda value: canonical(value))
    result["passed"] = not errors
    return result
