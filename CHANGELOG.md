# Changelog

All notable changes to the Alarm.com Home Assistant integration will be documented in this file.

---
## 2026.3.20

### Added
- **Camera support**: WebRTC live-streaming for Alarm.com cameras via a custom Lovelace card (`www/alarm-webrtc-card.js`)
- Camera entities include automatic token refresh every 45 minutes so streams are always ready
- Still image snapshots now supported — camera thumbnails display correctly in the HA media browser and dashboard cards

### Fixed
- `lock.py`: `code_format_fn` now correctly returns `CodeFormat.NUMBER` / `CodeFormat.TEXT` instead of raw regex strings, fixing silent failure of lock code format enforcement
- `alarm_control_panel.py`: Removed duplicate arm code validation that ran twice on every arm/disarm command
- `util.py`: Orphan cleanup logic rewritten — entities without a `unique_id` were incorrectly deleted on every restart; they are now matched solely by `entity_id`
- `climate.py`: `async_set_temperature` was reading `kwargs.get("target_temp")` but HA sends `"temperature"` (ATTR_TEMPERATURE), meaning single-target temperature changes silently did nothing
- `climate.py`: Combined two sequential `set_state` API calls for high/low setpoints into a single call
- `climate.py`: Fixed mismatched `# fmt: off` / `# fmt: on` comment pair in `initiate_state`
- `cover.py`: Gates now correctly use `CoverDeviceClass.GATE` instead of `CoverDeviceClass.GARAGE`
- `entity.py`: Removed unreachable duplicate `return device_info` statement
- `camera_api.py`: Auth retries now only trigger on HTTP 401/403 instead of catching all exceptions
- `alarm-webrtc-card.js`: Fixed `visibilitychange` event listener leak — listeners now properly removed in `disconnectedCallback`
- `alarm-webrtc-card.js`: Fixed `_requesting` flag deadlock — a 15-second safety timeout now resets the flag if HA never responds to a `turn_on` call
- `alarm-webrtc-card.js`: `callService` failures now immediately reset the `_requesting` flag instead of freezing the card

### Improved
- Camera session now reuses the authenticated `pyalarmdotcomajax` HTTP session where possible, avoiding a second login on startup
- Camera session initialization falls back gracefully to an independent login if session sharing is not available
- README updated with full camera setup instructions and Lovelace card configuration

---

## 2026.3.18.2

### Fixed
- Resolved issue where one-time password (OTP) was not sent during initial login when only a single 2FA method was available
- Fixed config flow skipping OTP request step, causing users to be stuck on verification screen
- Corrected OTP handling logic to properly request codes for SMS and email methods

### Improved
- Enhanced multi-factor authentication flow to handle all supported Alarm.com verification methods correctly
- Added safeguards for lost or invalid OTP method state during login
- Improved error handling and user feedback during authentication process
- Updated device registry identifiers to ensure compatibility with Home Assistant requirements

### Changed
- Updated pyalarmdotcomajax dependency to custom GitHub version with OTP fixes
- Cleaned up config flow logic for better reliability and maintainability

### Other
- Reordered manifest.json fields to meet Home Assistant and hassfest validation requirements
- General code cleanup and logging improvements

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