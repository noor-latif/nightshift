# env.example.sh — TEMPLATE for the lap launch env. Contains NO secrets.
#
#   cp env.example.sh env.sh && edit env.sh     # first run
#
# env.sh is gitignored (.gitignore: env.sh, .env, .env.*); this template is not,
# so `git status` shows env.example.sh as a new file and never env.sh.
#
# The launcher sources NOTHING: scripts/run-lap.sh only setsid+nohup`s
# `python3 src/lap.py`. Everything the lap reads comes from the launch env via
# src/settings.py, so you MUST export env.sh in the SAME shell you launch from:
#
#   cd ~/repos/factory-spike
#   set -a; . env.sh; set +a
#   scripts/run-lap.sh <issue-number>
#
# Every line below is commented out — uncomment only what the lap needs.
# Defaults quoted from src/settings.py.

# ---------------------------------------------------------------------------
# Gateway credential
# ---------------------------------------------------------------------------

# src/agent.py reads os.environ["SURPLUS_INTELLIGENCE_API_KEY"] (no default —
# the lap dies at gate=gateway without it). Required for every paid lap: all
# implementer/reviewer/qualifier calls go through the gateway.
# It MUST be exported in the launch shell: a lap once died at gate=gateway
# because the var lived in a different shell than the launcher — export it in
# the SAME shell you run scripts/run-lap.sh from.
# export SURPLUS_INTELLIGENCE_API_KEY=""

# ---------------------------------------------------------------------------
# Trusted native command config (src/settings.py FACTORY_NATIVE_CONFIG)
# ---------------------------------------------------------------------------

# Default: unset -> the historical Python gate. Value is a JSON object read
# from the LAUNCH ENV, never a file the candidate can edit. Shape (README
# "Local lap"):
#   {"verify": [[argv...], ...], "suite": [argv...], "prepare": [[argv...]],
#    "suite_runner": "tap|pytest", "suite_timeout_s": 600,
#    "task_kind": "bug|enhancement", "merge_mode": "auto|review"}
# `suite` must be exactly one of the `verify` argv entries; `suite_runner`
# (default "tap") picks the authoritative-total parser, never a command.
# merge_mode: "review" = stop after local verification — no push, no PR, no
# merge, no deploy, no close, ever (retains a local review/<run-id> ref).
# Example, the README's pytest copy-paste shape:
# export FACTORY_NATIVE_CONFIG='{"verify": [["python3", "-m", "pytest", "-q", "-p", "no:cacheprovider"]], "suite": ["python3", "-m", "pytest", "-q", "-p", "no:cacheprovider"], "suite_runner": "pytest", "suite_timeout_s": 900, "task_kind": "bug", "merge_mode": "auto"}'

# ---------------------------------------------------------------------------
# Local task input + mutation capability (Körmotorn local trial)
# ---------------------------------------------------------------------------

# Default: "" (unset) -> read the issue from GitHub via `gh`.
# Set to an ABSOLUTE path (a relative one raises) of a trusted read-only
# {title, body} file OUTSIDE the candidate checkout.
# export FACTORY_TASK_FILE=""

# Default: "" (unset) -> edit-only; no file may be created.
# Comma-separated plain relative paths the lap may create, e.g.
# index.html,styles.css,page.js,assets/* (an fnmatch glob char makes the entry
# a pattern; `..`, absolute and `~` entries are always rejected).
# export FACTORY_NEW_FILES=""

# F10 base pin. Default: "" (unset) -> resolve FACTORY_BASE_REF at lap start.
# Set to the exact commit id the lap must run on (e.g. the defect base); the
# worktree is checked out at that sha regardless of where the ref points.
# RECOMMENDED for every bank recipe: a movable ref cannot encode "this base".
# export FACTORY_BASE_SHA=""

# F10 red-at-base gate. Default: "" (unset) -> no pre-dispatch oracle run.
# Set to an ABSOLUTE path of an executable oracle; worktree_for() runs it at
# the base checkout BEFORE any paid call and fails the lap operational
# (gate=base-pin) if it exits 0 — GREEN at base = vacuous instance.
# export FACTORY_ORACLE=""

# ---------------------------------------------------------------------------
# Cost + repo knobs
# ---------------------------------------------------------------------------

# Default: 0.01 (settings.py COST_CEILING_USD). Enforced at lap level (G7):
# once accumulated cost passes it, add_cost raises and the lap ends
# finish(gate="cost"). Raise it before any lap expected to cost more.
# export COST_CEILING_USD="0.01"

# Default: "noor-latif/toy-product" (settings.py GITHUB_REPO). Used only by the
# gh-based task source — irrelevant when FACTORY_TASK_FILE is set.
# export GITHUB_REPO=""

# ---------------------------------------------------------------------------
# Optional notification (ntfy)
# ---------------------------------------------------------------------------

# Default: "" (unset) -> notify() skips transport but still writes its receipt
# (receipts are the S7 evidence; the phone channel is optional).
# settings.py derives NTFY_URL = "https://ntfy.sh/" + NTFY_TOPIC — there is no
# NTFY_URL env var. NTFY_TOPIC belongs in the LAUNCH ENV, never in a file: the
# old hardcoded topic was public on origin main.
# export NTFY_TOPIC=""

# ---------------------------------------------------------------------------
# Other operator knobs (all optional; defaults from src/settings.py)
# ---------------------------------------------------------------------------

# export PRODUCT_REPO="~/factory-lab/toy-product"   # local path, used as a local git cwd
# export DEPLOY_MODE="app"                          # "app" = boot + identity readback; "none" = library repos
# export CODE_PATHS="*.py"                          # implementer checkout globs, comma-separated
# export SCENARIOS_DIR=""                           # deployment-curated scenario dir (default: <repo>/scenarios)
# export IMPLEMENTER_MODEL="gpt-6-luna"             # implementer role model
# export IMPLEMENTER_MAX_TOKENS="16384"             # implementer completion cap
# export IMPLEMENTER_REASONING_EFFORT="high"        # effort=max returns empty content; high is mandatory
# export REVIEWER_MODEL="glm-5.3-flash"             # reviewer role model
# export REVIEWER_MAX_TOKENS="8192"                 # reviewer completion cap
# export REVIEWER_REASONING_EFFORT=""               # unset by default
# export QUALIFIER_MODEL="glm-5.3-flash"            # qualifier role model (only used by qualify.sh --agent)
# export QUALIFIER_MAX_TOKENS="65536"               # qualifier completion cap
# export QUALIFIER_REASONING_EFFORT="high"          # qualifier reasoning effort
# export IMPLEMENTER_API="openai-completions"       # openai-completions|openai-responses
# export REVIEWER_API="openai-completions"          # openai-completions|openai-responses
# export QUALIFIER_API="openai-completions"         # openai-completions|openai-responses
# export FACTORY_HTTP_TIMEOUT_S="120"               # per-request socket timeout for the paid call
# export CHECKOUT_CHAR_BUDGET="100000"              # implementer prompt cap
# export NIGHTSHIFT_RECIPES_DIR="~/nightshift/recipes"  # operator-side recipe store

# Must stay UNSET: settings.py PROVENANCE_ENV (FACTORY_RUNTIME_CANDIDATE) is a
# leak check — verify refuses (Hold) if it is set in the environment.
