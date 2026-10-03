#!/usr/bin/env bash
# run-lap.sh <issue-number> [logfile] — launch a paid lap DETACHED.
#
# Nobody may run a paid lap under a command deadline: a 300s agent command
# timeout once killed the launcher while the GLM stream was open, and the
# request still billed. setsid + nohup puts the lap in its own session, so
# the launcher dying (or any deadline on it) cannot kill the stream.
#
# This script sources nothing: the caller MUST have exported the lap env
# first, e.g.  set -a; . env.sh; set +a
#
# Prints the child PID, the log path, and the tail command. Runs from the
# repo root regardless of the caller's cwd.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ "$#" -lt 1 ] || [ "$#" -gt 2 ] || ! [[ "$1" =~ ^[0-9]+$ ]]; then
    echo "usage: $0 <issue-number> [logfile]" >&2
    exit 2
fi

issue="$1"
logfile="${2:-state/lap-${issue}-$(date -u +%Y%m%dT%H%M%SZ).log}"
mkdir -p "$(dirname "$logfile")"

setsid nohup python3 src/lap.py "$issue" >> "$logfile" 2>&1 &
pid=$!

echo "lap pid $pid"
echo "log:   $logfile"
echo "watch: tail -f $logfile"
