import time
import random
from typing import Any, Callable, Sequence, Union
import json

try:
    from tradingagents.utils.concurrency_limiter import limiter  # type: ignore
except Exception:  # pragma: no cover
    limiter = None  # Fallback if not available

# NOTE: The previous helper invoke_with_retries (llm_resilience.py) has been removed.
# All code should now use safe_invoke_llm + LLMRetryConfig for a single, consistent
# retry implementation (network/json transient errors with jittered exponential backoff).

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
        # Use NetworkError when available (httpx >= specific versions). Otherwise fall back to
        # RequestError rather than Exception to avoid masking programmer bugs (e.g. AttributeError, KeyError).
        httpx.NetworkError if hasattr(httpx, 'NetworkError') else httpx.RequestError,
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
    # Infer provider/model heuristically for limiting
    provider = getattr(llm, 'provider', None) or getattr(getattr(llm, '_client', None), 'provider', None)
    model_name = getattr(llm, 'model_name', None) or getattr(llm, 'model', None)

    while attempts < cfg.max_attempts:
        attempts += 1
        try:
            if limiter and (limiter._global_limit or provider in limiter._provider_limits):  # type: ignore[attr-defined]
                with limiter.acquire(provider=provider, model=model_name):
                    return llm.invoke(payload)
            else:
                return llm.invoke(payload)
        except Exception as e:  # noqa: BLE001
            is_transient = isinstance(e, tuple(TRANSIENT_EXCEPTION_TYPES))
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
