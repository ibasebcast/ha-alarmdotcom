"""Alarm.com controller for trouble conditions."""

from _pyalarmdotcomajax.controllers.base import BaseController
from _pyalarmdotcomajax.models.base import ResourceType
from _pyalarmdotcomajax.models.trouble_condition import TroubleCondition

from .base import device_controller


@device_controller(ResourceType.TROUBLE_CONDITION, TroubleCondition)
class TroubleConditionController(BaseController[TroubleCondition]):
    """Controller for trouble conditions."""
