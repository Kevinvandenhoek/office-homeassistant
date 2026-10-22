"""The API of the host, for the members' Home Assistants.

Reachable from outside without a Home Assistant login: the member's token is the key. It only reads and writes
Office's own data, and a member can only change their own days. A wrong token counts as a failed login, so the
IP ban of Home Assistant applies.
"""

from __future__ import annotations

import asyncio
from http import HTTPStatus
import json

from aiohttp import web

from homeassistant.components.http import HomeAssistantView
from homeassistant.components.http.ban import process_wrong_login
from homeassistant.core import HomeAssistant

from .const import API_PATH, DOMAIN
from .hub import OfficeHub

MAX_BODY = 1024
# A line every 30 seconds, as Cloudflare closes a quiet connection after 100; after an hour the stream closes, so
# the member connects again and the token is checked again.
HEARTBEAT = 30
LIFETIME = 3600


def _error(status: HTTPStatus, message: str) -> web.Response:
    return web.json_response({"error": message}, status=status)


async def _member(request: web.Request) -> tuple[OfficeHub | None, str | None, web.Response | None]:
    hass: HomeAssistant = request.app["hass"]
    hub: OfficeHub | None = hass.data.get(DOMAIN, {}).get("hub")
    if hub is None:
        return None, None, _error(HTTPStatus.SERVICE_UNAVAILABLE, "office not running")
    header = request.headers.get("Authorization", "")
    member = hub.member_for_token(header[7:].strip()) if header.startswith("Bearer ") else None
    if member is None or member == hub.me:
        await process_wrong_login(request)
        return None, None, _error(HTTPStatus.UNAUTHORIZED, "unauthorized")
    return hub, member, None


class OfficeStateView(HomeAssistantView):
    """GET: the members, the office days and everyone's skip days, as the member with this token sees them."""

    url = API_PATH
    name = "api:office"
    requires_auth = False

    async def get(self, request: web.Request) -> web.Response:
        hub, member, error = await _member(request)
        if error:
            return error
        return web.json_response(hub.view(member))


class OfficeSkipDayView(HomeAssistantView):
    """PUT {"skip": true|false}: the member's own skip day on one office day in the shown weeks."""

    url = API_PATH + "/skip_days/{day}"
    name = "api:office:skip_day"
    requires_auth = False

    async def put(self, request: web.Request, day: str) -> web.Response:
        hub, member, error = await _member(request)
        if error:
            return error
        if request.content_length is None or request.content_length > MAX_BODY:
            return _error(HTTPStatus.BAD_REQUEST, "a JSON body of at most 1 kB expected")
        try:
            body = await request.json()
        except ValueError:
            return _error(HTTPStatus.BAD_REQUEST, "JSON expected")
        if not isinstance(body, dict) or set(body) != {"skip"} or not isinstance(body["skip"], bool):
            return _error(HTTPStatus.BAD_REQUEST, '{"skip": true or false} expected')
        if not hub.can_skip(day):
            return _error(HTTPStatus.BAD_REQUEST, "not an office day from today to Sunday next week")
        hub.set_skip(member, day, body["skip"])
        return web.json_response(hub.view(member))


class OfficeEventsView(HomeAssistantView):
    """GET, held open (Server-Sent Events): the state right away, then again after every change."""

    url = API_PATH + "/events"
    name = "api:office:events"
    requires_auth = False

    async def get(self, request: web.Request) -> web.StreamResponse:
        hub, member, error = await _member(request)
        if error:
            return error
        queue = hub.open_stream(member)
        if queue is None:
            return _error(HTTPStatus.SERVICE_UNAVAILABLE, "too many streams")
        response = web.StreamResponse(headers={
            "Content-Type": "text/event-stream", "Cache-Control": "no-cache", "X-Accel-Buffering": "no",
        })
        loop = asyncio.get_running_loop()
        end = loop.time() + LIFETIME
        try:
            await response.prepare(request)
            await _event(response, hub.view(member))
            while (left := end - loop.time()) > 0:
                try:
                    change = await asyncio.wait_for(queue.get(), timeout=min(HEARTBEAT, left))
                except TimeoutError:
                    await response.write(b": keepalive\n\n")
                    continue
                if change is None:
                    break
                await _event(response, hub.view(member))
        except ConnectionResetError:
            pass
        finally:
            hub.release_stream(member, queue)
        return response


async def _event(response: web.StreamResponse, data: dict) -> None:
    await response.write(f"event: state\ndata: {json.dumps(data)}\n\n".encode())
