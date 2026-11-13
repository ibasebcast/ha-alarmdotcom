"""
Declined panel commands and the identity lookup budget (issue #157).

Alarm.com answers an arm request it will not carry out with a 422 error document. Before this, that 422 was
reported as a wrong two-factor code, the original library's retry without forceBypass never ran, and the reason
for the rejection was discarded. The identity lookup also had a per-attempt limit that a slow but working answer
could not meet.
"""

# Importing the component runs its sys.path shim, which must happen before the bare `_pyalarmdotcomajax`
# imports below resolve; see test_sensor_websocket_state.
import custom_components.alarmdotcom  # noqa: F401, I001

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import _pyalarmdotcomajax as adc
from _pyalarmdotcomajax import AlarmBridge, _LOGIN_IN_PROGRESS, _command_rejection_reason
from _pyalarmdotcomajax.controllers.partitions import PartitionController
from _pyalarmdotcomajax.exceptions import AuthenticationFailed, CommandRejected, ServiceUnavailable
from _pyalarmdotcomajax.models.partition import ExtendedArmingOptionItems, PartitionState

from custom_components.alarmdotcom.alarm_control_panel import _rejection_message

PARTITION_URL = "https://www.alarm.com/web/api/devices/partitions/123-1/armStay"
OTP_URL = "https://www.alarm.com/web/api/engines/twoFactorAuthentication/twoFactorAuthentications/9/verifyTwoFactorCode"
ZONE_NAME = "Back door - SECURITY-TEST"


def _error_body(title: str = "", detail: str = "") -> str:
    return json.dumps({"errors": [{"code": "422", "title": title, "detail": detail}]})


async def _request_with_body(bridge: AlarmBridge, url: str, body: str, status: int = 200) -> None:
    response = AsyncMock()
    response.text.return_value = body
    response.status = status

    @asynccontextmanager
    async def fake_request(*_args: Any, **_kwargs: Any) -> Any:
        yield response

    with patch.object(bridge, "create_request", side_effect=fake_request):
        await bridge.request("post", url, allow_login_repair=False, json={})


@pytest.mark.parametrize(
    ("title", "detail", "reason"),
    [
        ("Unable to arm", f"An open zone was reported: {ZONE_NAME}.", "open_zone"),
        ("Unable to arm", "Please acknowledge the system issues first.", "uncleared_issues"),
        ("Unprocessable", "", None),
        ("Sensor issue", "Clearance unavailable for this sensor.", None),
    ],
)
async def test_a_declined_device_command_keeps_only_a_safe_reason(
    caplog: pytest.LogCaptureFixture, title: str, detail: str, reason: str | None
) -> None:
    """A 422 on a device command is a rejection, not a wrong 2FA code, and never repeats Alarm.com's text."""
    bridge = AlarmBridge()

    with caplog.at_level(logging.DEBUG), pytest.raises(CommandRejected) as raised:
        await _request_with_body(bridge, PARTITION_URL, _error_body(title, detail))

    assert raised.value.reason == reason
    assert raised.value.error_codes == [422]
    emitted = str(raised.value) + "\n" + caplog.text
    assert ZONE_NAME not in emitted
    assert detail == "" or detail not in emitted


@pytest.mark.parametrize(
    ("status", "body"),
    [(422, "<html>rejected</html>"), (200, '{"errors":[{"status":"422","code":"vendor-rejection"}]}')],
)
async def test_device_command_422_without_numeric_error_code(status: int, body: str) -> None:
    """Handle a real HTTP 422 or a JSON:API status without a numeric vendor code."""
    with pytest.raises(CommandRejected) as raised:
        await _request_with_body(AlarmBridge(), PARTITION_URL, body, status=status)

    assert raised.value.error_codes == [422]


async def test_a_422_on_the_two_factor_code_is_still_a_wrong_code() -> None:
    """The OTP flow's 422 keeps its meaning."""
    bridge = AlarmBridge()

    with pytest.raises(AuthenticationFailed):
        await _request_with_body(bridge, OTP_URL, _error_body("Invalid code"))


def test_rejection_reason_prefers_uncleared_issues() -> None:
    """Text that mentions both a sensor and an issue to acknowledge points at the issue."""
    errors = [SimpleNamespace(title=None, detail="Acknowledge the trouble on the front door sensor.")]
    assert _command_rejection_reason(errors) == "uncleared_issues"


def _partition_controller(supported: list[ExtendedArmingOptionItems]) -> tuple[PartitionController, list]:
    sent: list[tuple[str, dict]] = []
    controller = object.__new__(PartitionController)
    options = SimpleNamespace(armed_stay=supported, armed_away=supported, armed_night=supported, disarmed=[])
    partition = SimpleNamespace(attributes=SimpleNamespace(extended_arming_options=options))
    controller.__dict__["_test_partition"] = partition
    return controller, sent


