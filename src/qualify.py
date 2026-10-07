"""Qualify: distill a repo's build/test recipe into `nightshift.recipe/1`.

Design: `factory-docs/QUALIFY-DISTILL-DESIGN_2026-10-07.md`.

Deterministic-first. Everything under "checks" (D1-D12) is stdlib shell work
and costs nothing. The model layer (`propose`, reachable only with `--agent`)
*proposes* argv and never decides pass/fail: a proposal is bound either by a
byte-verified quote at file:line or by a dry-run receipt, and the dry-run is
the binding one.

Nothing here reads the recipe at lap time. `--emit-env` renders it into the
launch env the kernel already trusts: `settings.py` reads FACTORY_NATIVE_CONFIG
from the environment, never from the checkout, so a recipe living inside the
candidate repo could point verify at /bin/true. The store is operator-side;
`--in-repo` publishes a byte-identical copy for readers only.

One documented deviation from the design's gate table: G2 does not require
every verify argv to exit 0 at base. A behavioural oracle is RED at base *by
construction* (the sealed flox oracle exits 1), so a blanket exit-0 rule would
fail every correct recipe. A verify entry therefore declares
`expect_at_base: "exit0" | "red"` (default "exit0"); G2 passes when the
observed exit matches the declaration, and "red" additionally requires a
non-zero exit so a vacuous oracle cannot pass.
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import agent  # noqa: E402
import settings  # noqa: E402
from verify import _SUITE_COUNTERS  # noqa: E402  (one definition of the count contract)

SCHEMA = "nightshift.recipe/1"

# Gate classification, straight from the design's §4 table.
NOGO_GATES = ("G1", "G2", "G3", "G6", "G7", "G8", "G11")
PARTIAL_GATES = ("G3b", "G4", "G5", "G9", "G10")

_BUILD_FILES = ("flake.nix", "flake.lock", "Justfile", "justfile", "Makefile",
                "makefile", "Cargo.toml", "package.json", "pyproject.toml",
                "setup.py", "go.mod", "devbox.json", "shell.nix", "default.nix",
                ".envrc", "devenv.nix")
_DOC_FILES = ("README.md", "README.rst", "README", "CONTRIBUTING.md",
              "CONTRIBUTING", "AGENTS.md", "CLAUDE.md", "docs/CONTRIBUTING.md",
              ".github/CONTRIBUTING.md")
_CI_PATHS = (".github/workflows", ".gitlab-ci.yml", ".circleci/config.yml",
             "azure-pipelines.yml", ".buildkite")
_NIX_ROOTS = ("shells", "nix", "modules", "pkgs", "devenv")
_OUT_DIRS = ("target", "build", "node_modules", "dist", ".venv", "_build", "out")
_CONFIG_ARG = re.compile(r"--config(?:=|\s+)(\S+)")
_SHELL_HOOK = re.compile(r"shellHook\s*=")
_DEFINE_VAR = re.compile(r"define_dev_env_var\s+([A-Za-z_][A-Za-z0-9_]*)")
_EXPORT = re.compile(r"^\s*export\s+([A-Z][A-Z0-9_]*)=")
MAX_HITS = 40


# --------------------------------------------------------------------------
# subprocess / git helpers
# --------------------------------------------------------------------------

def _run(argv, cwd=None, timeout_s=600, out_path=None, err_path=None, env=None):
    """One argv, captured to files. No shell, ever. Returns a result dict."""
    if not argv or not all(isinstance(a, str) and a.strip() for a in argv):
        raise ValueError("argv must be a nonempty array of nonempty strings")
    start = time.monotonic()
    timed_out, code = False, None
    with open(out_path, "w") as out, open(err_path, "w") as err:
        try:
            code = subprocess.run(argv, cwd=cwd, stdout=out, stderr=err,
                                  timeout=timeout_s, env=env).returncode
        except subprocess.TimeoutExpired:
            timed_out = True
        except OSError as exc:
            err.write("spawn error: %s\n" % exc)
    return {"argv": list(argv), "exit": code, "timed_out": timed_out,
            "duration_s": round(time.monotonic() - start, 3)}


def _git(args, cwd, check=True):
    r = subprocess.run(["git"] + list(args), cwd=cwd, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError("git %s failed in %s: %s"
                           % (" ".join(args), cwd, r.stderr.strip()))
    return r.stdout.strip()


def _git_ok(args, cwd):
    return subprocess.run(["git"] + list(args), cwd=cwd,
                          capture_output=True).returncode == 0


def _read(path):
    with open(path, errors="replace") as f:
        return f.read()


def _sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


# --------------------------------------------------------------------------
# D1-D5: static checks (no build, no run)
# --------------------------------------------------------------------------

def check_chain(repo, base, chain=()):
    """D1/G11: every clone in the chain is deep and can resolve <base>.

    A shallow clone dies at prepare when a flake input is `git+file://` (the
    input fetch walks commit history). Bare repos keep the marker at
    `<bare>/shallow`, not `.git/shallow`; both are probed.
    """
    clones = []
    for c in [repo] + [os.path.abspath(os.path.expanduser(x)) for x in chain]:
        if c not in clones:
            clones.append(c)
    rows = []
    for c in clones:
        marker = (os.path.join(c, "shallow") if os.path.isdir(os.path.join(c, "objects"))
                  else os.path.join(c, ".git", "shallow"))
        rows.append({
            "path": c,
            "shallow": _git(["rev-parse", "--is-shallow-repository"], c, check=False) == "true",
            "shallow_marker": os.path.exists(marker),
            "base_resolvable": _git_ok(["cat-file", "-e", base + "^{commit}"], c),
        })
    ok = bool(rows) and all(not r["shallow"] and r["base_resolvable"] for r in rows)
    return {"clones": rows, "ok": ok}


def check_hooks(repo):
    """D2/G9: does a dev-shell-installed hook point at a gitignored config?

    The flox class: the shellHook installs pre-commit hooks into the MAIN
    repo's `.git/hooks` with a RELATIVE `--config` path. The per-worktree
    config symlink dies with the worktree, so the next commit in any worktree
    dies with "No .pre-commit-config.yaml file was found" — and the config is
    gitignored by design (`.gitignore:7`), so a naive presence check passes.
    """
    hp = _git(["config", "--get", "core.hooksPath"], repo, check=False)
    hp = hp or os.path.join(repo, ".git", "hooks")
    if not os.path.isabs(hp):
        hp = os.path.join(repo, hp)
    hooks = []
    if os.path.isdir(hp):
        for name in sorted(os.listdir(hp)):
            path = os.path.join(hp, name)
            if name.endswith(".sample") or not os.path.isfile(path) or not os.access(path, os.X_OK):
                continue
            m = _CONFIG_ARG.search(_read(path))
            cfg = m.group(1) if m else None
            entry = {"name": name, "config": cfg, "config_gitignored": False}
            if cfg and not os.path.isabs(cfg):
                entry["config_gitignored"] = _git_ok(["check-ignore", "-q", cfg], repo)
            hooks.append(entry)
    poisoned = any(h["config"] and h["config_gitignored"] for h in hooks)
    return {"hooks_path": hp, "hooks": hooks, "poisoned": poisoned,
            "escape": "PRE_COMMIT_ALLOW_NO_CONFIG=1" if poisoned else None}


def check_fingerprint(repo):
    """D3: which build systems and docs are here. Decides the agent's doc set."""
    exists = lambda rel: os.path.exists(os.path.join(repo, rel))  # noqa: E731
    ci = []
    for rel in _CI_PATHS:
        path = os.path.join(repo, rel)
        if os.path.isdir(path):
            ci += [os.path.join(rel, n) for n in sorted(os.listdir(path))
                   if n.endswith((".yml", ".yaml"))]
        elif os.path.isfile(path):
            ci.append(rel)
    return {
        "build_files": [f for f in _BUILD_FILES if exists(f)],
        "docs": [f for f in _DOC_FILES if exists(f)],
        "ci": ci,
        "devshell": _nix_candidates(repo),
    }


