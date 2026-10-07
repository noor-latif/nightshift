#!/usr/bin/env bash
# qualify.sh <repo> [options] — distill a repo's build/test recipe.
#
# Deterministic by default: every check is local shell work and the run makes
# ZERO model calls. `--agent` is the only way to spend, and it buys exactly one
# proposal that the deterministic layer then has to bind.
#
# This script sources nothing (mirroring run-lap.sh): the caller owns the
# environment. It only normalises cwd to the kernel root and execs the module.
#
# Usage:
#   scripts/qualify.sh <repo> [--seed FILE] [--chain a,b] [--agent]
#                             [--netns] [--probe] [--no-hooks-ab] [--no-dry-run]
#                             [--out FILE] [--in-repo] [--evdir DIR]
#                             [--emit-env [PATH]] [--render]
set -euo pipefail
cd "$(dirname "$0")/.."

if [ "$#" -lt 1 ]; then
    sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//' >&2
    exit 2
fi

exec python3 src/qualify.py "$@"
