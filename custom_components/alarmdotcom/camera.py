"""Camera platform for Alarm.com (WebRTC)."""
from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import TYPE_CHECKING, Any

import aiohttp
from homeassistant.components.camera import Camera, CameraEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.event import async_track_time_interval

from .const import (
    CONF_CAMERA_TOKEN_REFRESH_INTERVAL,
    CONF_OPTIONS_DEFAULT,
    DOMAIN,
)

if TYPE_CHECKING:
    from .camera_api import AlarmCameraSession

# Entities are updated via push (websocket events), not per-entity polling -
# PARALLEL_UPDATES has no effect on update frequency here, but setting it
# to 0 is still the correct, explicit signal for a push-based integration.
PARALLEL_UPDATES = 0

_LOGGER = logging.getLogger(__name__)



async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Alarm.com cameras from a config entry."""
    camera_session: AlarmCameraSession | None = hass.data[DOMAIN][entry.entry_id].get(
        "camera_session"
    )

    if camera_session is None:
        _LOGGER.debug(
            "No camera session available for entry %s, skipping camera setup.",
            entry.entry_id,
        )
        return

    try:
        login_generation = camera_session.session_generation
        cameras = await camera_session.get_camera_list()
    except aiohttp.ClientResponseError as err:
        if err.status in (401, 403):
            _LOGGER.warning("Camera list fetch unauthorized, attempting re-login.")
            try:
                await camera_session.ensure_login(login_generation)
                cameras = await camera_session.get_camera_list()
            except Exception as retry_err:
                # A failed retry must not propagate: this is a separate platform from
                # alarm_control_panel/sensor/etc, and accounts with no cameras configured
                # (or with a persistent camera-specific auth issue) should still get their
                # other entities. Previously an unhandled exception here could take down
                # camera setup - and, per reports, leave the rest of the integration's
                # entities unavailable too.
                _LOGGER.error(
                    "Camera list fetch failed after re-login attempt: %s. "
                    "Skipping camera setup; other entities are unaffected.",
                    retry_err,
                )
                return
        else:
            _LOGGER.error("Camera list fetch failed (%s), skipping.", err.status)
            return
    except Exception as err:
        _LOGGER.error("Camera list fetch failed: %s, skipping.", err)
        return

    if not cameras:
        _LOGGER.debug("No cameras found for entry %s, skipping camera setup.", entry.entry_id)
        return

    # User-configurable via the options flow (#93); the entry reloads on change.
    refresh_interval = timedelta(
        minutes=entry.options.get(
            CONF_CAMERA_TOKEN_REFRESH_INTERVAL,
            CONF_OPTIONS_DEFAULT[CONF_CAMERA_TOKEN_REFRESH_INTERVAL],
        )
    )

    async_add_entities(
        [
            AlarmDotComCamera(camera_session, cam, entry.entry_id, refresh_interval)
            for cam in cameras
        ]
    )


class AlarmDotComCamera(Camera):
    """Alarm.com WebRTC Camera entity."""

    _attr_has_entity_name = False
    _attr_supported_features = CameraEntityFeature.ON_OFF

    def __init__(
        self,
        session: AlarmCameraSession,
        info: dict,
        entry_id: str,
        token_refresh_interval: timedelta,
    ) -> None:
        """Initialize the camera."""
        super().__init__()
        self._session = session
        self._id = info["id"]
        self._name = info.get("description", self._id)
        self._entry_id = entry_id
        self._token_refresh_interval = token_refresh_interval

        self._attr_unique_id = f"{entry_id}_camera_{self._id}"
        self._attr_name = self._name
        self._webrtc_config: dict | None = None
        self._remove_refresh: CALLBACK_TYPE | None = None

        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, f"camera_{self._id}")},
            name=self._name,
            manufacturer="Alarm.com",
            model=info.get("deviceModel"),
            sw_version=info.get("firmwareVersion"),
        )

        self._fetch_lock = asyncio.Lock()

    async def async_added_to_hass(self) -> None:
        """Start periodic token refresh when entity is added."""
        await super().async_added_to_hass()

        await self._fetch_stream_info()

        self._remove_refresh = async_track_time_interval(
            self.hass,
            self._async_refresh_tokens,
            self._token_refresh_interval,
        )

    async def async_will_remove_from_hass(self) -> None:
        """Cancel periodic refresh when entity is removed."""
        if self._remove_refresh is not None:
            self._remove_refresh()
            self._remove_refresh = None

    async def _async_refresh_tokens(self, _now: Any = None) -> None:
        """Refresh WebRTC tokens unconditionally."""
        _LOGGER.debug("Refreshing WebRTC tokens for camera %s", self._id)
        await self._fetch_stream_info()

    async def _fetch_stream_info(self) -> None:
        """Fetch stream info from Alarm.com with one auth retry."""
        if self._fetch_lock.locked():
            _LOGGER.debug(
                "Token fetch already in progress for camera %s, skipping.",
                self._id,
            )
            return

        async with self._fetch_lock:
            try:
                login_generation = self._session.session_generation
                config = await self._session.get_stream_info(self._id)

            except aiohttp.ClientResponseError as err:
                if err.status in (401, 403):
                    _LOGGER.info(
                        "WebRTC auth failure for camera %s (HTTP %s), re-authenticating.",
                        self._id,
                        err.status,
                    )
                    try:
                        if self._session.owns_session:
                            # self._fetch_lock only guards this one camera entity.
                            # All cameras on this config entry share one AlarmCameraSession,
                            # so ensure_login() (rather than login() directly) is required
                            # here: it lets concurrent cameras hitting this same 401/403 at
                            # the same moment collapse into a single real login instead of
                            # each independently re-authenticating.
                            await self._session.ensure_login(login_generation)
                        else:
                            # Normal case: this camera is on the session shared with the
                            # AlarmBridge (owns_session=False). repair_shared_session()
                            # coordinates the swap to an independent session across all
                            # cameras sharing it, so only one real login happens even
                            # though all cameras' refresh timers tend to fire together.
                            self._session = await self._session.repair_shared_session(
                                login_generation
                            )

                        config = await self._session.get_stream_info(self._id)

                    except Exception as retry_err:
                        _LOGGER.error(
                            "WebRTC re-login failed for camera %s: %s",
                            self._id,
                            retry_err,
                        )
                        self._webrtc_config = None
                        self.async_write_ha_state()
                        return
                else:
                    _LOGGER.error(
                        "WebRTC token fetch failed for camera %s: HTTP %s",
                        self._id,
                        err.status,
                    )
                    self._webrtc_config = None
                    self.async_write_ha_state()
                    return

            except Exception as err:
                _LOGGER.error(
                    "WebRTC token fetch error for camera %s: %s",
                    self._id,
                    err,
                )
                self._webrtc_config = None
                self.async_write_ha_state()
                return

        if not config:
            _LOGGER.warning("Empty stream info returned for camera %s", self._id)
            self._webrtc_config = None
        else:
            self._webrtc_config = config
            _LOGGER.debug("WebRTC tokens refreshed for camera %s", self._id)

        self.async_write_ha_state()

    @property
    def is_on(self) -> bool:
        """Return true if we have a valid WebRTC config."""
        return self._webrtc_config is not None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Return state attributes including the WebRTC config."""
        return {"webrtc_config": self._webrtc_config}

    async def stream_source(self) -> str | None:
        """
        Return a native HA stream source.

        Alarm.com cameras in this integration use WebRTC config delivered
        through entity attributes, not a native HLS or RTSP stream URL.
        Returning None prevents Home Assistant from treating the config dict
        like a native stream object.
        """
        return None

    async def async_turn_on(self) -> None:
        """Fetch fresh WebRTC tokens on demand."""
        await self._fetch_stream_info()

    async def async_turn_off(self) -> None:
        """Clear the WebRTC config."""
        self._webrtc_config = None
        self.async_write_ha_state()

    async def async_camera_image(
        self, width: int | None = None, height: int | None = None
    ) -> bytes | None:
        """Return a still snapshot image from the camera."""
        try:
            resp = await self._session.get(
                f"https://www.alarm.com/web/api/video/devices/cameras/{self._id}/snapshot"
            )
            return await resp.read()
        except aiohttp.ClientResponseError as err:
            if err.status == 404:
                _LOGGER.debug("Camera %s does not support snapshots (404).", self._id)
            else:
                _LOGGER.debug(
                    "Snapshot fetch failed for camera %s: HTTP %s",
                    self._id,
                    err.status,
                )
        except Exception as err:
            _LOGGER.debug("Snapshot fetch error for camera %s: %s", self._id, err)

        return None
