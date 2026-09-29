"""Literal configuration for the factory spike. No config framework."""

import os


REPO_HOST = "nixlab"
PRODUCT_REPO = os.environ.get("PRODUCT_REPO", "~/factory-lab/toy-product")  # remote path on REPO_HOST
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
MIN_MAX_TOKENS = 512  # reasoning models eat budget; below this content can come back null
IMPLEMENTER_MODEL = "gpt-6-luna"
IMPLEMENTER_MAX_TOKENS = 16384  # luna: 10,118 completion tokens observed on a real prompt
IMPLEMENTER_REASONING_EFFORT = "high"  # effort=max returns empty content; high is mandatory (luna-qualify)
REVIEWER_MODEL = "glm-5.3-flash"
RETRY_BUDGET = 2
MAX_CONCURRENT_LAPS = 1
# Public-subscription leak fix: the old hardcoded topic is public on origin
# main. From env only; empty default = notify() skips transport but still
# writes its receipt (receipts are the S7 evidence; the phone channel is
# optional). NTFY_TOPIC goes in the LAUNCH ENV, never in any file.
NTFY_TOPIC = os.environ.get("NTFY_TOPIC", "")
NTFY_URL = ("https://ntfy.sh/" + NTFY_TOPIC) if NTFY_TOPIC else ""
LAP_WALLCLOCK_LIMIT_S = 10800
SESSION_WALLCLOCK_LIMIT_S = 14400  # session backstop ≥ per-lap: luna lap ≈ 3×16min + review/verify
COST_CEILING_USD = 0.01
HEARTBEAT_PATH = "state/heartbeat"  # relative to the supervisor cwd
HEARTBEAT_TTL_S = 120  # ponytail: fixed TTL; tune on nixlab once real lap cadence is known
CLAIMS_DIR = "claims"
STATE_DIR = "state"
EVIDENCE_DIR = "state/evidence"
SCENARIO_PORT_RANGE = (8900, 8910)  # scenario candidate boots pick ports from here
FACTORY_PORT = 8899  # deployed app port on nixlab
READY_TIMEOUT_S = 30  # deploy readiness bound
CHECKOUT_CHAR_BUDGET = 100_000  # implementer prompt cap: root *.py files, sorted, whole files
PROVIDER_PINS = {"deepseek-v4.1-flash": "openrouter"}  # trusted provider; untrusted quant resellers leak DSML markup (see L-005). 404 no_sellers_for_model = fail loud, correct.
PROVENANCE_ENV = "FACTORY_RUNTIME_CANDIDATE"  # must be unset; leak = refuse
