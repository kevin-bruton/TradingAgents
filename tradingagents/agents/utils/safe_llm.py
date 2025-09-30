import time
import random
from typing import Any, Callable, Sequence, Union
import json

# Define which exceptions to treat as transient
try:
    import httpx  # type: ignore
except Exception:  # pragma: no cover
    httpx = None  # fallback if not installed (but project includes it transitively)

TRANSIENT_EXCEPTION_TYPES = []
if httpx:
    TRANSIENT_EXCEPTION_TYPES.extend([
        httpx.TimeoutException,
        httpx.ConnectError,
        httpx.NetworkError if hasattr(httpx, 'NetworkError') else Exception,  # broad fallback
    ])

# Always include JSON decode errors
from json import JSONDecodeError
TRANSIENT_EXCEPTION_TYPES.append(JSONDecodeError)


class LLMRetryConfig:
    def __init__(
        self,
        max_attempts: int = 4,
        base_delay: float = 0.75,
        max_delay: float = 8.0,
        jitter: float = 0.3,
    ):
        self.max_attempts = max_attempts
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.jitter = jitter


def _compute_backoff(attempt: int, cfg: LLMRetryConfig) -> float:
    # Exponential backoff with jitter
    delay = min(cfg.base_delay * (2 ** (attempt - 1)), cfg.max_delay)
    if cfg.jitter:
        delta = delay * cfg.jitter
        delay = random.uniform(delay - delta, delay + delta)
    return max(0.05, delay)


def safe_invoke_llm(llm: Any, payload: Union[str, Sequence[dict]], cfg: LLMRetryConfig | None = None):
    """Invoke an LLM with retries for transient decode/network errors.

    Parameters
    ----------
    llm : Any
        LangChain-compatible LLM/chat model with an .invoke() method.
    payload : str | list
        Prompt string or messages sequence.
    cfg : LLMRetryConfig | None
        Retry configuration (defaults sensible for API use).

    Returns
    -------
    result : Any
        Model response from final successful attempt.

    Raises
    ------
    Exception
        The last raised exception if all attempts fail.
    """
    if cfg is None:
        cfg = LLMRetryConfig()

    attempts = 0
    last_error: Exception | None = None
    while attempts < cfg.max_attempts:
        attempts += 1
        try:
            return llm.invoke(payload)
        except Exception as e:  # noqa: BLE001
            is_transient = isinstance(e, tuple(TRANSIENT_EXCEPTION_TYPES))
            # Some OpenAI / router errors wrap JSON decode text; heuristic fallback
            if not is_transient and 'Expecting value' in str(e) and 'json' in str(e).lower():
                is_transient = True
            if attempts >= cfg.max_attempts or not is_transient:
                raise
            last_error = e
            delay = _compute_backoff(attempts, cfg)
            time.sleep(delay)
    # Should not reach here; safeguard
    if last_error:
        raise last_error
    raise RuntimeError('safe_invoke_llm: exhausted without exception context')