_DEVSHELL_PREFIXES = ("shells/", "shells", "nix/", "devenv", "dev/", "hacking/")
MAX_NIX_FILES = 40
MAX_NIX_PER_ROOT = 20


def _nix_candidates(repo):
    """Bounded nix-file list, devshell entry points first.

    The cap must not silently drop the file the D4 trap has to cite. Measured
    on flox: a plain alphabetical `[:20]` over the collected paths listed
    `modules/*` and `pkgs/*` and cut `shells/default/default.nix` — the one file
    carrying the shellHook and the `define_dev_env_var` clobbers. Devshell-ish
    roots therefore sort first, and the walk is capped per root so one huge
    tree cannot crowd out the others.
    """
    out = [f for f in ("flake.nix", "shell.nix", "default.nix", "devenv.nix")
           if os.path.exists(os.path.join(repo, f))]
    for root in _NIX_ROOTS:
        d = os.path.join(repo, root)
        if not os.path.isdir(d):
            continue
        found = []
        for r, dirs, files in os.walk(d):
            dirs[:] = [x for x in dirs if x not in (".git", "target", "result")]
            found += [os.path.relpath(os.path.join(r, f), repo)
                      for f in sorted(files) if f.endswith(".nix")]
        out += sorted(found)[:MAX_NIX_PER_ROOT]

    def rank(path):
        devshellish = path.startswith(_DEVSHELL_PREFIXES) or "/" not in path
        return (not devshellish, path.count("/"), path)

    return sorted(dict.fromkeys(out), key=rank)[:MAX_NIX_FILES]


def check_devshell(repo, fingerprint):
    """D4: the shellHook's unconditional re-exports — the clobber mechanism.

    Measured consequence (flox): the hook calls `define_dev_env_var FLOX_BIN
    "${REPO_ROOT}/cli/target/debug/flox"` for every in-tree binary, and that
    helper does an unconditional `export`, so a `*_BIN` override supplied in
    the launch env is INERT and the shared target must be reached structurally
    (a `ln -sfn`) instead.

    Only lines that actually clobber are counted: `define_dev_env_var <NAME>`
    calls, and `export <NAME>=` assignments. The first is the flox mechanism;
    the second catches devshells that assign directly. Both carry their
    file:line so a trap can cite the real thing rather than a sample.
    """
    shell_hooks, clobbers, exports = [], [], []
    for rel in fingerprint["devshell"]:
        try:
            lines = _read(os.path.join(repo, rel)).splitlines()
        except OSError:
            continue
        for i, line in enumerate(lines, 1):
            text = line.strip()[:200]
            if _SHELL_HOOK.search(line):
                shell_hooks.append({"file": rel, "line": i, "text": text})
            m = _DEFINE_VAR.search(line)
            if m:
                clobbers.append({"file": rel, "line": i, "text": text, "name": m.group(1)})
                continue
            m = _EXPORT.match(line)
            if m:
                exports.append({"file": rel, "line": i, "text": text, "name": m.group(1)})
    return {"files": fingerprint["devshell"], "shell_hooks": shell_hooks[:MAX_HITS],
            "clobbers": clobbers[:MAX_HITS], "clobber_count": len(clobbers),
            "exports": exports[:MAX_HITS], "export_count": len(exports)}


def _names_out_dir(rule):
    """Does a .gitignore line name a build-output dir? `/cli/target` and
    `/build/*` both do; the trailing glob is not path syntax here."""
    seg = rule.strip().rstrip("*").rstrip("/").split("/")[-1]
    return seg in _OUT_DIRS


def check_build_writes(repo):
    """D5: are in-tree build outputs declared gitignored?

    This is what makes the shared-target `ln -sfn` step invisible to
    `git status` and to candidate hashing (flox `.gitignore:11` -> /cli/target).
    """
    gi = os.path.join(repo, ".gitignore")
    rules = _read(gi).splitlines() if os.path.exists(gi) else []
    return {
        "present_dirs": [d for d in _OUT_DIRS if os.path.isdir(os.path.join(repo, d))],
        "out_dir_rules": [r.strip() for r in rules if _names_out_dir(r)],
        "rule_count": len(rules),
    }


# --------------------------------------------------------------------------
# provenance (the anti-hallucination rule, made mechanical)
# --------------------------------------------------------------------------

def _quote_ok(repo, src):
    """A quote source must be byte-identical at the line it names."""
    path = os.path.join(repo, src["file"])
    try:
        lines = _read(path).splitlines()
    except OSError:
        return False
    if not 1 <= src["line"] <= len(lines):
        return False
    return src["text"] in lines[src["line"] - 1]


def _recorded_exit(receipt_path):
    with open(receipt_path) as f:
        return json.load(f)["exit"]


def _dryrun_ok(repo_state_dir, src):
    """A dry-run source must name a receipt that exists whose exit matches."""
    p = src.get("evidence") or ""
    p = p if os.path.isabs(p) else os.path.join(repo_state_dir, p)
    try:
        return os.path.isfile(p) and src.get("exit") == _recorded_exit(p)
    except (OSError, ValueError, KeyError):
        return False


