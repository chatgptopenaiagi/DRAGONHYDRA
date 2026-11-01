#!/bin/sh
# CORE NEXT only: explicit interpreter and validated installation profile.
set -eu
if [ "$#" -ne 4 ] || [ "$1" != '--python' ] || [ "$3" != '--installation-profile' ]; then
    printf '%s\n' 'Usage: linux-server.sh --python /absolute/venv/bin/python --installation-profile /absolute/core-next-lab/profiles/ID/installation-profile.json' >&2
    exit 64
fi
python=$2
profile=$4
case "$python" in /*) ;; *) printf '%s\n' 'An absolute existing CORE NEXT Python runtime is required.' >&2; exit 64 ;; esac
case "$profile" in /*) ;; *) printf '%s\n' 'An absolute CORE NEXT installation profile is required.' >&2; exit 64 ;; esac
if [ ! -x "$python" ] || [ ! -f "$profile" ]; then
    printf '%s\n' 'The explicit interpreter or installation profile is unavailable; no fallback selected.' >&2
    exit 66
fi
# A legacy interpreter/package cannot pass this read-only edition/profile check.
"$python" -B -c 'import sys; from dragonhydra.installation_profile import load_binding; from dragonhydra.kernel import KernelConfig; p,_=load_binding(profile_path=sys.argv[1]); KernelConfig(p["installation_id"],environment_id=p["environment_id"],product=p["product"],edition=p["edition"])' "$profile"
exec "$python" -B -m dragonhydra.server --installation-profile "$profile"
