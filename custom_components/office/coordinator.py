"""The skip days as this house sees them: from the hub on the host, from the host's API on a member."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .client import OfficeApiError, OfficeAuthError, OfficeClient
from .const import DOMAIN
from .hub import OfficeHub

_LOGGER = logging.getLogger(__name__)

# The host looks at its own hub once a minute. A member gets every change on the host's stream, and looks
# itself every 15 minutes and after every break in the stream, in case the stream misses something.
HOST_INTERVAL = timedelta(minutes=1)
MEMBER_INTERVAL = timedelta(minutes=15)
# After a break the member connects again after 5 seconds, then twice as long each time, up to 5 minutes.
RETRY_FIRST = 5
RETRY_MAX = 300


class OfficeCoordinator(DataUpdateCoordinator[dict]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, hub: OfficeHub | None = None,
                 client: OfficeClient | None = None) -> None:
        super().__init__(hass, _LOGGER, config_entry=entry, name=DOMAIN,
                         update_interval=HOST_INTERVAL if hub else MEMBER_INTERVAL)
        self.hub = hub
        self.client = client
        if hub:
            entry.async_on_unload(hub.async_add_listener(lambda: self.async_set_updated_data(hub.view(hub.me))))

    async def listen(self) -> None:
        """A member's stream from the host, connected again after every break; runs until the entry unloads."""
        wait = RETRY_FIRST
        while True:
            try:
                async for data in self.client.events():
                    _LOGGER.debug("office: state from the stream")
                    self.async_set_updated_data(data)
                    wait = RETRY_FIRST
            except OfficeAuthError:
                # The poll asks for a new token; the stream waits for the entry to load again.
                await self.async_request_refresh()
                return
            except OfficeApiError as err:
                _LOGGER.debug("office: the stream broke: %s", err)
            # Look once now, so the entities show at once whether the host is still there.
            await self.async_request_refresh()
            await asyncio.sleep(wait)
            wait = min(wait * 2, RETRY_MAX)

    async def _async_update_data(self) -> dict:
        if self.hub:
            return self.hub.view(self.hub.me)
        try:
            return await self.client.state()
        except OfficeAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except OfficeApiError as err:
            raise UpdateFailed(f"the office is not reachable: {err}") from err

    async def set_skip(self, day: str, skip: bool) -> None:
        if self.hub:
            if not self.hub.can_skip(day):
                raise HomeAssistantError(f"{day} is not an office day from today to Sunday next week")
            self.hub.set_skip(self.hub.me, day, skip)
            return
        try:
            self.async_set_updated_data(await self.client.set_skip(day, skip))
        except OfficeApiError as err:
            raise HomeAssistantError(f"Could not set the skip day: {err}") from err