def _source_ok(repo, state_dir, src, argv=None):
    """(ok, why). The three legal kinds, and nothing else."""
    if not isinstance(src, dict):
        return False, "missing source"
    kind = src.get("kind")
    if kind == "quote":
        if not (isinstance(src.get("file"), str) and isinstance(src.get("line"), int)
                and isinstance(src.get("text"), str)):
            return False, "quote source needs file/line/text"
        if _quote_ok(repo, src):
            return True, "quote verified at %s:%s" % (src["file"], src["line"])
        return False, "quote not byte-identical at %s:%s" % (src.get("file"), src.get("line"))
    if kind == "dryrun":
        if not isinstance(src.get("evidence"), str) or not isinstance(src.get("exit"), int):
            return False, "dryrun source needs evidence/exit"
        if _dryrun_ok(state_dir, src):
            return True, "dryrun receipt exit=%s matches" % src["exit"]
        return False, "dryrun receipt missing or exit mismatch"
    if kind == "operator":
        # Exactly one thing is allowed here: an argv whose first token is an
        # absolute path OUTSIDE the product repo (an operator-supplied oracle).
        # A model-authored command can therefore never be `operator`.
        first = (argv or src.get("argv") or [""])[0]
        if not os.path.isabs(first):
            return False, "operator source requires an absolute first token"
        if os.path.abspath(first).startswith(os.path.abspath(repo) + os.sep):
            return False, "operator source must live outside the product repo"
        return True, "operator-supplied oracle outside the repo"
    return False, "unknown source kind %r" % (kind,)


def check_provenance(repo, state_dir, entries):
    """D12/G7 over every prepare/verify entry."""
    rows = []
    for phase, entry in entries:
        ok, why = _source_ok(repo, state_dir, entry.get("source"), entry.get("argv"))
        rows.append({"phase": phase, "argv": entry.get("argv"), "ok": ok, "why": why})
    return {"entries": rows, "ok": bool(rows) and all(r["ok"] for r in rows)}


# --------------------------------------------------------------------------
# D6-D9: run checks (build + suite)
# --------------------------------------------------------------------------

def _suite_count(runner, out_path):
    """The kernel's own parser for the declared runner — imported, not copied."""
    return _SUITE_COUNTERS[runner](_read(out_path))


def run_suite(argv, cwd, runner, timeout_s, evdir, tag, env=None):
    out = os.path.join(evdir, tag + ".stdout")
    err = os.path.join(evdir, tag + ".stderr")
    res = _run(argv, cwd=cwd, timeout_s=timeout_s, out_path=out, err_path=err, env=env)
    res["count"] = _suite_count(runner, out)
    res["stdout"], res["stderr"] = out, err
    res["vacuous"] = res["count"] is None
    return res


def netns_argv(argv):
    """Dead-egress wrapper. `lo` must come up: flox is 218/0 with loopback and
    194/24 with it down, so a netns rig that forgets `lo` reports a false RED."""
    return ["unshare", "-rn", "bash", "-c",
            "ip link set lo up; exec \"$@\"", "--"] + list(argv)


def write_receipt(evdir, tag, res, **extra):
    """One receipt per executed argv: the dry-run branch's evidence."""
    receipt = dict(res)
    receipt.update(extra)
    path = os.path.join(evdir, tag + ".json")
    with open(path, "w") as f:
        json.dump(receipt, f, indent=1)
    return path


