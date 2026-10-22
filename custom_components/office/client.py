"""A member's side of the API: reads and sets the skip days at the host."""

from __future__ import annotations

import asyncio

import aiohttp

from .const import API_PATH


class OfficeApiError(Exception):
    """The host is not reachable or answered with an error."""


class OfficeAuthError(OfficeApiError):
    """The host does not know the token."""


class OfficeClient:
    def __init__(self, session: aiohttp.ClientSession, url: str, token: str) -> None:
        self._session = session
        self._base = url.rstrip("/") + API_PATH
        self._headers = {"Authorization": f"Bearer {token}"}

    async def state(self) -> dict:
        return await self._request("GET", self._base)

    async def set_skip(self, day: str, skip: bool) -> dict:
        return await self._request("PUT", f"{self._base}/skip_days/{day}", {"skip": skip})

    async def _request(self, method: str, url: str, body: dict | None = None) -> dict:
        try:
            async with self._session.request(
                method, url, json=body, headers=self._headers, timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                if resp.status in (401, 403):
                    raise OfficeAuthError("the host does not know this token")
                if resp.status >= 400:
                    raise OfficeApiError(f"{resp.status}: {(await resp.text())[:200]}")
                data = await resp.json()
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as err:
            raise OfficeApiError(str(err) or type(err).__name__) from err
        if not isinstance(data, dict) or data.get("version") != 1:
            raise OfficeApiError("unexpected answer from the host")
        return data
