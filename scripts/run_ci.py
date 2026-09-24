"""Run the explicit, dependency-free Python 3.14 CI tier; never run live probes.

The complete local suite remains scripts/run_tests.py. A new test class must be
classified below before CI accepts it; local tests are reported, not skipped.
"""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import tomllib
import unittest


ROOT = Path(__file__).resolve().parents[1]
PORTABLE_CLASSES = {
    "test_ci_contracts.PortablePublishedSchemaTests",
    "test_configuration.ConfigurationTests",
    "test_database_contracts.DatabaseContractTests",
    "test_dual_database.DualDatabaseConfigurationTests",
    "test_evidence.SyntheticCasesTests",
    "test_evidence.TemporalContractTests",
    "test_evidence.SupersessionAndConflictTests",
    "test_handoff_bridge.EnvelopeTests",
    "test_math_contracts.MathContractTests",
    "test_repository_audit.RepositoryAuditTests",
    "test_repository_links.RepositoryLinkTests",
    "test_web_pipeline.WebContractsTests",
    "test_web_pipeline.LicenseBridgeTests",
}
LOCAL_CLASSES = {
    "test_compute.ComputeBaselineTests": "TIER_3: canonical Conda and CUDA/cuDNN",
    "test_dual_database.LiveDualDatabaseTests": "TIER_3: Windows services, databases and XAMPP",
    "test_mariadb_probe.LiveMariaDBTests": "TIER_2: configured MariaDB and least-privilege identity",
    "test_web_pipeline.LiveWebSQLTests": "TIER_2: configured SQL Server, MariaDB and Joomla data",
    "test_handoff_bridge.LiveBridgeTests": "TIER_2: provisioned synthetic handoff and live storage",
}
LOCAL_METHODS = {
    "test_handoff_bridge.EnvelopeTests.test_schema_matches_published":
        "TIER_3: published handoff schema is bound to the canonical laboratory root",
    "test_configuration.ConfigurationTests.test_plaintext_probe_secret_absent_from_source_config_docs":
        "TIER_2: reads the generated local probe credential",
    "test_configuration.ConfigurationTests.test_credential_repr_does_not_reveal_password":
        "TIER_2: reads the generated local probe credential",
    "test_dual_database.DualDatabaseConfigurationTests.test_secrets_absent_from_source_config_and_checkpoints":
        "TIER_2: compares generated credentials with local checkpoints",
    "test_web_pipeline.LicenseBridgeTests.test_unreadable_pdf_stays_unverified":
        "TIER_3: pinned project-local pypdf vendor installation",
}


class RecordingResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.passed_ids = []

    def addSuccess(self, test):
        super().addSuccess(test)
        self.passed_ids.append(test.id())


def syntax_and_metadata():
    """Compile without importing provisioning scripts or creating bytecode."""
    count = 0
    for folder in ("src", "scripts", "tests"):
        for path in sorted((ROOT / folder).rglob("*.py")):
            compile(path.read_bytes(), str(path), "exec")
            count += 1
    with (ROOT / "pyproject.toml").open("rb") as stream:
        project = tomllib.load(stream)["project"]
    if project["name"] != "dragonhydra" or project["requires-python"] != ">=3.14,<3.15":
        raise ValueError("Package identity or canonical Python 3.14 metadata changed")
    if project.get("dependencies", []):
        raise ValueError("Portable tier is dependency-free; review CI before adding runtime dependencies")
    return count


def flatten(suite):
    for test in suite:
        if isinstance(test, unittest.TestSuite):
            yield from flatten(test)
        else:
            yield test


def classify(suite):
    portable, local, unknown = [], {}, []
    all_ids = set()
    for test in flatten(suite):
        test_id = test.id()
        all_ids.add(test_id)
        class_id = test_id.rsplit(".", 1)[0]
        reason = LOCAL_METHODS.get(test_id) or LOCAL_CLASSES.get(class_id)
        if reason:
            local[test_id] = reason
        elif class_id in PORTABLE_CLASSES:
            portable.append(test)
        else:
            unknown.append(test_id)
    if unknown:
        raise ValueError("Unclassified/import-failed tests: " + ", ".join(unknown))
    stale = set(LOCAL_METHODS) - all_ids
    class_ids = {test_id.rsplit(".", 1)[0] for test_id in all_ids}
    stale.update((PORTABLE_CLASSES | set(LOCAL_CLASSES)) - class_ids)
    if stale:
        raise ValueError("Stale CI classification: " + ", ".join(sorted(stale)))
    if not portable:
        raise ValueError("No portable tests selected")
    return unittest.TestSuite(portable), local


