"""Alarm.com controller for gates."""

import logging
from enum import StrEnum
from types import MappingProxyType

from pyalarmdotcomajax.adc.util import Param_Id, cli_action
from pyalarmdotcomajax.controllers.base import BaseController, device_controller
from pyalarmdotcomajax.exceptions import UnsupportedOperation
from pyalarmdotcomajax.models.base import ResourceType
from pyalarmdotcomajax.models.gate import Gate, GateState
from pyalarmdotcomajax.websocket.client import SupportedResourceEvents
from pyalarmdotcomajax.websocket.messages import ResourceEventType

log = logging.getLogger(__name__)


class GateCommand(StrEnum):
    """Commands for ADC gates."""

    OPEN = "open"
    CLOSE = "close"


STATE_COMMAND_MAP = {
    GateState.OPEN: GateCommand.OPEN,
    GateState.CLOSED: GateCommand.CLOSE,
}


@device_controller(ResourceType.GATE, Gate)
class GateController(BaseController[Gate]):
    """Controller for gates."""

    _event_state_map = MappingProxyType(
        {
            ResourceEventType.Opened: GateState.OPEN,
            ResourceEventType.Closed: GateState.CLOSED,
        }
    )
    _supported_resource_events = SupportedResourceEvents(
        events=[*_event_state_map.keys()]
    )

    @cli_action()
    async def open(self, id: Param_Id) -> None:
        """Open a gate."""
        await self.set_state(id, state=GateState.OPEN)

    @cli_action()
    async def close(self, id: Param_Id) -> None:
        """Close a gate."""
        await self.set_state(id, state=GateState.CLOSED)

    async def set_state(self, id: str, state: GateState) -> None:
        """Change gate state."""
        if not (command := STATE_COMMAND_MAP.get(state)):
            raise UnsupportedOperation(f"State {state} not implemented.")
        await self._send_command(id, command)
