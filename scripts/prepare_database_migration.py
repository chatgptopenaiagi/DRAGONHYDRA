"""Prepare or verify a private SQLite migration bundle inside this workspace."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from dragonhydra.migration import MigrationError, prepare, validate_bundle


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument('--database', type=Path, help='Explicit existing project-local core.sqlite3')
    choice.add_argument('--verify-bundle', type=Path, help='Reopen and verify an existing private bundle')
    parser.add_argument('--output', type=Path, help='New project-local directory, required with --database')
    args = parser.parse_args()
    if bool(args.database) != bool(args.output):
        parser.error('--database and --output must be supplied together; verification takes only --verify-bundle')
    try:
        result = prepare(args.database, args.output) if args.database else validate_bundle(args.verify_bundle)
    except MigrationError as error:
        print(json.dumps({'valid': False, 'code': error.code, 'message': error.message}))
        return 1
    except Exception as error:
        print(json.dumps({'valid': False, 'code': type(error).__name__,
                          'message': 'Preparation failed; source access was read-only. Inspect the protected candidate output.'}))
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