def install_portable_guard():
    """Catch accidental live dependencies; this is not a hostile-code sandbox."""
    blocked = []
    protected = [(ROOT / "runtime" / name).resolve() for name in ("secrets", "vendor")]
    optional_modules = {"pyodbc", "pymysql", "torch", "numpy", "pypdf"}

    def audit(event, args):
        forbidden = False
        if event in {"socket.connect", "socket.connect_ex", "socket.getaddrinfo",
                     "socket.gethostbyname", "socket.gethostbyaddr", "socket.sendto"}:
            forbidden = True
        elif event == "import" and args[0].split(".", 1)[0] in optional_modules:
            forbidden = True
        elif event == "open" and isinstance(args[0], (str, bytes)):
            path = Path(args[0].decode() if isinstance(args[0], bytes) else args[0]).resolve()
            forbidden = any(path.is_relative_to(folder) for folder in protected)
        if forbidden:
            # Do not expose network addresses, connection arguments or file content.
            blocked.append(event)
            raise RuntimeError("Portable tier attempted a forbidden live dependency")

    sys.addaudithook(audit)
    return blocked


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--syntax-only", action="store_true", help="compile and check package metadata only")
    parser.add_argument("--list", action="store_true", help="show explicit portable/local test classification")
    parser.add_argument("--output", type=Path, help="new JSON evidence file inside runtime/checkpoints")
    args = parser.parse_args()
    if sys.version_info[:2] != (3, 14):
        raise SystemExit("DRAGONHYDRA requires Python 3.14; no CI downgrade is allowed")
    destination = args.output.resolve() if args.output else None
    if destination and (not destination.is_relative_to(ROOT / "runtime/checkpoints") or destination.exists()):
        raise SystemExit("Output must be a new file inside runtime/checkpoints")
    sys.dont_write_bytecode = True
    sys.path[:0] = [str(ROOT / "src"), str(ROOT / "tests")]
    compiled = syntax_and_metadata()
    print(f"Python {sys.version.split()[0]}; syntax checked {compiled} authored Python files; metadata passed", flush=True)
    if args.syntax_only:
        return 0
    (ROOT / "runtime/tmp").mkdir(parents=True, exist_ok=True)
    blocked = install_portable_guard()
    loader = unittest.TestLoader()
    suite, local = classify(loader.discover(str(ROOT / "tests")))
    selected_ids = [test.id() for test in flatten(suite)]
    print(f"TIER 1: {len(selected_ids)} portable tests; {len(local)} local tests outside this tier (not skipped)", flush=True)
    if args.list:
        print(json.dumps({"portable": selected_ids, "local": local}, indent=2))
        return 0
    result = unittest.TextTestRunner(verbosity=2, resultclass=RecordingResult).run(suite)
    successful = result.wasSuccessful() and not result.skipped and not blocked
    summary = {
        "checked_utc": datetime.now(timezone.utc).isoformat(), "tier": 1,
        "python": sys.version, "executable": sys.executable, "syntax_files": compiled,
        "tests_run": result.testsRun, "tests_passed": len(result.passed_ids),
        "tests_failed": len(result.failures), "tests_errored": len(result.errors),
        "tests_skipped": len(result.skipped), "successful": successful,
        "blocked_live_dependency_attempts": len(blocked),
        "passed_ids": result.passed_ids,
        "failed_ids": [test.id() for test, _ in result.failures],
        "error_ids": [test.id() for test, _ in result.errors],
        "outside_tier": local,
    }
    if destination:
        with destination.open("x", encoding="utf-8") as stream:
            json.dump(summary, stream, indent=2)
            stream.write("\n")
    print(f"TIER 1 result: {summary['tests_passed']} passed, {summary['tests_failed']} failed, "
          f"{summary['tests_errored']} errors, {summary['tests_skipped']} skipped; "
          f"{len(blocked)} blocked live dependency attempts", flush=True)
    return 0 if successful else 1


if __name__ == "__main__":
    raise SystemExit(main())
