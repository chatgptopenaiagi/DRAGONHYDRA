"""Generate or reverify MariaDB staging SQL offline; never connect to a database."""
import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from dragonhydra.migration import MigrationError
from dragonhydra.mariadb_migration import MariaDBMigrationError, build_script, validate_script


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument('--bundle', type=Path, help='Verified SQLite preparation bundle')
    choice.add_argument('--verify-sql', type=Path, help='Existing generated SQL directory')
    parser.add_argument('--output', type=Path, help='New private project-local output directory')
    parser.add_argument('--schema', help='New schema named dragonhydra_migration_<suffix>')
    args = parser.parse_args()
    if args.bundle and (not args.output or not args.schema):
        parser.error('--bundle requires --output and an explicit --schema')
    if args.verify_sql and (args.output or args.schema):
        parser.error('--verify-sql takes no --output or --schema')
    try:
        result = build_script(args.bundle, args.output, args.schema) if args.bundle else validate_script(args.verify_sql)
    except (MariaDBMigrationError, MigrationError) as error:
        print(json.dumps({'valid': False, 'code': error.code, 'message': error.message}))
        return 1
    except Exception as error:
        print(json.dumps({'valid': False, 'code': type(error).__name__,
                          'message': 'Offline SQL preparation failed; no database connection or execution was attempted.'}))
        return 1
    print(json.dumps(result, indent=2))
    return 0


if __name__ == '__main__':
    sys.exit(main())
