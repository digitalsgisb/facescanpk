#!/usr/bin/env bash
set -euo pipefail
cd -- "$(dirname -- "$0")"
# Python loads kiosk.env safely and also supports direct python3 face.py startup.
exec python3 face.py
