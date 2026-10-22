"""A member's side of the API: reads and sets the skip days at the host."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
import json

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

    async def events(self) -> AsyncIterator[dict]:
        """The state at every change, from the stream of the host, until it closes. The host sends a line every
        30 seconds, so 90 seconds without one means the connection is gone."""
        try:
            async with self._session.get(
                f"{self._base}/events", headers=self._headers, timeout=aiohttp.ClientTimeout(total=None, sock_read=90)
            ) as resp:
                if resp.status in (401, 403):
                    raise OfficeAuthError("the host does not know this token")
                if resp.status >= 400:
                    raise OfficeApiError(f"{resp.status}: {(await resp.text())[:200]}")
                lines: list[str] = []
                async for raw in resp.content:
                    line = raw.decode().rstrip("\r\n")
                    if line.startswith("data:"):
                        lines.append(line[5:].lstrip())
                    elif not line and lines:
                        yield _checked(json.loads("\n".join(lines)))
                        lines = []
        except (aiohttp.ClientError, asyncio.TimeoutError, ValueError) as err:
            raise OfficeApiError(str(err) or type(err).__name__) from err

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
        return _checked(data)


def _checked(data) -> dict:
    if not isinstance(data, dict) or data.get("version") != 1:
        raise OfficeApiError("unexpected answer from the host")
    return data
