"""Lap: one issue through the full chain (the wiring between the six modules).

Runs as a child process of supervisor.py: `python3 src/lap.py <issue>`.
Chain: worktree from origin/main -> implementer (deepseek) -> apply diff ->
reviewer (glm, fresh context) -> verify ladder -> squash merge -> deploy ->
identity read-back -> close issue. Red anywhere = failure outcome with
per-gate evidence; the supervisor retries/parks per selector budget.

Evidence per SPIKE_PROD.md S8: state/evidence/<run-id>/ holds timeline.json,
cost.json, verdict.json, implementer_raw.txt, claimed.json, mutations.json,
applied.diff, review.txt, verify.json, merge.json, identity.json.

Liveness: heartbeat touched every 10s; wall-clock breach past the budget
writes a timeout result and exits (supervisor parks, never re-dispatches).
"""

import glob
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
    CHECKOUT_CHAR_BUDGET,
    CODE_PATHS,
    COST_CEILING_USD,
    DEPLOY_MODE,
    EVIDENCE_DIR,
    GITHUB_REPO,
    HEARTBEAT_PATH,
    IMPLEMENTER_MAX_TOKENS,
    IMPLEMENTER_MODEL,
    IMPLEMENTER_REASONING_EFFORT,
    LAP_WALLCLOCK_LIMIT_S,
    MIN_MAX_TOKENS,
    SCENARIOS_DIR,
    PRODUCT_REPO,
    REVIEWER_MODEL,
)

RESULT_PATH = os.path.join("state", "lap-result.json")
LIVE_PORT = 8642  # the rig's live port; PID file below (task contract overrides default)
LIVE_PID_FILE = "/tmp/toy-deploy.pid"
REVIEWER_MAX_TOKENS = max(4096, MIN_MAX_TOKENS)


class LapTimeout(Exception):
    pass


class CostCeilingExceeded(Exception):
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


def _worktree_path(issue, prefix="agent"):
    return os.path.join(os.path.expanduser(PRODUCT_REPO), ".factory",
                        "worktrees", "%s-issue-%d" % (prefix, issue))


def worktree_for(issue, prefix="agent"):
    """<prefix>/issue-<n> worktree under the product repo's .factory dir.
    Laps use the factory-owned agent/ ref; the dispatch-time RED re-check
    (L-013) uses a throwaway recheck/ ref it never pushes."""
    repo = os.path.expanduser(PRODUCT_REPO)
    path = _worktree_path(issue, prefix)
    branch = "%s/issue-%d" % (prefix, issue)
    _git(["fetch", "origin", "main", "--prune"], repo)
    _worktree_add(repo, path, branch)
    _git(["reset", "--hard", "origin/main"], path)
    _git(["clean", "-fdx"], path)
    return path


def _worktree_add(repo, path, branch, _retry=True):
    """worktree add, self-healing a registered-path collision (L-016):
    a crashed/killed lap can leave its worktree registered; unattended runs
    cannot depend on operator cleanup between launches. Only the collision
    signature heals; anything else fails loud as before."""
    r = subprocess.run(["git", "worktree", "add", path, "-B", branch, "origin/main"],
                       cwd=repo, capture_output=True, text=True)
    if r.returncode != 0 and "already exists" not in r.stderr and "already registered" not in r.stderr:
        if _retry and "is already used by worktree at" in r.stderr:
            subprocess.run(["git", "worktree", "remove", "--force", path],
                           cwd=repo, capture_output=True)
            subprocess.run(["git", "worktree", "prune"], cwd=repo, capture_output=True)
            return _worktree_add(repo, path, branch, _retry=False)
        raise RuntimeError("worktree add failed: %s" % r.stderr.strip())
    return r


def issue_data(issue):
    return json.loads(_gh(["issue", "view", str(issue), "--json", "title,body"]))