def _throwaway_worktree(repo, base, path):
    r = subprocess.run(["git", "worktree", "add", "--detach", path, base],
                       cwd=repo, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError("worktree add failed: %s" % r.stderr.strip())
    return path


def _remove_worktree(repo, path):
    subprocess.run(["git", "worktree", "remove", "--force", path],
                   cwd=repo, capture_output=True)
    subprocess.run(["git", "worktree", "prune"], cwd=repo, capture_output=True)


def dry_run(repo, base, prepare, verify, suite_index, runner, suite_timeout_s,
            evdir, env, *, netns=False, probe=None, hooks_ab=True, hooks_poisoned=False):
    """G1-G6, G3b, G9. All in ONE throwaway worktree at the pinned base."""
    gates, worktree = {}, None
    worktree = os.path.join(tempfile.mkdtemp(prefix="nightshift-qualify-"), "wt")
    try:
        _throwaway_worktree(repo, base, worktree)
        run_env = dict(os.environ)
        run_env.update(env)

        # ---- G1: prepare dry-run ------------------------------------------
        ok = True
        for i, entry in enumerate(prepare):
            res = _run(entry["argv"], cwd=worktree, timeout_s=entry.get("timeout_s", 600),
                       out_path=os.path.join(evdir, "prepare-%d.stdout" % i),
                       err_path=os.path.join(evdir, "prepare-%d.stderr" % i), env=run_env)
            receipt = write_receipt(evdir, "prepare-%d" % i, res)
            entry["source"] = {"kind": "dryrun", "exit": res["exit"],
                               "duration_s": res["duration_s"], "evidence": receipt}
            ok = ok and res["exit"] == 0
        gates["G1"] = "pass" if ok else "fail"

        # ---- G2: verify dry-run against each entry's declared base verdict -
        ver_rows, g2 = [], True
        for i, entry in enumerate(verify):
            expect = entry.get("expect_at_base", "exit0")
            if expect not in ("exit0", "red"):
                g2 = False
                entry["observed_at_base"] = {"error": "bad expect_at_base %r" % expect}
                continue
            res = _run(entry["argv"], cwd=worktree, timeout_s=entry.get("timeout_s", 600),
                       out_path=os.path.join(evdir, "verify-%d.stdout" % i),
                       err_path=os.path.join(evdir, "verify-%d.stderr" % i), env=run_env)
            receipt = write_receipt(evdir, "verify-%d" % i, res)
            observed = {"exit": res["exit"], "duration_s": res["duration_s"],
                        "evidence": receipt, "expect_at_base": expect}
            if expect == "exit0":
                good = res["exit"] == 0
                if i == suite_index:
                    count = _suite_count(runner, os.path.join(evdir, "verify-%d.stdout" % i))
                    observed["count"] = count
                    good = good and count is not None
            else:
                # a "red" oracle must actually be red, or it is vacuous
                good = res["exit"] not in (0, None)
            entry["observed_at_base"] = observed
            if entry.get("source", {}).get("kind") != "operator":
                entry["source"] = {"kind": "dryrun", "exit": res["exit"],
                                   "duration_s": res["duration_s"], "evidence": receipt}
            ver_rows.append(res)
            g2 = g2 and good
        gates["G2"] = "pass" if g2 else "fail"

        # ---- G3: count authority on the suite argv -------------------------
        suite_out = os.path.join(evdir, "verify-%d.stdout" % suite_index)
        if 0 <= suite_index < len(verify) and os.path.exists(suite_out):
            count = _suite_count(runner, suite_out)
            gates["G3"] = "pass" if (count is not None and count >= 1
                                     and ver_rows[suite_index]["exit"] == 0) else "fail"
            base_count = count
        else:
            gates["G3"], base_count = "fail", None

        # ---- G4: determinism (G2's suite run is run #1) --------------------
        suite_entry = verify[suite_index] if 0 <= suite_index < len(verify) else None
        if suite_entry is not None and gates["G3"] == "pass":
            again = run_suite(suite_entry["argv"], worktree, runner, suite_timeout_s,
                              evdir, "suite-det", env=run_env)
            same = (again["exit"] == ver_rows[suite_index]["exit"]
                    and again["count"] == base_count)
            write_receipt(evdir, "suite-det", again, base_exit=ver_rows[suite_index]["exit"],
                          base_count=base_count, identical=same)
            gates["G4"] = "pass" if same else "fail"
        else:
            gates["G4"] = "skip"

        # ---- G5: hermeticity under a dead-egress netns ---------------------
        if suite_entry is not None and gates["G3"] == "pass" and netns:
            ns = run_suite(netns_argv(suite_entry["argv"]), worktree, runner,
                           suite_timeout_s, evdir, "suite-netns", env=run_env)
            gates["G5"] = "pass" if (ns["exit"] == 0 and ns["count"] == base_count) else "fail"
            write_receipt(evdir, "suite-netns", ns, base_count=base_count,
                          argv_wrapped=netns_argv(suite_entry["argv"]),
                          lo_required=True, gate=gates["G5"])
        else:
            gates["G5"] = "skip"

        # ---- G6: build hygiene --------------------------------------------
        dirty = _git(["status", "--porcelain"], worktree)
        gates["G6"] = "pass" if not dirty else "fail"

        # ---- G3b: collection liveness (the free RED half) ------------------
        gates["G3b"] = "skip"
        if probe and base_count:
            gates["G3b"] = _collection_probe(worktree, probe, suite_entry, runner,
                                             suite_timeout_s, evdir, run_env, base_count)

        # ---- G9: hook trap neutralised, proven A/B -------------------------
        # Last, because its probes add empty commits to the throwaway HEAD and
        # a suite that reads `git rev-parse HEAD` (flox's FLOX_VERSION does)
        # must not be measured after that.
        if not hooks_poisoned:
            gates["G9"] = "pass"          # nothing to neutralise
            hook_finding = None
        elif not hooks_ab:
            gates["G9"], hook_finding = "skip", None
        else:
            hooks = _hooks_ab(worktree, env, evdir)
            gates["G9"], hook_finding = hooks["gate"], hooks["finding"]
    finally:
        if worktree:
            _remove_worktree(repo, worktree)
            shutil.rmtree(os.path.dirname(worktree), ignore_errors=True)
    return gates, hook_finding


def _hooks_ab(worktree, env, evdir):
    """G9, two states, because the flox trap has two.

    The devshell's shellHook writes `.pre-commit-config.yaml` into the worktree
    (which is exactly why `.gitignore:7` ignores it) and installs hooks into the
    MAIN repo's shared `.git/hooks` with a RELATIVE `--config` path. So:

    (a) **config absent** — run 2's state, and the state of every commit that
        happens before a devshell activation in this worktree (a `bug` lap
        commits before verify/prepare runs). `_validate_config` finds no file;
        the escape must turn that failure into a pass. This is what G9 gates.
    (b) **config present** — the state after prepare has activated the devshell
        in this worktree (which is where an `enhancement` lap's baseline
        `verify_candidate` leaves it). pre-commit then runs for real and the
        repo's own commit-msg linter applies to the kernel's literal
        `Implement issue N` message. The escape does NOT cover this, so it is
        recorded as a finding rather than folded into the gate: the linter is
        the repo's property and the kernel's message is not configurable here.

    Both use `--allow-empty`, so nothing tracked is touched either way.
    """
    ident = ["-c", "user.email=qualify@nightshift", "-c", "user.name=qualify"]
    escape = {k: v for k, v in env.items() if k == "PRE_COMMIT_ALLOW_NO_CONFIG"}
    if not escape:
        return {"gate": "skip", "finding": None}

    config = os.path.join(worktree, ".pre-commit-config.yaml")
    had_config = _read(config) if os.path.isfile(config) else None

    # (a) config absent: the documented failure state
    if had_config is not None:
        os.remove(config)
    without = dict(os.environ)
    without.pop("PRE_COMMIT_ALLOW_NO_CONFIG", None)
    with_ = dict(os.environ)
    with_.update(env)
    a = _commit_probe(worktree, ident, without, evdir, "g9-a", "Implement issue 0")
    b = _commit_probe(worktree, ident, with_, evdir, "g9-b", "Implement issue 0")
    gate = "pass" if (a["exit"] not in (0, None) and b["exit"] == 0) else "fail"

    # (b) config present: does the repo's own commit-msg linter accept the
    # kernel's message shape? Informational, and the finding is the point.
    finding = None
    if had_config is not None:
        _write_file(config, had_config)
        c = _commit_probe(worktree, ident, with_, evdir, "g9-c", "Implement issue 0")
        if c["exit"] != 0:
            # git normalizes any hook failure to exit 1, so the hook's own
            # message is the discriminator between "config missing" and
            # "the linter rejected this message".
            finding = {"state": "config-present-after-prepare",
                       "symptom": "the devshell-generated .pre-commit-config.yaml "
                                  "activates the repo's commit-msg linter, which "
                                  "rejects the kernel's commit message",
                       "kernel_message": "Implement issue N",
                       "exit": c["exit"],
                       "stderr_tail": c["stderr_tail"],
                       "evidence": c["receipt"]}
    return {"gate": gate, "finding": finding}


def _write_file(path, text):
    with open(path, "w") as f:
        f.write(text)


def _commit_probe(worktree, ident, env, evdir, tag, message):
    res = _run(["git"] + ident + ["commit", "--allow-empty", "-m", message],
               cwd=worktree, timeout_s=120, out_path=os.path.join(evdir, tag + ".stdout"),
               err_path=os.path.join(evdir, tag + ".stderr"), env=env)
    res["receipt"] = write_receipt(evdir, tag, res)
    res["stderr_tail"] = _read(os.path.join(evdir, tag + ".stderr"))[-600:]
    return res


_PROBE_TOKEN = re.compile(r"[A-Za-z_][A-Za-z0-9_]{3,}")
_PROBE_STOPWORDS = frozenset((
    "test", "tests", "fn", "def", "mod", "panic", "assert", "assert_eq", "expect",
    "fail", "fails", "failed", "true", "false", "self", "class", "void", "import",
    "from", "return", "raise", "with", "this", "that", "node", "line",
))


def _probe_tokens(snippet):
    """Identifier-like tokens from the probe snippet: what the runner prints
    back when it collects the injected test.

    A token merely has to be DISTINCTIVE, not unique: the check below is a
    secondary confirmation on top of `exit != 0`, and an over-eager match can
    only ever make the gate more permissive, never a false reject. The
    stoplist removes the words every test snippet contains.
    """
    return {t for t in _PROBE_TOKEN.findall(snippet)
            if t.lower() not in _PROBE_STOPWORDS}


def _collection_probe(worktree, probe, suite_entry, runner, timeout_s, evdir,
                      run_env, base_count):
    """G3b: append one failing test, require the suite to go red AND to show it
    collected the injected test.

    The design's literal rule was `exit != 0 and count == N0 + 1`. Measured
    against flox, that rule is wrong for a *passed-only* adapter: the cargo
    adapter's TAP total is the count of tests that PASSED, so an injected
    failing test leaves the total at N0 (218 -> 218) while cargo reports
    `218 passed; 1 failed` and exits 101. The rule below keeps the design's
    intent (the count is live, not cached; the suite can go red) and works for
    both count semantics:

      * exit != 0, and
      * the injected test is visible in the suite's own output — a token from
        the snippet appears in what the runner printed, which is what proves
        the run COLLECTED it rather than merely failing for some other reason, and
      * the total is consistent with the injection: `N0 + 1` (tests-run
        semantics: tap, pytest) or `N0` (passed-only semantics: the adapter).

    Runs in the throwaway worktree and restores the file, so nothing tracked
    outside it is ever touched.
    """
    target = os.path.join(worktree, probe["target"])
    try:
        with open(target, "a") as f:
            f.write("\n" + probe["snippet"] + "\n")
    except OSError:
        return "skip"
    try:
        res = run_suite(suite_entry["argv"], worktree, runner, timeout_s, evdir,
                        "suite-probe", env=run_env)
        output = _read(res["stdout"]) + _read(res["stderr"])
        tokens = _probe_tokens(probe["snippet"])
        seen = sorted(t for t in tokens if t in output)
        count_ok = res["count"] in (base_count + 1, base_count)
        result = {"exit": res["exit"], "count": res["count"], "base_count": base_count,
                  "count_semantics": ("tests-run" if res["count"] == base_count + 1
                                      else "passed-only" if res["count"] == base_count
                                      else "inconsistent"),
                  "probe_visible": bool(seen), "probe_tokens_seen": seen}
        write_receipt(evdir, "suite-probe", res, **result)
        probe["result"] = result
        return "pass" if (res["exit"] not in (0, None) and count_ok and seen) else "fail"
    finally:
        subprocess.run(["git", "checkout", "--", probe["target"]], cwd=worktree,
                       capture_output=True)


# --------------------------------------------------------------------------
# G8: the kernel's own guards decide whether the emitted config is legal
# --------------------------------------------------------------------------

def check_config_parses(config):
    src_dir = os.path.dirname(os.path.abspath(__file__))
    env = dict(os.environ)
    env["FACTORY_NATIVE_CONFIG"] = json.dumps(config, separators=(",", ":"))
    r = subprocess.run([sys.executable, "-c", "import settings"], cwd=src_dir,
                       capture_output=True, text=True, env=env)
    return {"ok": r.returncode == 0, "stderr": r.stderr.strip()[-500:]}


# --------------------------------------------------------------------------
# recipe assembly
# --------------------------------------------------------------------------

def build_config(prepare, verify, suite_index, runner, suite_timeout_s,
                 task_kind, merge_mode):
    """The kernel's FACTORY_NATIVE_CONFIG, in the key order the launch envs use."""
    suite = verify[suite_index]["argv"]
    if [e["argv"] for e in verify].count(suite) != 1:
        raise ValueError("suite must designate exactly one verify command")
    return {
        "prepare": [e["argv"] for e in prepare],
        "verify": [e["argv"] for e in verify],
        "suite": suite,
        "suite_runner": runner,
        "suite_timeout_s": suite_timeout_s,
        "task_kind": task_kind,
        "merge_mode": merge_mode,
    }


def compute_status(gate):
    if any(gate.get(g) != "pass" for g in NOGO_GATES):
        return "no-go"
    if any(gate.get(g) != "pass" for g in PARTIAL_GATES):
        return "partial"
    return "qualified"


def gap_from(gate):
    bad = [g for g in NOGO_GATES + PARTIAL_GATES if gate.get(g) not in ("pass", None)]
    return ",".join(bad) if bad else None


def slug_for(origin):
    """`github.com__flox__flox` from any origin shape.

    Three shapes reach here: a bare `owner/repo` (what GITHUB_REPO carries and
    what a GitHub-sourced recipe records), a host-qualified remote
    (`git@github.com:flox/flox.git`, `https://github.com/flox/flox`), and a
    local path (no host at all). Only the first two get a host segment.
    """
    o = origin.strip()
    m = re.match(r"^(?:git@|ssh://git@|https?://)([^/:]+)[:/]+([^/]+)/([^/]+?)(?:\.git)?$", o)
    if m:
        return "%s__%s__%s" % (m.group(1), m.group(2), m.group(3))
    if re.fullmatch(r"[A-Za-z0-9._-]+/[A-Za-z0-9._-]+", o):
        owner, name = o.split("/")
        return "github.com__%s__%s" % (owner, name.removesuffix(".git"))
    return re.sub(r"[^A-Za-z0-9._-]+", "_", o.strip("/")) or "repo"


def recipe_path(origin, recipes_dir=None):
    d = os.path.expanduser(recipes_dir or settings.RECIPES_DIR)
    return os.path.join(d, slug_for(origin) + ".json")


def emit_env(recipe, path=None):
    """Render the recipe into the launch env the kernel already trusts.

    The header carries the recipe file's own sha256, computed here from the
    bytes on disk, so a reader can re-derive it with `sha256sum` and nothing
    self-referential is stored inside the file.
    """
    repo, config = recipe["repo"], recipe["config"]
    digest = _sha256(path) if path and os.path.isfile(path) else "-"
    lines = [
        "# generated by qualify from %s" % (path or "<recipe>"),
        "# recipe sha256: %s   base: %s" % (digest, repo["base"]),
    ]
    if config:
        lines.append("export FACTORY_NATIVE_CONFIG='%s'"
                     % json.dumps(config, separators=(",", ":")))
    else:
        # No commands were bound, so there is no config to export. Emitting
        # `export FACTORY_NATIVE_CONFIG='null'` would make settings.py raise at
        # import; a comment is the honest shape for "nothing qualified".
        lines.append("# FACTORY_NATIVE_CONFIG not emitted: status=%s, no commands bound"
                     % recipe.get("status"))
    lines += [
        "export PRODUCT_REPO=%s" % repo["path"],
        "export GITHUB_REPO=%s" % repo["origin"],
        "export DEPLOY_MODE=%s" % recipe["deploy_mode"],
    ]
    lines += ["export %s=%s" % (k, v) for k, v in sorted(recipe["env"].items())]
    lines += [
        "",
        "# ---- per-task keys, authored by the operator, NOT by qualify ----",
        "# export FACTORY_TASK_FILE=…",
        "# export CODE_PATHS=…",
        "# export FACTORY_NEW_FILES=…        (unset = creation off)",
        "# export SCENARIOS_DIR=…",
    ]
    return "\n".join(lines) + "\n"


def render(recipe):
    """The human/agent-readable view, rendered on demand and never stored."""
    r = recipe
    out = ["# %s — nightshift recipe (`%s`)" % (r["repo"]["origin"], r["schema"]),
           "",
           "- base: `%s`" % r["repo"]["base"],
           "- status: **%s**%s" % (r["status"],
                                   " (gaps: %s)" % r["gap"] if r.get("gap") else ""),
           "- qualified_at: %s" % r["qualified_at"],
           "- gates: %s" % ", ".join("%s=%s" % kv for kv in sorted(r["gate"].items())),
           "",
           "## prepare"]
    for e in r["prepare"]:
        out.append("- `%s`%s" % (" ".join(e["argv"]),
                                 "  — %s" % e["hint"] if e.get("hint") else ""))
    out += ["", "## verify"]
    for i, e in enumerate(r["verify"]):
        mark = " **(suite)**" if i == r["suite_index"] else ""
        out.append("- `%s`%s — base: %s" % (" ".join(e["argv"]), mark,
                                            e.get("observed_at_base", {}).get("exit")))
    out += ["", "suite_runner `%s`, suite_timeout_s `%s`, network `%s`"
            % (r["suite_runner"], r["suite_timeout_s"], r["network"])]
    if r["env"]:
        out += ["", "## env"] + ["- `%s=%s`" % kv for kv in sorted(r["env"].items())]
    if r["traps"]:
        out += ["", "## traps"]
        for t in r["traps"]:
            out.append("- **%s** (%s): %s\n  - evidence: %s\n  - escape: %s"
                       % (t.get("id"), t.get("kind"), t.get("symptom"),
                          t.get("evidence"), t.get("escape")))
    out += ["", "## what this recipe does NOT carry",
            "Task text, acceptance criteria, CODE_PATHS and the oracle's authoring are",
            "per-task operator work. This recipe answers *how to build and test* only."]
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------
# the agent layer: one call, proposal only
# --------------------------------------------------------------------------

def doc_bundle(repo, fingerprint, limit=200_000):
    """The doc set D3 selected, concatenated with file:line anchors."""
    parts, total = [], 0
    for rel in fingerprint["docs"] + fingerprint["build_files"] + fingerprint["ci"] + fingerprint["devshell"]:
        path = os.path.join(repo, rel)
        if not os.path.isfile(path):
            continue
        text = _read(path)
        if total + len(text) > limit:
            text = text[:limit - total]
        parts.append("===== %s =====\n%s" % (rel, text))
        total += len(text)
        if total >= limit:
            break
    return "\n\n".join(parts), total


def propose(repo, fingerprint, hooks, devshell, base, evdir, limit=200_000):
    """A1-A7. ONE call; returns a proposal the deterministic layer then binds."""
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "prompts", "qualifier.txt")) as f:
        prompt = f.read()
    bundle, size = doc_bundle(repo, fingerprint, limit)
    for k, v in {
        "{{base}}": base,
        "{{fingerprint}}": json.dumps(fingerprint, indent=1),
        "{{hooks}}": json.dumps(hooks, indent=1),
        "{{devshell}}": json.dumps(devshell, indent=1),
        "{{docs}}": bundle,
    }.items():
        prompt = prompt.replace(k, v)
    r = agent.chat([{"role": "user", "content": prompt}], settings.QUALIFIER_MODEL,
                   max_tokens=settings.QUALIFIER_MAX_TOKENS,
                   api=settings.QUALIFIER_API,
                   reasoning_effort=settings.QUALIFIER_REASONING_EFFORT,
                   trace_dir=evdir, call_id="qualifier")
    with open(os.path.join(evdir, "qualifier_raw.txt"), "w") as f:
        f.write(r["content"])
    return parse_proposal(r["content"]), r.get("usage") or {}, size


