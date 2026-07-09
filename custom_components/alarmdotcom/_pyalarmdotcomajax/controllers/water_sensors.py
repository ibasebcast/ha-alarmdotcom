"""Alarm.com controller for water sensors."""

from _pyalarmdotcomajax.controllers.base import BaseController, device_controller
from _pyalarmdotcomajax.models.base import ResourceType
from _pyalarmdotcomajax.models.water_sensor import WaterSensor
from _pyalarmdotcomajax.websocket.client import SupportedResourceEvents
from _pyalarmdotcomajax.websocket.messages import ResourceEventType


@device_controller(ResourceType.WATER_SENSOR, WaterSensor)
class WaterSensorController(BaseController[WaterSensor]):
    """Controller for water sensors."""

    _supported_resource_events = SupportedResourceEvents(
        events=[ResourceEventType.Opened, ResourceEventType.Closed]
    )