def checkout_files(worktree, char_budget=CHECKOUT_CHAR_BUDGET):
    """Bounded view of the worktree for the implementer: the CODE_PATHS
    globs (worktree-relative), sorted by path, whole files, stopped at the
    char budget. A path segment starting with "." excludes a file (dotdirs,
    .factory/). A file matching two globs appears once. Default
    CODE_PATHS=["*.py"] = the historical root-only view, byte-identical.
    """
    paths = set()
    for pat in CODE_PATHS:
        for p in glob.glob(os.path.join(worktree, pat)):
            rel = os.path.relpath(p, worktree)
            if any(part.startswith(".") for part in rel.split(os.sep)):
                continue
            if not os.path.isfile(p):
                continue
            paths.add(rel)
    out, used = [], 0
    for rel in sorted(paths):
        with open(os.path.join(worktree, rel)) as f:
            text = f.read()
        block = "=== %s ===\n%s" % (rel, text)
        if used + len(block) > char_budget:
            break  # sorted order → deterministic prefix; bigger repos truncate
        out.append(block)
        used += len(block)
    return out


def criteria_from(body):
    m = re.search(r"Acceptance criteria:?\s*\n(.+)", body, re.S | re.I)
    return m.group(1).strip() if m else body


def extract_mutations(text, allowed_files=None):
    """Mutation-parse gate (BIGGEST_ISSUE_ANALYSIS §4): strict JSON parse +
    shape check. DSML/prose leaks die here, as the old extract gate caught
    them. Returns (mutations, error); exactly one is non-None.

    A fenced ```json block is transport noise, not content: the instrument
    accepts what a compliant model emits (L-007's false-red lesson) — strip
    fences and parse; anything else is prose and fails loud.
    """
    blocks = re.findall(r"```(?:json)?\n(.*?)```", text, re.S)
    candidates = [b.strip() for b in blocks]
    span = _json_array_span(text)
    if span:
        candidates.append(span)
    candidates.append(text.strip())
    first_err = None
    for payload in candidates:
        try:
            data = json.loads(payload)
        except ValueError as e:
            if first_err is None:
                first_err = "mutation-parse: invalid JSON: %s" % e
            continue
        if not isinstance(data, list):
            return None, ("mutation-parse: top-level must be a JSON array, got %s"
                          % type(data).__name__)
        err = _mutation_shape_error(data, allowed_files)
        if err:
            return None, err
        if not data:
            return None, "mutation-parse: empty mutation array"
        return data, None
    return None, first_err or "mutation-parse: no JSON payload found"


def _mutation_shape_error(data, allowed_files):
    """Per-mutation shape check: dict, exactly string file/find/replace."""
    for i, m in enumerate(data):
        if not isinstance(m, dict):
            return "mutation-parse: mutation %d is not a JSON object" % i
        missing = [k for k in ("file", "find", "replace") if k not in m]
        if missing:
            return "mutation-parse: mutation %d missing keys %s" % (i, missing)
        for k in ("file", "find", "replace"):
            if not isinstance(m[k], str):
                return "mutation-parse: mutation %d field %r must be a string" % (i, k)
        if not m["find"]:
            return "mutation-parse: mutation %d has an empty find anchor" % i
        if allowed_files is not None and m["file"] not in allowed_files:
            return ("mutation-parse: mutation %d file %r is not in the provided checkout"
                    % (i, m["file"]))
    return None


def applied_files(worktree):
    """Files actually changed in the worktree (modified/tracked + untracked)."""
    r = subprocess.run(["git", "status", "--porcelain"], cwd=worktree,
                       capture_output=True, text=True)
    return {line[3:] for line in r.stdout.splitlines() if line.strip()}


def _json_array_span(text):
    """Bare-array fallback: the outermost [ ... ] span, as the old bare-diff
    fallback did for diffs. None when the text has no array at all."""
    a, b = text.find("["), text.rfind("]")
    return text[a:b + 1] if a != -1 and b > a else None


def _norm_indexed(text):
    """Trailing-whitespace-normalized copy + index back-map.

    Returns (norm, idx) where norm[i] came from original text[idx[i]] — the
    one tolerance worth building (models drift trailing whitespace;
    BIGGEST_ISSUE_ANALYSIS §4); nothing fuzzier.
    """
    norm, idx, off = [], [], 0
    for line in text.split("\n"):
        s = line.rstrip()
        norm.append(s)
        idx.extend(range(off, off + len(s)))
        norm.append("\n")
        idx.append(off + len(line))
        off += len(line) + 1
    return "".join(norm)[:-1], idx[:-1]


