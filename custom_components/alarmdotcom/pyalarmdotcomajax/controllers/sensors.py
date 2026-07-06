"""Alarm.com controller for sensors."""

import logging
from typing import TYPE_CHECKING

from pyalarmdotcomajax.const import ATTR_DESIRED_STATE, ATTR_STATE
from pyalarmdotcomajax.controllers.base import BaseController, device_controller
from pyalarmdotcomajax.models.base import ResourceType
from pyalarmdotcomajax.models.sensor import Sensor, SensorState, SensorSubtype
from pyalarmdotcomajax.websocket.client import SupportedResourceEvents
from pyalarmdotcomajax.websocket.messages import (
    BaseWSMessage,
    EventWSMessage,
    ResourceEventType,
)

if TYPE_CHECKING:
    from pyalarmdotcomajax.models import AdcResourceT

log = logging.getLogger(__name__)


MOTION_EVENT_STATE_MAP = {
    ResourceEventType.Closed: SensorState.IDLE,
    ResourceEventType.DoorLeftOpenRestoral: SensorState.IDLE,
    ResourceEventType.OpenedClosed: SensorState.OPENED_CLOSED,
    ResourceEventType.Opened: SensorState.ACTIVE,
}
SENSOR_EVENT_STATE_MAP = {
    ResourceEventType.Closed: SensorState.CLOSED,
    ResourceEventType.DoorLeftOpenRestoral: SensorState.CLOSED,
    ResourceEventType.OpenedClosed: SensorState.OPENED_CLOSED,
    ResourceEventType.Opened: SensorState.OPEN,
}


SUPPORTED_RESOURCE_EVENTS = SupportedResourceEvents(
    events=[
        ResourceEventType.Bypassed,
        ResourceEventType.EndOfBypass,
        ResourceEventType.Closed,
        ResourceEventType.OpenedClosed,
        ResourceEventType.Opened,
        ResourceEventType.DoorLeftOpenRestoral,
    ]
)


@device_controller(ResourceType.SENSOR, Sensor)
class SensorController(BaseController[Sensor]):
    """Controller for sensors."""

    _supported_resource_events = SUPPORTED_RESOURCE_EVENTS

    async def _handle_event(
        self, adc_resource: "AdcResourceT", message: BaseWSMessage
    ) -> "AdcResourceT":
        """Handle light-specific WebSocket events."""

        # Be careful here. message.value may be 0, so we need to explicitly check for None instead of relying on truthiness.
        if (
            isinstance(message, EventWSMessage)
            and message.value is not None
            and isinstance(adc_resource, Sensor)
        ):
            #
            # STATE UPDATES
            #

            state: SensorState | None = None

            match message.subtype:
                case ResourceEventType.Closed:
                    state = (
                        SensorState.IDLE
                        if adc_resource.subtype == SensorSubtype.MOTION_SENSOR
                        else SensorState.CLOSED
                    )
                case ResourceEventType.Opened:
                    state = (
                        SensorState.ACTIVE
                        if adc_resource.subtype == SensorSubtype.MOTION_SENSOR
                        else SensorState.OPEN
                    )
                case ResourceEventType.OpenedClosed:
                    state = SensorState.OPENED_CLOSED
                case ResourceEventType.DoorLeftOpenRestoral:
                    state = SensorState.CLOSED

            if state:
                adc_resource.api_resource.attributes.update(
                    {
                        ATTR_STATE: state.value,
                        ATTR_DESIRED_STATE: state.value,
                    }
                )

            #
            # BYPASS UPDATES
            #

            if message.subtype in [
                ResourceEventType.Bypassed,
                ResourceEventType.EndOfBypass,
            ]:
                adc_resource.api_resource.attributes.update(
                    {
                        "isBypassed": message.subtype == ResourceEventType.Bypassed,
                    }
                )

        return adc_resource
