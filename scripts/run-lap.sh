#!/usr/bin/env bash
# run-lap.sh <issue-number> [logfile] — launch a paid lap DETACHED.
#
# Nobody may run a paid lap under a command deadline: a 300s agent command
# timeout once killed the launcher while the GLM stream was open, and the
# request still billed. setsid + nohup puts the lap in its own session, so
# the launcher dying (or any deadline on it) cannot kill the stream.
#
# PID contract: setsid FORKS (util-linux 2.42.2 forks even in the foreground:
# `setsid sleep 3` returns in ~70ms, and `--fork` changes nothing), so the
# launcher's own `$!` is a transient wrapper that is gone while the lap runs —
# it can neither be watched nor killed. The child therefore publishes its own
# pid: the setsid'd `bash -c` writes `$$` to <logfile>.pid and then `exec`s
# python3, so the pidfile holds the pid of the live lap process. Stop the lap
# with the printed `kill "$(cat <logfile>.pid)"`.
#
# Log contract: src/lap.py writes NOTHING to stdout — its live progress goes to
# state/evidence/<run-id>/timeline.json and the terminal artifact is
# state/lap-result.json. So `tail -f <logfile>` is NOT live progress; the log
# is retained for interpreter-crash capture (startup errors, tracebacks).
#
# This script sources nothing: the caller MUST have exported the lap env
# first, e.g.  set -a; . env.sh; set +a
#
# Prints the lap PID + pidfile, the log path, and the progress/stop commands.
# Runs from the repo root regardless of the caller's cwd.
set -euo pipefail
cd "$(dirname "$0")/.."

if [ "$#" -lt 1 ] || [ "$#" -gt 2 ] || ! [[ "$1" =~ ^[0-9]+$ ]]; then
    echo "usage: $0 <issue-number> [logfile]" >&2
    exit 2
fi

issue="$1"
logfile="${2:-state/lap-${issue}-$(date -u +%Y%m%dT%H%M%SZ).log}"
mkdir -p "$(dirname "$logfile")"
pidfile="${logfile}.pid"
rm -f "$pidfile"

# The child publishes its own pid before exec'ing the lap: `$$` in the bash -c
# is the setsid'd child, and `exec` keeps that pid for python3.
# shellcheck disable=SC2016  # $$ and $1 must reach the child unexpanded
setsid nohup bash -c 'echo $$ > "$1"; shift; exec "$@"' bash "$pidfile" \
    python3 src/lap.py "$issue" >> "$logfile" 2>&1 &

for _ in {1..100}; do
    if [ -s "$pidfile" ]; then break; fi
    sleep 0.1
done
if [ ! -s "$pidfile" ]; then
    echo "run-lap: child never published $pidfile (launch failed?)" >&2
    echo "run-lap: check the log: $logfile" >&2
    exit 1
fi
pid=$(cat "$pidfile")
if ! kill -0 "$pid" 2>/dev/null; then
    echo "run-lap: lap pid $pid ($pidfile) is already gone — see $logfile" >&2
    exit 1
fi

echo "lap pid:  $pid  (pidfile: $pidfile)"
echo "log:      $logfile  (crash capture only — lap.py writes no stdout)"
echo "progress: state/evidence/*-issue-${issue}/timeline.json  (live gate rows)"
echo "done:     while [ ! -s state/lap-result.json ]; do sleep 5; done; cat state/lap-result.json"
echo "stop:     kill \"\$(cat $pidfile)\""
