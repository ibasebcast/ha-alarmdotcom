"""The alarmdotcom integration."""

import logging

import aiohttp
import pyalarmdotcomajax as pyadc
import voluptuous as vol
from homeassistant.helpers import config_validation as cv
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, ServiceCall
from homeassistant.exceptions import ConfigEntryAuthFailed, ConfigEntryNotReady

from homeassistant.const import CONF_PASSWORD, CONF_USERNAME

from .const import (
    CONF_ARM_AWAY,
    CONF_ARM_HOME,
    CONF_ARM_NIGHT,
    CONF_FORCE_BYPASS,
    CONF_MFA_TOKEN,
    CONF_NO_ENTRY_DELAY,
    CONF_SILENT_ARM,
    ATTR_PARTITION_ID,
    ATTR_RESOURCE_ID,
    DATA_HUB,
    DEBUG_REQ_EVENT,
    DOMAIN,
    PLATFORMS,
    SERVICE_BYPASS_SENSOR,
    SERVICE_UNBYPASS_SENSOR,
    STARTUP_MESSAGE,
)
from .hub import AlarmHub
from .camera_api import AlarmCameraSession

LOGGER = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Set up alarmdotcom hub from a config entry."""

    LOGGER.info("%s: Initializing Alarmdotcom from config entry.", __name__)
    LOGGER.info(STARTUP_MESSAGE)

    hub = AlarmHub(hass, config_entry)

    try:
        await hub.initialize()
    except pyadc.AuthenticationException as ex:
        raise ConfigEntryAuthFailed from ex
    except (TimeoutError, pyadc.AlarmdotcomException, aiohttp.ClientError) as ex:
        raise ConfigEntryNotReady from ex

    if DOMAIN not in hass.data:
        hass.data[DOMAIN] = {}
    if config_entry.entry_id not in hass.data[DOMAIN]:
        hass.data[DOMAIN][config_entry.entry_id] = {}

    hass.data[DOMAIN][config_entry.entry_id][DATA_HUB] = hub

    # Initialize WebRTC camera session, best effort.
    # Prefer reusing the already-authenticated pyalarmdotcomajax session to
    # avoid a second login. Falls back to an independent login automatically.
    try:
        camera_session = AlarmCameraSession.from_alarm_bridge(
            bridge=hub.api,
            username=config_entry.data[CONF_USERNAME],
            password=config_entry.data[CONF_PASSWORD],
            mfa_cookie=config_entry.data.get(CONF_MFA_TOKEN),
        )

        # Only log in when we had to create our own independent session and
        # still do not have an ajax key.
        if camera_session._owns_session and not camera_session.ajax_key:
            LOGGER.debug("Camera session: performing independent login.")
            await camera_session.login()
        else:
            LOGGER.debug(
                "Camera session: reusing pyalarmdotcomajax session, no second login needed."
            )

        hass.data[DOMAIN][config_entry.entry_id]["camera_session"] = camera_session
    except Exception as err:
        LOGGER.warning(
            "Alarm.com camera session could not be initialized: %s. "
            "Camera entities will be unavailable.",
            err,
        )
        hass.data[DOMAIN][config_entry.entry_id]["camera_session"] = None

    await hass.config_entries.async_forward_entry_setups(config_entry, PLATFORMS)

    async def handle_alarmdotcom_debug_request_event(event: Event) -> None:
        """Dump debug data when requested via Home Assistant event."""

        event_resource = hub.api.resources.get(str(event.data.get("resource_id")))

        if event_resource is None:
            LOGGER.warning(
                "ALARM.COM DEBUG DATA FOR %s: No such device.",
                str(event.data.get("resource_id")).upper(),
            )
            return

        LOGGER.warning(
            "ALARM.COM DEBUG DATA FOR %s: %s",
            str(event_resource.attributes.description).upper(),
            event_resource.api_resource.to_json(),
        )

    hass.bus.async_listen(DEBUG_REQ_EVENT, handle_alarmdotcom_debug_request_event)

    async def handle_bypass_service(call: ServiceCall) -> None:
        """Handle a bypass or unbypass service request."""

        resource_id = str(call.data[ATTR_RESOURCE_ID])
        partition_id = call.data.get(ATTR_PARTITION_ID)
        bypass = call.service == SERVICE_BYPASS_SENSOR

        sensor = hub.api.sensors.get(resource_id)
        if sensor is None:
            LOGGER.warning("Alarm.com bypass request failed, no such sensor: %s", resource_id)
            return

        if not (sensor.attributes.supports_bypass or sensor.attributes.supports_immediate_bypass):
            LOGGER.warning("Alarm.com sensor does not support bypass: %s", resource_id)
            return

        resolved_partition_id = str(partition_id) if partition_id else None
        if resolved_partition_id is None:
            matching_partition = next(
                (
                    partition
                    for partition in hub.api.partitions.values()
                    if partition.system_id == sensor.system_id
                ),
                None,
            )
            if matching_partition is None:
                LOGGER.warning(
                    "Alarm.com bypass request failed, no partition found for sensor: %s",
                    resource_id,
                )
                return
            resolved_partition_id = matching_partition.id

        await hub.api.partitions.change_sensor_bypass(
            resolved_partition_id,
            bypass_ids=[resource_id] if bypass else None,
            unbypass_ids=[resource_id] if not bypass else None,
        )

    service_schema = vol.Schema(
        {
            vol.Required(ATTR_RESOURCE_ID): cv.string,
            vol.Optional(ATTR_PARTITION_ID): cv.string,
        }
    )

    if not hass.services.has_service(DOMAIN, SERVICE_BYPASS_SENSOR):
        hass.services.async_register(
            DOMAIN,
            SERVICE_BYPASS_SENSOR,
            handle_bypass_service,
            schema=service_schema,
        )

    if not hass.services.has_service(DOMAIN, SERVICE_UNBYPASS_SENSOR):
        hass.services.async_register(
            DOMAIN,
            SERVICE_UNBYPASS_SENSOR,
            handle_bypass_service,
            schema=service_schema,
        )

    LOGGER.info("%s: Finished initializing Alarmdotcom from config entry.", __name__)
    return True


async def async_migrate_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Migrate old entry."""

    if config_entry.version == 1:
        LOGGER.debug("Migrating from version %s", config_entry.version)

        v2_options = {**config_entry.options}
        v2_options["use_arm_code"] = bool(config_entry.options.get("arm_code"))
        v2_options["arm_code"] = (
            str(arm_code) if (arm_code := config_entry.options.get("arm_code")) else ""
        )

        hass.config_entries.async_update_entry(
            config_entry, data={**config_entry.data}, options=v2_options, version=2
        )
        LOGGER.info("Migration to version %s successful", 2)

    if config_entry.version == 2:
        LOGGER.debug("Migrating from version %s", config_entry.version)

        v3_options = {**config_entry.options}

        if not v3_options.get("use_arm_code"):
            v3_options["arm_code"] = None

        new_arm_home: list[str] = []
        if v3_options.get("force_bypass") in ["Stay Only", "Always"]:
            new_arm_home.append("bypass")
        if v3_options.get("silent_arming") in ["Stay Only", "Always"]:
            new_arm_home.append("silent")
        if v3_options.get("no_entry_delay") not in ["Stay Only", "Always"]:
            new_arm_home.append("delay")
        v3_options[CONF_ARM_HOME] = new_arm_home

        new_arm_away: list[str] = []
        if v3_options.get("force_bypass") in ["Away Only", "Always"]:
            new_arm_away.append("bypass")
        if v3_options.get("silent_arming") in ["Away Only", "Always"]:
            new_arm_away.append("silent")
        if v3_options.get("no_entry_delay") not in ["Away Only", "Always"]:
            new_arm_away.append("delay")
        v3_options[CONF_ARM_AWAY] = new_arm_away

        new_arm_night: list[str] = []
        if v3_options.get("force_bypass") == "Always":
            new_arm_night.append("bypass")
        if v3_options.get("silent_arming") == "Always":
            new_arm_night.append("silent")
        if v3_options.get("no_entry_delay") != "Always":
            new_arm_night.append("delay")
        v3_options[CONF_ARM_NIGHT] = new_arm_night

        if v3_options.get("use_arm_code"):
            v3_options["use_arm_code"] = None
        if v3_options.get("force_bypass"):
            v3_options["force_bypass"] = None
        if v3_options.get("silent_arming"):
            v3_options["silent_arming"] = None
        if v3_options.get("no_entry_delay"):
            v3_options["no_entry_delay"] = None

        hass.config_entries.async_update_entry(
            config_entry, data={**config_entry.data}, options=v3_options, version=3
        )
        LOGGER.info("Migration to version %s successful", 3)

    if config_entry.version == 3:
        LOGGER.debug("Migrating from version %s", config_entry.version)

        v4_options: dict = {**config_entry.options}

        v4_options.pop("use_arm_code", None)
        v4_options.pop("force_bypass", None)
        v4_options.pop("silent_arming", None)
        v4_options.pop("no_entry_delay", None)

        for arm_mode in (CONF_ARM_HOME, CONF_ARM_AWAY, CONF_ARM_NIGHT):
            if arm_mode in v4_options:
                if "bypass" in v4_options[arm_mode]:
                    v4_options[arm_mode].remove("bypass")
                    v4_options[arm_mode].append(CONF_FORCE_BYPASS)
                if "silent" in v4_options[arm_mode]:
                    v4_options[arm_mode].remove("silent")
                    v4_options[arm_mode].append(CONF_SILENT_ARM)
                if "delay" in v4_options[arm_mode]:
                    v4_options[arm_mode].remove("delay")
                    v4_options[arm_mode].append(CONF_NO_ENTRY_DELAY)

        hass.config_entries.async_update_entry(
            config_entry, data={**config_entry.data}, options=v4_options, version=4
        )
        LOGGER.info("Migration to version %s successful", 4)

    if config_entry.version == 4:
        LOGGER.debug("Migrating from version %s", config_entry.version)

        v5_options: dict = {**config_entry.options}
        v5_options.pop("update_interval", None)
        v5_options.pop("ws_reconnect_timeout", None)

        hass.config_entries.async_update_entry(
            config_entry, data={**config_entry.data}, options=v5_options, version=5
        )
        LOGGER.info("Migration to version %s successful", 5)

    return True


async def async_unload_entry(hass: HomeAssistant, config_entry: ConfigEntry) -> bool:
    """Unload a config entry."""

    entry_data = hass.data[DOMAIN].pop(config_entry.entry_id)
    hub: AlarmHub = entry_data[DATA_HUB]
    camera_session: AlarmCameraSession | None = entry_data.get("camera_session")

    if camera_session is not None:
        await camera_session.close()

    unload_success = await hub.close()

    if len(hass.data[DOMAIN]) == 0:
        hass.data.pop(DOMAIN)
        if hass.services.has_service(DOMAIN, SERVICE_BYPASS_SENSOR):
            hass.services.async_remove(DOMAIN, SERVICE_BYPASS_SENSOR)
        if hass.services.has_service(DOMAIN, SERVICE_UNBYPASS_SENSOR):
            hass.services.async_remove(DOMAIN, SERVICE_UNBYPASS_SENSOR)

    return unload_success