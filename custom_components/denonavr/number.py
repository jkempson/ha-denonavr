"""Numeric receiver settings: tone controls and audio delay."""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import override

from denonavr import DenonAVR

from homeassistant.components.number import NumberEntity, NumberEntityDescription
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import DenonavrConfigEntry
from .entity import (
    DenonAvrSettingDescription,
    DenonAvrSettingEntity,
    async_send,
    telnet_enabled,
)

# The library reports and takes tone levels on its own 0 to 12 scale, where 6
# is flat (raw PSBAS/PSTRE 44 to 56). The entities show dB either side of flat.
TONE_FLAT = 6


def _tone_db(level: int | None) -> int | None:
    return None if level is None else level - TONE_FLAT


def _delay_ms(receiver: DenonAVR) -> int | None:
    # The telnet parser keeps the PSDELAY argument as the receiver sent it,
    # a zero-padded string such as "010".
    try:
        return int(receiver.delay)
    except (TypeError, ValueError):
        return None


def _set_delay(receiver: DenonAVR, ms: int) -> Awaitable[None]:
    # The library only steps the delay up or down. The receiver takes an
    # absolute value on the same command.
    return receiver.async_send_telnet_commands(f"PSDELAY {ms:03d}")


@dataclass(frozen=True, kw_only=True)
class DenonAvrNumberDescription(DenonAvrSettingDescription, NumberEntityDescription):
    """A numeric setting and how to write it."""

    set_fn: Callable[[DenonAVR, int], Awaitable[None]]


NUMBERS: tuple[DenonAvrNumberDescription, ...] = (
    DenonAvrNumberDescription(
        key="bass",
        name="Bass",
        icon="mdi:speaker",
        native_min_value=-TONE_FLAT,
        native_max_value=TONE_FLAT,
        native_step=1,
        native_unit_of_measurement="dB",
        entity_category=EntityCategory.CONFIG,
        value_fn=lambda r: _tone_db(r.bass),
        set_fn=lambda r, db: r.async_set_bass(db + TONE_FLAT),
    ),
    DenonAvrNumberDescription(
        key="treble",
        name="Treble",
        icon="mdi:speaker",
        native_min_value=-TONE_FLAT,
        native_max_value=TONE_FLAT,
        native_step=1,
        native_unit_of_measurement="dB",
        entity_category=EntityCategory.CONFIG,
        value_fn=lambda r: _tone_db(r.treble),
        set_fn=lambda r, db: r.async_set_treble(db + TONE_FLAT),
    ),
    DenonAvrNumberDescription(
        key="audio_delay",
        name="Audio delay",
        icon="mdi:timer-sand",
        native_min_value=0,
        native_max_value=200,
        native_step=1,
        native_unit_of_measurement=UnitOfTime.MILLISECONDS,
        entity_category=EntityCategory.CONFIG,
        value_fn=_delay_ms,
        set_fn=_set_delay,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: DenonavrConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add the main zone's numeric settings."""
    if not telnet_enabled(config_entry):
        return
    receiver = config_entry.runtime_data
    async_add_entities(
        DenonAvrNumber(receiver, config_entry, description) for description in NUMBERS
    )


class DenonAvrNumber(DenonAvrSettingEntity, NumberEntity):
    """A numeric receiver setting."""

    entity_description: DenonAvrNumberDescription

    @property
    @override
    def native_value(self) -> int | None:
        """Return the current value."""
        return self._value

    @override
    async def async_set_native_value(self, value: float) -> None:
        """Send the new value to the receiver."""
        await async_send(self.entity_description.set_fn(self._receiver, int(value)))
