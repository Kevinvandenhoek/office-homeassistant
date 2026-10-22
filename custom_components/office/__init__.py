"""Office: colleagues see each other's skip days, through one Home Assistant that hosts the office."""

from __future__ import annotations

from pathlib import Path

import voluptuous as vol

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import async_get_integration

from .api import OfficeEventsView, OfficeSkipDayView, OfficeStateView
from .client import OfficeClient
from .const import CONF_ROLE, CONF_TOKEN, CONF_URL, DOMAIN, ROLE_HOST, STATIC_PATH
from .coordinator import OfficeCoordinator
from .hub import OfficeHub
from .notifier import Notifier

PLATFORMS = [Platform.CALENDAR, Platform.SELECT, Platform.SENSOR, Platform.SWITCH, Platform.TIME]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)
SET_SKIP_DAY = vol.Schema({vol.Required("date"): cv.date, vol.Required("skip"): cv.boolean})

type OfficeConfigEntry = ConfigEntry[OfficeCoordinator]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """The card for dashboards, loaded on every page, and the service for days other than today."""
    version = (await async_get_integration(hass, DOMAIN)).version
    await hass.http.async_register_static_paths(
        [StaticPathConfig(STATIC_PATH, str(Path(__file__).parent / "frontend"), True)]
    )
    add_extra_js_url(hass, f"{STATIC_PATH}/office-card.js?v={version}")

    async def set_skip_day(call: ServiceCall) -> None:
        entries = [e for e in hass.config_entries.async_entries(DOMAIN) if e.state is ConfigEntryState.LOADED]
        if not entries:
            raise ServiceValidationError("Office is not set up")
        await entries[0].runtime_data.set_skip(call.data["date"].isoformat(), call.data["skip"])

    hass.services.async_register(DOMAIN, "set_skip_day", set_skip_day, schema=SET_SKIP_DAY)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: OfficeConfigEntry) -> bool:
    if entry.data[CONF_ROLE] == ROLE_HOST:
        hub = OfficeHub(hass, entry)
        await hub.async_load()
        entry.async_on_unload(hub.async_stop)
        domain = hass.data.setdefault(DOMAIN, {})
        domain["hub"] = hub
        entry.async_on_unload(lambda: domain.pop("hub", None))
        # Views cannot be removed again; they look the hub up, and answer 503 while it is gone.
        if not domain.get("views"):
            hass.http.register_view(OfficeStateView())
            hass.http.register_view(OfficeSkipDayView())
            hass.http.register_view(OfficeEventsView())
            domain["views"] = True
        coordinator = OfficeCoordinator(hass, entry, hub=hub)
    else:
        client = OfficeClient(async_get_clientsession(hass), entry.data[CONF_URL], entry.data[CONF_TOKEN])
        coordinator = OfficeCoordinator(hass, entry, client=client)
    await coordinator.async_config_entry_first_refresh()
    entry.runtime_data = coordinator
    if entry.data[CONF_ROLE] != ROLE_HOST:
        entry.async_create_background_task(hass, coordinator.listen(), "office stream")
    await Notifier(hass, entry, coordinator).async_start()
    # The settings are read when they are used, so only a change of the office days needs a fresh look.
    entry.async_on_unload(entry.add_update_listener(_options_updated))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _options_updated(hass: HomeAssistant, entry: OfficeConfigEntry) -> None:
    hub = entry.runtime_data.hub
    if hub:
        # Other office days: the members on a stream get them now.
        hub.changed()
    else:
        await entry.runtime_data.async_request_refresh()


async def async_unload_entry(hass: HomeAssistant, entry: OfficeConfigEntry) -> bool:
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
