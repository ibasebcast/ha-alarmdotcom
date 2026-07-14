"""
Activity feed and lock-unlock user attribution via Alarm.com's activity history endpoint.

Genuinely separate from every other piece of live state this integration
tracks: none of what this module covers (who unlocked a door, a general
account activity feed) is part of any device's ongoing state - it only
exists in Alarm.com's activity history (see _pyalarmdotcomajax's
AlarmBridge.get_activity_history), an entirely different, actively-polled
data source from the live websocket resource stream everything else in
this integration relies on.

Originally built for GitHub issue #79 (lock unlock attribution only);
extended to also fire a curated general activity feed on Home Assistant's
event bus and maintain a short rolling "recent activity" list, since the
poller already fetches every event Alarm.com logs - the lock-specific
tracking was just discarding everything else.

Lights and switches have no unlock-style attribution - Alarm.com's own
system does not attribute those to a specific user at all, only knowing
that a device was turned on/off, not by whom. This is confirmed
integration-owner domain knowledge, not a gap in what this poller checks
for.
"""

from __future__ import annotations

import logging
from collections import deque
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, TypedDict

import _pyalarmdotcomajax as pyadc
from homeassistant.core import callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .const import CONF_ACTIVITY_POLL_INTERVAL, CONF_OPTIONS_DEFAULT, DOMAIN

if TYPE_CHECKING:
    from .hub import AlarmHub

_LOGGER = logging.getLogger(__name__)

# How far back to look on the very first poll after startup - covers
# anything that happened while Home Assistant was offline or restarting,
# without re-processing the account's entire activity history.
INITIAL_LOOKBACK = timedelta(minutes=5)

# Default poll interval, used until a user configures their own via the
# options flow (see config_flow.py's ADCOptionsFlowHandler.async_step_polling).
# Deliberately more frequent than the 5-minute periodic full-state refresh
# hub.py already runs, since "who unlocked the door" needs to feel prompt
# for a welcome-home automation (e.g. TTS on a speaker), not just
# eventually-consistent.
#
# This polls an entirely undocumented endpoint with zero confirmed rate
# limit information - 15 seconds is a real, deliberate tradeoff (4x the
# request volume of the 60-second interval this shipped with initially),
# made because a welcome-home automation genuinely benefits from a
# tighter response time, not chosen without weighing the risk. The web
# app's own request carries debounceTimeMs=1000, suggesting the endpoint
# is built to tolerate fairly frequent calls, but that's an inference
# from one observed request, not a confirmed rate limit. Being
# configurable (rather than just a hardcoded constant) exists specifically
# so this can be dialed back by anyone who hits an actual problem, without
# needing a code change.
DEFAULT_POLL_INTERVAL_SECONDS = CONF_OPTIONS_DEFAULT[CONF_ACTIVITY_POLL_INTERVAL]

# Home Assistant event bus event type fired for every curated activity event.
EVENT_ACTIVITY = f"{DOMAIN}_activity"

# How many recent events to keep for the "Recent Activity" sensor's
# attribute - a glanceable list, not a full history browser.
RECENT_ACTIVITY_MAX_LEN = 10

# Curated allow-list of event_type_name values considered "significant"
# enough to fire on the event bus and appear in the recent-activity list,
# regardless of which device they came from. A deliberate default, not a
# claim of completeness - real captured data showed roughly one event
# every 2-3 minutes during ordinary evening activity, much of it
# genuinely noisy for automation purposes (every light interaction fires
# twice - once for the "[Web] Command:" and once for the resulting state
# change; doorbell motion and button presses fire constantly). This list
# favors clearly-significant, low-frequency event types over completeness.
#
# Garage door open/close is deliberately NOT in this set - see
# GARAGE_DOOR_EVENT_TYPES below for why it needs a different check.
#
# Deliberately excluded, and why:
# - LightTurnedOn/LightTurnedOff, ButtonPressed: high-frequency, and
#   Alarm.com does not attribute these to a user at all (see module
#   docstring), so they carry less unique value than the events below.
# - The "[Web] Command: ..." pseudo-events (eventType == -1, "Unknown"):
#   redundant with the resulting state-change event these are always
#   paired with (e.g. "[Web] Command: Disarm" + "Disarmed by Web").
# - SuccessfulWebsiteLogin, SensorLeftOpenRule/Restoral: account/session
#   or rule-engine noise, not device activity.
ACTIVITY_FEED_EVENT_TYPES = frozenset(
    {
        "ArmedAway",
        "ArmedStay",
        "ArmedNight",  # inferred to exist alongside ArmedStay/ArmedAway - not directly confirmed from captured data.
        "Disarmed",
        "DoorLocked",
        "DoorUnlocked",
        "VideoCameraTriggered",
    }
)

# Event type names used for garage door open/close - handled separately
# from ACTIVITY_FEED_EVENT_TYPES above because these same names are also
# used by ordinary window/door sensors (both share identical
# event_type_name values in captured data). A garage door event only
# qualifies for the curated feed if its global_device_id also matches one
# of this account's known garage door resources - see
# hub.api.garage_doors, the same controller cover.py already uses to set
# up garage door entities, cross-referenced the same way
# known_lock_ids is used for lock unlock attribution.
GARAGE_DOOR_EVENT_TYPES = frozenset({"Opened", "Closed", "OpenedClosed"})


