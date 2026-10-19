"""Camera token refresh cadence follows the option (#93)."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import AsyncMock, MagicMock

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

# homeassistant.components.camera imports PyTurboJPEG at module level, and the
# test helper does not install component requirements. Skip rather than fail
# where it is absent; the options-flow tests still cover the option itself.
pytest.importorskip("turbojpeg")

from custom_components.alarmdotcom.camera import AlarmDotComCamera, async_setup_entry
from custom_components.alarmdotcom.const import DOMAIN


def _session_with_one_camera() -> MagicMock:
    session = MagicMock()
    session.session_generation = 1
    session.get_camera_list = AsyncMock(return_value=[{"id": "cam-1", "description": "Porch"}])
    return session


async def _setup(hass: HomeAssistant, options: dict) -> list[AlarmDotComCamera]:
    entry = MockConfigEntry(domain=DOMAIN, data={}, options=options, title="Alarm.com")
    entry.add_to_hass(hass)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = {"camera_session": _session_with_one_camera()}
    added: list[AlarmDotComCamera] = []
    await async_setup_entry(hass, entry, added.extend)
    return added


async def test_setup_passes_the_configured_interval_to_each_camera(hass: HomeAssistant) -> None:
    """A user who set 10 minutes gets a 10-minute refresh."""
    (camera,) = await _setup(hass, {"camera_token_refresh_interval": 10})
    assert camera._token_refresh_interval == timedelta(minutes=10)


async def test_setup_falls_back_to_thirty_minutes_when_unset(hass: HomeAssistant) -> None:
    """An entry configured before this option existed keeps the old hardcoded cadence."""
    (camera,) = await _setup(hass, {})
    assert camera._token_refresh_interval == timedelta(minutes=30)
