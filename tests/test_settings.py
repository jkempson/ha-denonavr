"""Tests for the telnet-driven receiver settings entities."""

from unittest.mock import MagicMock, patch

from denonavr.exceptions import AvrCommandError
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

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
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers import entity_registry as er

NAME = "Test_Receiver"
UNIQUE_ID = "model5-123456789"
PLAYER = f"media_player.{NAME.lower()}"
BASS = f"number.{NAME.lower()}_bass"
TREBLE = f"number.{NAME.lower()}_treble"
AUDIO_DELAY = f"number.{NAME.lower()}_audio_delay"
DYNAMIC_VOLUME = f"select.{NAME.lower()}_dynamic_volume"
MULTI_EQ = f"select.{NAME.lower()}_multeq"
REF_LEVEL = f"select.{NAME.lower()}_reference_level_offset"
DYNAMIC_EQ = f"switch.{NAME.lower()}_dynamic_eq"


@pytest.fixture(name="client")
def client_fixture():
    """A receiver whose telnet feed the test drives by hand."""
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
        client.telnet_healthy = True
        client.bass = 8
        client.treble = 6
        client.delay = "010"
        client.dynamic_volume = "Off"
        client.multi_eq = "Reference"
        client.reference_level_offset = "0dB"
        client.dynamic_eq = True
        # An attrs instance attribute, which autospec cannot see on the class.
        client.audyssey = MagicMock()
        client.audyssey.dynamic_volume_setting_list = [
            "Off",
            "Light",
            "Medium",
            "Heavy",
        ]
        client.audyssey.multi_eq_setting_list = ["Off", "Flat", "Reference"]
        client.audyssey.reference_level_offset_setting_list = ["0dB", "+5dB"]
        callbacks = []
        client.register_callback.side_effect = lambda _event, cb: callbacks.append(cb)
        client.fire = lambda: [cb("Main", "PS", "") for cb in list(callbacks)]
        yield client


async def setup_receiver(hass: HomeAssistant, use_telnet: bool = True) -> None:
    """Add a receiver config entry with telnet on or off."""
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
        options={CONF_USE_TELNET: use_telnet},
    )
    entry.add_to_hass(hass)
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_states_read_from_receiver(hass: HomeAssistant, client) -> None:
    """Tone shows as dB either side of flat and delay as a number of ms."""
    await setup_receiver(hass)

    assert hass.states.get(BASS).state == "2"
    assert hass.states.get(TREBLE).state == "0"
    assert hass.states.get(AUDIO_DELAY).state == "10"
    assert hass.states.get(DYNAMIC_VOLUME).state == "Off"
    assert hass.states.get(MULTI_EQ).state == "Reference"
    assert hass.states.get(REF_LEVEL).state == "0dB"
    assert hass.states.get(DYNAMIC_EQ).state == STATE_ON
    assert hass.states.get(BASS).attributes["min"] == -6
    assert hass.states.get(BASS).attributes["max"] == 6
    assert hass.states.get(DYNAMIC_VOLUME).attributes["options"] == [
        "Off",
        "Light",
        "Medium",
        "Heavy",
    ]


async def test_entities_share_the_media_player_device(
    hass: HomeAssistant, client, entity_registry: er.EntityRegistry
) -> None:
    """Settings sit on the same device as the media player."""
    await setup_receiver(hass)

    player = entity_registry.async_get(PLAYER)
    bass = entity_registry.async_get(BASS)
    assert bass.device_id == player.device_id
    assert bass.unique_id == f"{UNIQUE_ID}-bass"


async def test_no_settings_without_telnet(hass: HomeAssistant, client) -> None:
    """Without telnet nothing would update them, so none are created."""
    await setup_receiver(hass, use_telnet=False)

    assert hass.states.get(PLAYER)
    assert hass.states.get(BASS) is None
    assert hass.states.get(DYNAMIC_VOLUME) is None
    assert hass.states.get(DYNAMIC_EQ) is None


async def test_telnet_event_updates_state(hass: HomeAssistant, client) -> None:
    """A change pushed over telnet reaches the entity state."""
    await setup_receiver(hass)

    client.bass = 2
    client.dynamic_volume = "Heavy"
    client.dynamic_eq = False
    client.fire()
    await hass.async_block_till_done()

    assert hass.states.get(BASS).state == "-4"
    assert hass.states.get(DYNAMIC_VOLUME).state == "Heavy"
    assert hass.states.get(DYNAMIC_EQ).state == STATE_OFF


async def test_unchanged_event_does_not_write_state(
    hass: HomeAssistant, client
) -> None:
    """Unrelated telnet lines leave the entity's state untouched."""
    await setup_receiver(hass)
    before = hass.states.get(BASS).last_reported

    client.fire()
    await hass.async_block_till_done()

    assert hass.states.get(BASS).last_reported == before