def parse_proposal(text):
    """Strict-ish JSON extraction: fenced block first, then the outer object."""
    m = re.search(r"```(?:json)?\s*\n(.*?)```", text, re.S)
    raw = m.group(1) if m else text
    try:
        return json.loads(raw)
    except ValueError:
        i, j = raw.find("{"), raw.rfind("}")
        if i >= 0 and j > i:
            try:
                return json.loads(raw[i:j + 1])
            except ValueError:
                pass
    return {"abstain": True, "gap": "proposal was not parseable JSON"}


# --------------------------------------------------------------------------
# orchestration
# --------------------------------------------------------------------------

def qualify(repo, *, seed=None, chain=(), use_agent=False, netns=False, probe=False,
            hooks_ab=True, dry_run_enabled=True, evdir=None, out=None,
            agent_limit=200_000):
    """Run the pass. Deterministic checks always; the model only with use_agent."""
    repo = os.path.abspath(os.path.expanduser(repo))
    seed = dict(seed or {})
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    evdir = os.path.abspath(evdir or os.path.join(settings.STATE_DIR, "qualify", run_id))
    os.makedirs(evdir, exist_ok=True)

    base = seed.get("base") or _git(["rev-parse", "HEAD"], repo)
    origin = seed.get("origin") or _origin(repo)
    chain = list(chain) + list(seed.get("chain") or [])

    checks, gate = {}, {}

    checks["chain"] = check_chain(repo, base, chain)
    gate["G11"] = "pass" if checks["chain"]["ok"] else "fail"
    checks["hooks"] = check_hooks(repo)
    checks["fingerprint"] = check_fingerprint(repo)
    checks["devshell"] = check_devshell(repo, checks["fingerprint"])
    checks["build_writes"] = check_build_writes(repo)

    proposal, usage, doc_chars = None, {}, 0
    if use_agent:
        proposal, usage, doc_chars = propose(repo, checks["fingerprint"], checks["hooks"],
                                             checks["devshell"], base, evdir, agent_limit)
        checks["proposal"] = {"usage": usage, "doc_chars": doc_chars}

    # The model proposes; the operator seed and the deterministic layer win on
    # everything the model is not allowed to decide.
    merged = dict(seed)
    if proposal:
        if proposal.get("abstain"):
            merged.setdefault("abstain", True)
            merged.setdefault("gap", proposal.get("gap"))
        for key in ("prepare", "verify", "env", "traps", "code_roots", "oracle",
                    "adapter", "collection_probe", "runner_gap", "suite_runner"):
            if proposal.get(key) and not merged.get(key):
                merged[key] = proposal[key]
        for key in ("suite_index", "suite_timeout_s", "deploy_mode",
                    "task_kind_default", "merge_mode_default"):
            if key not in merged and key in proposal:
                merged[key] = proposal[key]

    prepare = [{"argv": e["argv"], "timeout_s": e.get("timeout_s", 600),
                **({"hint": e["hint"]} if e.get("hint") else {}),
                **({"source": e["source"]} if e.get("source") else {})}
               for e in merged.get("prepare", [])]
    verify = [{"argv": e["argv"], "timeout_s": e.get("timeout_s", 600),
               "expect_at_base": e.get("expect_at_base", "exit0"),
               **({"source": e["source"]} if e.get("source") else {})}
              for e in merged.get("verify", [])]
    suite_index = int(merged.get("suite_index", 0))
    runner = merged.get("suite_runner", "tap")
    if runner not in _SUITE_COUNTERS:
        runner = "tap"
    suite_timeout_s = int(merged.get("suite_timeout_s", 600))
    env = dict(merged.get("env") or {})
    config = None

    if not prepare and not verify:
        # A7: nothing to propose is a first-class no-go, not a failure.
        gate.update({"G1": "skip", "G2": "skip", "G3": "skip", "G3b": "skip",
                     "G4": "skip", "G5": "skip", "G6": "skip", "G7": "skip",
                     "G8": "skip", "G9": "skip", "G10": "skip"})
        gap = merged.get("gap") or ("no build/test commands proposed; no docs named them"
                                    if not checks["fingerprint"]["docs"] else
                                    "no commands proposed (run with --agent or --seed)")
    else:
        if dry_run_enabled:
            ran, hook_finding = dry_run(repo, base, prepare, verify, suite_index, runner,
                                        suite_timeout_s, evdir, env, netns=netns,
                                        probe=merged.get("collection_probe") if probe else None,
                                        hooks_ab=hooks_ab,
                                        hooks_poisoned=checks["hooks"]["poisoned"])
            gate.update(ran)
            if hook_finding:
                checks["hooks"]["commit_msg_linter"] = hook_finding
        else:
            gate.update({g: "skip" for g in ("G1", "G2", "G3", "G3b", "G4", "G5",
                                             "G6", "G9")})
        prov = check_provenance(repo, evdir,
                                [("prepare", e) for e in prepare]
                                + [("verify", e) for e in verify])
        checks["provenance"] = prov
        gate["G7"] = "pass" if prov["ok"] else "fail"
        try:
            config = build_config(prepare, verify, suite_index, runner,
                                  suite_timeout_s, merged.get("task_kind_default", "bug"),
                                  merged.get("merge_mode_default", "review"))
            parsed = check_config_parses(config)
            gate["G8"] = "pass" if parsed["ok"] else "fail"
        except ValueError as exc:
            config, parsed = None, {"ok": False, "stderr": str(exc)}
            gate["G8"] = "fail"
        checks["config_parse"] = parsed
        gate["G10"] = _adapter_gate(merged, evdir)
        gap = merged.get("gap") or gap_from(gate)

    status = compute_status(gate)
    recipe = {
        "schema": SCHEMA,
        "repo": {"origin": origin, "base": base, "path": repo,
                 "chain": [c["path"] for c in checks["chain"]["clones"]]},
        "qualified_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "status": status,
        "gap": gap,
        "evidence_root": evdir,
        "env": env,
        "prepare": prepare,
        "verify": verify,
        "suite_index": suite_index,
        "suite_runner": runner,
        "suite_timeout_s": suite_timeout_s,
        "runner_gap": merged.get("runner_gap"),
        "adapter": merged.get("adapter"),
        "collection_probe": merged.get("collection_probe"),
        "code_roots": merged.get("code_roots") or [],
        "deploy_mode": merged.get("deploy_mode", "none"),
        "task_kind_default": merged.get("task_kind_default", "bug"),
        "merge_mode_default": merged.get("merge_mode_default", "review"),
        "network": merged.get("network", "loopback" if netns else "unknown"),
        "hermetic": {"lo_required": True,
                     "egress_dead_green": gate.get("G5") == "pass"},
        "traps": merged.get("traps") or _traps_from_checks(checks),
        "oracle": merged.get("oracle") or {"strategy": "none", "location": None,
                                           "authored_by": None},
        "checks": checks,
        "gate": gate,
        "usage": usage,
    }
    recipe["config"] = config if prepare or verify else None
    if out:
        write_recipe(recipe, out)
    return recipe


