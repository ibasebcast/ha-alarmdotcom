"""
Tests for LockActivityTracker (activity_history.py).

Mocks hub.api.get_activity_history and hub.api.locks directly - the
fetch mechanism itself is already covered by test_get_activity_history.py;
these tests focus on what's new here: filtering, deduplication, and the
change-notification mechanism.
"""

from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.alarmdotcom.activity_history import LockActivityTracker

FRONT_DOOR_ID = "110353471-1201"
PATIO_DOOR_ID = "110353471-1200"


def _make_lock(resource_id: str) -> MagicMock:
    """Build a mock lock resource with just the .id attribute needed."""
    lock = MagicMock()
    lock.id = resource_id
    return lock


def _make_event(
    event_type_name: str,
    global_device_id: str,
    event_date: str,
    unlocked_by_name: str | None,
) -> MagicMock:
    """Build a mock HistoryEvent with just the attributes LockActivityTracker actually reads."""
    event = MagicMock()
    event.attributes.event_type_name = event_type_name
    event.attributes.global_device_id = global_device_id
    event.attributes.event_date = event_date
    event.attributes.unlocked_by_name = unlocked_by_name
    return event


def _make_hub(locks: list[MagicMock], events: list[MagicMock]) -> MagicMock:
    """Build a mock hub whose api returns the given locks and get_activity_history returns the given events."""
    hub = MagicMock()
    hub.api.locks = locks
    hub.api.get_activity_history = AsyncMock(return_value=events)
    return hub


@pytest.fixture
def tracker(hass) -> LockActivityTracker:
    """Build a fresh, unstarted LockActivityTracker (no locks, no events by default)."""
    hub = _make_hub(locks=[_make_lock(FRONT_DOOR_ID)], events=[])
    hub.hass = hass
    return LockActivityTracker(hub)


async def test_keypad_unlock_is_tracked() -> None:
    """A DoorUnlocked event for a known lock, with attribution, gets tracked."""
    event = _make_event("DoorUnlocked", FRONT_DOOR_ID, "2026-07-14T02:22:56.307Z", "Chris Pulliam")
    hub = _make_hub(locks=[_make_lock(FRONT_DOOR_ID)], events=[event])
    tracker = LockActivityTracker(hub)

    await tracker.async_poll()

    result = tracker.get_last_unlock(FRONT_DOOR_ID)
    assert result is not None
    unlocked_by, unlocked_at = result
    assert unlocked_by == "Chris Pulliam"
    assert unlocked_at == datetime(2026, 7, 14, 2, 22, 56, 307000, tzinfo=UTC)


async def test_unattributed_unlock_is_still_tracked_with_none() -> None:
    """A DoorUnlocked event with no attribution (web session, manual) is still tracked - as None, not skipped."""
    event = _make_event("DoorUnlocked", FRONT_DOOR_ID, "2026-07-14T02:22:56.307Z", None)
    hub = _make_hub(locks=[_make_lock(FRONT_DOOR_ID)], events=[event])
    tracker = LockActivityTracker(hub)

    await tracker.async_poll()

    result = tracker.get_last_unlock(FRONT_DOOR_ID)
    assert result is not None
    assert result[0] is None


async def test_non_unlock_events_are_ignored(tracker: LockActivityTracker) -> None:
    """Events that aren't DoorUnlocked (light on/off, arm/disarm, etc.) don't get tracked at all."""
    event = _make_event("LightTurnedOn", FRONT_DOOR_ID, "2026-07-14T02:22:56.307Z", None)
    tracker.hub.api.get_activity_history = AsyncMock(return_value=[event])

    await tracker.async_poll()

    assert tracker.get_last_unlock(FRONT_DOOR_ID) is None


async def test_unlock_for_unknown_device_is_ignored(tracker: LockActivityTracker) -> None:
    """A DoorUnlocked event for a device that isn't one of this account's known locks is ignored."""
    event = _make_event("DoorUnlocked", "some-other-device-id", "2026-07-14T02:22:56.307Z", "Someone")
    tracker.hub.api.get_activity_history = AsyncMock(return_value=[event])

    await tracker.async_poll()

    assert tracker.get_last_unlock("some-other-device-id") is None


