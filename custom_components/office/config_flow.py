"""Set up Office: host the office in this house, or join one with the address and a token from the host."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from . import planner
from .client import OfficeApiError, OfficeAuthError, OfficeClient
from .const import CONF_NAME, CONF_OFFICE_DAYS, CONF_ROLE, CONF_TOKEN, CONF_URL, DOMAIN, ROLE_HOST, ROLE_MEMBER

TOKEN = TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD))
URL = TextSelector(TextSelectorConfig(type=TextSelectorType.URL))
DAYS = SelectSelector(SelectSelectorConfig(
    options=[SelectOptionDict(value=str(i), label=d) for i, d in enumerate(planner.WEEKDAYS)], multiple=True,
))


async def _check(hass, url: str, token: str) -> tuple[dict | None, str | None]:
    try:
        return await OfficeClient(async_get_clientsession(hass), url, token).state(), None
    except OfficeAuthError:
        return None, "invalid_auth"
    except OfficeApiError:
        return None, "cannot_connect"


class OfficeConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_show_menu(step_id="user", menu_options=["member", "host"])

    async def async_step_host(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        await self.async_set_unique_id(ROLE_HOST)
        self._abort_if_unique_id_configured()
        errors = {}
        if user_input is not None:
            name = user_input[CONF_NAME].strip()
            if not planner.member_id(name):
                errors[CONF_NAME] = "invalid_name"
            else:
                return self.async_create_entry(
                    title="Office", data={CONF_ROLE: ROLE_HOST, CONF_NAME: name},
                    options={CONF_OFFICE_DAYS: planner.DEFAULT_OFFICE_DAYS},
                )
        return self.async_show_form(step_id="host", data_schema=vol.Schema({vol.Required(CONF_NAME): str}), errors=errors)

    async def async_step_member(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors = {}
        if user_input is not None:
            url, token = user_input[CONF_URL].strip().rstrip("/"), user_input[CONF_TOKEN].strip()
            state, error = await _check(self.hass, url, token)
            if error:
                errors["base"] = error
            else:
                await self.async_set_unique_id(f"{url}#{state['me']}")
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=f"Office ({state['members'].get(state['me'], state['me'])})",
                    data={CONF_ROLE: ROLE_MEMBER, CONF_URL: url, CONF_TOKEN: token},
                )
        schema = vol.Schema({vol.Required(CONF_URL, default="https://"): URL, vol.Required(CONF_TOKEN): TOKEN})
        return self.async_show_form(step_id="member", data_schema=schema, errors=errors)

    async def async_step_reauth(self, entry_data: Mapping[str, Any]) -> ConfigFlowResult:
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        entry = self._get_reauth_entry()
        errors = {}
        if user_input is not None:
            token = user_input[CONF_TOKEN].strip()
            _, error = await _check(self.hass, entry.data[CONF_URL], token)
            if error:
                errors["base"] = error
            else:
                return self.async_update_reload_and_abort(entry, data_updates={CONF_TOKEN: token})
        return self.async_show_form(
            step_id="reauth_confirm", data_schema=vol.Schema({vol.Required(CONF_TOKEN): TOKEN}), errors=errors
        )

    @classmethod
    @callback
    def async_supports_options_flow(cls, config_entry: ConfigEntry) -> bool:
        return config_entry.data[CONF_ROLE] == ROLE_HOST

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return OfficeOptionsFlow()


class OfficeOptionsFlow(OptionsFlow):
    """On the host: the office days, and the colleagues with their tokens. The settings of the pushes are entities."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_show_menu(step_id="init", menu_options=["office_days", "add_member", "remove_member"])

    def _done(self, **changes: Any) -> ConfigFlowResult:
        return self.async_create_entry(data={**self.config_entry.options, **changes})

    async def async_step_office_days(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            return self._done(**{CONF_OFFICE_DAYS: sorted(int(d) for d in user_input[CONF_OFFICE_DAYS])})
        days = [str(d) for d in self.config_entry.options.get(CONF_OFFICE_DAYS, planner.DEFAULT_OFFICE_DAYS)]
        schema = vol.Schema({vol.Required(CONF_OFFICE_DAYS, default=days): DAYS})
        return self.async_show_form(step_id="office_days", data_schema=schema)

    async def async_step_add_member(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        hub = self.config_entry.runtime_data.hub
        errors = {}
        if user_input is not None:
            name = user_input[CONF_NAME].strip()
            if not planner.member_id(name) or planner.member_id(name) == hub.me:
                errors[CONF_NAME] = "invalid_name"
            else:
                self._token = hub.add_member(name)
                self._name = name
                return await self.async_step_token()
        return self.async_show_form(step_id="add_member", data_schema=vol.Schema({vol.Required(CONF_NAME): str}), errors=errors)

    async def async_step_token(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """The token, shown this once; only its hash is kept."""
        if user_input is not None:
            return self._done()
        return self.async_show_form(
            step_id="token", data_schema=vol.Schema({}),
            description_placeholders={"name": self._name, "token": self._token},
        )

    async def async_step_remove_member(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        hub = self.config_entry.runtime_data.hub
        colleagues = hub.colleagues()
        if not colleagues:
            return self.async_abort(reason="no_colleagues")
        if user_input is not None:
            hub.remove_member(user_input["member"])
            return self._done()
        options = [SelectOptionDict(value=m, label=n) for m, n in colleagues.items()]
        schema = vol.Schema({vol.Required("member"): SelectSelector(SelectSelectorConfig(options=options))})
        return self.async_show_form(step_id="remove_member", data_schema=schema)
