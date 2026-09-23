"""Audyssey Dynamic EQ as a switch."""

from typing import Any, override

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import DenonavrConfigEntry
from .entity import (
    DenonAvrSettingDescription,
    DenonAvrSettingEntity,
    async_send,
    telnet_enabled,
)

DYNAMIC_EQ = DenonAvrSettingDescription(
    key="dynamic_eq",
    name="Dynamic EQ",
    icon="mdi:equalizer-outline",
    entity_category=EntityCategory.CONFIG,
    value_fn=lambda r: r.dynamic_eq,
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: DenonavrConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the main zone's Dynamic EQ switch."""
    if not telnet_enabled(config_entry):
        return
    async_add_entities(
        [DenonAvrDynamicEqSwitch(config_entry.runtime_data, config_entry, DYNAMIC_EQ)]
    )


class DenonAvrDynamicEqSwitch(DenonAvrSettingEntity, SwitchEntity):
    """Dynamic EQ on or off."""

    @property
    @override
    def is_on(self) -> bool | None:
        """Return whether Dynamic EQ is on."""
        return self._value

    @override
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn Dynamic EQ on."""
        await async_send(self._receiver.async_dynamic_eq_on())

    @override
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn Dynamic EQ off."""
        await async_send(self._receiver.async_dynamic_eq_off())
