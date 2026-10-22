"""The phone that gets the pushes: one of the notify services of the mobile apps."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CONF_PHONE, NO_PHONE
from .entity import OfficeSetting


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, add: AddConfigEntryEntitiesCallback) -> None:
    add([PhoneSelect(entry, "skip_day_phone", CONF_PHONE)])


class PhoneSelect(OfficeSetting, SelectEntity):
    _attr_icon = "mdi:cellphone"

    @property
    def options(self) -> list[str]:
        phones = sorted(f"notify.{s}" for s in self.hass.services.async_services_for_domain("notify") if s.startswith("mobile_app_"))
        if self.value and self.value not in phones:
            phones.append(self.value)
        return [NO_PHONE, *phones]

    @property
    def current_option(self) -> str:
        return self.value or NO_PHONE

    async def async_select_option(self, option: str) -> None:
        self.set(None if option == NO_PHONE else option)
