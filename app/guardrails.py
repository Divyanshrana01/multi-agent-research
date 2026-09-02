import asyncio
import boto3
from app.config import Config
from app.retry import with_retry


# sends text to aws bedrock's guardrail to check if it's safe
# boto3 is not async, so this is the plain blocking version - the async
# functions below run it in a separate thread so it doesn't freeze the app
def _apply_guardrail_sync(config: Config, text: str, source: str) -> dict:
    client = boto3.client("bedrock-runtime", region_name=config.aws_region)
    return client.apply_guardrail(
        guardrailIdentifier=config.bedrock_guardrail_id,
        guardrailVersion=config.bedrock_guardrail_version,
        source=source,  # "INPUT" = user's question, "OUTPUT" = our answer
        content=[{"text": {"text": text}}],
    )


# checks the user's question BEFORE we send it to the llm
# returns (is_it_ok, message_to_show_if_not_ok)
async def validate_input(config: Config, text: str) -> tuple[bool, str]:
    # to_thread runs the blocking boto3 call without blocking everything else,
    # with_retry tries again if aws hiccups
    response = await with_retry(
        lambda: asyncio.to_thread(_apply_guardrail_sync, config, text, "INPUT"),
        max_retries=config.llm_max_retries,
        delay=config.llm_retry_delay,
    )
    # "GUARDRAIL_INTERVENED" means bedrock decided this text breaks the rules
    if response.get("action") == "GUARDRAIL_INTERVENED":
        return False, "Input blocked by safety guardrail."
    return True, ""


# same thing but for the llm's answer, BEFORE we show it to the user
# (the model could still say something bad even if the question was fine)
async def validate_output(config: Config, text: str) -> tuple[bool, str]:
    response = await with_retry(
        lambda: asyncio.to_thread(_apply_guardrail_sync, config, text, "OUTPUT"),
        max_retries=config.llm_max_retries,
        delay=config.llm_retry_delay,
    )
    if response.get("action") == "GUARDRAIL_INTERVENED":
        return False, "Output blocked by safety guardrail."
    return True, ""
