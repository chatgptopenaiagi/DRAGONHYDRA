"""Small CLI for measured genesis checkpoints; no product services are started."""

import argparse
import json
from pathlib import Path

from .config import PROJECT_ROOT


def main() -> int:
    import sys
    if len(sys.argv)>1 and sys.argv[1]=='handoff':
        from .handoff.consumer import main as handoff_main
        return handoff_main(sys.argv[2:])
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["diagnostics", "probe", "inventory"])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.command == "probe":
        from .integration.mariadb_probe import run_probe
        result = run_probe()
        passed = result["passed"]
    elif args.command == "diagnostics":
        from .diagnostics import compute_diagnostic
        result = compute_diagnostic()
        passed = result["gpu_baseline_passed"] and result["canonical_interpreter_matches"]
    else:
        from .diagnostics import technology_inventory
        result = technology_inventory()
        passed = True
    payload = json.dumps(result, indent=2, allow_nan=False)
    if args.output:
        destination = args.output.resolve()
        if not destination.is_relative_to(PROJECT_ROOT / "runtime/checkpoints"):
            parser.error("Evidence output must remain under runtime/checkpoints")
        with destination.open("x", encoding="utf-8") as stream:
            stream.write(payload + "\n")
    print(payload)
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
