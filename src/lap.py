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

import difflib
import fnmatch
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
    DEPLOY_PORT,
    EVIDENCE_DIR,
    GITHUB_REPO,
    HEARTBEAT_PATH,
    IMPLEMENTER_MAX_TOKENS,
    IMPLEMENTER_MAX_TOKENS_FIELD,
    IMPLEMENTER_API,
    IMPLEMENTER_MODEL,
    IMPLEMENTER_REASONING_EFFORT,
    LAP_WALLCLOCK_LIMIT_S,
    MERGE_MODE,
    NEW_FILES,
    SCENARIOS_DIR,
    TASK_FILE,
    PRODUCT_REPO,
    REVIEWER_MAX_TOKENS,
    REVIEWER_MAX_TOKENS_FIELD,
    REVIEWER_API,
    REVIEWER_REASONING_EFFORT,
    REVIEWER_MODEL,
    TASK_KIND,
)

RESULT_PATH = os.path.join("state", "lap-result.json")
LIVE_PID_FILE = "/tmp/toy-deploy.pid"


def _feedback_path(issue):
    return os.path.join(os.path.dirname(RESULT_PATH) or ".",
                        "implementer-feedback-%d.json" % issue)


def _save_implementer_feedback(issue, detail, results):
    path = _feedback_path(issue)
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w") as f:
        json.dump({"issue": issue, "detail": detail, "mutations": results}, f,
                  indent=1, default=str)


def _load_implementer_feedback(issue):
    try:
        with open(_feedback_path(issue)) as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict) or data.get("issue") != issue:
        return None
    detail = data.get("detail")
    return detail if isinstance(detail, str) and detail else None


def _clear_implementer_feedback(issue):
    try:
        os.remove(_feedback_path(issue))
    except OSError:
        pass


def _implementer_prompt(data, criteria, issue, files):
    prompt = agent.implementer_prompt(data, criteria, issue)
    if NEW_FILES:
        prompt += ("\n\nNew files: the ONLY paths you may create: %s (literal "
                   "entries do not exist yet; entries with * ? [ are fnmatch "
                   "patterns). Create one with "
                   '{"file": "<path>", "find": "", "replace": "<entire file '
                   'content>", "create": true}. Any other path is rejected.'
                   % ", ".join(NEW_FILES))
    feedback = _load_implementer_feedback(issue)
    if feedback:
        prompt += ("\n\nFeedback from the previous implementer attempt. "
                   "Correct this mutation-apply failure rather than repeating "
                   "the same anchor:\n" + feedback)
    return prompt + "\n\nCurrent checkout files:\n" + "\n".join(files)


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
    """Issue text from the trusted local task file when configured, else gh.

    The local path exists for operator-run laps whose task is not a GitHub
    issue (a docs-only product with no tracker); it is never read from the
    candidate checkout. Shape is validated loud — a malformed task file must
    not reach a paid call.
    """
    if TASK_FILE:
        with open(TASK_FILE) as f:
            data = json.load(f)
        if (not isinstance(data, dict)
                or not isinstance(data.get("title"), str) or not data["title"].strip()
                or not isinstance(data.get("body"), str) or not data["body"].strip()):
            raise ValueError("task file %s must be an object with non-empty "
                             "string title and body" % TASK_FILE)
        return {"title": data["title"], "body": data["body"]}
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