async def test_a_declined_forced_arm_is_retried_once_without_force_bypass() -> None:
    """The retry the original library intended, which its raise_for_status=True prevented."""
    controller, sent = _partition_controller([ExtendedArmingOptionItems.BYPASS_SENSORS])

    async def send(_id: str, command: str, body: dict) -> None:
        sent.append((command, dict(body)))
        if body.get("forceBypass"):
            raise CommandRejected([422], "open_zone")

    with (
        patch.object(PartitionController, "__getitem__", lambda self, _id: self.__dict__["_test_partition"]),
        patch.object(controller, "_send_command", side_effect=send, create=True),
    ):
        await controller.set_state("123-1", PartitionState.ARMED_STAY, [ExtendedArmingOptionItems.BYPASS_SENSORS])

    assert sent == [("armStay", {"forceBypass": True}), ("armStay", {})]


async def test_a_declined_arm_without_force_bypass_is_not_retried() -> None:
    """Only a forced arm is retried; anything else reaches the user once."""
    controller, _sent = _partition_controller([])
    send = AsyncMock(side_effect=CommandRejected([422], None))

    with (
        patch.object(PartitionController, "__getitem__", lambda self, _id: self.__dict__["_test_partition"]),
        patch.object(controller, "_send_command", send, create=True),
        pytest.raises(CommandRejected),
    ):
        await controller.set_state("123-1", PartitionState.ARMED_AWAY)

    assert send.await_count == 1


async def test_identity_lookup_shares_one_budget_across_attempts(monkeypatch: pytest.MonkeyPatch) -> None:
    """The first attempt is capped so a retry still fits, and both together stay within the overall budget."""
    monkeypatch.setattr(adc, "IDENTITY_LOOKUP_BUDGET_S", 0.3)
    monkeypatch.setattr(adc, "IDENTITY_FIRST_ATTEMPT_S", 0.1)
    monkeypatch.setattr(adc, "IDENTITY_MIN_RETRY_S", 0.01)
    bridge = AlarmBridge()

    async def hang(**_kwargs: Any) -> None:
        await asyncio.sleep(10)

    request = AsyncMock(side_effect=hang)
    monkeypatch.setattr(bridge, "request", request)
    token = _LOGIN_IN_PROGRESS.set(True)
    loop = asyncio.get_running_loop()
    started = loop.time()
    try:
        with pytest.raises(ServiceUnavailable):
            await bridge.get("identities/", None)
    finally:
        _LOGIN_IN_PROGRESS.reset(token)

    elapsed = loop.time() - started
    assert request.await_count == 2
    assert 0.25 <= elapsed < 0.5


async def test_identity_lookup_answer_within_the_budget_succeeds(monkeypatch: pytest.MonkeyPatch) -> None:
    """A slow first attempt that times out still leaves the retry room to succeed."""
    monkeypatch.setattr(adc, "IDENTITY_LOOKUP_BUDGET_S", 0.4)
    monkeypatch.setattr(adc, "IDENTITY_FIRST_ATTEMPT_S", 0.1)
    monkeypatch.setattr(adc, "IDENTITY_MIN_RETRY_S", 0.01)
    bridge = AlarmBridge()
    answer = MagicMock()

    async def slow_then_answer(**_kwargs: Any) -> Any:
        if request.await_count == 1:
            await asyncio.sleep(10)
        await asyncio.sleep(0.15)
        return answer

    request = AsyncMock(side_effect=slow_then_answer)
    monkeypatch.setattr(bridge, "request", request)
    token = _LOGIN_IN_PROGRESS.set(True)
    try:
        assert await bridge.get("identities/", None) is answer
    finally:
        _LOGIN_IN_PROGRESS.reset(token)


@pytest.mark.parametrize(
    ("reason", "needs_clear", "expected"),
    [
        ("open_zone", False, "not ready to arm"),
        ("open_zone", True, "not ready to arm"),
        ("uncleared_issues", False, "must be acknowledged"),
        (None, True, "must be acknowledged"),
        (None, False, "without a recognized reason"),
    ],
)
def test_panel_message_explains_the_rejection(reason: str | None, needs_clear: bool, expected: str) -> None:  # noqa: FBT001
    """The panel's own uncleared-issues flag is used when Alarm.com's reply gives no recognisable reason."""
    partition = SimpleNamespace(attributes=SimpleNamespace(needs_clear_issues_prompt=needs_clear))
    controller = SimpleNamespace(get=lambda _id: partition)
    assert expected in _rejection_message("arm_stay", reason, controller, "123-1")
