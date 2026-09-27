"""Shared fixtures for the denonavr custom integration tests."""

from urllib.parse import parse_qsl

import pytest
from pytest_homeassistant_custom_component.test_util.aiohttp import (
    AiohttpClientMocker,
    AiohttpClientMockResponse,
)

LEVELS_URL = "http://1.2.3.4/SETUP/SPEAKERS/LEVELS/d_speakersetup.asp"
LEVELS_SUBMIT_URL = "http://1.2.3.4/SETUP/SPEAKERS/LEVELS/s_speakersetup.asp"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Load custom_components/denonavr in place of the built-in integration."""
    return


class FakeLevelsForm:
    """The receiver's Speakers > Levels form, trimmed to what it posts."""

    def __init__(self) -> None:
        """Start from a 3.1 layout."""
        self.levels = {"FL": "1.5", "C": "-0.5", "FR": "-2.5", "SW": "-5.0"}
        self.locked = False
        self.keep_writes = True
        self.posts: list[dict[str, str]] = []

    def html(self) -> str:
        """Render the form the way the NR1506 does."""
        lock = "ON" if self.locked else "OFF"
        rows = "".join(
            f"<input id='RangeCV{code}' type='range' value='{db}' min='-12'"
            f" max='12' step='0.5'/>"
            f"<INPUT type='hidden' name='textCV{code}' value='{db}'>"
            for code, db in self.levels.items()
        )
        return (
            "<FORM name='spsetup' action='s_speakersetup.asp' method='POST'>"
            f"<INPUT type='hidden' name='setPureDirectOn' value='{lock}'>"
            "<INPUT type='hidden' name='setSetupLock' value='OFF'>"
            f"{rows}"
            "<INPUT type='button' name='setbtnCLA' value='Set'>"
            "<INPUT type='hidden' name='setCLA' value='off'></FORM>"
        )

    async def handle(self, method, url, data):
        """Serve the form, and store a submitted one."""
        if method.lower() == "post":
            fields = dict(parse_qsl(data)) if isinstance(data, str) else dict(data)
            self.posts.append(fields)
            if self.keep_writes and fields.get("setCLA") == "Set":
                for code in self.levels:
                    self.levels[code] = fields[f"textCV{code}"]
            return AiohttpClientMockResponse(method, url, text="")
        return AiohttpClientMockResponse(method, url, text=self.html())


@pytest.fixture(autouse=True)
def levels_form(aioclient_mock: AiohttpClientMocker) -> FakeLevelsForm:
    """Answer the integration's requests for the Levels form."""
    form = FakeLevelsForm()
    aioclient_mock.get(LEVELS_URL, side_effect=form.handle)
    aioclient_mock.post(LEVELS_SUBMIT_URL, side_effect=form.handle)
    return form


@pytest.fixture(autouse=True)
def no_settle_delay(monkeypatch):
    """Skip the wait for the receiver to store a write."""
    monkeypatch.setattr("custom_components.denonavr.speaker_levels.SETTLE_SECONDS", 0)
