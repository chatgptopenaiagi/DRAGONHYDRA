"""Write an exclusive, machine-readable test result alongside the full text log."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import sys
import unittest

from dragonhydra.config import PROJECT_ROOT


class RecordingResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.passed_ids = []

    def addSuccess(self, test):
        super().addSuccess(test)
        self.passed_ids.append(test.id())


parser = argparse.ArgumentParser()
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
destination = args.output.resolve()
if not destination.is_relative_to(PROJECT_ROOT / "runtime/checkpoints") or destination.exists():
    raise SystemExit("Test evidence path must be new and inside runtime/checkpoints")
suite = unittest.defaultTestLoader.discover(str(PROJECT_ROOT / "tests"))
result = unittest.TextTestRunner(verbosity=2, resultclass=RecordingResult).run(suite)
summary = {
    "checked_utc": datetime.now(timezone.utc).isoformat(),
    "python": sys.version, "executable": sys.executable,
    "tests_run": result.testsRun, "tests_passed": len(result.passed_ids),
    "tests_failed": len(result.failures), "tests_errored": len(result.errors),
    "tests_skipped": len(result.skipped), "successful": result.wasSuccessful(),
    "passed_ids": result.passed_ids,
    "failed_ids": [str(test) for test, _ in result.failures],
    "error_ids": [str(test) for test, _ in result.errors],
}
with destination.open("x", encoding="utf-8") as stream:
    json.dump(summary, stream, indent=2)
    stream.write("\n")
raise SystemExit(0 if result.wasSuccessful() else 1)
