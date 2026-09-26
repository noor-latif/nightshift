"""Lap: one issue through the full chain (the wiring between the six modules).

Runs as a child process of supervisor.py: `python3 src/lap.py <issue>`.
Chain: worktree from origin/main -> implementer (deepseek) -> apply diff ->
reviewer (glm, fresh context) -> verify ladder -> squash merge -> deploy ->
identity read-back -> close issue. Red anywhere = failure outcome with
per-gate evidence; the supervisor retries/parks per selector budget.

Evidence per SPIKE_PROD.md S8: state/evidence/<run-id>/ holds timeline.json,
cost.json, verdict.json, implementer_raw.txt, claimed.diff, applied.diff,
review.txt, verify.json, merge.json, identity.json.

Liveness: heartbeat touched every 10s; wall-clock breach past the budget
writes a timeout result and exits (supervisor parks, never re-dispatches).
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.dirname(__file__))

import agent
import deploy
import merge
import verify
from settings import (
    EVIDENCE_DIR,
    GITHUB_REPO,
    HEARTBEAT_PATH,
    IMPLEMENTER_MODEL,
    LAP_WALLCLOCK_LIMIT_S,
    MIN_MAX_TOKENS,
    PRODUCT_REPO,
    REVIEWER_MODEL,
)

RESULT_PATH = os.path.join("state", "lap-result.json")
LIVE_PORT = 8642  # the rig's live port; PID file below (task contract overrides default)
LIVE_PID_FILE = "/tmp/toy-deploy.pid"
IMPLEMENTER_MAX_TOKENS = max(8192, MIN_MAX_TOKENS)
REVIEWER_MAX_TOKENS = max(4096, MIN_MAX_TOKENS)


class LapTimeout(Exception):
    pass


def _git(args, cwd, check=True):
    r = subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError("git %s failed: %s" % (" ".join(args), r.stderr.strip()))
    return r.stdout.strip()


def _gh(args):
    r = subprocess.run(["gh"] + args + ["-R", GITHUB_REPO], capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("gh %s failed: %s" % (" ".join(args), r.stderr.strip()))
    return r.stdout


def worktree_for(issue):
    """agent/issue-<n> worktree under the product repo's .factory dir."""
    repo = os.path.expanduser(PRODUCT_REPO)
    path = os.path.join(repo, ".factory", "worktrees", "issue-%d" % issue)
    branch = "agent/issue-%d" % issue
    _git(["fetch", "origin", "main", "--prune"], repo)
    r = subprocess.run(["git", "worktree", "add", path, "-B", branch, "origin/main"],
                       cwd=repo, capture_output=True, text=True)
    if r.returncode != 0 and "already exists" not in r.stderr and "already registered" not in r.stderr:
        raise RuntimeError("worktree add failed: %s" % r.stderr.strip())
    _git(["reset", "--hard", "origin/main"], path)
    _git(["clean", "-fdx"], path)
    return path


def issue_data(issue):
    return json.loads(_gh(["issue", "view", str(issue), "--json", "title,body"]))


def criteria_from(body):
    m = re.search(r"Acceptance criteria:?\s*\n(.+)", body, re.S | re.I)
    return m.group(1).strip() if m else body


def extract_diff(text):
    """Pull the diff out of model prose: all fenced diff blocks, else a bare diff."""
    blocks = [b.strip() for b in re.findall(r"```(?:diff)?\n(.*?)```", text, re.S)
              if "--- a/" in b or "+++ b/" in b]
    if blocks:
        return "\n".join(b + "\n" for b in blocks)
    m = re.search(r"^diff --git.*", text, re.S | re.M)
    return m.group(0).strip() + "\n" if m else None


def apply_diff(diff_text, worktree):
    """Strict-first ladder: plain, then --recount, then --recount -C1.

    The tier that applied is a measurable implementer-quality signal
    (recount-only = sloppy hunk headers) and must not be hidden.
    """
    fd, path = tempfile.mkstemp(suffix=".patch")
    with os.fdopen(fd, "w") as f:
        f.write(diff_text)
    try:
        r = None
        tier = None
        for tier, extra in (("plain", []), ("recount", ["--recount"]),
                            ("recount-C1", ["--recount", "-C1"])):
            r = subprocess.run(["git", "apply", "--whitespace=nowarn"] + extra + [path],
                               cwd=worktree, capture_output=True, text=True)
            if r.returncode == 0:
                return True, "applied", tier
        return False, (r.stderr or "apply failed").strip(), tier
    finally:
        os.unlink(path)


