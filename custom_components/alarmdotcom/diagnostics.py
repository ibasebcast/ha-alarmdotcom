"""
Diagnostics support for Alarm.com.

Exposes everything the integration currently knows: config entry data
(redacted), connection/websocket health, and a raw JSON:API dump of every
resource across every controller (locks, sensors, thermostats, cameras,
partitions, etc.) - the same raw data the per-sensor "Debug" button logs
one device at a time, but comprehensive and available as a single
downloadable file via Settings -> Devices & Services -> Alarm.com ->
Download diagnostics (or per-device, from that device's own page).

Sensitive values (credentials, session tokens, camera stream tokens) are
redacted before this data is ever assembled into the returned dict -
diagnostics downloads are meant to be safe to attach to a GitHub issue.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntry

from .const import (
    CONF_ARM_CODE,
    CONF_CAMERA_MFA_CODE,
    CONF_CAMERA_MFA_COOKIE,
    CONF_MFA_TOKEN,
    CONF_OTP,
    DATA_HUB,
    DOMAIN,
)

if TYPE_CHECKING:
    from .hub import AlarmHub

# Config-entry-level fields, plus every raw JSON:API attribute key known to
# carry a live credential or session token (camera stream tokens in
# particular - see camera_api.py's _redact_stream_info, which redacts the
# same set for the separate, much narrower case of debug logging).
TO_REDACT = {
    CONF_USERNAME,
    CONF_PASSWORD,
    CONF_ARM_CODE,
    CONF_MFA_TOKEN,
    CONF_OTP,
    CONF_CAMERA_MFA_CODE,
    CONF_CAMERA_MFA_COOKIE,
    "mfa_cookie",
    "proxyUrl",
    "janusToken",
    "signallingServerToken",
    "cameraAuthToken",
    "credential",
    "username",
    "email",
    "ajax_key",
}


def _dump_all_resources(hub: AlarmHub) -> dict[str, list[dict[str, Any]]]:
    """
    Return a raw JSON:API dump of every resource across every controller.

    Keyed by controller class name (LockController, SensorController, etc.)
    so the output is grouped by device type without needing HA's own entity
    layer at all - this is the underlying Alarm.com data as the library
    receives it, before any of it gets mapped onto HA entities.
    """
    dump: dict[str, list[dict[str, Any]]] = {}
    for controller in hub.api.resource_controllers:
        dump[type(controller).__name__] = [
            resource.api_resource.to_dict() for resource in controller.items
        ]
    return dump


def _connection_health(hub: AlarmHub) -> dict[str, Any]:
    """Return connection/websocket health, independent of any specific device."""
    return {
        "available": hub.available,
        "active_system": {
            "id": hub.api.active_system.id,
            "name": hub.api.active_system.name,
        }
        if hub.api.active_system
        else None,
    }


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for the whole config entry (the full account)."""
    hub: AlarmHub = hass.data[DOMAIN][entry.entry_id][DATA_HUB]

    return async_redact_data(
        {
            "config_entry": {
                "data": dict(entry.data),
                "options": dict(entry.options),
            },
            "connection": _connection_health(hub),
            "resources": _dump_all_resources(hub),
        },
        TO_REDACT,
    )


async def async_get_device_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry, device: DeviceEntry
) -> dict[str, Any]:
    """
    Return diagnostics for a single device's page.

    Same underlying data as the config-entry-wide dump, filtered down to
    just the resource(s) backing this specific HA device - useful when
    someone's reporting an issue with one sensor/lock/camera and doesn't
    need (or want to share) the whole account's data.
    """
    hub: AlarmHub = hass.data[DOMAIN][entry.entry_id][DATA_HUB]

    device_identifiers = {identifier[1] for identifier in device.identifiers if identifier[0] == DOMAIN}

    matching_resources: dict[str, list[dict[str, Any]]] = {}
    for controller in hub.api.resource_controllers:
        matches = [
            resource.api_resource.to_dict()
            for resource in controller.items
            if resource.id in device_identifiers
        ]
        if matches:
            matching_resources[type(controller).__name__] = matches

    return async_redact_data(
        {
            "device": {
                "name": device.name,
                "model": device.model,
                "manufacturer": device.manufacturer,
            },
            "connection": _connection_health(hub),
            "resources": matching_resources,
        },
        TO_REDACT,
    )
