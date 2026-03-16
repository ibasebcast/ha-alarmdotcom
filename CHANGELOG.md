# Changelog

All notable changes to the Alarm.com Home Assistant integration will be documented in this file.

---

## 2026.3.16

Expanded Alarm.com entity coverage with new diagnostic sensors, system actions, trouble reporting, and bypass services.

### Added

- Added Home Assistant `sensor` platform to the integration
- Added diagnostic battery percentage sensors where Alarm.com exposes battery data
- Added diagnostic battery status enum sensors where Alarm.com exposes battery classification data
- Added diagnostic bypass state binary sensors for supported sensors
- Added system action buttons:
  - Stop Alarms
  - Clear Alarms In Memory
- Added smoke reset button support for smoke detector resources
- Added system-level trouble condition binary sensors
- Added per-device trouble mapping binary sensors
- Added `alarmdotcom.bypass_sensor` and `alarmdotcom.unbypass_sensor` services
- Added `services.yaml` definitions for the new bypass services

### Improved

- Expanded diagnostic visibility for Alarm.com systems and managed devices
- Integration now surfaces additional diagnostic and system state information
- Improved cleanup handling for newly created sensor entities
- Included the new `sensor` platform in the integration platform loader

### Dependency Updates

- Updated `pyalarmdotcomajax` dependency to `2026.3.15`
- Integration now pulls the library directly from the GitHub tag to ensure compatibility

### Notes

- Battery percentage and battery status only appear for device types where Alarm.com returns usable battery data
- Many panel sensors currently report no battery value and no bypass capability through the available Alarm.com payloads
- Bypass services will only work for sensors where Alarm.com reports `supportsBypass: true`

---

## 2026.3.14

Initial stabilization release for the maintained fork of the Alarm.com Home Assistant integration.

### Added

- Forked and modernized Alarm.com integration
- Updated codebase for compatibility with recent Home Assistant versions
- Initial repository structure cleanup and documentation improvements

### Improved

- Improved reliability and entity initialization
- Updated internal structure to better align with modern Home Assistant integration patterns

---

## Earlier Versions

Earlier development history was inherited from the original Alarm.com integration project and may not reflect the current maintained codebase.