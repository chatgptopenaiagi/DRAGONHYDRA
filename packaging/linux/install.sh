#!/usr/bin/env bash
printf '%s\n' 'Historical installer disabled in CORE NEXT. Use scripts/core_next/linux-server.sh with an explicit isolated installation profile; no installation was performed.' >&2
exit 64
# Historical A9 implementation retained below; unreachable in this edition.
set -euo pipefail
bundle=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
# Inspection is the default. Only an explicit --apply installs into a new prefix.
exec "${DRAGONHYDRA_PYTHON:-python3}" "$bundle/preflight.py" --bundle "$bundle" "$@"
