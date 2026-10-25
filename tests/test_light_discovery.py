"""Regression tests for provider-specific Alarm.com light discovery URLs."""

import pytest

from custom_components.alarmdotcom._pyalarmdotcomajax import AlarmBridge


def test_single_light_uses_scoped_query():
    """A single light must not be converted into a /lights/{id} request."""
    path = AlarmBridge._build_light_discovery_path({"123-456"})
    assert path == "devices/lights?ids%5B%5D=123-456"


def test_multiple_light_ids_are_sorted_and_encoded():
    """Multiple IDs must produce a stable, safely encoded query string."""
    path = AlarmBridge._build_light_discovery_path({"b/2", "a 1"})
    assert path == "devices/lights?ids%5B%5D=a+1&ids%5B%5D=b%2F2"


def test_empty_light_ids_are_rejected():
    """Do not accidentally issue an unscoped request."""
    with pytest.raises(ValueError, match="At least one light ID"):
        AlarmBridge._build_light_discovery_path(set())
