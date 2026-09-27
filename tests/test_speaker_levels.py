"""Tests for the Speakers > Levels entities read from the receiver's web form."""

from datetime import timedelta
from unittest.mock import MagicMock, patch

from aiohttp import ClientError
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from custom_components.denonavr.config_flow import (
    CONF_MANUFACTURER,
    CONF_SERIAL_NUMBER,
    CONF_TYPE,
    DOMAIN,
)
from custom_components.denonavr.const import CONF_USE_TELNET
from homeassistant.const import (
    ATTR_ENTITY_ID,
    CONF_HOST,
    CONF_MODEL,
    STATE_UNAVAILABLE,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

LEVELS_URL = "http://1.2.3.4/SETUP/SPEAKERS/LEVELS/d_speakersetup.asp"

NAME = "Test_Receiver"
UNIQUE_ID = "model5-123456789"
FRONT_LEFT = "number.test_receiver_front_left_speaker_level"
CENTRE = "number.test_receiver_centre_speaker_level"
SUB = "number.test_receiver_subwoofer_speaker_level"
SURROUND_LEFT = "number.test_receiver_surround_left_speaker_level"


@pytest.fixture(name="client")
def client_fixture():
    """A receiver with telnet off, so only the web form is in play."""
    with (
        patch(
            "custom_components.denonavr.receiver.DenonAVR", autospec=True
        ) as mock_class,
        patch("custom_components.denonavr.config_flow.denonavr.async_discover"),
    ):
        client = mock_class.return_value
        client.name = NAME
        client.model_name = "model5"
        client.serial_number = "123456789"
        client.manufacturer = "Marantz"
        client.receiver_type = "avr-x"
        client.zone = "Main"
        client.input_func_list = []
        client.sound_mode_list = []
        client.zones = {"Main": client}
        client.audyssey = MagicMock()
        yield client


async def setup_receiver(hass: HomeAssistant) -> None:
    """Add a receiver config entry."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=UNIQUE_ID,
        data={
            CONF_HOST: "1.2.3.4",
            CONF_MODEL: "model5",
            CONF_TYPE: "avr-x",
            CONF_MANUFACTURER: "Marantz",
            CONF_SERIAL_NUMBER: "123456789",
        },
        options={CONF_USE_TELNET: False},
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def set_level(hass: HomeAssistant, entity_id: str, value: float) -> None:
    """Call number.set_value and wait for it."""
    await hass.services.async_call(
        "number",
        "set_value",
        {ATTR_ENTITY_ID: entity_id, "value": value},
        blocking=True,
    )


async def test_levels_read_from_form(
    hass: HomeAssistant, client, entity_registry: er.EntityRegistry
) -> None:
    """Each channel on the form becomes a number on the receiver's device."""
    await setup_receiver(hass)

    assert hass.states.get(FRONT_LEFT).state == "1.5"
    assert hass.states.get(CENTRE).state == "-0.5"
    assert hass.states.get(SUB).state == "-5.0"
    assert hass.states.get(SURROUND_LEFT) is None
    assert hass.states.get(SUB).attributes["step"] == 0.5
    player = entity_registry.async_get("media_player.test_receiver")
    sub = entity_registry.async_get(SUB)
    assert sub.device_id == player.device_id
    assert sub.unique_id == f"{UNIQUE_ID}-speaker_level_sw"


async def test_write_posts_whole_form(hass: HomeAssistant, client, levels_form) -> None:
    """A write changes one field, keeps the rest, and shows the readback."""
    await setup_receiver(hass)

    await set_level(hass, SUB, -3.5)

    posted = levels_form.posts[-1]
    assert posted["textCVSW"] == "-3.5"
    assert posted["textCVFL"] == "1.5"
    assert posted["setCLA"] == "Set"
    assert posted["setPureDirectOn"] == "OFF"
    assert "setbtnCLA" not in posted
    assert hass.states.get(SUB).state == "-3.5"


async def test_write_snaps_to_half_db(hass: HomeAssistant, client, levels_form) -> None:
    """A value between steps is rounded to the receiver's half-dB step."""
    await setup_receiver(hass)

    await set_level(hass, CENTRE, 1.3)

    assert levels_form.posts[-1]["textCVC"] == "1.5"


async def test_write_refused_when_locked(
    hass: HomeAssistant, client, levels_form
) -> None:
    """Pure Direct or setup lock stops the write before anything is posted."""
    await setup_receiver(hass)
    levels_form.locked = True

    with pytest.raises(HomeAssistantError, match="locked"):
        await set_level(hass, SUB, 0)
    assert levels_form.posts == []


async def test_write_not_kept_is_an_error(
    hass: HomeAssistant, client, levels_form
) -> None:
    """A receiver that ignores the post fails the call and keeps the old state."""
    await setup_receiver(hass)
    levels_form.keep_writes = False

    with pytest.raises(HomeAssistantError, match="did not keep"):
        await set_level(hass, SUB, 2)
    assert hass.states.get(SUB).state == "-5.0"


async def test_poll_picks_up_change_on_receiver(
    hass: HomeAssistant, client, levels_form
) -> None:
    """A level changed on the receiver itself shows after the next poll."""
    await setup_receiver(hass)

    levels_form.levels["FL"] = "-1.0"
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=2))
    await hass.async_block_till_done()

    assert hass.states.get(FRONT_LEFT).state == "-1.0"


async def test_unreachable_receiver_is_unavailable_then_recovers(
    hass: HomeAssistant, client, aioclient_mock, levels_form
) -> None:
    """A failed poll marks the levels unavailable until one succeeds."""
    await setup_receiver(hass)
    aioclient_mock.clear_requests()
    aioclient_mock.get(LEVELS_URL, exc=ClientError("down"))

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=2))
    await hass.async_block_till_done()
    assert hass.states.get(SUB).state == STATE_UNAVAILABLE

    aioclient_mock.clear_requests()
    aioclient_mock.get(LEVELS_URL, side_effect=levels_form.handle)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=4))
    await hass.async_block_till_done()
    assert hass.states.get(SUB).state == "-5.0"


async def test_channels_added_when_first_poll_succeeds(
    hass: HomeAssistant, client, aioclient_mock, levels_form
) -> None:
    """A receiver offline at start-up gets its levels once it answers."""
    aioclient_mock.clear_requests()
    aioclient_mock.get(LEVELS_URL, exc=ClientError("down"))
    await setup_receiver(hass)
    assert hass.states.get(SUB) is None

    aioclient_mock.clear_requests()
    aioclient_mock.get(LEVELS_URL, side_effect=levels_form.handle)
    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=2))
    await hass.async_block_till_done()

    assert hass.states.get(SUB).state == "-5.0"