def prompt_view_discrepancy(view, usage, min_view_tokens=1000):
    """Detect a badly wired implementer call whose billed prompt is far
    smaller than the checkout view rendered into the prompt.

    The gateway's prompt_tokens count and the checkout view are measured in
    the same lap. A four-characters-per-token estimate is intentionally
    conservative; only a tenfold-or-more shortfall is anomalous, which keeps
    normal tokenizer variance and legitimate checkout truncation clean.
    """
    if not isinstance(usage, dict):
        return None
    raw_billed = usage.get("prompt_tokens")
    try:
        billed = int(raw_billed)
    except (TypeError, ValueError):
        return None
    if billed < 0:
        return None
    rendered = view if isinstance(view, str) else "\n".join(view or [])
    rendered_chars = len(rendered)
    rendered_tokens = (rendered_chars + 3) // 4
    if rendered_tokens < min_view_tokens or billed * 10 >= rendered_tokens:
        return None
    ratio = billed / float(rendered_tokens)
    return {
        "type": "prompt-size-vs-view",
        "attribution": "instrument-anomaly",
        "role": "implementer",
        "prompt_tokens": billed,
        "rendered_view_tokens": rendered_tokens,
        "rendered_view_chars": rendered_chars,
        "ratio": round(ratio, 6),
        "message": (
            "prompt-size-vs-view discrepancy: implementer billed "
            "prompt_tokens=%d for a rendered checkout view of approximately "
            "%d tokens (%d chars); billed/view ratio %.6f is below the "
            "0.1 sanity threshold" %
            (billed, rendered_tokens, rendered_chars, ratio)
        ),
    }


def criteria_from(body):
    m = re.search(r"Acceptance criteria:?\s*\n(.+)", body, re.S | re.I)
    return m.group(1).strip() if m else body

def design_brief_from(body):
    """The creative-direction section of a task body, for the reviewer.

    The implementer is told the direction; without it the reviewer can only
    fail a design-compliance criterion as unverifiable (observed on the
    Körmotorn trial). Returns "" when the task has no such section.
    """
    m = re.search(r"^#{1,6}\s*Creative direction[^\n]*\n(.+?)(?=^#{1,6}\s|\Z)",
                  body, re.S | re.M | re.I)
    return m.group(1).strip() if m else ""


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


_GLOB_CHARS = "*?["

def _is_glob(entry):
    """Is this FACTORY_NEW_FILES entry an fnmatch pattern (not a literal)?"""
    return any(c in entry for c in _GLOB_CHARS)

def _new_file_authorized(name):
    """Is `name` inside the FACTORY_NEW_FILES create surface?

    A literal entry authorizes that exact path (the fast path); an entry
    containing fnmatch glob characters authorizes every path it matches.
    This is membership only — the lexical, realpath-containment and
    existence checks in _create_path_error apply either way, so a glob
    never widens them (and a matched '..' segment is still rejected).
    """
    if name in NEW_FILES:
        return True
    return any(fnmatch.fnmatch(name, e) for e in NEW_FILES if _is_glob(e))

def _mutation_shape_error(data, allowed_files):
    """Per-mutation shape check: dict, exactly string file/find/replace.

    A create mutation ({"file","create":true,"replace":<whole content>}) is
    valid only for an allowlisted new path that is not already in the
    provided checkout: find must be empty, and the file must not exist.
    """
    for i, m in enumerate(data):
        if not isinstance(m, dict):
            return "mutation-parse: mutation %d is not a JSON object" % i
        create = m.get("create")
        if create is not None and not isinstance(create, bool):
            return "mutation-parse: mutation %d field 'create' must be a boolean" % i
        keys = ("file", "find", "replace") if not create else ("file", "replace")
        missing = [k for k in keys if k not in m]
        if missing:
            return "mutation-parse: mutation %d missing keys %s" % (i, missing)
        for k in keys:
            if not isinstance(m[k], str):
                return "mutation-parse: mutation %d field %r must be a string" % (i, k)
        if create:
            if not _new_file_authorized(m["file"]):
                return ("mutation-parse: mutation %d creates %r which is not in "
                        "FACTORY_NEW_FILES" % (i, m["file"]))
            if m.get("find", ""):
                return ("mutation-parse: mutation %d create must carry an empty "
                        "find" % i)
            if allowed_files is not None and m["file"] in allowed_files:
                return ("mutation-parse: mutation %d creates %r but it already "
                        "exists in the provided checkout" % (i, m["file"]))
            continue
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


def _line_context(text, pos):
    line = text.count("\n", 0, pos) + 1
    start = text.rfind("\n", 0, pos) + 1
    end = text.find("\n", pos)
    if end == -1:
        end = len(text)
    return line, pos - start + 1, text[start:end]


