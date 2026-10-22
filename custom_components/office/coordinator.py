"""The skip days as this house sees them: from the hub on the host, from the host's API on a member."""

from __future__ import annotations

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

# A member looks once a minute; the host too, so a new day shows after midnight.
INTERVAL = timedelta(minutes=1)


class OfficeCoordinator(DataUpdateCoordinator[dict]):
    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, hub: OfficeHub | None = None,
                 client: OfficeClient | None = None) -> None:
        super().__init__(hass, _LOGGER, config_entry=entry, name=DOMAIN, update_interval=INTERVAL)
        self.hub = hub
        self.client = client
        if hub:
            entry.async_on_unload(hub.async_add_listener(lambda: self.async_set_updated_data(hub.view(hub.me))))

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