def apply_mutations(mutations, worktree):
    """Mutation-apply gate (§4): each anchor must occur exactly once
    (trailing-whitespace-normalized); 0 or >1 → loud fail naming file +
    anchor prefix. Mutations apply in array order, each on the previous
    result. No auto-repair — an anchor miss is a genuine model failure the
    gate records, never fixes (L-008). Files are written only if every
    mutation matches.

    Returns (ok, detail, results); results is the per-mutation evidence
    {file, anchor_count, applied, error} — every rung recorded, never only
    the last failure (L-014's lesson carried over to this contract).
    """
    contents, results = {}, []
    for i, m in enumerate(mutations):
        name = m["file"]
        if name not in contents:
            try:
                with open(os.path.join(worktree, name)) as f:
                    contents[name] = f.read()
            except OSError as e:
                results.append({"index": i, "file": name, "anchor_count": 0,
                                "applied": False, "error": "unreadable: %s" % e})
                return False, ("mutation-apply: %s: cannot read file (%s)" % (name, e)), results
        text = contents[name]
        hay, hay_idx = _norm_indexed(text)
        needle, _ = _norm_indexed(m["find"])
        count = hay.count(needle)
        row = {"index": i, "file": name, "anchor_count": count, "applied": False}
        results.append(row)
        if count != 1:
            row["error"] = ("anchor not found" if count == 0
                            else "anchor occurs %d times" % count)
            return False, ("mutation-apply: %s: anchor occurs %d times (expected 1), "
                           "anchor prefix: %r" % (name, count, m["find"][:60])), results
        start = hay.index(needle)
        a = hay_idx[start]
        end = start + len(needle)
        if needle.endswith("\n") and len(needle) > 1:
            end -= 1  # the anchor's final newline is a line boundary, not
                      # content: keep the file's own trailing bytes of that line
        b = hay_idx[end - 1] + 1
        contents[name] = text[:a] + m["replace"] + text[b:]
        row["applied"] = True
    for name, text in contents.items():
        with open(os.path.join(worktree, name), "w") as f:
            f.write(text)
    # post-condition: the mutated file set must appear in git status
    # (L-008 declared-vs-applied discipline; git-apply exit-0's silent
    # drop has no analogue here, but the post-condition stays).
    actual = applied_files(worktree)
    missing = sorted(set(contents) - actual)
    if missing:
        return False, ("apply_incomplete: mutated %s but git status shows %s"
                       % (sorted(contents), sorted(actual))), results
    return True, "applied %d mutations" % len(mutations), results


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
        """One row per call, always: a dropped row silently undercounts
        published cost tables. Falsy usage (gateway sent no usage chunk)
        records usage=None, buyer_cost_micro=0, missing_usage=true — the
        row's existence proves the call happened; per-call count is
        assertable. Raises CostCeilingExceeded (caught by run() →
        gate='cost' lap failure) once the cumulative total passes
        COST_CEILING_USD — the whitepaper's ceiling is a real runtime
        gate, not a dead constant."""
        if usage:
            self.costs.append({"role": role, "usage": usage})
        else:
            self.costs.append({"role": role, "usage": None,
                                "buyer_cost_micro": 0, "missing_usage": True})
        total_usd = sum((c["usage"] or {}).get("buyer_cost_micro") or 0
                        for c in self.costs) / 1e6
        self._dump("cost.json", {
            "calls": self.costs,
            # buyer_cost_micro is the truthful field (exact vs order book);
            # usage.cost reads ~15% low (luna-qualify probe 3)
            "total_usd": total_usd,
        })
        if total_usd > COST_CEILING_USD:
            raise CostCeilingExceeded(
                "cumulative %f USD exceeds ceiling %f USD"
                % (total_usd, COST_CEILING_USD))

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
    # the cleanup path must hold the path even if worktree_for raises before
    # assignment (L-016): a skipped finally is how the crash loop started
    worktree = _worktree_path(issue)
    try:
        worktree = worktree_for(issue)
        data = issue_data(issue)
        criteria = criteria_from(data["body"])
        lap.event("claimed", title=data["title"])

        files = checkout_files(worktree)
        prompt = (agent.implementer_prompt(data, criteria, issue)
                  + "\n\nCurrent checkout files:\n" + "\n".join(files))
        r = agent.chat([{"role": "user", "content": prompt}], IMPLEMENTER_MODEL,
                       max_tokens=IMPLEMENTER_MAX_TOKENS,
                       reasoning_effort=IMPLEMENTER_REASONING_EFFORT)
        lap.add_cost(r["usage"], "implementer")
        with open(os.path.join(lap.evdir, "implementer_raw.txt"), "w") as f:
            f.write(r["content"])
        lap.event("implementer-done", finish_reason=r["finish_reason"], chars=len(r["content"]))
        lap.check_clock()
        names = {f.split("\n", 1)[0][4:-4] for f in files}
        mutations, parse_err = extract_mutations(r["content"], allowed_files=names)
        if not mutations:
            return finish(lap, "failure", gate="mutation-parse", error=parse_err,
                          caught="model produced no mutation JSON despite claiming to implement")
        with open(os.path.join(lap.evdir, "claimed.json"), "w") as f:
            json.dump(mutations, f, indent=1)
        ok, detail, mut_results = apply_mutations(mutations, worktree)
        lap._dump("mutations.json", mut_results)
        lap.event("mutation-apply", ok=ok, detail=detail[:500])
        if not ok:
            if detail.startswith("apply_incomplete"):
                return finish(lap, "apply_incomplete", gate="mutation-apply", error=detail,
                               caught=detail)
            return finish(lap, "failure", gate="mutation-apply", error=detail,
                          caught="anchor miss: mutations did not apply to the checkout")
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

        rev = agent.chat([{"role": "user", "content":
                          agent.reviewer_prompt(branch_diff, criteria,
                                                files="\n".join(checkout_files(worktree)))}],
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
        evidence = verify.verify_candidate(worktree, pid_file, SCENARIOS_DIR, issue=issue)
        lap._dump("verify.json", evidence)
        if evidence["verdict"] != "pass":
            return finish(lap, "failure", gate="verify", error=evidence)
        lap.event("verify-green")
        lap.check_clock()

        # agent/issue-<n> branches are factory-owned; a crashed lap after the
        # push leaves the remote branch ahead, and a retried lap rebuilds its
        # local branch from origin/main — plain push is then rejected forever.
        # --force-with-lease keeps the retry deterministic.
        _git(["push", "--force-with-lease", "-u", "origin", "agent/issue-%d" % issue], worktree)
        m = merge.full_merge(issue, GITHUB_REPO, worktree, evidence)
        if not m.get("merged"):
            return finish(lap, "failure", gate="merge", error=m)
        lap.event("merged", pr=m.get("pr"), merge_sha=m.get("merge_sha"))
        lap._dump("merge.json", m)

        # deploy: the supervisor runs on nixlab itself, so the deploy script
        # runs directly here — no ssh hop. Kill ONLY by the documented PID file.
        # DEPLOY_MODE="none" (library repos) has nothing to deploy and no
        # live rig to compare identity against — skip both, loudly in the
        # event log.
        if DEPLOY_MODE == "none":
            lap.event("deploy-skip", mode=DEPLOY_MODE)
        else:
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
    except CostCeilingExceeded as e:
        finish(lap, "failure", gate="cost", error=str(e))
    except agent.PermanentError as e:
        finish(lap, "failure", gate="gateway", error="permanent: %s" % e)
    except agent.TransientError as e:
        finish(lap, "failure", gate="gateway", error="transient after retry: %s" % e)
    except LapTimeout as e:
        finish(lap, "timeout", error=str(e))
    except Exception as e:  # supervisor classifies via the result file
        stderr = getattr(e, "stderr", "")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", "replace")
        finish(lap, "crash", error="%s: %s%s" % (
            type(e).__name__, e, ("\n" + stderr.strip()[-1500:]) if stderr else ""))
    finally:
        lap._hb_stop.set()
        if worktree:
            subprocess.run(["git", "worktree", "remove", "--force", worktree],
                           cwd=os.path.expanduser(PRODUCT_REPO), capture_output=True)


if __name__ == "__main__":
    run(int(sys.argv[1]))
