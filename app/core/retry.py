import asyncio
import inspect
import logging
import random
from typing import Callable, Any, List, Optional
import httpx
from botocore.exceptions import ClientError, EndpointConnectionError, ConnectTimeoutError
from fastapi import HTTPException
from app.core.config import get_settings

logger = logging.getLogger(__name__)

def is_retryable(exc: Exception) -> bool:
    """
    Determines if an exception represents a transient failure eligible for retry.
    """
    if isinstance(exc, (httpx.TimeoutException, httpx.ConnectError, httpx.NetworkError)):
        return True
        
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in {408, 429, 500, 502, 503, 504}
        
    if isinstance(exc, HTTPException):
        return exc.status_code in {408, 429, 500, 502, 503, 504}
        
    if isinstance(exc, (EndpointConnectionError, ConnectTimeoutError)):
        return True
        
    if isinstance(exc, ClientError):
        code = exc.response.get("Error", {}).get("Code", "")
        http_status = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0)
        if http_status in {408, 429, 500, 502, 503, 504}:
            return True
        if code in {"RequestTimeout", "SlowDown", "ServiceUnavailable", "InternalError"}:
            return True
            
    return False

async def retry_call(
    fn: Callable,
    *args,
    max_retries: Optional[int] = None,
    delays: Optional[List[float]] = None,
    jitter: Optional[bool] = None,
    op_label: str = "operation",
    **kwargs
) -> Any:
    """
    Bounded-retry executor for async or sync functions with backoff and jitter.
    """
    settings = get_settings()
    retries = max_retries if max_retries is not None else settings.EXTERNAL_CALL_MAX_RETRIES
    retry_delays = delays if delays is not None else settings.EXTERNAL_CALL_RETRY_DELAYS
    use_jitter = jitter if jitter is not None else settings.EXTERNAL_CALL_JITTER
    
    attempt = 0
    while True:
        try:
            if inspect.iscoroutinefunction(fn):
                return await fn(*args, **kwargs)
            else:
                return fn(*args, **kwargs)
        except Exception as exc:
            attempt += 1
            if attempt > retries or not is_retryable(exc):
                logger.warning(
                    f"[{op_label}] Failed on attempt {attempt}/{retries + 1} (retryable={is_retryable(exc)}): {exc}"
                )
                raise
                
            delay_idx = min(attempt - 1, len(retry_delays) - 1)
            base_delay = retry_delays[delay_idx]
            delay = base_delay * random.uniform(0.8, 1.2) if use_jitter else base_delay
            
            logger.info(
                f"[{op_label}] Transient failure on attempt {attempt}/{retries + 1}: {exc}. Retrying in {delay:.2f}s..."
            )
            await asyncio.sleep(delay)