class RecentActivityEntry(TypedDict):
    """One entry in the recent-activity rolling list."""

    description: str
    event_type_name: str
    device_description: str
    event_date: str


class ActivityFeedTracker:
    """Polls Alarm.com's activity history for lock-unlock attribution and a curated general activity feed."""

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
        self._recent_activity: deque[RecentActivityEntry] = deque(maxlen=RECENT_ACTIVITY_MAX_LEN)
        self._change_listeners: list[Callable[[], None]] = []
        self._unsub_timer: Callable[[], None] | None = None

    def get_last_unlock(self, resource_id: str) -> tuple[str | None, datetime] | None:
        """Return (unlocked_by_name, unlocked_at) for resource_id's most recently tracked unlock, if any."""

        return self._last_unlock.get(resource_id)

    def get_recent_activity(self) -> list[RecentActivityEntry]:
        """Return the most recent curated activity events, newest first."""

        return list(reversed(self._recent_activity))

    @callback
    def add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Register a callback invoked whenever new attribution or activity is found. Returns an unsubscribe function."""

        self._change_listeners.append(listener)

        @callback
        def _unsubscribe() -> None:
            self._change_listeners.remove(listener)

        return _unsubscribe

    def async_start(self) -> None:
        """Begin periodic polling, at the user-configured interval if one is set."""

        interval_seconds = self.hub.config_entry.options.get(
            CONF_ACTIVITY_POLL_INTERVAL, DEFAULT_POLL_INTERVAL_SECONDS
        )
        self._unsub_timer = async_track_time_interval(
            self.hub.hass, self.async_poll, timedelta(seconds=interval_seconds)
        )

    def async_stop(self) -> None:
        """Stop periodic polling."""

        if self._unsub_timer is not None:
            self._unsub_timer()
            self._unsub_timer = None

    async def async_poll(self, _now: datetime | None = None) -> None:
        """
        Fetch activity history since the last poll, update lock attribution, and fire curated feed events.

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
            _LOGGER.debug("Activity poll failed, will retry next interval.", exc_info=True)
            return

        self._last_poll_end = poll_end

        known_lock_ids = {lock.id for lock in self.hub.api.locks}
        known_garage_door_ids = {door.id for door in self.hub.api.garage_doors}
        changed = False
        matched_unlock_count = 0
        feed_count = 0

        for event in events:
            event_type_name = event.attributes.event_type_name

            is_curated = event_type_name in ACTIVITY_FEED_EVENT_TYPES
            is_curated_garage_event = (
                event_type_name in GARAGE_DOOR_EVENT_TYPES
                and event.attributes.global_device_id in known_garage_door_ids
            )

            if is_curated or is_curated_garage_event:
                feed_count += 1
                self._fire_activity_event(event)

            if event_type_name != "DoorUnlocked":
                continue

            resource_id = event.attributes.global_device_id
            if resource_id not in known_lock_ids:
                continue

            matched_unlock_count += 1
            unlocked_at = dt_util.parse_datetime(event.attributes.event_date) or poll_end
            existing = self._last_unlock.get(resource_id)
            if existing is not None and existing[1] >= unlocked_at:
                # Already have a same-or-newer record for this lock - a
                # real scenario given start_time/end_time windows can
                # overlap slightly between polls (a caught-up-but-not-yet-
                # advanced last_poll_end), not just a defensive check.
                continue

            unlocked_by = event.attributes.unlocked_by_name
            self._last_unlock[resource_id] = (unlocked_by, unlocked_at)
            changed = True

            # Deliberately INFO, not debug: this only fires on a real,
            # new unlock event - not every poll - so it's a useful,
            # non-noisy confirmation the whole pipeline is actually
            # working, visible without needing debug logging turned on
            # or a live test to check.
            _LOGGER.info(
                "Lock activity: %s unlocked (attributed to: %s)",
                resource_id,
                unlocked_by or "unknown/unattributed",
            )

        # Debug-level per-poll summary - not useful at normal log levels
        # (would just be noise every poll), but confirms the poller is
        # alive and fetching successfully when debug logging is actually
        # turned on to investigate something.
        _LOGGER.debug(
            "Activity poll completed: %s event(s) fetched, %s matched a known lock, %s matched the "
            "curated feed, window %s to %s.",
            len(events),
            matched_unlock_count,
            feed_count,
            poll_start.isoformat(),
            poll_end.isoformat(),
        )

        if changed or feed_count:
            self._notify_listeners()

    def _fire_activity_event(self, event: pyadc.HistoryEvent) -> None:
        """Fire a curated event on Home Assistant's event bus and append it to the recent-activity list."""

        attrs = event.attributes
        entry: RecentActivityEntry = {
            "description": attrs.description,
            "event_type_name": attrs.event_type_name,
            "device_description": attrs.device_description,
            "event_date": attrs.event_date,
        }
        self._recent_activity.append(entry)
        self.hub.hass.bus.async_fire(
            EVENT_ACTIVITY,
            {
                "description": attrs.description,
                "event_type_name": attrs.event_type_name,
                "device_id": attrs.global_device_id,
                "device_description": attrs.device_description,
                "event_date": attrs.event_date,
            },
        )

    def _notify_listeners(self) -> None:
        for listener in self._change_listeners:
            listener()
