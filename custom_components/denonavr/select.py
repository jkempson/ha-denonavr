"""Audyssey settings with a fixed set of options."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import override

from denonavr import DenonAVR

from homeassistant.components.select import SelectEntity, SelectEntityDescription
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


@dataclass(frozen=True, kw_only=True)
class DenonAvrSelectDescription(DenonAvrSettingDescription, SelectEntityDescription):
    """An option setting, where its options come from, and how to write it."""

    options_fn: Callable[[DenonAVR], list[str]]
    set_fn: Callable[[DenonAVR, str], Awaitable[None]]


SELECTS: tuple[DenonAvrSelectDescription, ...] = (
    DenonAvrSelectDescription(
        key="dynamic_volume",
        name="Dynamic Volume",
        icon="mdi:volume-vibrate",
        entity_category=EntityCategory.CONFIG,
        value_fn=lambda r: r.dynamic_volume,
        options_fn=lambda r: r.audyssey.dynamic_volume_setting_list,
        set_fn=lambda r, option: r.async_set_dynamicvol(option),
    ),
    DenonAvrSelectDescription(
        key="multi_eq",
        name="MultEQ",
        icon="mdi:equalizer",
        entity_category=EntityCategory.CONFIG,
        value_fn=lambda r: r.multi_eq,
        options_fn=lambda r: r.audyssey.multi_eq_setting_list,
        set_fn=lambda r, option: r.async_set_multieq(option),
    ),
    DenonAvrSelectDescription(
        key="reference_level_offset",
        name="Reference level offset",
        icon="mdi:tune-vertical",
        entity_category=EntityCategory.CONFIG,
        value_fn=lambda r: r.reference_level_offset,
        options_fn=lambda r: r.audyssey.reference_level_offset_setting_list,
        set_fn=lambda r, option: r.async_set_reflevoffset(option),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: DenonavrConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the main zone's Audyssey option settings."""
    if not telnet_enabled(config_entry):
        return
    receiver = config_entry.runtime_data
    async_add_entities(
        DenonAvrSelect(receiver, config_entry, description) for description in SELECTS
    )


class DenonAvrSelect(DenonAvrSettingEntity, SelectEntity):
    """An option setting on the receiver."""

    entity_description: DenonAvrSelectDescription

    @property
    @override
    def options(self) -> list[str]:
        """Return the options the receiver accepts."""
        return self.entity_description.options_fn(self._receiver)

    @property
    @override
    def current_option(self) -> str | None:
        """Return the selected option."""
        return self._value

    @override
    async def async_select_option(self, option: str) -> None:
        """Send the chosen option to the receiver."""
        await async_send(self.entity_description.set_fn(self._receiver, option))