def _anchor_miss_diagnosis(needle, hay):
    """Explain the first difference in the best matching file region."""
    if not hay:
        return "file is empty; no best-match region exists"
    match = difflib.SequenceMatcher(None, needle, hay, autojunk=False).find_longest_match(
        0, len(needle), 0, len(hay))
    start = max(0, match.b - match.a)
    start = min(start, max(0, len(hay) - len(needle)))
    candidate = hay[start:start + len(needle)]
    limit = min(len(needle), len(candidate))
    diff = next((i for i in range(limit) if needle[i] != candidate[i]), None)
    if diff is None:
        diff = limit
    anchor_line, anchor_col, expected = _line_context(needle, diff)
    file_pos = start + min(diff, len(candidate))
    file_line, file_col, actual = _line_context(hay, file_pos)
    if diff == limit and len(needle) == len(candidate):
        return ("best-match region had no differing character despite the miss "
                "(anchor length %d, file region length %d)" %
                (len(needle), len(candidate)))
    return (
        "best-match region: first divergence at anchor offset %d (line %d, column %d) "
        "vs file offset %d (line %d, column %d); expected line: %r; "
        "actual file line: %r" %
        (diff, anchor_line, anchor_col, file_pos, file_line, file_col,
         expected, actual)
    )


def _anchor_occurrence_diagnosis(needle, hay, count):
    positions, cursor = [], 0
    while len(positions) < 8:
        found = hay.find(needle, cursor)
        if found == -1:
            break
        positions.append(found)
        cursor = found + 1
    lines = [_line_context(hay, p)[0] for p in positions]
    return ("anchor has %d exact matches at file offsets %s (lines %s); "
            "ambiguous anchor, so no mutation was applied" %
            (count, positions, lines))


