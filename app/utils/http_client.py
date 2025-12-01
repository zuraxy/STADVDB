"""Thin HTTP client wrapper with retries for peer communication."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Optional

import httpx

_LOGGER = logging.getLogger(__name__)


class HTTPClient:
    """Wrapper around httpx.AsyncClient with retry/backoff."""

    def __init__(self, timeout: float = 10.0, max_retries: int = 3) -> None:
        self._client = httpx.AsyncClient(timeout=timeout)
        self._max_retries = max_retries

    async def _request_with_retries(
        self,
        method: str,
        url: str,
        **kwargs: Any,
    ) -> httpx.Response:
        delay = 0.5
        last_exc: Optional[Exception] = None
        for attempt in range(1, self._max_retries + 2):
            try:
                response = await self._client.request(method, url, **kwargs)
                response.raise_for_status()
                return response
            except Exception as exc:  # pragma: no cover - exercised via unit tests
                last_exc = exc
                _LOGGER.warning(
                    "HTTP %s %s failed on attempt %s/%s: %s",
                    method,
                    url,
                    attempt,
                    self._max_retries + 1,
                    exc,
                )
                await asyncio.sleep(delay)
                delay = min(delay * 2, 5)
        assert last_exc is not None
        raise last_exc

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
