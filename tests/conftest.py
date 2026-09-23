"""Shared fixtures for the denonavr custom integration tests."""

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Load custom_components/denonavr in place of the built-in integration."""
    return
