"""Literal configuration for the factory spike. No config framework."""

REPO_HOST = "nixlab"
PRODUCT_REPO = "~/factory-lab/toy-product"  # remote path on REPO_HOST
GITHUB_REPO = "noor-latif/toy-product"
SURPLUS_BASE_URL = "https://api.surplusintelligence.ai"
SURPLUS_CHAT_PATH = "/v1/chat/completions"
SURPLUS_API_KEY_ENV = "SURPLUS_INTELLIGENCE_API_KEY"  # key never hardcoded, never printed
MIN_MAX_TOKENS = 512  # reasoning models eat budget; below this content can come back null
IMPLEMENTER_MODEL = "deepseek-v4.1-flash"  # exact live id; no effort suffixes on this gateway
REVIEWER_MODEL = "glm-5.3-flash"
RETRY_BUDGET = 2
MAX_CONCURRENT_LAPS = 1
NTFY_TOPIC = "nightshift-388c2cd67dbf9d80"
NTFY_URL = "https://ntfy.sh/" + NTFY_TOPIC
LAP_WALLCLOCK_LIMIT_S = 10800
COST_CEILING_USD = 0.01
HEARTBEAT_PATH = "state/heartbeat"  # relative to the supervisor cwd
HEARTBEAT_TTL_S = 120  # ponytail: fixed TTL; tune on nixlab once real lap cadence is known
CLAIMS_DIR = "claims"
STATE_DIR = "state"
EVIDENCE_DIR = "state/evidence"
SCENARIO_PORT_RANGE = (8900, 8910)  # scenario candidate boots pick ports from here
FACTORY_PORT = 8899  # deployed app port on nixlab
READY_TIMEOUT_S = 30  # deploy readiness bound
PROVIDER_PINS = {}  # model id -> provider allow-list (str or list); pinned models fail loud on 404
PROVENANCE_ENV = "FACTORY_RUNTIME_CANDIDATE"  # must be unset; leak = refuse
