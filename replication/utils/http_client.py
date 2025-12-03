"""Thin HTTP client wrapper with retries for peer communication."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional

import httpx

_LOGGER = logging.getLogger(__name__)


class HTTPClient:
    """Wrapper around httpx.AsyncClient with retry/backoff."""

    def __init__(self, timeout: float = 5.0, max_retries: int = 2) -> None:
        # Reduced default timeout for faster failure detection
        self._client = httpx.AsyncClient(timeout=timeout)
        self._max_retries = max_retries
        self._node_errors: Dict[str, str] = {}  # Track per-node errors

    def get_node_error(self, node_url: str) -> Optional[str]:
        """Get the last error for a node URL."""
        return self._node_errors.get(node_url)

    def clear_node_error(self, node_url: str) -> None:
        """Clear error state for a node."""
        self._node_errors.pop(node_url, None)

    async def _request_with_retries(
        self,
        method: str,
        url: str,
        raise_on_error: bool = True,
        **kwargs: Any,
    ) -> httpx.Response:
        delay = 0.3  # Faster initial retry
        last_exc: Optional[Exception] = None
        
        for attempt in range(1, self._max_retries + 2):
            try:
                response = await self._client.request(method, url, **kwargs)
                response.raise_for_status()
                # Clear error on success
                base_url = url.split('/')[0] + '//' + url.split('/')[2] if '://' in url else url
                self._node_errors.pop(base_url, None)
                return response
            except httpx.TimeoutException as exc:
                last_exc = exc
                base_url = url.split('/')[0] + '//' + url.split('/')[2] if '://' in url else url
                self._node_errors[base_url] = f"Timeout after {self._client.timeout.connect}s"
                _LOGGER.warning(
                    "HTTP %s %s timeout on attempt %s/%s",
                    method, url, attempt, self._max_retries + 1,
                )
                if attempt <= self._max_retries:
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, 2)
            except httpx.ConnectError as exc:
                last_exc = exc
                base_url = url.split('/')[0] + '//' + url.split('/')[2] if '://' in url else url
                self._node_errors[base_url] = "Connection refused"
                _LOGGER.warning(
                    "HTTP %s %s connection failed on attempt %s/%s: %s",
                    method, url, attempt, self._max_retries + 1, exc,
                )
                if attempt <= self._max_retries:
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, 2)
            except Exception as exc:
                last_exc = exc
                base_url = url.split('/')[0] + '//' + url.split('/')[2] if '://' in url else url
                self._node_errors[base_url] = str(exc)
                _LOGGER.warning(
                    "HTTP %s %s failed on attempt %s/%s: %s",
                    method, url, attempt, self._max_retries + 1, exc,
                )
                if attempt <= self._max_retries:
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, 2)
        
        if raise_on_error and last_exc is not None:
            raise last_exc
        return None  # type: ignore

    async def get_json_safe(self, url: str, params: Optional[Dict[str, Any]] = None, default: Any = None) -> Any:
        """Get JSON with fallback to default on failure (no exception)."""
        try:
            response = await self._request_with_retries("GET", url, params=params, raise_on_error=False)
            if response is not None:
                return response.json()
        except Exception as e:
            _LOGGER.debug("get_json_safe failed for %s: %s", url, e)
        return default

    async def get_json(self, url: str, params: Optional[Dict[str, Any]] = None) -> Any:
        response = await self._request_with_retries("GET", url, params=params)
        return response.json()

    async def post_json(self, url: str, payload: Dict[str, Any]) -> Any:
        response = await self._request_with_retries("POST", url, json=payload)
        return response.json()

    async def put_json(self, url: str, payload: Dict[str, Any]) -> Any:
        response = await self._request_with_retries("PUT", url, json=payload)
        return response.json()

    async def delete(self, url: str) -> Any:
        response = await self._request_with_retries("DELETE", url)
        if response.content:
            return response.json()
        return {"status": response.status_code}

    async def close(self) -> None:
        await self._client.aclose()
