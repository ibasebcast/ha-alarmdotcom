"""Interfaces with Alarm.com sensors."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Generic

import pyalarmdotcomajax as pyadc
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory, PERCENTAGE
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import DiscoveryInfoType

from .const import DATA_HUB, DOMAIN
from .entity import (
    AdcControllerT,
    AdcEntity,
    AdcEntityDescription,
    AdcManagedDeviceT,
)
from .util import cleanup_orphaned_entities_and_devices

if TYPE_CHECKING:
    from .hub import AlarmHub

log = logging.getLogger(__name__)

BATTERY_CLASSIFICATION_LABELS: dict[pyadc.base.BatteryLevel, str] = {
    pyadc.base.BatteryLevel.CRITICAL: "Critical",
    pyadc.base.BatteryLevel.LOW: "Low",
    pyadc.base.BatteryLevel.MEDIUM: "Medium",
    pyadc.base.BatteryLevel.HIGH: "High",
    pyadc.base.BatteryLevel.NONE: "None",
}

BATTERY_CLASSIFICATION_OPTIONS = list(BATTERY_CLASSIFICATION_LABELS.values())


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
    discovery_info: DiscoveryInfoType | None = None,
) -> None:
    """Set up the sensor platform."""

    hub: AlarmHub = hass.data[DOMAIN][config_entry.entry_id][DATA_HUB]

    entities: list[AdcSensorEntity] = []
    for entity_description in ENTITY_DESCRIPTIONS:
        entities.extend(
            AdcSensorEntity(hub=hub, resource_id=device.id, description=entity_description)
            for device in hub.api.managed_devices.values()
            if entity_description.supported_fn(hub, device.id)
        )

    async_add_entities(entities)

    current_entity_ids = {entity.entity_id for entity in entities}
    current_unique_ids = {uid for uid in (entity.unique_id for entity in entities) if uid is not None}
    await cleanup_orphaned_entities_and_devices(hass, config_entry, current_entity_ids, current_unique_ids, "sensor")


@callback
def battery_percentage_supported_fn(hub: AlarmHub, resource_id: str) -> bool:
    """Check if the battery percentage sensor is supported."""

    resource = hub.api.managed_devices.get(resource_id)
    if resource is None:
        return False

    return getattr(resource.attributes, "battery_level_pct", None) is not None


@callback
def battery_percentage_native_value_fn(hub: AlarmHub, resource_id: str) -> int | None:
    """Return the native battery percentage value."""

    resource = hub.api.managed_devices.get(resource_id)
    if resource is None:
        return None

    return getattr(resource.attributes, "battery_level_pct", None)


@callback
def battery_classification_supported_fn(hub: AlarmHub, resource_id: str) -> bool:
    """Check if the battery classification sensor is supported."""

    resource = hub.api.managed_devices.get(resource_id)
    if resource is None:
        return False

    classification = getattr(resource.attributes, "battery_level_classification", None)
    return classification is not None


@callback
def battery_classification_native_value_fn(hub: AlarmHub, resource_id: str) -> str | None:
    """Return the battery classification label."""

    resource = hub.api.managed_devices.get(resource_id)
    if resource is None:
        return None

    classification = getattr(resource.attributes, "battery_level_classification", None)
    if classification is None:
        return None

    return BATTERY_CLASSIFICATION_LABELS.get(classification, str(classification).title())


@dataclass(frozen=True, kw_only=True)
class AdcSensorEntityDescription(
    Generic[AdcManagedDeviceT, AdcControllerT],
    AdcEntityDescription[AdcManagedDeviceT, AdcControllerT],
    SensorEntityDescription,
):
    """Base Alarm.com sensor entity description."""

    native_value_fn: Callable[[AlarmHub, str], str | int | None]
    """Return the sensor native value."""


ENTITY_DESCRIPTIONS: list[AdcSensorEntityDescription] = [
    AdcSensorEntityDescription[pyadc.base.AdcDeviceResource, pyadc.BaseController](
        key="battery_level_pct",
        controller_fn=lambda hub, resource_id: hub.api.get_controller(resource_id),
        name="Battery",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        supported_fn=battery_percentage_supported_fn,
        native_value_fn=battery_percentage_native_value_fn,
    ),
    AdcSensorEntityDescription[pyadc.base.AdcDeviceResource, pyadc.BaseController](
        key="battery_level_classification",
        controller_fn=lambda hub, resource_id: hub.api.get_controller(resource_id),
        name="Battery Status",
        entity_category=EntityCategory.DIAGNOSTIC,
        device_class=SensorDeviceClass.ENUM,
        options=BATTERY_CLASSIFICATION_OPTIONS,
        supported_fn=battery_classification_supported_fn,
        native_value_fn=battery_classification_native_value_fn,
    ),
]


class AdcSensorEntity(AdcEntity[AdcManagedDeviceT, AdcControllerT], SensorEntity):
    """Base Alarm.com sensor entity."""

    entity_description: AdcSensorEntityDescription

    @callback
    def initiate_state(self) -> None:
        """Initiate entity state."""

        self._attr_native_value = self.entity_description.native_value_fn(self.hub, self.resource_id)

        super().initiate_state()

    @callback
    def update_state(self, message: pyadc.EventBrokerMessage | None = None) -> None:
        """Update entity state."""

        if isinstance(message, pyadc.ResourceEventMessage):
            self._attr_native_value = self.entity_description.native_value_fn(self.hub, self.resource_id)