def _adapter_gate(merged, evdir=None):
    """G10: an adapter must not be able to green on zero tests.

    The zero-tests half is measurable without knowing anything about the
    adapter's interface: run it in an empty scratch directory, where the
    underlying runner cannot produce a single `test result:` line, and require
    the vacuous signature (`# tests 0` plus a non-zero exit). An adapter that
    prints a green there is the vacuous-green hole itself. The "expected total
    on synthetic input" half needs a runner-specific fixture and stays with the
    operator's `self_test` declaration.
    """
    adapter = merged.get("adapter") or {}
    if adapter.get("self_test") == "pass":
        return "pass"
    path = adapter.get("path")
    if not path or evdir is None or not os.path.isfile(path):
        return "skip"
    if adapter.get("zero_tests_probe") is False:
        return "skip"
    scratch = tempfile.mkdtemp(prefix="qualify-zerotests-")
    try:
        res = _run([path], cwd=scratch, timeout_s=120,
                   out_path=os.path.join(evdir, "adapter-zerotests.stdout"),
                   err_path=os.path.join(evdir, "adapter-zerotests.stderr"))
        out = _read(os.path.join(evdir, "adapter-zerotests.stdout")).strip()
        receipt = write_receipt(evdir, "adapter-zerotests", res, stdout=out)
        adapter["zero_tests"] = {"exit": res["exit"], "stdout": out, "evidence": receipt}
        merged["adapter"] = adapter
        return "pass" if res["exit"] not in (0, None) and out == "# tests 0" else "fail"
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def _traps_from_checks(checks):
    """Trap prose from the deterministic findings. No gate depends on it."""
    traps = []
    if not checks["chain"]["ok"]:
        traps.append({"id": "shallow-chain", "kind": "operator",
                      "symptom": "prepare fails walking a flake input's history",
                      "evidence": "D1 chain check",
                      "escape": "deepen every clone in repo.chain (git fetch --unshallow)"})
    if checks["hooks"]["poisoned"]:
        traps.append({"id": "hooks-clobber", "kind": "env",
                      "symptom": "commit fails: the hook's relative --config is gitignored",
                      "evidence": "D2: %s" % json.dumps(checks["hooks"]["hooks"]),
                      "escape": checks["hooks"]["escape"]})
    if checks["hooks"].get("commit_msg_linter"):
        traps.append({"id": "commit-msg-linter", "kind": "operator",
                      "symptom": "commit fails: the devshell generated "
                                 ".pre-commit-config.yaml during prepare, so the "
                                 "repo's commit-msg linter runs for real and "
                                 "rejects the kernel's literal commit message",
                      "evidence": json.dumps(checks["hooks"]["commit_msg_linter"]),
                      "escape": "an enhancement lap runs verify_candidate (prepare) "
                                "BEFORE the commit, so this fires there; a bug lap "
                                "commits first and does not reach it"})
    if checks["devshell"]["clobber_count"]:
        traps.append({"id": "devshell-env-clobber", "kind": "structural",
                      "symptom": "launch-env overrides are inert; the shellHook re-exports",
                      "evidence": "D4: %s" % json.dumps(checks["devshell"]["clobbers"][:5]),
                      "escape": "reach the shared target structurally (ln -sfn), not by env"})
    return traps


