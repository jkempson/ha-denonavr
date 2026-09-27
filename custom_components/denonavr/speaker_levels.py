"""Speaker levels from the receiver's setup menu (Speakers > Levels).

These are the per-channel trims Audyssey writes, applied on every input. The
receiver offers no telnet command for them and sends no event when they
change, so they are read and written through its web setup form and polled.
"""

import asyncio
from dataclasses import dataclass
from datetime import timedelta
from html.parser import HTMLParser
import logging
from typing import override

from aiohttp import ClientError, ClientSession, ClientTimeout
from denonavr import DenonAVR
from denonavr.const import CHANNEL_MAP

from homeassistant.components.number import NumberEntity
from homeassistant.const import CONF_HOST, EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from . import DenonavrConfigEntry
from .entity import receiver_device_info, setting_unique_id

_LOGGER = logging.getLogger(__name__)

FORM_PATH = "SETUP/SPEAKERS/LEVELS/d_speakersetup.asp"
SUBMIT_PATH = "SETUP/SPEAKERS/LEVELS/s_speakersetup.asp"
FIELD_PREFIX = "textCV"
LOCK_FIELDS = ("setPureDirectOn", "setSetupLock")
# The fields a browser submits. The form's Set control is a plain button.
SUBMITTED_TYPES = ("hidden", "text", "number")
LEVEL_LIMIT = 12
LEVEL_STEP = 0.5
POLL_INTERVAL = timedelta(minutes=1)
TIMEOUT = ClientTimeout(total=5)
# The receiver acknowledges the POST before it has stored the new value.
SETTLE_SECONDS = 0.3


class _FormFields(HTMLParser):
    """Collect the form's named input values without running its scripts."""

    def __init__(self, html: str) -> None:
        super().__init__(convert_charrefs=True)
        self.values: dict[str, str] = {}
        self.feed(html)

    @override
    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        fields = dict(attrs)
        name = fields.get("name")
        kind = (fields.get("type") or "text").lower()
        if (
            tag == "input"
            and name
            and kind in SUBMITTED_TYPES
            and "disabled" not in fields
        ):
            self.values[name] = fields.get("value") or ""


@dataclass(frozen=True)
class SpeakerLevels:
    """One reading of the Levels form."""

    fields: dict[str, str]

    @property
    def locked(self) -> bool:
        """Setup lock and Pure Direct both make the receiver ignore the form."""
        return any(self.fields.get(name) == "ON" for name in LOCK_FIELDS)

    @property
    def levels(self) -> dict[str, float]:
        """Level in dB by channel code, for the channels the layout drives."""
        levels = {}
        for name, value in self.fields.items():
            code = name.removeprefix(FIELD_PREFIX)
            if name.startswith(FIELD_PREFIX) and code in CHANNEL_MAP:
                try:
                    levels[code] = float(value)
                except ValueError:
                    continue
        return levels


class SpeakerLevelsClient:
    """Reads and writes the Levels form on the receiver's web server."""

    def __init__(self, session: ClientSession, host: str) -> None:
        """Point the client at the receiver."""
        self._session = session
        self._base_url = f"http://{host}"

    async def async_read(self) -> SpeakerLevels:
        """Fetch the form as it stands."""
        async with self._session.get(
            f"{self._base_url}/{FORM_PATH}", timeout=TIMEOUT
        ) as response:
            response.raise_for_status()
            return SpeakerLevels(_FormFields(await response.text()).values)

    async def async_write(self, code: str, db: float) -> SpeakerLevels:
        """Set one channel, posting the rest of the form unchanged.

        Returns the form read back afterwards, and raises if the receiver
        did not keep the new value.
        """
        current = await self.async_read()
        if current.locked:
            raise HomeAssistantError("Receiver setup is locked or Pure Direct is on")
        if code not in current.levels:
            raise HomeAssistantError(f"Receiver has no {code} speaker level")
        payload = dict(current.fields)
        payload[f"{FIELD_PREFIX}{code}"] = format(db, "g")
        payload["setCLA"] = "Set"
        async with self._session.post(
            f"{self._base_url}/{SUBMIT_PATH}", data=payload, timeout=TIMEOUT
        ) as response:
            response.raise_for_status()
        await asyncio.sleep(SETTLE_SECONDS)
        after = await self.async_read()
        if after.levels.get(code) != db:
            raise HomeAssistantError(
                f"Receiver did not keep {code} at {db} dB,"
                f" it reads {after.levels.get(code)} dB"
            )
        return after


