#!/usr/bin/env bash
# Reproducible isolated dependency environment for the LiveKit HR voice agent.
#
# backend/speakvenv is the running server's environment and is used read-only as the interpreter
# here; it is never written to. Two things must be true at once for the agent to work, and this
# script is the record of how:
#
#   1. livekit-agents (the RTC bindings) is not in speakvenv and must be installed elsewhere.
#   2. PyAV 19 dropped the metadata_errors keyword that faster-whisper 1.2.1 passes to av.open(),
#      so the interpreter's own PyAV must not be shadowed by the newer one livekit-agents pulls in.
#      PyAV 18.0.0 is installed here and PREPENDED; livekit-agents-deps is APPENDED. See
#      backend/app/agents/hr_voice_agent.py for the runtime side of that ordering.
#
# Usage:  bash backend/scripts/setup_livekit_agent_env.sh [target-parent-dir]
# Defaults to <repo>/../agent-deps. Requires only the speakvenv interpreter and network access to
# PyPI. Idempotent: re-running into an existing directory just refreshes it.
set -euo pipefail

BACKEND_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PARENT="${1:-"${BACKEND_DIR}/../agent-deps"}"
mkdir -p "${PARENT}"

AGENTS_DIR="${PARENT}/livekit-agents-deps"
AV_DIR="${PARENT}/av-compat"
PY="${BACKEND_DIR}/speakvenv/Scripts/python.exe"
[ -x "${PY}" ] || PY="${BACKEND_DIR}/speakvenv/bin/python"

echo "== installing into ${PARENT} (speakvenv is not touched) =="
"${PY}" -m pip install --disable-pip-version-check --no-warn-script-location \
  --target "${AV_DIR}" --no-deps "av==18.0.0"
"${PY}" -m pip install --disable-pip-version-check --no-warn-script-location \
  --target "${AGENTS_DIR}" "livekit-agents>=1.0.0"

echo "== verifying the pairing that the fix depends on =="
PYTHONPATH="${AV_DIR}:${AGENTS_DIR}" "${PY}" - <<'PY'
import av
from livekit import rtc
from livekit.api import AccessToken

print(f"av            {av.__version__}  <- must be <19: av.open() needs the metadata_errors keyword")
print(f"livekit.rtc   sdk {[m for m in ('AudioSource','AudioStream','LocalAudioTrack') if hasattr(rtc, m)]}")
print(f"livekit.api   AccessToken={'yes' if AccessToken else 'no'}")
try:
    av.open("none.mp3", metadata_errors="ignore")
except TypeError as exc:
    raise SystemExit(f"FAIL: this PyAV rejects metadata_errors, faster-whisper will return empty: {exc}")
except Exception:
    print("ok            av.open(metadata_errors=...) accepted")
PY

cat <<EOF

Point the agent at these two directories in that order, e.g. for a checkout at ${PARENT}:
  AV_COMPAT=${AV_DIR}
  LIVEKIT_AGENTS_DEPS=${AGENTS_DIR}
EOF
