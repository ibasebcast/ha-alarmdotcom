"""Alarm.com model for WaterValves."""

from dataclasses import dataclass
from enum import Enum

from pyalarmdotcomajax.models.base import (
    AdcDeviceResource,
    BaseManagedDeviceAttributes,
    ResourceType,
)


class WaterValveState(Enum):
    """Enum of water valve states."""

    UNKNOWN = 0
    OPEN = 1
    CLOSED = 2


WaterValveAttributes = BaseManagedDeviceAttributes[WaterValveState]


@dataclass
class WaterValve(AdcDeviceResource[WaterValveAttributes]):
    """WaterValve resource."""

    resource_type = ResourceType.WATER_VALVE
    attributes_type = WaterValveAttributes
