"""Alarm.com controller for sensors."""

import logging
from types import MappingProxyType
from typing import TYPE_CHECKING

from _pyalarmdotcomajax.const import ATTR_DESIRED_STATE, ATTR_STATE
from _pyalarmdotcomajax.controllers.base import BaseController, device_controller
from _pyalarmdotcomajax.models.base import ResourceType
from _pyalarmdotcomajax.models.sensor import Sensor, SensorState, SensorSubtype
from _pyalarmdotcomajax.websocket.client import SupportedResourceEvents
from _pyalarmdotcomajax.websocket.messages import (
    BaseWSMessage,
    EventWSMessage,
    ResourceEventType,
)

if TYPE_CHECKING:
    from _pyalarmdotcomajax.models import AdcResourceT

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


# Derived from the state map, as in every other device controller, so the
# subscription list and the state map can no longer drift apart.
SUPPORTED_RESOURCE_EVENTS = SupportedResourceEvents(
    events=[
        ResourceEventType.Bypassed,
        ResourceEventType.EndOfBypass,
        *SENSOR_EVENT_STATE_MAP.keys(),
    ]
)


@device_controller(ResourceType.SENSOR, Sensor)
class SensorController(BaseController[Sensor]):
    """Controller for sensors."""

    # Contact-sensor mapping is the class-level default, so state updates go
    # through the same unguarded path every other device controller uses
    # (BaseController._base_handle_event). Motion sensors need IDLE/ACTIVE
    # rather than CLOSED/OPEN, which a ClassVar cannot express per device, so
    # _handle_event below corrects them.
    _event_state_map = MappingProxyType(SENSOR_EVENT_STATE_MAP)
    _supported_resource_events = SUPPORTED_RESOURCE_EVENTS

    async def _handle_event(
        self, adc_resource: "AdcResourceT", message: BaseWSMessage
    ) -> "AdcResourceT":
        """Handle light-specific WebSocket events."""

        # Contact-sensor state is carried entirely by `subtype` (Opened /
        # Closed / OpenedClosed). `event_value` means nothing for these events
        # and is not read anywhere below, but gating on it dropped every state
        # update whenever Alarm.com sent the event without one.
        if isinstance(message, EventWSMessage) and isinstance(adc_resource, Sensor):
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
