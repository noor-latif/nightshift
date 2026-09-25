"""Merge: evidence-gated squash merge + tree-equality identity check.

Gate = all verify evidence green. Then `gh pr create` + `gh pr merge --squash
--match-head-commit <head-sha>`. Post-merge identity is TREE equality between
the merge commit and the PR head — never SHA equality (squash creates new
SHAs; this rule is load-bearing).
"""

import json
import subprocess


def gate_green(evidence):
    """Merge gate: verify evidence must exist and be all-pass."""
    if not isinstance(evidence, dict) or evidence.get("verdict") != "pass":
        return False
    return True


def _git(args, cwd, git="git"):
    return subprocess.run(
        [git] + args, cwd=cwd, capture_output=True, text=True, check=True
    ).stdout


def trees_equal(repo_cwd, a, b, git="git"):
    """Tree equality: `git diff --stat a b` empty output. Never SHA compare."""
    out = _git(["diff", "--stat", a, b], repo_cwd, git)
    return out.strip() == ""


def head_sha(repo_cwd, ref="HEAD", git="git"):
    return _git(["rev-parse", ref], repo_cwd, git).strip()


def create_pr(issue, repo, branch, base="main", gh="gh", cwd=None):
    title = "agent/issue-%d" % issue
    out = _gh(["pr", "create", "--head", branch, "--base", base,
               "--title", title, "--body", title], repo, gh, cwd)
    # gh prints the PR URL
    return out.strip().splitlines()[-1]


def _gh(args, repo, gh="gh", cwd=None):
    return subprocess.run(
        [gh] + args + ["-R", repo], cwd=cwd,
        capture_output=True, text=True, check=True,
    ).stdout


def merge_pr(issue, repo, head_sha_value, pr_url=None, gh="gh", cwd=None):
    """Squash-merge pinned to the verified head SHA; returns merge commit SHA."""
    args = ["pr", "merge", "--squash", "--match-head-commit", head_sha_value]
    if pr_url:
        args.append(pr_url)
    else:
        args.append("agent/issue-%d" % issue)
    _gh(args, repo, gh, cwd)
    # post-merge: fetch main and find the squash commit
    _gh(["api", "repos/%s/commits/main" % repo, "-q", ".sha"], repo, gh, cwd)
    return None  # actual SHA resolved by caller via git fetch; gh output only


def post_merge_identity(repo_cwd, merge_commit, head, git="git"):
    """Tree-bound identity: mergeCommit^{tree} == head tree (empty diff)."""
    if not trees_equal(repo_cwd, merge_commit, head, git):
        raise IdentityMismatch(
            "tree mismatch after squash merge: %s vs %s" % (merge_commit, head)
        )
    return True


class IdentityMismatch(Exception):
    pass


def full_merge(issue, repo, worktree_cwd, evidence, gh="gh", git="git"):
    """Gate → PR → squash merge → tree-equality identity. Returns evidence dict."""
    if not gate_green(evidence):
        return {"merged": False, "reason": "gate not green"}
    branch = "agent/issue-%d" % issue
    sha = head_sha(worktree_cwd, git=git)
    pr_url = create_pr(issue, repo, branch, gh=gh, cwd=worktree_cwd)
    merge_pr(issue, repo, sha, pr_url=pr_url, gh=gh, cwd=worktree_cwd)
    subprocess.run(["git", "fetch", "origin", "main"], cwd=worktree_cwd,
                   capture_output=True, text=True, check=True)
    merge_sha = head_sha(worktree_cwd, "origin/main", git)
    post_merge_identity(worktree_cwd, merge_sha, sha, git)
    return {"merged": True, "pr": pr_url, "merge_sha": merge_sha, "head_sha": sha}
