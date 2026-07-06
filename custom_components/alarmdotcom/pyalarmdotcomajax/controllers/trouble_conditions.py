"""Alarm.com controller for trouble conditions."""

from pyalarmdotcomajax.controllers.base import BaseController
from pyalarmdotcomajax.models.base import ResourceType
from pyalarmdotcomajax.models.trouble_condition import TroubleCondition

from .base import device_controller


@device_controller(ResourceType.TROUBLE_CONDITION, TroubleCondition)
class TroubleConditionController(BaseController[TroubleCondition]):
    """Controller for trouble conditions."""