def _origin(repo):
    """`owner/repo` when origin is a real remote; the path itself when local."""
    url = _git(["remote", "get-url", "origin"], repo, check=False)
    if not url:
        return repo
    m = re.match(r"^(?:git@|ssh://git@|https?://)?([^/:]+)[:/]([^/]+/[^/]+?)(?:\.git)?$", url)
    return m.group(2) if m else url


def write_recipe(recipe, path):
    """Write the recipe. Its sha256 is the file's own hash, computed by the
    emitter from the bytes on disk — never stored inside the file, so there is
    no self-reference to get wrong."""
    path = os.path.abspath(os.path.expanduser(path))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(json.dumps(recipe, indent=1) + "\n")
    return path


def load_recipe(path):
    with open(os.path.expanduser(path)) as f:
        return json.load(f)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="qualify",
        description="Distill a repo's build/test recipe into nightshift.recipe/1.")
    ap.add_argument("repo", nargs="?", help="path to the product repo clone")
    ap.add_argument("--agent", action="store_true",
                    help="allow ONE qualifier model call (default: deterministic only)")
    ap.add_argument("--seed", help="operator-authored JSON seed (prepare/verify/env/…)")
    ap.add_argument("--chain", default="", help="comma-separated extra clones in the chain")
    ap.add_argument("--netns", action="store_true", help="run the G5 dead-egress probe")
    ap.add_argument("--probe", action="store_true", help="run the G3b collection probe")
    ap.add_argument("--no-hooks-ab", action="store_true", help="skip the G9 A/B commit test")
    ap.add_argument("--no-dry-run", action="store_true",
                    help="static checks only (no build, no suite run)")
    ap.add_argument("--out", help="recipe path (default $NIGHTSHIFT_RECIPES_DIR/<slug>.json)")
    ap.add_argument("--in-repo", action="store_true",
                    help="also publish a byte-identical copy at <repo>/.nightshift/recipe.json")
    ap.add_argument("--emit-env", nargs="?", const="-", metavar="PATH",
                    help="print the launch-env fragment ('-' = stdout)")
    ap.add_argument("--render", action="store_true", help="print the readable view")
    ap.add_argument("--evdir", help="evidence dir (default state/qualify/<run-id>)")
    args = ap.parse_args(argv)

    if not args.repo:
        ap.error("repo is required")
    repo = os.path.abspath(os.path.expanduser(args.repo))
    seed = load_recipe(args.seed) if args.seed else {}
    out = args.out or recipe_path(seed.get("origin") or _origin(repo))

    if (args.emit_env or args.render) and os.path.exists(out):
        recipe = load_recipe(out)
    else:
        recipe = qualify(repo, seed=seed,
                         chain=[c for c in args.chain.split(",") if c.strip()],
                         use_agent=args.agent, netns=args.netns, probe=args.probe,
                         hooks_ab=not args.no_hooks_ab,
                         dry_run_enabled=not args.no_dry_run,
                         evdir=args.evdir, out=out)
        if args.in_repo:
            mirror = os.path.join(repo, ".nightshift", "recipe.json")
            os.makedirs(os.path.dirname(mirror), exist_ok=True)
            shutil.copyfile(out, mirror)
    recipe.setdefault("source_path", out)
    recipe.setdefault("config", None)

    if args.emit_env:
        text = emit_env(recipe, out)
        if args.emit_env == "-":
            sys.stdout.write(text)
        else:
            with open(args.emit_env, "w") as f:
                f.write(text)
    if args.render:
        sys.stdout.write(render(recipe))
    if not (args.emit_env or args.render):
        print(json.dumps({"status": recipe["status"], "gap": recipe.get("gap"),
                          "gate": recipe["gate"], "recipe": out}, indent=1))
    return 0 if recipe["status"] != "no-go" else 1


if __name__ == "__main__":
    sys.exit(main())