def _create_path_error(name, worktree):
    """Validate a create target. Returns an error string, or None.

    Lexical '..' rejection alone is not enough: a symlinked parent
    directory can redirect the write outside the checkout, so the real
    path of the parent is resolved and required to stay inside the real
    worktree root.
    """
    if not _new_file_authorized(name):
        return "not in FACTORY_NEW_FILES"
    if (os.path.isabs(name) or "\\" in name
            or any(part in ("", ".", "..") for part in name.split("/"))):
        return "must be a plain relative path"
    root = os.path.realpath(worktree)
    parent = os.path.realpath(os.path.join(worktree, os.path.dirname(name)))
    if parent != root and not parent.startswith(root + os.sep):
        return "parent directory resolves outside the checkout"
    if os.path.lexists(os.path.join(worktree, name)):
        return "file already exists"
    return None

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
    creates = set()
    for i, m in enumerate(mutations):
        name = m["file"]
        if m.get("create"):
            # Creation is the one write that has no existing bytes to anchor
            # on, so the path itself is the trust boundary: allowlisted,
            # plain relative, real parent inside the checkout, and absent
            # (the write below is O_EXCL, so a race cannot overwrite).
            err = _create_path_error(name, worktree)
            if err or name in creates:
                err = err or "duplicate create of %r in one mutation set" % name
                results.append({"index": i, "file": name, "create": True,
                                "applied": False, "error": err})
                return False, ("mutation-apply: %s: %s" % (name, err)), results
            contents[name] = m["replace"]
            creates.add(name)
            results.append({"index": i, "file": name, "create": True, "applied": True})
            continue
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
            diagnosis = (_anchor_miss_diagnosis(needle, hay) if count == 0 else
                         _anchor_occurrence_diagnosis(needle, hay, count))
            row["diagnosis"] = diagnosis
            return False, ("mutation-apply: %s: anchor occurs %d times (expected 1), "
                           "anchor prefix: %r; %s" %
                           (name, count, m["find"][:60], diagnosis)), results

        start = hay.index(needle)
        a = hay_idx[start]
        end = start + len(needle)
        if (needle.endswith("\n") and len(needle) > 1
                and hay_idx[end - 1] != hay_idx[end - 2] + 1):
            # Step back only when the anchor's final newline is a line
            # boundary the normalizer re-created: if the normalized index did
            # not advance, source bytes were stripped before that newline
            # (trailing whitespace / a CR in CRLF) and must be preserved.
            # Otherwise the newline is anchor content — consuming it dropped
            # the line break and corrupted the file (K3).
            end -= 1
        b = hay_idx[end - 1] + 1
        contents[name] = text[:a] + m["replace"] + text[b:]
        row["applied"] = True
    for name in sorted(creates):
        path = os.path.join(worktree, name)
        try:
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        except OSError as e:
            return False, ("mutation-apply: %s: cannot create file (%s)"
                           % (name, e)), results
        with os.fdopen(fd, "w") as f:
            f.write(contents[name])
    for name, text in contents.items():
        if name in creates:
            continue
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
        self.observations = []
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

    def add_cost(self, usage, role, *, cost_unknown=False):
        """One row per call, always: a dropped row silently undercounts
        published cost tables. Falsy usage (gateway sent no usage chunk)
        records usage=None, buyer_cost_micro=0, missing_usage=true — the
        row's existence proves the call happened; per-call count is
        assertable. A call that FAILED (no response at all, so no usage
        will ever arrive) records cost_unknown=true instead: its billed
        spend is unknown, not zero. Raises CostCeilingExceeded (caught by
        run() → gate='cost' lap failure) once the cumulative total passes
        COST_CEILING_USD — the whitepaper's ceiling is a real runtime
        gate, not a dead constant."""
        if usage:
            self.costs.append({"role": role, "usage": usage})
        else:
            row = {"role": role, "usage": None,
                   "buyer_cost_micro": 0, "missing_usage": True}
            if cost_unknown:
                row["cost_unknown"] = True
            self.costs.append(row)
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

    def set_result(self, outcome, error=None, gate=None, observations=None,
                   extra=None):
        os.makedirs(os.path.dirname(RESULT_PATH) or ".", exist_ok=True)
        row = {"issue": self.issue, "outcome": outcome, "run_id": self.run_id,
               "evidence_dir": os.path.abspath(self.evdir)}
        if gate:
            row["gate"] = gate
        if error:
            row["error"] = str(error)
        if observations:
            row["observations"] = observations
        if extra:
            row.update(extra)
        tmp = RESULT_PATH + ".tmp"
        with open(tmp, "w") as f:
            json.dump(row, f)
        os.replace(tmp, RESULT_PATH)


def finish(lap, outcome, gate=None, error=None, caught=None, extra=None):
    """Terminal lap state: verdict evidence + result file for the supervisor.
    extra lands in both artifacts: terminal facts a supervisor/reviewer needs
    to find without reading the evidence dir (e.g. a retained candidate)."""
    observations = getattr(lap, "observations", [])
    verdict = {"verdict": "pass" if outcome in ("success", "success-close-failed", "awaiting-review") else "fail", "outcome": outcome}
    if gate:
        verdict["gate"] = gate
    if observations:
        verdict["observations"] = observations
        verdict["attribution"] = "instrument-anomaly"
    if caught and not observations:
        # model claimed work that a gate killed — factory winning (L-000)
        verdict["caught_confabulation"] = caught
    if error is not None:
        verdict["error"] = error if isinstance(error, str) else json.dumps(error, default=str)
    if extra:
        verdict.update(extra)
    lap._dump("verdict.json", verdict)
    lap.set_result(outcome, error=verdict.get("error"), gate=gate,
                   observations=observations, extra=extra)
    lap.event("lap-end", outcome=outcome, gate=gate)


