"""Base entity for the receiver settings the telnet connection keeps current."""

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, override

from denonavr import DenonAVR
from denonavr.const import ALL_TELNET_EVENTS
from denonavr.exceptions import AvrCommandError, AvrProcessingError

from homeassistant.const import CONF_HOST, CONF_MODEL
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity, EntityDescription

from . import DenonavrConfigEntry
from .config_flow import CONF_MANUFACTURER, CONF_TYPE
from .const import CONF_USE_TELNET, DEFAULT_USE_TELNET, DOMAIN


def telnet_enabled(config_entry: DenonavrConfigEntry) -> bool:
    """Whether the settings entities have events to follow.

    Nothing polls the settings entities, so without telnet they would never
    leave their first state and each platform adds none.
    """
    return config_entry.options.get(CONF_USE_TELNET, DEFAULT_USE_TELNET)


@dataclass(frozen=True, kw_only=True)
class DenonAvrSettingDescription(EntityDescription):
    """A receiver setting read from the main zone."""

    value_fn: Callable[[DenonAVR], Any]


class DenonAvrSettingEntity(Entity):
    """A main-zone setting whose state follows the receiver's telnet events.

    The library parses every telnet line into its own properties, so the
    entity only has to re-read its property when a line arrives. State is
    written only when the value changed, because the receiver sends lines
    for unrelated changes (every volume step, every now-playing update).
    """

    entity_description: DenonAvrSettingDescription
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        receiver: DenonAVR,
        config_entry: DenonavrConfigEntry,
        description: DenonAvrSettingDescription,
    ) -> None:
        """Initialise the entity against the main zone's receiver object."""
        self.entity_description = description
        self._receiver = receiver
        device_id = config_entry.unique_id or config_entry.entry_id
        self._attr_unique_id = f"{device_id}-{description.key}"
        self._attr_device_info = DeviceInfo(
            configuration_url=f"http://{config_entry.data[CONF_HOST]}/",
            hw_version=config_entry.data[CONF_TYPE],
            identifiers={(DOMAIN, device_id)},
            manufacturer=config_entry.data[CONF_MANUFACTURER],
            model=config_entry.data[CONF_MODEL],
            name=receiver.name,
        )
        self._last_snapshot: tuple[Any, bool] | None = None

    @property
    def _value(self) -> Any:
        return self.entity_description.value_fn(self._receiver)

    @property
    @override
    def available(self) -> bool:
        """Available while the telnet connection is up."""
        return bool(self._receiver.telnet_healthy)

    def _snapshot(self) -> tuple[Any, bool]:
        return self._value, self.available

    def _telnet_callback(self, zone: str, event: str, parameter: str) -> None:
        snapshot = self._snapshot()
        if snapshot == self._last_snapshot:
            return
        self._last_snapshot = snapshot
        self.async_write_ha_state()

    @override
    async def async_added_to_hass(self) -> None:
        """Follow the receiver's telnet events."""
        self._last_snapshot = self._snapshot()
        self._receiver.register_callback(ALL_TELNET_EVENTS, self._telnet_callback)

    @override
    async def async_will_remove_from_hass(self) -> None:
        """Stop following telnet events."""
        self._receiver.unregister_callback(ALL_TELNET_EVENTS, self._telnet_callback)


async def async_send(coro) -> None:
    """Await a library command, surfacing its errors to the caller."""
    try:
        await coro
    except (AvrCommandError, AvrProcessingError) as err:
        raise HomeAssistantError(str(err)) from err
