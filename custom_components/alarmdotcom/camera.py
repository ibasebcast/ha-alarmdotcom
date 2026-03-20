"""Camera platform for Alarm.com cameras."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import DiscoveryInfoType

from .const import DATA_HUB, DOMAIN
from .hub import AlarmHub
from .util import cleanup_orphaned_entities_and_devices

log = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up Alarm.com camera entities."""
    hub: AlarmHub = hass.data[DOMAIN][config_entry.entry_id][DATA_HUB]

    if hub.camera_api is None:
        log.warning("Camera API not initialized, skipping Alarm.com cameras.")
        return

    try:
        cameras = await hub.camera_api.get_camera_list()
    except Exception:
        try:
            await hub.camera_api.ensure_logged_in()
            cameras = await hub.camera_api.get_camera_list()
        except Exception as err:
            log.error("Failed to fetch Alarm.com camera list: %s", err)
            return

    entities = [AdcWebRTCCameraEntity(hub=hub, info=cam) for cam in cameras]
    log.info("Discovered %s Alarm.com cameras.", len(entities))
    async_add_entities(entities)

    current_entity_ids = {entity.entity_id for entity in entities}
    current_unique_ids = {uid for uid in (entity.unique_id for entity in entities) if uid is not None}
    await cleanup_orphaned_entities_and_devices(
        hass,
        config_entry,
        current_entity_ids,
        current_unique_ids,
        "camera",
    )


class AdcWebRTCCameraEntity(Camera):
    """Alarm.com WebRTC camera."""

    _attr_has_entity_name = True
    _attr_should_poll = False
    _attr_supported_features = CameraEntityFeature.ON_OFF

    def __init__(self, hub: AlarmHub, info: dict[str, Any]) -> None:
        """Initialize the camera."""
        super().__init__()
        self.hub = hub
        self._info = info
        self.resource_id = str(info["id"])
        self._webrtc_config: dict[str, Any] | None = None

        self._attr_unique_id = f"{hub.api.active_system.id}-camera-{self.resource_id}"
        self._attr_name = info.get("description") or self.resource_id
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"camera_{self.resource_id}")},
            manufacturer="Alarm.com",
            name=self._attr_name,
            model=info.get("deviceModel"),
            sw_version=info.get("firmwareVersion"),
            via_device=(DOMAIN, str(hub.api.active_system.id)),
        )

    @property
    def available(self) -> bool:
        """Return if entity is available."""
        return self.hub.available and self.hub.camera_api is not None

    @property
    def is_on(self) -> bool:
        """Return true if live config is loaded."""
        return self._webrtc_config is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return extra attributes."""
        attrs = dict(self._info)
        if self._webrtc_config is not None:
            attrs["webrtc_config"] = self._webrtc_config
        return attrs

    async def async_turn_on(self) -> None:
        """Load WebRTC tokens for the camera."""
        if self.hub.camera_api is None:
            return
        try:
            config = await self.hub.camera_api.get_stream_info(self.resource_id)
            if not config:
                await self.hub.camera_api.ensure_logged_in()
                config = await self.hub.camera_api.get_stream_info(self.resource_id)
            self._webrtc_config = config
        except Exception as err:
            log.error("Failed to fetch WebRTC config for %s: %s", self.resource_id, err)
            self._webrtc_config = None
        self.async_write_ha_state()

    async def async_turn_off(self) -> None:
        """Clear cached WebRTC config."""
        self._webrtc_config = None
        self.async_write_ha_state()

    async def async_camera_image(self, width: int | None = None, height: int | None = None) -> bytes | None:
        """Return a still image response from the camera."""
        if self.hub.camera_api is None:
            return None
        try:
            image = await self.hub.camera_api.get_snapshot(self.resource_id)
            if image is None:
                await self.hub.camera_api.ensure_logged_in()
                image = await self.hub.camera_api.get_snapshot(self.resource_id)
            return image
        except Exception:
            return None
