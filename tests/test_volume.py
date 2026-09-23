"""Tests for main-zone volume keeping the receiver's half steps."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.denonavr.config_flow import (
    CONF_MANUFACTURER,
    CONF_SERIAL_NUMBER,
    CONF_TYPE,
    DOMAIN,
)
from custom_components.denonavr.const import CONF_USE_TELNET
from custom_components.denonavr.volume import telnet_volume_command
from homeassistant.const import ATTR_ENTITY_ID, CONF_HOST, CONF_MODEL
from homeassistant.core import HomeAssistant

PLAYER = "media_player.test_receiver"


@pytest.mark.parametrize(
    ("db", "command"),
    [
        (-80.0, "MV00"),
        (-75.0, "MV05"),
        (-74.5, "MV055"),
        (-36.0, "MV44"),
        (-30.5, "MV495"),
        (-30.3, "MV495"),
        (-30.8, "MV49"),
        (0.0, "MV80"),
        (18.0, "MV98"),
        (-90.0, "MV00"),
        (25.0, "MV98"),
    ],
)
def test_telnet_volume_command(db, command) -> None:
    """Half steps get a third digit and the range is clamped."""
    assert telnet_volume_command(db) == command


@pytest.fixture(name="client")
def client_fixture():
    """A main-zone receiver with telnet available."""
    with (
        patch(
            "custom_components.denonavr.receiver.DenonAVR", autospec=True
        ) as mock_class,
        patch("custom_components.denonavr.config_flow.denonavr.async_discover"),
    ):
        client = mock_class.return_value
        client.name = "Test_Receiver"
        client.model_name = "model5"
        client.serial_number = "123456789"
        client.manufacturer = "Marantz"
        client.receiver_type = "avr-x"
        client.zone = "Main"
        client.input_func_list = []
        client.sound_mode_list = []
        client.zones = {"Main": client}
        client.telnet_available = True
        client.telnet_healthy = True
        # attrs instance attributes, which autospec cannot see on the class.
        client.audyssey = MagicMock()
        # The settings entities load alongside the media player with telnet on.
        for attr in (
            "bass",
            "treble",
            "delay",
            "dynamic_volume",
            "multi_eq",
            "reference_level_offset",
            "dynamic_eq",
        ):
            setattr(client, attr, None)
        client.audyssey.dynamic_volume_setting_list = []
        client.audyssey.multi_eq_setting_list = []
        client.audyssey.reference_level_offset_setting_list = []
        client.telnet_api = MagicMock()
        client.telnet_api.async_send_commands = AsyncMock()
        yield client


async def setup_receiver(hass: HomeAssistant, use_telnet: bool = True) -> None:
    """Add a receiver config entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="model5-123456789",
        data={
            CONF_HOST: "1.2.3.4",
            CONF_MODEL: "model5",
            CONF_TYPE: "avr-x",
            CONF_MANUFACTURER: "Marantz",
            CONF_SERIAL_NUMBER: "123456789",
        },
        options={CONF_USE_TELNET: use_telnet},
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def set_level(hass: HomeAssistant, level: float) -> None:
    """Call media_player.volume_set on the receiver."""
    await hass.services.async_call(
        "media_player",
        "volume_set",
        {ATTR_ENTITY_ID: PLAYER, "volume_level": level},
        blocking=True,
    )


async def test_half_step_sent_over_telnet(hass: HomeAssistant, client) -> None:
    """0.495 is -30.5 dB and reaches the receiver as MV495."""
    await setup_receiver(hass)

    await set_level(hass, 0.495)

    client.telnet_api.async_send_commands.assert_awaited_once_with("MV495")
    client.async_set_volume.assert_not_awaited()


async def test_http_only_uses_library(hass: HomeAssistant, client) -> None:
    """Without telnet the library's HTTP path, which keeps half steps, is used."""
    client.telnet_available = False
    await setup_receiver(hass, use_telnet=False)

    await set_level(hass, 0.495)

    client.async_set_volume.assert_awaited_once_with(pytest.approx(-30.5))
    client.telnet_api.async_send_commands.assert_not_awaited()


async def test_other_zone_uses_library(hass: HomeAssistant, client) -> None:
    """Zone 2 and 3 use a different telnet prefix, so they go through the library."""
    client.zone = "Zone2"
    client.zones = {"Zone2": client}
    await setup_receiver(hass)

    await set_level(hass, 0.495)

    client.async_set_volume.assert_awaited_once_with(pytest.approx(-30.5))
    client.telnet_api.async_send_commands.assert_not_awaited()
