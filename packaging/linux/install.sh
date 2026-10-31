#!/usr/bin/env bash
set -euo pipefail
bundle=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
# Inspection is the default. Only an explicit --apply installs into a new prefix.
exec "${DRAGONHYDRA_PYTHON:-python3}" "$bundle/preflight.py" --bundle "$bundle" "$@"
