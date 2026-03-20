"""Controller interfaces with the Alarm.com API via pyalarmdotcomajax."""

import asyncio
import logging

import pyalarmdotcomajax as pyadc
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from pyalarmdotcomajax import AlarmBridge

from .alarm_camera_api import AlarmCameraSession
from .const import (
    CONF_MFA_TOKEN,
    DATA_HUB,
    DOMAIN,
    PLATFORMS,
)

log = logging.getLogger(__name__)

CONF_CAMERA_AJAX_KEY = "camera_ajax_key"
CONF_CAMERA_MFA_COOKIE = "camera_mfa_cookie"
CONF_CAMERA_IDENTITY_ID = "camera_identity_id"


class AlarmHub:
    """Config-entry initiated Alarm Hub."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize the system."""
        self.hass: HomeAssistant = hass
        self.config_entry: ConfigEntry = config_entry

        self.api = AlarmBridge(
            username=config_entry.data[CONF_USERNAME],
            password=config_entry.data[CONF_PASSWORD],
            mfa_token=config_entry.data.get(CONF_MFA_TOKEN),
        )

        self.close_jobs: list[CALLBACK_TYPE] = []

        self.camera_api = AlarmCameraSession(
            username=config_entry.data[CONF_USERNAME],
            password=config_entry.data[CONF_PASSWORD],
            ajax_key=config_entry.data.get(CONF_CAMERA_AJAX_KEY),
            mfa_cookie=config_entry.data.get(CONF_CAMERA_MFA_COOKIE),
            identity_id=config_entry.data.get(CONF_CAMERA_IDENTITY_ID),
        )

        hass.data.setdefault(DOMAIN, {})[self.config_entry.entry_id] = {DATA_HUB: self}

        self.available: bool = True

    async def login(self) -> bool:
        """Log in to alarm.com."""
        try:
            await self.api.login()
        except pyadc.AuthenticationFailed as err:
            raise ConfigEntryAuthFailed from err
        except pyadc.MustConfigureMfa:
            log.error(
                "Alarm.com requires that two-factor authentication be set up on your account. "
                "Please log in to Alarm.com and set up two-factor authentication."
            )
            return False
        except Exception as err:
            log.error("Unexpected error during Alarm.com login: %s", err)
            return False

        return True

    async def _initialize_camera_session(self) -> None:
        """Initialize camera session and persist refreshed session values."""
        try:
            result = await self.camera_api.login()
            log.debug("Alarm.com camera session login result: %s", result)
        except Exception as err:
            log.warning("Camera session login failed during initialization: %s", err)
            return

        session_data = self.camera_api.session_data
        updated_data = dict(self.config_entry.data)
        changed = False

        for key, value in (
            (CONF_CAMERA_AJAX_KEY, session_data.get("ajax_key")),
            (CONF_CAMERA_MFA_COOKIE, session_data.get("mfa_cookie")),
            (CONF_CAMERA_IDENTITY_ID, session_data.get("identity_id")),
        ):
            if value and updated_data.get(key) != value:
                updated_data[key] = value
                changed = True

        if changed:
            self.hass.config_entries.async_update_entry(
                self.config_entry,
                data=updated_data,
            )
            log.debug("Persisted refreshed Alarm.com camera session metadata.")

    async def initialize(self) -> bool:
        """Initialize connection to Alarm.com after user-driven authentication has already taken place."""
        setup_ok = False

        try:
            async with asyncio.timeout(10):
                await self.api.initialize()
            setup_ok = True
        except (
            TimeoutError,
            pyadc.UnexpectedResponse,
            pyadc.ServiceUnavailable,
        ) as err:
            raise ConfigEntryNotReady("Could not connect to Alarm.com.") from err
        except pyadc.AuthenticationException as err:
            raise ConfigEntryAuthFailed from err
        except Exception:
            log.exception("Unexpected error during Alarm.com initialization.")
            return False
        finally:
            if not setup_ok:
                await self.api.close()
                await self.camera_api.close()

        await self._initialize_camera_session()

        await self.api.start_event_monitoring(_ws_state_handler)

        self.close_jobs.append(self.config_entry.add_update_listener(_update_listener))

        device_registry = dr.async_get(self.hass)

        device_registry.async_get_or_create(
            config_entry_id=self.config_entry.entry_id,
            identifiers={(DOMAIN, self.api.active_system.id)},
            manufacturer="Alarm.com",
            name=self.api.active_system.name,
            entry_type=dr.DeviceEntryType.SERVICE,
        )

        return True

    async def close(self) -> bool:
        """
        Reset this bridge to default state.

        Will cancel any scheduled setup retry and will unload
        the config entry.
        """
        while self.close_jobs:
            self.close_jobs.pop()()

        await self.api.close()
        await self.camera_api.close()

        unload_success: bool = await self.hass.config_entries.async_unload_platforms(
            self.config_entry, PLATFORMS
        )

        return unload_success


async def _ws_state_handler(message: pyadc.EventBrokerMessage) -> None:
    """Handle changes to websocket state for ConfigEntry and logging."""
    if not isinstance(message, pyadc.ConnectionEvent):
        return

    if message.current_state == pyadc.WebSocketState.DEAD:
        log.error("Alarm.com websocket state message: %s", message)
        raise ConfigEntryNotReady("Alarm.com websocket connection died.")

    if message.current_state not in [
        pyadc.WebSocketState.CONNECTED,
        pyadc.WebSocketState.CONNECTING,
    ]:
        log.info("Alarm.com websocket state message: %s", message)
        return

    log.debug("Alarm.com websocket state: %s", message.current_state)


async def _update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle ConfigEntry options update."""
    await hass.config_entries.async_reload(entry.entry_id)