async def test_unavailable_when_telnet_drops(hass: HomeAssistant, client) -> None:
    """A dead telnet connection shows as unavailable."""
    await setup_receiver(hass)

    client.telnet_healthy = False
    client.fire()
    await hass.async_block_till_done()

    assert hass.states.get(BASS).state == STATE_UNAVAILABLE


async def test_unknown_until_receiver_reports(hass: HomeAssistant, client) -> None:
    """A value the receiver has not sent yet reads as unknown."""
    client.delay = None
    client.multi_eq = None
    await setup_receiver(hass)

    assert hass.states.get(AUDIO_DELAY).state == STATE_UNKNOWN
    assert hass.states.get(MULTI_EQ).state == STATE_UNKNOWN


@pytest.mark.parametrize(
    ("entity_id", "value", "method", "sent"),
    [
        (BASS, -6, "async_set_bass", 0),
        (BASS, 6, "async_set_bass", 12),
        (TREBLE, 3, "async_set_treble", 9),
    ],
)
async def test_set_tone(
    hass: HomeAssistant, client, entity_id, value, method, sent
) -> None:
    """dB from the entity goes to the library on its 0 to 12 scale."""
    await setup_receiver(hass)

    await hass.services.async_call(
        "number",
        "set_value",
        {ATTR_ENTITY_ID: entity_id, "value": value},
        blocking=True,
    )

    getattr(client, method).assert_awaited_once_with(sent)


@pytest.mark.parametrize(("ms", "command"), [(0, "PSDELAY 000"), (120, "PSDELAY 120")])
async def test_set_audio_delay(hass: HomeAssistant, client, ms, command) -> None:
    """Audio delay is sent as an absolute, zero-padded PSDELAY value."""
    await setup_receiver(hass)

    await hass.services.async_call(
        "number",
        "set_value",
        {ATTR_ENTITY_ID: AUDIO_DELAY, "value": ms},
        blocking=True,
    )

    client.async_send_telnet_commands.assert_awaited_once_with(command)


async def test_audio_delay_rejects_out_of_range(hass: HomeAssistant, client) -> None:
    """Values past the receiver's range never reach it."""
    await setup_receiver(hass)

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "number",
            "set_value",
            {ATTR_ENTITY_ID: AUDIO_DELAY, "value": 201},
            blocking=True,
        )
    client.async_send_telnet_commands.assert_not_awaited()


@pytest.mark.parametrize(
    ("entity_id", "option", "method"),
    [
        (DYNAMIC_VOLUME, "Medium", "async_set_dynamicvol"),
        (MULTI_EQ, "Flat", "async_set_multieq"),
        (REF_LEVEL, "+5dB", "async_set_reflevoffset"),
    ],
)
async def test_select_option(
    hass: HomeAssistant, client, entity_id, option, method
) -> None:
    """Choosing an option sends it to the receiver."""
    await setup_receiver(hass)

    await hass.services.async_call(
        "select",
        "select_option",
        {ATTR_ENTITY_ID: entity_id, "option": option},
        blocking=True,
    )

    getattr(client, method).assert_awaited_once_with(option)


@pytest.mark.parametrize(
    ("service", "method"),
    [("turn_on", "async_dynamic_eq_on"), ("turn_off", "async_dynamic_eq_off")],
)
async def test_dynamic_eq_switch(hass: HomeAssistant, client, service, method) -> None:
    """The switch turns Dynamic EQ on and off."""
    await setup_receiver(hass)

    await hass.services.async_call(
        "switch", service, {ATTR_ENTITY_ID: DYNAMIC_EQ}, blocking=True
    )

    getattr(client, method).assert_awaited_once()


async def test_receiver_error_surfaces(hass: HomeAssistant, client) -> None:
    """A command the receiver rejects fails the service call."""
    await setup_receiver(hass)
    client.async_set_dynamicvol.side_effect = AvrCommandError("rejected", "PSDYNVOL")

    with pytest.raises(HomeAssistantError, match="rejected"):
        await hass.services.async_call(
            "select",
            "select_option",
            {ATTR_ENTITY_ID: DYNAMIC_VOLUME, "option": "Heavy"},
            blocking=True,
        )


async def test_unload_stops_following_telnet(hass: HomeAssistant, client) -> None:
    """Unloading the entry removes every callback it registered."""
    await setup_receiver(hass)
    entry = hass.config_entries.async_entries(DOMAIN)[0]

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()

    assert client.unregister_callback.call_count == client.register_callback.call_count