class Lap:
    def __init__(self, issue):
        self.issue = issue
        self.run_id = time.strftime("%Y%m%dT%H%M%S", time.gmtime()) + "-issue-%d" % issue
        self.evdir = os.path.join(EVIDENCE_DIR, self.run_id)
        os.makedirs(self.evdir, exist_ok=True)
        self.deadline = time.time() + LAP_WALLCLOCK_LIMIT_S
        self.costs = []
        self.timeline = []
        self._hb_stop = threading.Event()

    def event(self, kind, **kw):
        row = {"ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "event": kind}
        row.update(kw)
        self.timeline.append(row)
        self._dump("timeline.json", self.timeline)

    def _dump(self, name, obj):
        with open(os.path.join(self.evdir, name), "w") as f:
            json.dump(obj, f, indent=1, default=str)

    def check_clock(self):
        if time.time() > self.deadline:
            raise LapTimeout("wall-clock budget %.0fs exceeded" % LAP_WALLCLOCK_LIMIT_S)

    def add_cost(self, usage, role):
        if usage:
            self.costs.append({"role": role, "usage": usage})
            self._dump("cost.json", {
                "calls": self.costs,
                "total_usd": sum(c["usage"].get("cost") or 0 for c in self.costs),
            })

    def heartbeat_loop(self):
        os.makedirs(os.path.dirname(HEARTBEAT_PATH) or ".", exist_ok=True)
        while not self._hb_stop.is_set():
            with open(HEARTBEAT_PATH, "w") as f:
                f.write(str(time.time()))
            if time.time() > self.deadline + 60:  # hard wedge guard past soft budget
                self.set_result("timeout")
                os._exit(70)
            self._hb_stop.wait(10)

    def set_result(self, outcome, error=None):
        os.makedirs(os.path.dirname(RESULT_PATH) or ".", exist_ok=True)
        row = {"issue": self.issue, "outcome": outcome, "run_id": self.run_id}
        if error:
            row["error"] = str(error)
        tmp = RESULT_PATH + ".tmp"
        with open(tmp, "w") as f:
            json.dump(row, f)
        os.replace(tmp, RESULT_PATH)


def finish(lap, outcome, gate=None, error=None, caught=None):
    """Terminal lap state: verdict evidence + result file for the supervisor."""
    verdict = {"verdict": "pass" if outcome == "success" else "fail", "outcome": outcome}
    if gate:
        verdict["gate"] = gate
    if caught:
        # model claimed work that a gate killed — factory winning (L-000)
        verdict["caught_confabulation"] = caught
    if error is not None:
        verdict["error"] = error if isinstance(error, str) else json.dumps(error, default=str)
    lap._dump("verdict.json", verdict)
    lap.set_result(outcome, error=verdict.get("error"))
    lap.event("lap-end", outcome=outcome, gate=gate)


def run(issue):
    lap = Lap(issue)
    lap.set_result("running")
    hb = threading.Thread(target=lap.heartbeat_loop, daemon=True)
    hb.start()
    lap.event("lap-start", issue=issue, run_id=lap.run_id)
    worktree = None
    try:
        worktree = worktree_for(issue)
        data = issue_data(issue)
        criteria = criteria_from(data["body"])
        lap.event("claimed", title=data["title"])

        files = []
        for name in ("app.py", "app_test.py"):
            p = os.path.join(worktree, name)
            if os.path.exists(p):
                with open(p) as f:
                    files.append("=== %s ===\n%s" % (name, f.read()))
        prompt = (agent.implementer_prompt(data, criteria, issue)
                  + "\n\nCurrent checkout files:\n" + "\n".join(files))
        r = agent.chat([{"role": "user", "content": prompt}], IMPLEMENTER_MODEL,
                       max_tokens=IMPLEMENTER_MAX_TOKENS)
        lap.add_cost(r["usage"], "implementer")
        with open(os.path.join(lap.evdir, "implementer_raw.txt"), "w") as f:
            f.write(r["content"])
        lap.event("implementer-done", finish_reason=r["finish_reason"], chars=len(r["content"]))
        lap.check_clock()

        diff_text = extract_diff(r["content"])
        if not diff_text:
            return finish(lap, "failure", gate="diff-extraction",
                          caught="model produced no diff despite claiming to implement")
        with open(os.path.join(lap.evdir, "claimed.diff"), "w") as f:
            f.write(diff_text)
        ok, detail, tier = apply_diff(diff_text, worktree)
        lap.event("diff-apply", ok=ok, tier=tier, detail=detail[:500])
        if not ok:
            return finish(lap, "failure", gate="diff-apply", error=detail,
                          caught="diff did not apply to a clean checkout")
        lap.check_clock()

        _git(["add", "-A"], worktree)
        c = subprocess.run(
            ["git", "-c", "user.name=factory", "-c", "user.email=factory@nightshift.local",
             "commit", "-m", "Implement issue %d" % issue],
            cwd=worktree, capture_output=True, text=True)
        if c.returncode != 0:
            return finish(lap, "failure", gate="commit",
                          error=(c.stderr or "nothing to commit").strip())
        branch_diff = _git(["diff", "origin/main", "HEAD"], worktree)
        with open(os.path.join(lap.evdir, "applied.diff"), "w") as f:
            f.write(branch_diff)

        rev = agent.chat([{"role": "user", "content": agent.reviewer_prompt(branch_diff, criteria)}],
                         REVIEWER_MODEL, max_tokens=REVIEWER_MAX_TOKENS)
        lap.add_cost(rev["usage"], "reviewer")
        with open(os.path.join(lap.evdir, "review.txt"), "w") as f:
            f.write(rev["content"])
        verdict_m = re.search(r"VERDICT:\s*(accept|reject)", rev["content"], re.I)
        if not verdict_m or verdict_m.group(1).lower() != "accept":
            return finish(lap, "failure", gate="review",
                          caught=("reviewer rejected the diff" if verdict_m
                                  else "reviewer gave no parseable verdict"))
        lap.event("review-accept")
        lap.check_clock()

        pid_file = os.path.join("/tmp", "factory-verify-%s.pid" % lap.run_id)
        scenarios_dir = os.path.join(os.path.dirname(__file__), "..", "scenarios")
        evidence = verify.verify_candidate(worktree, pid_file, scenarios_dir, issue=issue)
        lap._dump("verify.json", evidence)
        if evidence["verdict"] != "pass":
            return finish(lap, "failure", gate="verify", error=evidence)
        lap.event("verify-green")
        lap.check_clock()

        _git(["push", "-u", "origin", "agent/issue-%d" % issue], worktree)
        m = merge.full_merge(issue, GITHUB_REPO, worktree, {"verdict": "pass"})
        if not m.get("merged"):
            return finish(lap, "failure", gate="merge", error=m)
        lap.event("merged", pr=m.get("pr"), merge_sha=m.get("merge_sha"))
        lap._dump("merge.json", m)

        # deploy: the supervisor runs on nixlab itself, so the deploy script
        # runs directly here — no ssh hop. Kill ONLY by the documented PID file.
        script = deploy.build_deploy_script(port=LIVE_PORT,
                                            product_repo=os.path.expanduser(PRODUCT_REPO),
                                            pid_file=LIVE_PID_FILE)
        fd, spath = tempfile.mkstemp(suffix=".sh")
        with os.fdopen(fd, "w") as f:
            f.write(script)
        try:
            d = subprocess.run(["bash", spath], capture_output=True, text=True, timeout=120)
        finally:
            os.unlink(spath)
        lap.event("deploy", rc=d.returncode, tail=(d.stdout + d.stderr)[-300:])
        if d.returncode != 0:
            return finish(lap, "failure", gate="deploy", error=(d.stdout + d.stderr)[-2000:])
        ident = deploy.identity_readback("http://127.0.0.1:%d" % LIVE_PORT,
                                         os.path.expanduser(PRODUCT_REPO))
        lap._dump("identity.json", ident)
        if not ident["match"]:
            return finish(lap, "failure", gate="deploy-identity", error=ident)
        _gh(["issue", "close", str(issue), "--comment",
             "Merged and deployed by nightshift lap %s (PR: %s)" % (lap.run_id, m.get("pr"))])
        lap.event("issue-closed")
        finish(lap, "success")
    except agent.PermanentError as e:
        finish(lap, "failure", gate="gateway", error="permanent: %s" % e)
    except agent.TransientError as e:
        finish(lap, "failure", gate="gateway", error="transient after retry: %s" % e)
    except LapTimeout as e:
        finish(lap, "timeout", error=str(e))
    except Exception as e:  # supervisor classifies via the result file
        finish(lap, "crash", error="%s: %s" % (type(e).__name__, e))
    finally:
        lap._hb_stop.set()
        if worktree:
            subprocess.run(["git", "worktree", "remove", "--force", worktree],
                           cwd=os.path.expanduser(PRODUCT_REPO), capture_output=True)


if __name__ == "__main__":
    run(int(sys.argv[1]))
