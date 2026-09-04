import os
import socket
import json
import logging
from functools import lru_cache

logger = logging.getLogger(__name__)

# every setting the app reads, so local mode knows which env vars to look at
_SETTING_NAMES = (
    "AWS_REGION", "BEDROCK_GUARDRAIL_ID", "BEDROCK_GUARDRAIL_VERSION",
    "REDIS_URL", "DATABASE_URL", "TENSORZERO_URL", "API_KEY",
    "LANGSMITH_API_KEY", "LANGCHAIN_PROJECT", "LANGSMITH_DATASET",
    "CACHE_TTL", "CACHE_SIMILARITY_THRESHOLD",
    "SESSION_TTL", "SESSION_MAX_MESSAGES", "SESSION_CONTENT_TRUNCATE",
    "LTM_DAYS", "LTM_RELATED_DAYS", "LTM_THRESHOLD", "LTM_DIFF_THRESHOLD",
    "LTM_DIFF_LIMIT", "IVFFLAT_LISTS",
    "STREAM_KEY", "CONSUMER_GROUP", "CONSUMER_NAME", "RESULT_TTL",
    "AGENT_REPORT_TRUNCATE", "AGENT_MAX_ITERATIONS",
    "EVAL_REPORT_TRUNCATE", "EVAL_COMMENT_TRUNCATE",
    "LLM_MAX_RETRIES", "LLM_RETRY_DELAY",
    "RATE_LIMIT_REQUESTS", "RATE_LIMIT_WINDOW",
    "DB_POOL_MIN", "DB_POOL_MAX",
)


# reads the settings out of environment variables instead of AWS.
# this is what lets the app run locally under docker compose without any
# AWS account at all - set LOCAL_CONFIG=1 to use it.
def _load_from_env() -> dict:
    return {name: os.environ[name] for name in _SETTING_NAMES if name in os.environ}


# this function goes to AWS Secrets Manager and pulls our config secret
# lru_cache(maxsize=1) means it only runs once and remembers the result,
# so we don't call AWS again every time we need the config
@lru_cache(maxsize=1)
def _load_secret() -> dict:
    if os.environ.get("LOCAL_CONFIG") == "1":
        logger.info("LOCAL_CONFIG=1, reading settings from environment variables")
        return _load_from_env()

    # imported here so local mode doesn't need boto3 configured at all
    import boto3

    # get region from env var, default to global if not set
    region = os.environ.get("AWS_REGION", "global")
    secret_id = os.environ.get("CONFIG_SECRET_ID", "research-agent/config")
    try:
        # make a boto3 client to talk to secrets manager
        client = boto3.client("secretsmanager", region_name=region)
        # ask AWS for our secret by its name/id
        response = client.get_secret_value(SecretId=secret_id)
    except Exception as exc:
        # the raw boto error is hard to read, so say what actually went wrong
        raise RuntimeError(
            f"Could not read '{secret_id}' from AWS Secrets Manager in {region}: {exc}. "
            "Set LOCAL_CONFIG=1 to read settings from environment variables instead."
        ) from exc
    # the secret comes back as a JSON string, so parse it into a dict
    return json.loads(response["SecretString"])


# pulls a setting that the app can't run without, and says which one is missing
def _required(data: dict, name: str) -> str:
    value = data.get(name)
    if not value:
        raise RuntimeError(
            f"Missing required setting {name}. Add it to the AWS secret, or set it as "
            "an environment variable and run with LOCAL_CONFIG=1."
        )
    return value