def run(issue):
    lap = Lap(issue)
    lap.set_result("running")
    hb = threading.Thread(target=lap.heartbeat_loop, daemon=True)
    hb.start()
    lap.event("lap-start", issue=issue, run_id=lap.run_id)

    def chat_or_cost_unknown(role, messages, model, **kw):
        # A failed call still happened (and may still bill): record it as
        # cost_unknown instead of silently omitting its row from cost.json.
        try:
            return agent.chat(messages, model, **kw)
        except (agent.PermanentError, agent.TransientError):
            lap.add_cost(None, role, cost_unknown=True)
            raise

    # the cleanup path must hold the path even if worktree_for raises before
    # assignment (L-016): a skipped finally is how the crash loop started
    worktree = _worktree_path(issue)
    try:
        worktree = worktree_for(issue)
        data = issue_data(issue)
        criteria = criteria_from(data["body"])
        lap.event("claimed", title=data["title"])
        if TASK_KIND == "enhancement":
            baseline = verify.verify_candidate(
                worktree, os.path.join(lap.evdir, "baseline.pid"), SCENARIOS_DIR,
                evidence_dir=os.path.join(lap.evdir, "baseline-commands"))
            lap._dump("baseline.json", baseline)
            lap.event("baseline-check", verdict=baseline["verdict"])
            if baseline["verdict"] != "pass":
                return finish(lap, "failure", gate="baseline", error=baseline)
            if _git(["diff", "--name-only", "HEAD"], worktree):
                return finish(lap, "failure", gate="baseline-source",
                              error="baseline verification changed tracked sources")
            lap.check_clock()

        files = checkout_files(worktree)
        prompt = _implementer_prompt(data, criteria, issue, files)

        r = chat_or_cost_unknown(
            "implementer", [{"role": "user", "content": prompt}], IMPLEMENTER_MODEL,
            max_tokens=IMPLEMENTER_MAX_TOKENS,
            api=IMPLEMENTER_API,
            reasoning_effort=IMPLEMENTER_REASONING_EFFORT,
            max_tokens_field=IMPLEMENTER_MAX_TOKENS_FIELD,
            trace_dir=os.path.join(lap.evdir, "traces"),
            call_id="%s-implementer" % lap.run_id)
        view_observation = prompt_view_discrepancy(files, r.get("usage"))
        if view_observation:
            lap.observations.append(view_observation)
            lap.event("instrument-anomaly", observation=view_observation)
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
            _save_implementer_feedback(issue, detail, mut_results)
            if detail.startswith("apply_incomplete"):

                return finish(lap, "apply_incomplete", gate="mutation-apply", error=detail,
                               caught=detail)
            return finish(lap, "failure", gate="mutation-apply", error=detail,
                          caught="anchor miss: mutations did not apply to the checkout")
        _clear_implementer_feedback(issue)
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

        rev = chat_or_cost_unknown(
            "reviewer", [{"role": "user", "content":
                          agent.reviewer_prompt(branch_diff, criteria,
                                                files="\n".join(checkout_files(worktree)),
                                                brief=design_brief_from(data["body"]))}],
            REVIEWER_MODEL, max_tokens=REVIEWER_MAX_TOKENS,
            api=REVIEWER_API, reasoning_effort=REVIEWER_REASONING_EFFORT,
            max_tokens_field=REVIEWER_MAX_TOKENS_FIELD,
            trace_dir=os.path.join(lap.evdir, "traces"),
            call_id="%s-reviewer" % lap.run_id)
        lap.add_cost(rev["usage"], "reviewer")
        with open(os.path.join(lap.evdir, "review.txt"), "w") as f:
            f.write(rev["content"])
        if rev["finish_reason"] == "length":
            lap.event("review-truncated", finish_reason="length",
                      chars=len(rev["content"]))
            return finish(lap, "failure", gate="review",
                          error="reviewer completion truncated at output limit",
                          caught="reviewer completion truncated (finish_reason=length)")
        verdict_m = re.search(r"VERDICT:\s*(accept|reject)", rev["content"], re.I)
        if not verdict_m or verdict_m.group(1).lower() != "accept":
            # A rejected candidate is still real work: retain it under its own
            # ref (the agent branch survives cleanup, but nothing points at
            # it) and record verdict + sha in the run's artifacts, so the
            # candidate is machine-discoverable instead of tribal knowledge.
            commit = _git(["rev-parse", "HEAD"], worktree)
            repo = os.path.abspath(os.path.expanduser(PRODUCT_REPO))
            ref = "refs/heads/rejected/%s" % lap.run_id
            _git(["update-ref", ref, commit, "0" * 40], repo)
            rejected = {"verdict": "reject" if verdict_m else "unparseable",
                        "commit": commit, "ref": ref, "repository": repo,
                        "inspect_argv": ["git", "-C", repo, "show", commit]}
            lap._dump("rejected.json", rejected)
            lap.event("review-reject", verdict=rejected["verdict"],
                      commit=commit, ref=ref)
            return finish(lap, "failure", gate="review",
                          caught=("reviewer rejected the diff" if verdict_m
                                  else "reviewer gave no parseable verdict"),
                          extra={"rejected_candidate": rejected})
        lap.event("review-accept")
        lap.check_clock()
        pid_file = os.path.join("/tmp", "factory-verify-%s.pid" % lap.run_id)
        evidence = verify.verify_candidate(
            worktree, pid_file, SCENARIOS_DIR, issue=issue,
            evidence_dir=os.path.join(lap.evdir, "verify-commands"))
        lap._dump("verify.json", evidence)
        if evidence["verdict"] != "pass":
            return finish(lap, "failure", gate="verify", error=evidence)
        lap.event("verify-green")
        lap.check_clock()
        # Only literal entries are promises ("create exactly these"); a glob
        # entry is a create surface, so it is not required to have produced
        # anything — a task that never needed it must not fail red here.
        missing_new = [n for n in NEW_FILES
                       if not _is_glob(n)
                       and not os.path.isfile(os.path.join(worktree, n))]
        if missing_new:
            return finish(lap, "failure", gate="new-files",
                          error="required new files absent after verification: %s"
                                % ", ".join(missing_new),
                          caught="lap promised new files but produced %s" % missing_new)
        if _git(["diff", "--name-only", "HEAD"], worktree):
            return finish(lap, "failure", gate="verify-source",
                          error="verification changed tracked sources after review/commit")
        # A local retained ref survives worktree cleanup and future agent retries.
        # No push/PR/merge is implied by awaiting-review.
        if MERGE_MODE == "review":
            repo = os.path.abspath(os.path.expanduser(PRODUCT_REPO))
            commit = _git(["rev-parse", "HEAD"], worktree)
            ref = "refs/heads/review/%s" % lap.run_id
            _git(["update-ref", ref, commit, "0" * 40], repo)
            snapshot = {"merged": False, "pushed": False, "pr": None,
                        "reason": "local verified snapshot awaiting owner review",
                        "repository": repo, "ref": ref, "commit": commit,
                        "tree": _git(["rev-parse", "HEAD^{tree}"], worktree),
                        "source_paths": _git(["diff", "--name-only", "origin/main", "HEAD"], worktree).splitlines(),
                        "diff": os.path.abspath(os.path.join(lap.evdir, "applied.diff")),
                        "inspect_argv": ["git", "-C", repo, "show", commit],
                        "checkout_argv": ["git", "-C", repo, "worktree", "add", "--detach",
                                          "<new-owner-selected-path>", commit]}
            lap._dump("merge.json", snapshot)
            lap.event("review-stop", task_kind=TASK_KIND, ref=ref, commit=commit)
            return finish(lap, "awaiting-review")
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
            script = deploy.build_deploy_script(port=DEPLOY_PORT,
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
            ident = deploy.identity_readback("http://127.0.0.1:%d" % DEPLOY_PORT,
                                             os.path.expanduser(PRODUCT_REPO))
            lap._dump("identity.json", ident)
            if not ident["match"]:
                return finish(lap, "failure", gate="deploy-identity", error=ident)
        try:
            _gh(["issue", "close", str(issue), "--comment",
                 "Merged and deployed by nightshift lap %s (PR: %s)" % (lap.run_id, m.get("pr"))])
        except Exception as e:
            close_error = "%s: %s" % (type(e).__name__, e)
            lap.event("issue-close-failed", error=close_error)
            return finish(lap, "success-close-failed", gate="issue-close",
                          error=close_error)
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
