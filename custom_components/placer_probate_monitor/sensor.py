"""Status sensors for Placer Probate Monitor."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ATTR_LAST_ERROR,
    ATTR_LAST_RESULT,
    ATTR_LAST_RUN,
    ATTR_NEW_COUNT,
    ATTR_PDF,
    DOMAIN,
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities(
        [
            PlacerProbateStatusSensor(hass, entry, "status", "Status", ATTR_LAST_RESULT),
            PlacerProbateStatusSensor(hass, entry, "last_run", "Last run", ATTR_LAST_RUN),
            PlacerProbateStatusSensor(hass, entry, "new_cases", "New cases", ATTR_NEW_COUNT),
            PlacerProbateStatusSensor(hass, entry, "last_pdf", "Last PDF", ATTR_PDF),
        ]
    )


class PlacerProbateStatusSensor(SensorEntity):
    _attr_has_entity_name = True
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_should_poll = False

    def __init__(
        self, hass: HomeAssistant, entry: ConfigEntry, key: str, name: str, attr: str
    ) -> None:
        self.hass = hass
        self._entry = entry
        self._attr = attr
        self._attr_name = name
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_icon = "mdi:gavel"

    @property
    def native_value(self):
        store = self.hass.data.get(DOMAIN, {}).get(self._entry.entry_id) or {}
        status = store.get("status") or {}
        if store.get("running") and self._attr == ATTR_LAST_RESULT:
            return "running"
        return status.get(self._attr)

    @property
    def extra_state_attributes(self):
        store = self.hass.data.get(DOMAIN, {}).get(self._entry.entry_id) or {}
        status = store.get("status") or {}
        return {
            ATTR_LAST_ERROR: status.get(ATTR_LAST_ERROR),
            "running": store.get("running", False),
        }

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(self.hass, f"{DOMAIN}_status", self._handle_update)
        )

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()