class Config:
    # this class just loads all our settings once when created
    # and stores them as attributes so rest of app can do config.something
    def __init__(self):
        # get the secret dict (cached after first call)
        data = _load_secret()

        # AWS
        self.aws_region: str = data.get("AWS_REGION", "us-east-1")

        # Bedrock Guardrails. optional so the app can run locally without a
        # guardrail configured - see guardrails.py, checks are skipped if unset
        self.bedrock_guardrail_id: str = data.get("BEDROCK_GUARDRAIL_ID", "")
        self.bedrock_guardrail_version: str = data.get("BEDROCK_GUARDRAIL_VERSION", "DRAFT")

        # Storage. these three are genuinely required - fail loudly at startup
        # rather than with a confusing connection error later
        self.redis_url: str = _required(data, "REDIS_URL")
        self.database_url: str = _required(data, "DATABASE_URL")
        self.tensorzero_url: str = _required(data, "TENSORZERO_URL")

        # Auth
        self.api_key: str = data.get("API_KEY", "")

        # LangSmith tracing
        self.langsmith_api_key: str = data.get("LANGSMITH_API_KEY", "")
        self.langchain_project: str = data.get("LANGCHAIN_PROJECT", "research-agent")
        self.langsmith_dataset: str = data.get("LANGSMITH_DATASET", "research-agent-reports")

        # Semantic cache
        self.cache_ttl: int = int(data.get("CACHE_TTL", 3600))
        self.cache_similarity_threshold: float = float(data.get("CACHE_SIMILARITY_THRESHOLD", 0.85))

        # Session memory
        self.session_ttl: int = int(data.get("SESSION_TTL", 1800))
        self.session_max_messages: int = int(data.get("SESSION_MAX_MESSAGES", 5))
        self.session_content_truncate: int = int(data.get("SESSION_CONTENT_TRUNCATE", 500))

        # Long-term memory
        self.ltm_days: int = int(data.get("LTM_DAYS", 7))
        # how far back to look for a *related* report to hand the writer as
        # reference. wider than ltm_days because old context is still useful.
        self.ltm_related_days: int = int(data.get("LTM_RELATED_DAYS", 90))
        self.ltm_threshold: float = float(data.get("LTM_THRESHOLD", 0.88))
        self.ltm_diff_threshold: float = float(data.get("LTM_DIFF_THRESHOLD", 0.7))
        self.ltm_diff_limit: int = int(data.get("LTM_DIFF_LIMIT", 5))
        self.ivfflat_lists: int = int(data.get("IVFFLAT_LISTS", 100))

        # Job queue
        self.stream_key: str = data.get("STREAM_KEY", "research:jobs")
        self.consumer_group: str = data.get("CONSUMER_GROUP", "workers")
        # hostname = unique per ECS task = safe for horizontal scaling
        self.consumer_name: str = data.get("CONSUMER_NAME", socket.gethostname())
        self.result_ttl: int = int(data.get("RESULT_TTL", 3600))

        # Agent tuning
        self.agent_report_truncate: int = int(data.get("AGENT_REPORT_TRUNCATE", 3000))
        self.agent_max_iterations: int = int(data.get("AGENT_MAX_ITERATIONS", 2))

        # Eval tuning
        self.eval_report_truncate: int = int(data.get("EVAL_REPORT_TRUNCATE", 1500))
        self.eval_comment_truncate: int = int(data.get("EVAL_COMMENT_TRUNCATE", 300))

        # LLM retry
        self.llm_max_retries: int = int(data.get("LLM_MAX_RETRIES", 3))
        self.llm_retry_delay: float = float(data.get("LLM_RETRY_DELAY", 1.0))

        # Rate limiting (per IP, per window)
        self.rate_limit_requests: int = int(data.get("RATE_LIMIT_REQUESTS", 10))
        self.rate_limit_window: int = int(data.get("RATE_LIMIT_WINDOW", 60))

        # DB connection pool
        self.db_pool_min: int = int(data.get("DB_POOL_MIN", 2))
        self.db_pool_max: int = int(data.get("DB_POOL_MAX", 10))

        # only turn on LangSmith tracing if we actually have an api key for it
        # LangChain reads these specific env var names itself, so we set them here
        if self.langsmith_api_key:
            os.environ["LANGCHAIN_TRACING_V2"] = "true"
            os.environ["LANGCHAIN_API_KEY"] = self.langsmith_api_key
            os.environ["LANGCHAIN_PROJECT"] = self.langchain_project
            os.environ["LANGCHAIN_ENDPOINT"] = "https://api.smith.langchain.com"
