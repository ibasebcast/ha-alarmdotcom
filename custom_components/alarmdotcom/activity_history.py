"""
Lock-unlock user attribution via Alarm.com's activity history endpoint.

Genuinely separate from every other piece of live state this integration
tracks: "who unlocked this door" only exists in Alarm.com's activity
history (see _pyalarmdotcomajax's AlarmBridge.get_activity_history), an
entirely different, actively-polled data source from the live websocket
resource stream everything else in this integration relies on. Built for
GitHub issue #79.

Lights and switches are deliberately not covered here - Alarm.com's own
system does not attribute those to a specific user at all, only knowing
that a device was turned on/off, not by whom. This is confirmed
integration-owner domain knowledge, not a gap in what this poller checks
for.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

from homeassistant.core import callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

if TYPE_CHECKING:
    from .hub import AlarmHub

_LOGGER = logging.getLogger(__name__)

# How far back to look on the very first poll after startup - covers
# anything that happened while Home Assistant was offline or restarting,
# without re-processing the account's entire activity history.
INITIAL_LOOKBACK = timedelta(minutes=5)

# How often to poll. A genuinely separate cadence from the 5-minute
# periodic full-state refresh hub.py already runs - this is deliberately
# more frequent, since "who unlocked the door" needs to feel prompt for a
# welcome-home automation, not just eventually-consistent. Polls an
# entirely undocumented endpoint, so this errs toward a conservative
# interval rather than assuming an unknown rate limit can absorb something
# tighter.
POLL_INTERVAL = timedelta(seconds=60)


class LockActivityTracker:
    """Polls Alarm.com's activity history for lock-unlock user attribution."""

    def __init__(self, hub: AlarmHub) -> None:
        """Initialize the tracker for one hub."""

        self.hub = hub
        self._last_poll_end: datetime = dt_util.utcnow() - INITIAL_LOOKBACK
        # resource_id -> (unlocked_by_name, unlocked_at). unlocked_by_name
        # is None both when the unlock wasn't a keypad-code unlock at all
        # and when Alarm.com didn't attribute it to a specific person -
        # see HistoryEventAttributes.unlocked_by_name for why those two
        # cases are deliberately not distinguished.
        self._last_unlock: dict[str, tuple[str | None, datetime]] = {}
        self._change_listeners: list[Callable[[], None]] = []
        self._unsub_timer: Callable[[], None] | None = None

    def get_last_unlock(self, resource_id: str) -> tuple[str | None, datetime] | None:
        """Return (unlocked_by_name, unlocked_at) for resource_id's most recently tracked unlock, if any."""

        return self._last_unlock.get(resource_id)

    @callback
    def add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Register a callback invoked whenever new unlock attribution is found. Returns an unsubscribe function."""

        self._change_listeners.append(listener)

        @callback
        def _unsubscribe() -> None:
            self._change_listeners.remove(listener)

        return _unsubscribe

    def async_start(self) -> None:
        """Begin periodic polling."""

        self._unsub_timer = async_track_time_interval(self.hub.hass, self.async_poll, POLL_INTERVAL)

    def async_stop(self) -> None:
        """Stop periodic polling."""

        if self._unsub_timer is not None:
            self._unsub_timer()
            self._unsub_timer = None

    async def async_poll(self, _now: datetime | None = None) -> None:
        """
        Fetch activity history since the last poll and update lock attribution.

        Deliberately never raises - a failed poll (including against this
        undocumented endpoint returning something unexpected) should be
        logged and retried next interval, not crash the periodic timer or
        take down anything else in the integration.
        """

        poll_start = self._last_poll_end
        poll_end = dt_util.utcnow()

        try:
            events = await self.hub.api.get_activity_history(start_time=poll_start, end_time=poll_end)
        except Exception:
            _LOGGER.debug("Lock activity poll failed, will retry next interval.", exc_info=True)
            return

        self._last_poll_end = poll_end

        known_lock_ids = {lock.id for lock in self.hub.api.locks}
        changed = False

        for event in events:
            if event.attributes.event_type_name != "DoorUnlocked":
                continue

            resource_id = event.attributes.global_device_id
            if resource_id not in known_lock_ids:
                continue

            unlocked_at = dt_util.parse_datetime(event.attributes.event_date) or poll_end
            existing = self._last_unlock.get(resource_id)
            if existing is not None and existing[1] >= unlocked_at:
                # Already have a same-or-newer record for this lock - a
                # real scenario given start_time/end_time windows can
                # overlap slightly between polls (a caught-up-but-not-yet-
                # advanced last_poll_end), not just a defensive check.
                continue

            self._last_unlock[resource_id] = (event.attributes.unlocked_by_name, unlocked_at)
            changed = True

        if changed:
            self._notify_listeners()

    def _notify_listeners(self) -> None:
        for listener in self._change_listeners:
            listener()
