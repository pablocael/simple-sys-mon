#!/usr/bin/env bash
# Launch sys-mon using its virtualenv.
cd "$(dirname "$0")"
exec .venv/bin/python sysmon.py "$@"
