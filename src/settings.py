"""Literal configuration for the factory spike. No config framework."""

import os


PRODUCT_REPO = os.environ.get("PRODUCT_REPO", "~/factory-lab/toy-product")  # local path: expanded and used as a local git cwd
GITHUB_REPO = os.environ.get("GITHUB_REPO", "noor-latif/toy-product")
# "app" = boot + identity readback (toy-product); "none" = library repos with
# nothing to deploy and no live rig to compare identity against.
DEPLOY_MODE = os.environ.get("DEPLOY_MODE", "app")
# Implementer checkout globs (relative to the worktree root), comma-separated
# in env. Default = exactly the historical root *.py view.
CODE_PATHS = [p.strip() for p in os.environ.get("CODE_PATHS", "*.py").split(",") if p.strip()]
SURPLUS_BASE_URL = "https://api.surplusintelligence.ai"
SURPLUS_CHAT_PATH = "/v1/chat/completions"
SURPLUS_API_KEY_ENV = "SURPLUS_INTELLIGENCE_API_KEY"  # key never hardcoded, never printed
# Per-request socket timeout for the paid call. 120 was the historical
# literal; a long high-effort generation on a large prompt legitimately
# exceeds it (observed: 200 + SSE headers, then empty body at ~104s and a
# read timeout at 120s on the same request shape). Operator-overridable
# from the launch env; the default is unchanged.
HTTP_TIMEOUT_S = int(os.environ.get("FACTORY_HTTP_TIMEOUT_S", "120"))
MIN_MAX_TOKENS = 512  # reasoning models eat budget; below this content can come back null
IMPLEMENTER_MODEL = os.environ.get("IMPLEMENTER_MODEL", "gpt-6-luna")
IMPLEMENTER_MAX_TOKENS = int(os.environ.get("IMPLEMENTER_MAX_TOKENS", "16384"))  # luna: 10,118 completion tokens observed on a real prompt; a full three-file page exceeded 16384 (observed), so the cap is operator-overridable like the other knobs
IMPLEMENTER_REASONING_EFFORT = os.environ.get("IMPLEMENTER_REASONING_EFFORT", "high")  # effort=max returns empty content; high is mandatory (luna-qualify)
REVIEWER_MODEL = os.environ.get("REVIEWER_MODEL", "glm-5.3-flash")
REVIEWER_MAX_TOKENS = int(os.environ.get("REVIEWER_MAX_TOKENS", "8192"))
IMPLEMENTER_API = os.environ.get("IMPLEMENTER_API", "openai-completions")
REVIEWER_API = os.environ.get("REVIEWER_API", "openai-completions")
REVIEWER_REASONING_EFFORT = os.environ.get("REVIEWER_REASONING_EFFORT")
if any(api not in ("openai-completions", "openai-responses") for api in (IMPLEMENTER_API, REVIEWER_API)):
    raise ValueError("role API must be openai-completions|openai-responses")
RETRY_BUDGET = 2
# Public-subscription leak fix: the old hardcoded topic is public on origin
# main. From env only; empty default = notify() skips transport but still
# writes its receipt (receipts are the S7 evidence; the phone channel is
# optional). NTFY_TOPIC goes in the LAUNCH ENV, never in any file.
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "")
NTFY_URL = ("https://ntfy.sh/" + NTFY_TOPIC) if NTFY_TOPIC else ""
LAP_WALLCLOCK_LIMIT_S = 10800
SESSION_WALLCLOCK_LIMIT_S = 14400  # session backstop ≥ per-lap: luna lap ≈ 3×16min + review/verify
COST_CEILING_USD = float(os.environ.get("COST_CEILING_USD", "0.01"))  # enforced at lap level (G7): add_cost raises past this; run() → finish(gate="cost")
HEARTBEAT_PATH = "state/heartbeat"  # relative to the supervisor cwd
HEARTBEAT_TTL_S = 120  # ponytail: fixed TTL; tune on nixlab once real lap cadence is known
CLAIMS_DIR = "claims"
STATE_DIR = "state"
EVIDENCE_DIR = "state/evidence"
SCENARIO_PORT_RANGE = (8900, 8910)  # scenario candidate boots pick ports from here
DEPLOY_PORT = 8642  # the rig's deployed app port (deploy + identity read-back)
READY_TIMEOUT_S = 30  # deploy readiness bound
CHECKOUT_CHAR_BUDGET = int(os.environ.get("CHECKOUT_CHAR_BUDGET", 100_000))  # implementer prompt cap; env-overridable for larger multi-glob views
SCENARIOS_DIR = os.environ.get(
    "SCENARIOS_DIR",
    os.path.join(os.path.dirname(__file__), "..", "scenarios"))  # deployment-curated dir (self-run: issue-1..6 only)
