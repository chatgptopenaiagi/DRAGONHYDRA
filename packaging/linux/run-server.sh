#!/usr/bin/env bash
set -euo pipefail
prefix=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
: "${DRAGONHYDRA_STATE:?Set the selected private DRAGONHYDRA_STATE directory}"
exec "$prefix/venv/bin/dragonhydra-server" --host 127.0.0.1 --port "${DRAGONHYDRA_PORT:-18743}" --state "$DRAGONHYDRA_STATE"
