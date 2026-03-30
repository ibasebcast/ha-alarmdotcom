# Changelog

All notable changes to the Alarm.com Home Assistant integration will be documented in this file.

---
## 2026.3.30

### Added
- **Janus proxy camera support**: Cameras that use the Alarm.com Janus WebRTC gateway are now fully supported. The backend resolves the Janus mountpoint ID from the API response — first trying the HD quality stream entry, falling back to SD, and finally deriving it from the camera ID suffix for cameras that don't include quality message entries. The Lovelace card supports a `janusStreamId` override in card config for cases where the API does not expose the correct mountpoint.
- **Janus proxy mountpoint creation**: For cameras served via a proxy URL, the card automatically creates the Janus mountpoint (using the `proxyUrl` as the media source) before issuing the watch request. The mountpoint ID is dynamic per session and is captured from the Janus create response.
- **Lovelace card debug logging**: Internal card diagnostics now use `console.debug` so they are only visible when browser debug logging is enabled.

### Fixed
- **Camera stream reconnect**: The Lovelace card now automatically reconnects when a WebRTC stream drops. ICE disconnection, failure, and closure events trigger a retry sequence with up to 5 attempts at 4-second intervals. After exhausting retries a manual reconnect button is shown. Janus hangup, detach, and error events also trigger the retry path. A token request safety timeout prevents the card from freezing indefinitely if the backend does not respond.
- **Documentation**: Corrected token refresh interval in README from 45 minutes to 30 minutes to match the actual value in `camera.py`.

---
## 2026.3.27

### Fixed
- **Lock**: Removed incorrect code requirement on lock/unlock actions. The integration was applying the alarm panel arm code to locks, causing HA to reject lock/unlock commands with "The code for {device} doesn't match pattern number" for any user without an arm code configured, or whose arm code didn't match. Locks no longer require a code to operate — the arm code option applies to the alarm control panel only.
- **Lock**: Removed incorrect code requirement on lock/unlock actions. The integration was applying the alarm panel arm code to locks, causing HA to reject lock/unlock commands with "The code for {device} doesn't match pattern number." Locks no longer require a code — the arm code option applies to the alarm control panel only.
- **Websocket reconnect**: When the Alarm.com websocket died, the integration would silently stop receiving all state updates with no recovery path. Users had to manually reload or reboot HA. The hub now automatically attempts to reconnect with exponential backoff (up to 5 attempts, 30–150 second delays). If all attempts fail it schedules a full integration reload automatically.
- **Stale state after reconnect**: Added a periodic full state poll every 5 minutes as a safety net. Any state changes that occurred during a websocket gap are now caught and reflected in HA.
- **Camera session recovery**: Camera session re-login on auth failure now correctly checks whether it owns the session before attempting an independent login, preventing incorrect login attempts when sharing the pyalarmdotcomajax session.

### Improved
- Websocket death no longer raises `ConfigEntryNotReady` into a void — it now triggers a managed reconnect task with proper logging at each attempt
- Reconnect task is cleanly cancelled on integration unload

---

## 2026.3.21

Builds on 2026.3.18.2 with camera support, a full bug fix pass across all platforms, and HACS readiness improvements.

### Added
- **Camera support**: WebRTC live-streaming for Alarm.com cameras via a custom Lovelace card (`www/alarm-webrtc-card.js`)
- Camera entities automatically refresh WebRTC tokens every 45 minutes so streams are always ready without manual intervention
- Still image snapshots now supported — camera thumbnails display correctly in the HA media browser and picture-glance dashboard cards
- `brand/logo.png` added for HACS integration detail page display
- `info.md` added for HACS store listing

### Fixed

#### Platforms
- **Thermostat**: `async_set_temperature` was silently doing nothing — it read `kwargs.get("target_temp")` but HA sends `"temperature"` (`ATTR_TEMPERATURE`). Single-target temperature changes now work correctly
- **Thermostat**: High/low setpoints now sent in a single API call instead of two sequential calls, avoiding potential race conditions and rate limiting
- **Thermostat**: Fixed mismatched `# fmt: off` / `# fmt: on` comment pair in `initiate_state`
- **Lock**: `code_format_fn` now correctly returns `CodeFormat.NUMBER` / `CodeFormat.TEXT` instead of raw regex strings that HA doesn't understand, fixing silent failure of lock code format enforcement
- **Lock**: Removed `import re` buried inside a function body — moved to top-level import
- **Alarm Panel**: Removed duplicate arm code validation that ran twice on every arm/disarm command (once silently, once raising an exception)
- **Cover**: Gates now correctly use `CoverDeviceClass.GATE` instead of `CoverDeviceClass.GARAGE` — gate entities now show the correct icon and label in HA
- **Entity**: Removed unreachable duplicate `return device_info` statement in `device_info_fn`

#### Infrastructure
- **Orphan cleanup** (`util.py`): Entities without a `unique_id` were incorrectly deleted on every HA restart because the match condition was inverted. They are now matched solely by `entity_id` as intended
- **Camera session** (`camera_api.py`): Auth retries now only trigger on HTTP 401/403 responses instead of catching all exceptions blindly
- **Camera import** (`__init__.py`): Fixed `NameError` — `CONF_MFA_TOKEN`, `CONF_USERNAME`, and `CONF_PASSWORD` were referenced before being imported
- **Config flow** (`config_flow.py`): Replaced deprecated `async_timeout` package (removed in HA 2024.x) with `asyncio.timeout`

#### Lovelace Card (`www/alarm-webrtc-card.js`)
- Fixed `visibilitychange` event listener leak — a new listener was added on every stream restart and never removed. Listeners are now stored and cleaned up in `disconnectedCallback`
- Fixed `_requesting` flag deadlock — if HA never responded to a `camera.turn_on` call the card would freeze on "Refreshing session..." indefinitely. A 15-second safety timeout now resets the flag automatically
- `callService` failures now immediately reset `_requesting` instead of leaving the card frozen

### Improved
- Camera session reuses the authenticated `pyalarmdotcomajax` HTTP session where possible, avoiding a second full login on every HA startup. Falls back gracefully to an independent login if session internals are not accessible
- README updated with full camera setup instructions, Lovelace card configuration example, and camera added to supported devices table
- Camera removed from roadmap in README since it is now implemented
- Cleaned up dead commented-out platform stubs (`Platform.NUMBER`, `Platform.SWITCH`, `Platform.SELECT`) from `const.py`

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