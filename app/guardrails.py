import asyncio
import logging
import boto3
from app.config import Config
from app.retry import with_retry

logger = logging.getLogger(__name__)

# boto3 clients are expensive to build (they resolve credentials and set up TLS)
# and they're thread-safe, so build one per region and reuse it
_clients: dict[str, "boto3.client"] = {}


def _client(region: str):
    if region not in _clients:
        _clients[region] = boto3.client("bedrock-runtime", region_name=region)
    return _clients[region]


# sends text to aws bedrock's guardrail to check if it's safe
# boto3 is not async, so this is the plain blocking version - the async
# functions below run it in a separate thread so it doesn't freeze the app
def _apply_guardrail_sync(config: Config, text: str, source: str) -> dict:
    return _client(config.aws_region).apply_guardrail(
        guardrailIdentifier=config.bedrock_guardrail_id,
        guardrailVersion=config.bedrock_guardrail_version,
        source=source,  # "INPUT" = user's question, "OUTPUT" = our answer
        content=[{"text": {"text": text}}],
    )


# shared by both checks below: run the guardrail and say whether the text passed
async def _check(config: Config, text: str, source: str, label: str) -> tuple[bool, str]:
    # no guardrail configured (local runs), so nothing to check against
    if not config.bedrock_guardrail_id:
        return True, ""

    try:
        # to_thread runs the blocking boto3 call without blocking everything else,
        # with_retry tries again if aws hiccups
        response = await with_retry(
            lambda: asyncio.to_thread(_apply_guardrail_sync, config, text, source),
            max_retries=config.llm_max_retries,
            delay=config.llm_retry_delay,
        )
    except Exception as exc:
        # bedrock being unreachable must not quietly turn safety checking off,
        # so treat it as a block rather than letting the text through
        logger.error(f"Guardrail check failed for {source}: {exc}")
        return False, "Safety check is unavailable right now. Try again shortly."

    # "GUARDRAIL_INTERVENED" means bedrock decided this text breaks the rules
    if response.get("action") == "GUARDRAIL_INTERVENED":
        return False, f"{label} blocked by safety guardrail."
    return True, ""


# checks the user's question BEFORE we send it to the llm
# returns (is_it_ok, message_to_show_if_not_ok)
async def validate_input(config: Config, text: str) -> tuple[bool, str]:
    return await _check(config, text, "INPUT", "Input")


# same thing but for the llm's answer, BEFORE we show it to the user
# (the model could still say something bad even if the question was fine)
async def validate_output(config: Config, text: str) -> tuple[bool, str]:
    return await _check(config, text, "OUTPUT", "Output")
