"""Controller interfaces with the Alarm.com API via pyalarmdotcomajax."""

import asyncio
import contextlib
import logging
from datetime import timedelta

import pyalarmdotcomajax as pyadc
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import CALLBACK_TYPE, HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.event import async_track_time_interval
from pyalarmdotcomajax import AlarmBridge

from .const import (
    CONF_MFA_TOKEN,
    DATA_HUB,
    DOMAIN,
    PLATFORMS,
)

log = logging.getLogger(__name__)

# How often to do a full state poll as a safety net against missed websocket events
POLLING_INTERVAL = timedelta(minutes=5)

# Reconnect backoff: wait this long before reloading after a websocket death
WS_RECONNECT_DELAY = 30  # seconds
WS_MAX_RECONNECT_ATTEMPTS = 5

WS_HEARTBEAT_INTERVAL = 60  # seconds


class _AlarmBridgeWithHeartbeat(AlarmBridge):
    """AlarmBridge subclass that injects a WebSocket heartbeat.

    aiohttp will send a PING frame every WS_HEARTBEAT_INTERVAL seconds and
    close the connection if no PONG is received, triggering reconnection.
    This catches silent drops that the library's HTTP-based keep-alive misses.
    """

    @contextlib.asynccontextmanager
    async def ws_connect(self, url, **kwargs):
        if self._websession is None:
            raise pyadc.NotInitialized(
                "Cannot initiate WebSocket connection without an existing session."
            )
        kwargs.setdefault("heartbeat", WS_HEARTBEAT_INTERVAL)
        async with self._websession.ws_connect(url, **kwargs) as res:
            yield res


class AlarmHub:
    """Config-entry initiated Alarm Hub."""

    def __init__(self, hass: HomeAssistant, config_entry: ConfigEntry) -> None:
        """Initialize the system."""
        self.hass: HomeAssistant = hass
        self.config_entry: ConfigEntry = config_entry

        self.api = _AlarmBridgeWithHeartbeat(
            username=config_entry.data[CONF_USERNAME],
            password=config_entry.data[CONF_PASSWORD],
            mfa_token=config_entry.data.get(CONF_MFA_TOKEN),
        )

        self.close_jobs: list[CALLBACK_TYPE] = []
        self.available: bool = True
        self._reconnect_attempts: int = 0
        self._reconnect_task: asyncio.Task | None = None

        hass.data.setdefault(DOMAIN, {})[self.config_entry.entry_id] = {DATA_HUB: self}

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

    async def initialize(self) -> bool:
        """Initialize connection to Alarm.com."""
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

        await self.api.start_event_monitoring(self._ws_state_handler)

        # Periodic full state refresh as a safety net for missed websocket events
        self.close_jobs.append(
            async_track_time_interval(
                self.hass,
                self._async_refresh_state,
                POLLING_INTERVAL,
            )
        )

        self.close_jobs.append(self.config_entry.add_update_listener(_update_listener))

        device_registry = dr.async_get(self.hass)
        device_registry.async_get_or_create(
            config_entry_id=self.config_entry.entry_id,
            identifiers={(DOMAIN, str(self.api.active_system.id))},
            manufacturer="Alarm.com",
            name=self.api.active_system.name,
            entry_type=dr.DeviceEntryType.SERVICE,
            model="Security System",
        )

        self._reconnect_attempts = 0
        return True

    async def _async_refresh_state(self, _now=None) -> None:
        """Periodically poll full state as a safety net against missed websocket events."""
        try:
            log.debug("Alarm.com: performing periodic full state refresh.")
            await self.api.fetch_full_state()
        except pyadc.AuthenticationException:
            log.warning("Alarm.com: periodic refresh failed — auth error. Will attempt reconnect.")
            await self._async_handle_ws_death()
        except Exception as err:
            log.warning("Alarm.com: periodic refresh failed: %s", err)

    async def _ws_state_handler(self, message: pyadc.EventBrokerMessage) -> None:
        """Handle websocket state changes with automatic reconnect."""
        if not isinstance(message, pyadc.ConnectionEvent):
            return

        if message.current_state == pyadc.WebSocketState.DEAD:
            log.warning(
                "Alarm.com websocket died. Will attempt reconnect in %s seconds (attempt %d/%d).",
                WS_RECONNECT_DELAY,
                self._reconnect_attempts + 1,
                WS_MAX_RECONNECT_ATTEMPTS,
            )
            self.available = False
            await self._async_handle_ws_death()

        elif message.current_state == pyadc.WebSocketState.CONNECTED:
            if not self.available:
                log.info("Alarm.com websocket reconnected.")
            self.available = True
            self._reconnect_attempts = 0

        elif message.current_state not in (
            pyadc.WebSocketState.CONNECTED,
            pyadc.WebSocketState.CONNECTING,
        ):
            log.info("Alarm.com websocket state: %s", message.current_state)

        log.debug("Alarm.com websocket state: %s", message.current_state)

    async def _async_handle_ws_death(self) -> None:
        """Schedule a reconnect attempt with backoff. Reloads the entry if all attempts fail."""
        if self._reconnect_task and not self._reconnect_task.done():
            return  # Already a reconnect in progress

        self._reconnect_task = self.hass.async_create_task(
            self._async_reconnect_with_backoff()
        )

    async def _async_reconnect_with_backoff(self) -> None:
        """Attempt to reconnect with exponential backoff, then reload entry if exhausted."""
        while self._reconnect_attempts < WS_MAX_RECONNECT_ATTEMPTS:
            self._reconnect_attempts += 1
            delay = WS_RECONNECT_DELAY * self._reconnect_attempts
            log.info(
                "Alarm.com: reconnect attempt %d/%d in %d seconds...",
                self._reconnect_attempts,
                WS_MAX_RECONNECT_ATTEMPTS,
                delay,
            )
            await asyncio.sleep(delay)

            try:
                await self.api.close()
                async with asyncio.timeout(15):
                    await self.api.initialize()
                await self.api.start_event_monitoring(self._ws_state_handler)
                self.available = True
                self._reconnect_attempts = 0
                log.info("Alarm.com: reconnect successful.")
                return
            except pyadc.AuthenticationException:
                log.error("Alarm.com: reconnect failed — authentication error. Triggering reauth.")
                self.hass.async_create_task(
                    self.hass.config_entries.async_reload(self.config_entry.entry_id)
                )
                return
            except Exception as err:
                log.warning(
                    "Alarm.com: reconnect attempt %d failed: %s",
                    self._reconnect_attempts,
                    err,
                )

        # All attempts exhausted — schedule a full entry reload
        log.error(
            "Alarm.com: all %d reconnect attempts failed. Scheduling integration reload.",
            WS_MAX_RECONNECT_ATTEMPTS,
        )
        self.hass.async_create_task(
            self.hass.config_entries.async_schedule_reload(self.config_entry.entry_id)
        )

    async def close(self) -> bool:
        """Close the hub and unload platforms."""
        # Cancel any in-progress reconnect
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass

        while self.close_jobs:
            self.close_jobs.pop()()

        await self.api.close()

        unload_success: bool = await self.hass.config_entries.async_unload_platforms(
            self.config_entry,
            PLATFORMS,
        )

        return unload_success


async def _update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Handle ConfigEntry options update."""
    await hass.config_entries.async_reload(entry.entry_id)