PROVIDER_PINS = {"deepseek-v4.1-flash": "openrouter"}  # trusted provider; untrusted quant resellers leak DSML markup (see L-005). 404 no_sellers_for_model = fail loud, correct.
PROVENANCE_ENV = "FACTORY_RUNTIME_CANDIDATE"  # must be unset; leak = refuse
# --- prerequisites (Götalands Trafikskola frontend slice, owner-approved 2026-10-02) ---
# Trusted env JSON: verify/prepare are lists of argv commands; suite is one
# designated verify argv. Missing commands use the historical Python gate;
# explicit null/empty values are invalid. Native verify requires a suite
# whose authoritative Node TAP '# tests N' total proves non-vacuity.
# trusted from the LAUNCH ENV, never a file the candidate can edit.
import json as _json

_env_cfg = os.environ.get("FACTORY_NATIVE_CONFIG", "")
_cfg = _json.loads(_env_cfg) if _env_cfg else {}
if not isinstance(_cfg, dict):
    raise ValueError("FACTORY_NATIVE_CONFIG must be a JSON object")
# Native commands: each value is a LIST of commands, each command a flat
# nonempty argv array of nonempty strings, no shell. Explicit empty list
# or null = a config error, never a silent pass; MISSING key = unset
# (historical Python default).
def _one_argv(v):
    return (isinstance(v, list) and v
            and all(isinstance(a, str) and a.strip() for a in v))

def _argv(v, what):
    if not _one_argv(v):
        raise ValueError("FACTORY_NATIVE_CONFIG %s must be a nonempty argv array of nonempty strings" % what)
    return v


def _command_list(v):
    if not (isinstance(v, list) and v and all(_one_argv(c) for c in v)):
        raise ValueError("FACTORY_NATIVE_CONFIG commands must be nonempty argv arrays of nonempty strings")
    return v


NATIVE_VERIFY_COMMANDS = _command_list(_cfg["verify"]) if "verify" in _cfg else None
NATIVE_SUITE_COMMAND = _argv(_cfg["suite"], "suite") if "suite" in _cfg else None
NATIVE_PREPARE_COMMANDS = _command_list(_cfg["prepare"]) if "prepare" in _cfg else None
if NATIVE_VERIFY_COMMANDS is not None and NATIVE_SUITE_COMMAND is None:
    raise ValueError("FACTORY_NATIVE_CONFIG native verify requires suite")
if NATIVE_SUITE_COMMAND is not None and (NATIVE_VERIFY_COMMANDS or []).count(NATIVE_SUITE_COMMAND) != 1:
    raise ValueError("FACTORY_NATIVE_CONFIG suite must designate exactly one verify command")
# Suite runner selects the authoritative-total PARSER for the suite argv, never
# a command: a closed enum, no shell, no path into the checkout. Missing =
# "tap", byte-identical to the historical Node TAP contract. suite_timeout_s
# replaces the hard-coded 600 s for the suite argv only.
SUITE_RUNNERS = ("tap", "pytest")
SUITE_RUNNER = _cfg.get("suite_runner", "tap")
if SUITE_RUNNER not in SUITE_RUNNERS:
    raise ValueError("FACTORY_NATIVE_CONFIG suite_runner must be one of %s" % (SUITE_RUNNERS,))
