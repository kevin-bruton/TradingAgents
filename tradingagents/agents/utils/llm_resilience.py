import time
import json
import logging
from typing import Any, Callable, Dict
from json import JSONDecodeError

logger = logging.getLogger(__name__)


def invoke_with_retries(chain: Any, messages: Any, config: Dict[str, Any]):
    """Invoke a langchain chain with retries and detailed logging.

    Handles transient HTTP issues and JSON decode errors coming from provider SDKs.
    """
    max_retries = config.get("llm_max_retries", 3)
    backoff = config.get("llm_retry_backoff", 2.0)

    last_err = None
    for attempt in range(1, max_retries + 1):
        try:
            result = chain.invoke(messages)
            return result
        except JSONDecodeError as e:
            last_err = e
            logger.warning(
                "JSONDecodeError on attempt %s/%s: %s", attempt, max_retries, e
            )
        except Exception as e:  # noqa: BLE001
            # Capture common transient network / HTTP errors keywords
            transient = any(
                kw in str(e).lower() for kw in [
                    "timeout", "temporarily", "rate limit", "connection reset", "503", "502", "jsondecodeerror"
                ]
            )
            last_err = e
            logger.warning(
                "LLM invocation error (transient=%s) attempt %s/%s: %s", transient, attempt, max_retries, e
            )
            if not transient and not isinstance(e, JSONDecodeError):
                # Non transient -> abort early
                break
        # Exponential backoff
        sleep_for = backoff ** (attempt - 1)
        time.sleep(sleep_for)
    # All attempts failed
    raise last_err  # propagate last error