async def test_multiple_locks_are_tracked_independently() -> None:
    """Two different locks unlocking get tracked separately, not overwriting each other."""
    events = [
        _make_event("DoorUnlocked", FRONT_DOOR_ID, "2026-07-14T02:22:56.307Z", "Chris Pulliam"),
        _make_event("DoorUnlocked", PATIO_DOOR_ID, "2026-07-13T23:35:28.823Z", None),
    ]
    hub = _make_hub(locks=[_make_lock(FRONT_DOOR_ID), _make_lock(PATIO_DOOR_ID)], events=events)
    tracker = LockActivityTracker(hub)

    await tracker.async_poll()

    assert tracker.get_last_unlock(FRONT_DOOR_ID)[0] == "Chris Pulliam"
    assert tracker.get_last_unlock(PATIO_DOOR_ID)[0] is None


async def test_older_event_does_not_overwrite_a_newer_tracked_record() -> None:
    """A same-or-older event (e.g. from overlapping poll windows) never overwrites a newer tracked record."""
    hub = _make_hub(locks=[_make_lock(FRONT_DOOR_ID)], events=[])
    tracker = LockActivityTracker(hub)

    newer_event = _make_event("DoorUnlocked", FRONT_DOOR_ID, "2026-07-14T02:22:56.307Z", "Chris Pulliam")
    tracker.hub.api.get_activity_history = AsyncMock(return_value=[newer_event])
    await tracker.async_poll()

    older_event = _make_event("DoorUnlocked", FRONT_DOOR_ID, "2026-07-13T23:35:28.823Z", "Someone Else")
    tracker.hub.api.get_activity_history = AsyncMock(return_value=[older_event])
    await tracker.async_poll()

    assert tracker.get_last_unlock(FRONT_DOOR_ID)[0] == "Chris Pulliam"


async def test_listener_notified_when_new_attribution_found(tracker: LockActivityTracker) -> None:
    """A registered listener fires when a poll actually finds something new."""
    calls = 0

    def _on_change() -> None:
        nonlocal calls
        calls += 1

    tracker.add_listener(_on_change)
    event = _make_event("DoorUnlocked", FRONT_DOOR_ID, "2026-07-14T02:22:56.307Z", "Chris Pulliam")
    tracker.hub.api.get_activity_history = AsyncMock(return_value=[event])

    await tracker.async_poll()

    assert calls == 1


async def test_listener_not_notified_when_nothing_new(tracker: LockActivityTracker) -> None:
    """A poll that finds nothing new (empty response) does not spuriously notify listeners."""
    calls = 0

    def _on_change() -> None:
        nonlocal calls
        calls += 1

    tracker.add_listener(_on_change)

    await tracker.async_poll()

    assert calls == 0


async def test_unsubscribe_stops_future_notifications(tracker: LockActivityTracker) -> None:
    """The unsubscribe function returned by add_listener actually stops future notifications."""
    calls = 0

    def _on_change() -> None:
        nonlocal calls
        calls += 1

    unsubscribe = tracker.add_listener(_on_change)
    unsubscribe()

    event = _make_event("DoorUnlocked", FRONT_DOOR_ID, "2026-07-14T02:22:56.307Z", "Chris Pulliam")
    tracker.hub.api.get_activity_history = AsyncMock(return_value=[event])
    await tracker.async_poll()

    assert calls == 0


async def test_a_failed_poll_does_not_raise(tracker: LockActivityTracker) -> None:
    """A poll that fails (e.g. network error, unexpected response shape) is logged and swallowed, not raised."""
    tracker.hub.api.get_activity_history = AsyncMock(side_effect=ConnectionError("boom"))

    # Must not raise - this is the actual behavior under test.
    await tracker.async_poll()

    assert tracker.get_last_unlock(FRONT_DOOR_ID) is None


async def test_get_last_unlock_returns_none_for_untracked_lock(tracker: LockActivityTracker) -> None:
    """A lock with no tracked unlock at all returns None, not an error."""
    assert tracker.get_last_unlock(FRONT_DOOR_ID) is None