if NATIVE_SUITE_COMMAND is None and ("suite_runner" in _cfg or "suite_timeout_s" in _cfg):
    raise ValueError("FACTORY_NATIVE_CONFIG suite_runner/suite_timeout_s require suite")
try:
    SUITE_TIMEOUT_S = int(_cfg.get("suite_timeout_s", 600))
except (TypeError, ValueError):
    raise ValueError("FACTORY_NATIVE_CONFIG suite_timeout_s must be an integer 60..3600")
if not 60 <= SUITE_TIMEOUT_S <= 3600:
    raise ValueError("FACTORY_NATIVE_CONFIG suite_timeout_s must be 60..3600")
TASK_KIND = _cfg.get("task_kind", "bug")
MERGE_MODE = _cfg.get("merge_mode", "auto")
if TASK_KIND not in ("bug", "enhancement") or MERGE_MODE not in ("auto", "review"):
    raise ValueError("FACTORY_NATIVE_CONFIG: task_kind must be bug|enhancement, merge_mode must be auto|review")
TRACE_HEADER_ALLOWLIST = ["content-type", "request-id", "x-request-id", "x-ratelimit-remaining-requests",
                          "x-ratelimit-reset-requests", "retry-after"]
# --- qualify (per-repo build/test distillation, src/qualify.py) ---
# The qualifier is a THIRD role: it proposes argv, it never decides pass/fail
# (the deterministic checks and the dry-runs do). Its call is opt-in behind
# `--agent`, so a default run makes zero model calls. Same env-override shape
# as the other roles; no model name is hardcoded here.
QUALIFIER_MODEL = os.environ.get("QUALIFIER_MODEL", "glm-5.3-flash")
# MF-4: the field test burned attempt 1 at 16,382 reasoning tokens with
# finish_reason=length and zero content (QUALIFY-FIELDTEST §9); tokens were the
# binding constraint at effort=high, so the default leaves room for both.
QUALIFIER_MAX_TOKENS = int(os.environ.get("QUALIFIER_MAX_TOKENS", "65536"))
QUALIFIER_REASONING_EFFORT = os.environ.get("QUALIFIER_REASONING_EFFORT", "high")
QUALIFIER_API = os.environ.get("QUALIFIER_API", "openai-completions")
# Recipe store: operator-side by construction. The kernel reads the gate config
# from the LAUNCH ENV (FACTORY_NATIVE_CONFIG above), never from the checkout, so
# a recipe inside the candidate repo could point verify at /bin/true. The store
# is the trust anchor; `--in-repo` publishes a byte-identical copy for readers.
RECIPES_DIR = os.environ.get("NIGHTSHIFT_RECIPES_DIR", "~/nightshift/recipes")
# --- local trusted task input + explicit new-file creation (Körmotorn local trial) ---
# The task file is an operator-provided, read-only artifact OUTSIDE the
# candidate checkout; when set, the lap reads the issue text from it instead
# of GitHub. Empty (default) preserves the historical gh path exactly.
TASK_FILE = os.environ.get("FACTORY_TASK_FILE", "")
if TASK_FILE and not os.path.isabs(TASK_FILE):
    raise ValueError("FACTORY_TASK_FILE must be an absolute path")
# Creation is opt-in and allowlisted from the launch env, never a candidate
# file: only these relative paths may be created. An entry containing an
# fnmatch glob character (* ? [) is a pattern and authorizes every plain
# relative path it matches (a bare '*' authorizes any of them). Empty
# (default) = no creation capability, so the historical edit-only contract
# is unchanged.
# The lexical rules below are identical for literal and glob entries: the
# glob characters are not path syntax, so '..' stays a rejected segment
# even in a pattern ('assets/../*' can never be authorized).
NEW_FILES = [p.strip() for p in os.environ.get("FACTORY_NEW_FILES", "").split(",") if p.strip()]
for _p in NEW_FILES:
    if (os.path.isabs(_p) or _p.startswith("~") or "\\" in _p
            or any(s in ("", ".", "..") for s in _p.split("/"))):
        raise ValueError("FACTORY_NEW_FILES entries must be plain relative paths: %r" % _p)
