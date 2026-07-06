"""Alarm.com controller for water sensors."""

from pyalarmdotcomajax.controllers.base import BaseController, device_controller
from pyalarmdotcomajax.models.base import ResourceType
from pyalarmdotcomajax.models.water_sensor import WaterSensor
from pyalarmdotcomajax.websocket.client import SupportedResourceEvents
from pyalarmdotcomajax.websocket.messages import ResourceEventType


@device_controller(ResourceType.WATER_SENSOR, WaterSensor)
class WaterSensorController(BaseController[WaterSensor]):
    """Controller for water sensors."""

    _supported_resource_events = SupportedResourceEvents(
        events=[ResourceEventType.Opened, ResourceEventType.Closed]
    )
