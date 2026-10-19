"""Utility functions."""

from typing import TYPE_CHECKING

from homeassistant.helpers.device_registry import (
    DeviceEntryType,
    async_entries_for_config_entry,
)
from homeassistant.helpers.device_registry import async_get as async_get_device_registry
from homeassistant.helpers.entity_registry import async_get as async_get_entity_registry

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry
    from homeassistant.core import HomeAssistant


def slug_to_title(slug: str) -> str:
    """Convert slug to title case."""

    return slug.replace("_", " ").title()


async def cleanup_orphaned_entities_and_devices(
    hass: "HomeAssistant",
    config_entry: "ConfigEntry",
    current_entity_ids: set[str],
    current_unique_ids: set[str],
    platform: str,
) -> None:
    """
    Remove orphaned entities and devices for a given platform.

    Args:
        hass: HomeAssistant instance
        config_entry: The config entry for the integration
        current_entity_ids: Set of entity_ids currently provided by the integration
        current_unique_ids: Set of unique_ids currently provided by the integration
        platform: The Home Assistant platform (e.g., "light", "lock", "cover", etc.)

    """
    entity_registry = async_get_entity_registry(hass)
    device_registry = async_get_device_registry(hass)

    # Remove orphaned entities for this platform.
    # An entity is orphaned when NEITHER its entity_id NOR its unique_id is
    # present in the current set. Entities without a unique_id are matched
    # solely by entity_id — we must not delete them just because unique_id is absent.
    for entry in list(entity_registry.entities.values()):
        if entry.config_entry_id != config_entry.entry_id or entry.domain != platform:
            continue

        matched_by_entity_id = entry.entity_id in current_entity_ids
        matched_by_unique_id = bool(entry.unique_id) and entry.unique_id in current_unique_ids

        if not matched_by_entity_id and not matched_by_unique_id:
            entity_registry.async_remove(entry.entity_id)

    # Remove orphaned devices with no entities left, but skip SERVICE devices.
    # async_entries_for_config_entry rather than device_registry.devices, whose mapping
    # interface is deprecated and stops working in HA Core 2027.9. The helper already
    # narrows to devices this entry touches; the check below keeps only those it owns
    # outright, which is the same set the previous full scan selected.
    remaining_device_ids = {entry.device_id for entry in entity_registry.entities.values() if entry.device_id}
    for device in list(
        async_entries_for_config_entry(device_registry, config_entry.entry_id)
    ):
        if (
            (
                device.config_entry_id == config_entry.entry_id
                if hasattr(device, "config_entry_id")
                else device.config_entries == {config_entry.entry_id}
            )
            and device.entry_type != DeviceEntryType.SERVICE
        ):
            if device.id not in remaining_device_ids:
                device_registry.async_remove_device(device.id)