type SpeakerLevelsCoordinator = DataUpdateCoordinator[SpeakerLevels]


async def async_setup_speaker_levels(
    hass: HomeAssistant,
    config_entry: DenonavrConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Poll the Levels form and add a number for each channel it lists."""
    client = SpeakerLevelsClient(
        async_get_clientsession(hass), config_entry.data[CONF_HOST]
    )

    async def _async_update() -> SpeakerLevels:
        try:
            return await client.async_read()
        except (ClientError, TimeoutError) as err:
            raise UpdateFailed(f"Could not read speaker levels: {err}") from err

    coordinator: SpeakerLevelsCoordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        config_entry=config_entry,
        name="denonavr speaker levels",
        update_interval=POLL_INTERVAL,
        update_method=_async_update,
    )
    receiver = config_entry.runtime_data
    added: set[str] = set()

    # A receiver that is unreachable at start-up has its channels added on
    # the first poll that succeeds.
    @callback
    def add_listed_channels() -> None:
        if coordinator.data is None:
            return
        new = [code for code in coordinator.data.levels if code not in added]
        if not new:
            return
        added.update(new)
        async_add_entities(
            SpeakerLevelNumber(coordinator, client, receiver, config_entry, code)
            for code in new
        )

    config_entry.async_on_unload(coordinator.async_add_listener(add_listed_channels))
    await coordinator.async_refresh()
    add_listed_channels()


class SpeakerLevelNumber(CoordinatorEntity[SpeakerLevelsCoordinator], NumberEntity):
    """One channel's level on Speakers > Levels."""

    _attr_has_entity_name = True
    _attr_icon = "mdi:speaker"
    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_min_value = -LEVEL_LIMIT
    _attr_native_max_value = LEVEL_LIMIT
    _attr_native_step = LEVEL_STEP
    _attr_native_unit_of_measurement = "dB"

    def __init__(
        self,
        coordinator: SpeakerLevelsCoordinator,
        client: SpeakerLevelsClient,
        receiver: DenonAVR,
        config_entry: DenonavrConfigEntry,
        code: str,
    ) -> None:
        """Initialise the entity for one channel code."""
        super().__init__(coordinator)
        self._client = client
        self._code = code
        channel = CHANNEL_MAP[code].capitalize().replace("Center", "Centre")
        self._attr_name = f"{channel} speaker level"
        self._attr_unique_id = setting_unique_id(
            config_entry, f"speaker_level_{code.lower()}"
        )
        self._attr_device_info = receiver_device_info(config_entry, receiver)

    @property
    @override
    def available(self) -> bool:
        """Available while the last poll succeeded and listed this channel."""
        return super().available and self._code in self.coordinator.data.levels

    @property
    @override
    def native_value(self) -> float | None:
        """Return the level in dB."""
        return self.coordinator.data.levels.get(self._code)

    @override
    async def async_set_native_value(self, value: float) -> None:
        """Write the level, snapped to the receiver's half-dB step."""
        db = round(value / LEVEL_STEP) * LEVEL_STEP
        try:
            readback = await self._client.async_write(self._code, db)
        except (ClientError, TimeoutError) as err:
            raise HomeAssistantError(f"Could not reach the receiver: {err}") from err
        self.coordinator.async_set_updated_data(readback)
