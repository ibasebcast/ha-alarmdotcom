"""General event broker for all events in the system."""

from __future__ import annotations

import asyncio
import logging
from asyncio import Task
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import Enum
from functools import partial
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pyalarmdotcomajax.models.base import AdcResource

log = logging.getLogger(__name__)


class EventBrokerTopic(Enum):
    """Resource event types for transmission from pyalarmdotcomajax."""

    # Controller Events
    RESOURCE_ADDED = "add"
    RESOURCE_UPDATED = "update"
    RESOURCE_DELETED = "delete"

    # Websocket Events
    RAW_RESOURCE_EVENT = "RESOURCE_EVENT"
    CONNECTION_EVENT = "CONNECTION_EVENT"


@dataclass(kw_only=True)
class EventBrokerMessage:
    """Represent a message to be published."""

    topic: EventBrokerTopic


EventBrokerCallbackT = Callable[[EventBrokerMessage], None | Awaitable[None]]


class EventBroker:
    """Manage subscriptions and distribute messages to subscribers."""

    def __init__(self) -> None:
        self._subscriptions: dict[
            EventBrokerTopic, dict[EventBrokerCallbackT, list[str] | None]
        ] = {}
        self._background_tasks: set[Task] = set()

    def subscribe(
        self,
        topics: EventBrokerTopic | list[EventBrokerTopic],
        callback: EventBrokerCallbackT,
        ids: list[str] | str | None = None,
    ) -> Callable[[], None]:
        """Register a callback function to one or more topics."""

        if isinstance(topics, EventBrokerTopic):
            topics = [topics]

        if not ids:
            ids = []

        if isinstance(ids, str):
            ids = [ids]

        def unsubscribe_topic(
            topic: EventBrokerTopic, callback: EventBrokerCallbackT = callback
        ) -> None:  # Fixed closure issue
            """Unregister the callback from a specific topic."""
            if topic in self._subscriptions:
                del self._subscriptions[topic][callback]
                if not self._subscriptions[topic]:  # If list is empty, remove the entry
                    del self._subscriptions[topic]

        unsubscribe_functions = []
        for topic in topics:
            self._subscriptions.setdefault(topic, {})[callback] = ids
            unsubscribe_functions.append(partial(unsubscribe_topic, topic, callback))

        def unsubscribe_all() -> None:
            """Unregister the callback from all topics."""
            for unsubscribe_func in unsubscribe_functions:
                unsubscribe_func()

        return unsubscribe_all

    def publish(self, message: EventBrokerMessage) -> None:
        """Publish a message to subscribers of a topic."""

        for callback, ids in self._subscriptions.get(message.topic, {}).items():
            if (
                hasattr(message, "id")
                and ids
                and getattr(message, "id", None) not in ids
            ):
                continue

            if asyncio.iscoroutinefunction(callback):
                task = asyncio.create_task(callback(message))
                self._background_tasks.add(task)
                task.add_done_callback(self._background_tasks.discard)
            else:
                callback(message)


#
# CONTROLLER EVENTS
#


@dataclass(kw_only=True)
class ResourceEventMessage(EventBrokerMessage):
    """Message class for updated resources."""

    id: str
    resource: AdcResource | None = None


#
# /CONTROLLER EVENTS
#
