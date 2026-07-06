"""Alarm.com controller for thermostats."""

# ruff: noqa: UP007

import logging
from typing import TYPE_CHECKING, Annotated, Any, Optional

import typer


from pyalarmdotcomajax.adc.util import ValueEnum, cli_action
from pyalarmdotcomajax.const import ATTR_DESIRED_STATE, ATTR_STATE
from pyalarmdotcomajax.controllers.base import BaseController, device_controller
from pyalarmdotcomajax.models.base import ResourceType
from pyalarmdotcomajax.models.thermostat import (
    Thermostat,
    ThermostatFanMode,
    ThermostatScheduleMode,
    ThermostatState,
)
from pyalarmdotcomajax.websocket.client import SupportedResourceEvents
from pyalarmdotcomajax.websocket.messages import (
    BaseWSMessage,
    EventWSMessage,
    PropertyChangeWSMessage,
    ResourceEventType,
    ResourcePropertyChangeType,
)

if TYPE_CHECKING:
    from pyalarmdotcomajax import AlarmBridge
    from pyalarmdotcomajax.models import AdcResourceT

log = logging.getLogger(__name__)

ATTR_FAN_MODE = "fanMode"
ATTR_SETPOINT_OFFSET = "setpointOffset"
ATTR_COOL_SETPOINT = "coolSetpoint"
ATTR_DESIRED_COOL_SETPOINT = "desiredCoolSetpoint"
ATTR_HEAT_SETPOINT = "heatSetpoint"
ATTR_DESIRED_HEAT_SETPOINT = "desiredHeatSetpoint"
ATTR_DESIRED_SCHEDULE_MODE = "desiredScheduleMode"


