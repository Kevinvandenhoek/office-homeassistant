"""Base entities on the Office device: the skip days from the coordinator, the settings from the options."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import dt as dt_util

from .const import DEFAULTS, DOMAIN
from .coordinator import OfficeCoordinator


def device_info(entry: ConfigEntry) -> DeviceInfo:
    return DeviceInfo(
        identifiers={(DOMAIN, entry.entry_id)},
        name="Office",
        manufacturer="Office",
        entry_type=DeviceEntryType.SERVICE,
        configuration_url="https://github.com/Kevinvandenhoek/office-homeassistant",
    )


class OfficeEntity(CoordinatorEntity[OfficeCoordinator]):
    _attr_has_entity_name = True

    def __init__(self, coordinator: OfficeCoordinator, key: str) -> None:
        super().__init__(coordinator)
        self._attr_translation_key = key
        self._attr_unique_id = f"{coordinator.config_entry.entry_id}_{key}"
        self._attr_device_info = device_info(coordinator.config_entry)

    @property
    def today(self) -> str:
        return dt_util.now().date().isoformat()


class OfficeSetting(Entity):
    """A notification setting of this house, kept in the options; it works while the host is away."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, entry: ConfigEntry, key: str, option: str) -> None:
        self.entry = entry
        self.option = option
        self._attr_translation_key = key
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_device_info = device_info(entry)

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(self.entry.add_update_listener(self._entry_updated))

    async def _entry_updated(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.async_write_ha_state()

    @property
    def value(self) -> Any:
        return self.entry.options.get(self.option, DEFAULTS[self.option])

    def set(self, value: Any) -> None:
        self.hass.config_entries.async_update_entry(self.entry, options={**self.entry.options, self.option: value})
        self.async_write_ha_state()
