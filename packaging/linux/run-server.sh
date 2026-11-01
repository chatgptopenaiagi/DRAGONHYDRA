#!/usr/bin/env bash
printf '%s\n' 'Historical launcher disabled in CORE NEXT. Use scripts/core_next/linux-server.sh with an explicit isolated installation profile; no fallback was selected.' >&2
exit 64
# Historical A9 implementation retained below; unreachable in this edition.
set -euo pipefail
prefix=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
: "${DRAGONHYDRA_STATE:?Set the selected private DRAGONHYDRA_STATE directory}"
exec "$prefix/venv/bin/dragonhydra-server" --host 127.0.0.1 --port "${DRAGONHYDRA_PORT:-18743}" --state "$DRAGONHYDRA_STATE"