@device_controller(ResourceType.THERMOSTAT, Thermostat)
class ThermostatController(BaseController[Thermostat]):
    """Controller for thermostats."""

    _supported_resource_events = SupportedResourceEvents(
        events=[
            ResourceEventType.ThermostatModeChanged,
            ResourceEventType.ThermostatFanModeChanged,
            ResourceEventType.ThermostatSetPointChanged,
            ResourceEventType.ThermostatOffset,
        ],
        property_changes=[
            ResourcePropertyChangeType.AmbientTemperature,
            ResourcePropertyChangeType.HeatSetPoint,
            ResourcePropertyChangeType.CoolSetPoint,
        ],
    )

    def __init__(
        self,
        bridge: "AlarmBridge",
        data_provider: BaseController | None = None,
        target_device_ids: list[str] | None = None,
    ) -> None:
        """Initialize controller."""

        super().__init__(bridge, data_provider, target_device_ids)

    async def _inject_attributes(self, resource: Thermostat) -> Thermostat:
        """Inject uses_celsius from the Identity model into Thermostats."""

        resource.attributes.uses_celsius = self._bridge.auth_controller.use_celsius

        return resource

    @cli_action()
    async def set_state(
        self,
        id: Annotated[str, typer.Option(help="The ID of the thermostat.", show_default=False)],
        state: Annotated[
            Optional[ThermostatState],
            typer.Option(
                click_type=ValueEnum(ThermostatState, "UNKNOWN"),
                case_sensitive=False,
                show_default=False,
                help="The desired state of the thermostat.",
            ),
        ] = None,
        fan_mode: Annotated[
            Optional[ThermostatFanMode],
            typer.Option(
                click_type=ValueEnum(ThermostatFanMode, ["UNKNOWN"]),
                case_sensitive=False,
                show_default=False,
                help="The desired fan mode.",
            ),
        ] = None,
        fan_mode_duration: Annotated[
            Optional[int],
            typer.Option(
                help="The duration for which the desired fan mode should run. Fan duration must be in device's list of supported durations.",
                show_default=False,
            ),
        ] = None,
        cool_setpoint: Annotated[
            Optional[float],
            typer.Option(help="The desired cool setpoint.", show_default=False),
        ] = None,
        heat_setpoint: Annotated[
            Optional[float],
            typer.Option(help="The desired heat setpoint.", show_default=False),
        ] = None,
        schedule_mode: Annotated[
            Optional[ThermostatScheduleMode],
            typer.Option(
                click_type=ValueEnum(ThermostatScheduleMode),
                case_sensitive=False,
                show_default=False,
                help="The desired schedule mode.",
            ),
        ] = None,
    ) -> None:
        """
        Set thermostat attributes.

        Only one attribute can be set at a time, with the exception of --fan-mode and --fan-mode-duration, which must be set together.
        """
        # Make sure that multiple attributes are not being set at the same time.
        if (fan_mode is None) != (fan_mode_duration is None):
            raise ValueError("fan_mode and fan_mode_duration must be used together.")

        set_count = sum(
            value is not None
            for value in (
                state,
                fan_mode,
                cool_setpoint,
                heat_setpoint,
                schedule_mode,
            )
        )
        if set_count == 0:
            raise ValueError("At least one attribute must be provided.")
        if set_count > 1 and not ({cool_setpoint, heat_setpoint} != {None} and state is None and fan_mode is None and schedule_mode is None):
            raise ValueError("Only one attribute can be set at a time, except heat and cool setpoints may be updated together.")

        msg_body: dict[str, Any] = {}

        if state:
            msg_body[ATTR_DESIRED_STATE] = state.value
        elif fan_mode is not None and fan_mode_duration is not None:
            if fan_mode_duration not in self._resources[id].supported_fan_durations:
                raise ValueError("Requested fan duration is not supported by the device.")
            msg_body["desiredFanMode"] = fan_mode.value
            msg_body["desiredFanDuration"] = 0 if fan_mode == ThermostatFanMode.AUTO else fan_mode_duration
        elif cool_setpoint is not None:
            msg_body[ATTR_DESIRED_COOL_SETPOINT] = cool_setpoint
        elif heat_setpoint is not None:
            msg_body[ATTR_DESIRED_HEAT_SETPOINT] = heat_setpoint
        elif schedule_mode is not None:
            msg_body[ATTR_DESIRED_SCHEDULE_MODE] = schedule_mode.value

        await self._send_command(id, "setState", msg_body)

    async def _handle_event(self, adc_resource: "AdcResourceT", message: BaseWSMessage) -> "AdcResourceT":
        """Handle light-specific WebSocket events."""

        updated_data: dict[str, Any] = {}

        # Be careful here. message.value may be 0, so we need to explicitly check for None instead of relying on truthiness.
        if isinstance(message, EventWSMessage) and message.value is not None:
            if message.subtype == ResourceEventType.ThermostatModeChanged:
                updated_data[ATTR_STATE] = int(message.value) + 1
                updated_data[ATTR_DESIRED_STATE] = int(message.value) + 1

            elif message.subtype == ResourceEventType.ThermostatFanModeChanged:
                updated_data[ATTR_FAN_MODE] = int(message.value)

            elif message.subtype == ResourceEventType.ThermostatOffset:
                updated_data[ATTR_SETPOINT_OFFSET] = message.value

        if isinstance(message, PropertyChangeWSMessage) and message.value is not None:
            adjusted_value = message.value / 100

            if self._bridge.auth_controller.use_celsius:
                adjusted_value = round(((adjusted_value - 32) * 5 / 9), 1)

            if message.subtype == ResourcePropertyChangeType.CoolSetPoint:
                updated_data[ATTR_COOL_SETPOINT] = adjusted_value
                updated_data[ATTR_DESIRED_COOL_SETPOINT] = adjusted_value

            elif message.subtype == ResourcePropertyChangeType.HeatSetPoint:
                updated_data[ATTR_HEAT_SETPOINT] = adjusted_value
                updated_data[ATTR_DESIRED_HEAT_SETPOINT] = adjusted_value

        adc_resource.api_resource.attributes.update(updated_data)

        return adc_resource
