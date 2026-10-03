"""Deploy: generate the reset + PID-file launch script, then read the
deployed identity back.

The script is a standalone file (NEVER inline nested quotes): the supervisor
runs on the rig itself, so lap.py executes it locally with bash — no ssh hop.
"""

import json
import subprocess
import urllib.request

from settings import (
    FACTORY_PORT,
    PRODUCT_REPO,
    READY_TIMEOUT_S,
)

def build_deploy_script(port=FACTORY_PORT, product_repo=PRODUCT_REPO,
                        pid_file="app.pid", ready_timeout=READY_TIMEOUT_S):
    """Full deploy script text: fetch+reset, PID-file kill, nohup start, readiness.

    Generated as text so tests can assert: no pkill, no quoting hazards.
    """
    return f"""set -eu
cd {product_repo}
git fetch origin
git reset --hard origin/main
if [ -f {pid_file} ]; then
  OLDPID=$(cat {pid_file})
  if kill -0 "$OLDPID" 2>/dev/null; then
    kill "$OLDPID"
    for i in $(seq 1 20); do kill -0 "$OLDPID" 2>/dev/null || break; sleep 0.5; done
    kill -9 "$OLDPID" 2>/dev/null || true
  fi
  rm -f {pid_file}
fi
FACTORY_PORT={port} nohup python3 app.py >> app.log 2>&1 &
echo $! > {pid_file}
for i in $(seq 1 {ready_timeout * 2}); do
  if curl -sf http://127.0.0.1:{port}/health > /dev/null; then
    echo READY
    exit 0
  fi
  sleep 0.5
done
echo "NOT READY after {ready_timeout}s"
exit 1
"""

def read_health(host_url):
    with urllib.request.urlopen(host_url.rstrip("/") + "/health", timeout=10) as r:
        return json.loads(r.read())

def identity_readback(host_url, repo_cwd, git="git"):
    """/health revision must equal the local main HEAD (deploy identity)."""
    reported = read_health(host_url).get("revision")
    head = subprocess.run(
        ["git", "rev-parse", "main"], cwd=repo_cwd,
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return {"reported": reported, "head": head, "match": reported == head}
