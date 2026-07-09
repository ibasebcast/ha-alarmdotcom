## 2026.7.9.3b0 (beta)

### Fixed
- **Preemptive fix for a Home Assistant deprecation that becomes a hard error in December 2026.** Home Assistant 2026.6 deprecated using a config-entry update listener together with any reloading method in a config flow, because the combination can trigger the same config entry to reload twice at once - a race condition, not just wasted work. Verified directly against `home-assistant/core`'s real source (not just the changelog): our reauth flow called `async_update_entry(data=...)` and then explicitly `async_reload()` right after - and `async_update_entry` itself schedules every registered update listener (we have one, in `hub.py`, registered for the options flow) as soon as *any* field changes, `data` included. So reauth was firing two reload paths for the same entry nearly simultaneously.
  - Fixed by switching the reauth path to `async_update_and_abort()` - confirmed via `home-assistant/core`'s actual `2026.7.1` source that this method updates the entry and aborts with no reload of its own, leaving the existing listener to do the one necessary reload. The options flow, which relies entirely on that same listener and never reloads explicitly itself, is unaffected and still correct.

## 2026.7.9.2b0 (beta)

### Added
- **New: account-wide low/critical battery count sensors** (`sensor.Low Battery Count`, `sensor.Critical Battery Count`). Unlike every other sensor in this integration, these are single, permanent entities per account rather than one per device - they recount and update live whenever any device's battery status changes, not just at startup. Each sensor's state is the count of matching devices; a `devices` attribute lists which ones by name, so you don't need to go hunting through every individual device's battery sensor to find out which one actually needs a new battery. Both attach to the account's System device. Covered by `tests/test_sensor_battery_summary.py`.

### Fixed
- **Diagnostics downloads were silently missing all camera data.** Found by inspecting an actual diagnostics download from a live account: `CameraController` showed `0 items` despite the account having real, working cameras, while every other controller (lights, locks, sensors, thermostat) showed correct real counts. Root cause: cameras aren't discovered through the standard `resource_controllers` system the rest of the integration uses - `camera.py` fetches them through a separate session (`AlarmCameraSession`) entirely, so the standard `CameraController` is never actually populated. `diagnostics.py` now pulls camera data from that real source: a summary list (`get_camera_list()`) plus per-camera stream/connectivity info (`get_stream_info()`) for both the whole-account and per-device diagnostics views.
  - `get_stream_info()`'s raw response includes live session tokens - the exact data already redacted for debug logging (see `2026.7.6.1b0`) - so this only went in because it flows through the same redaction as everything else in the diagnostics dump, not a separate, easier-to-miss path. Covered by a dedicated test asserting the tokens actually come back redacted, not just that the feature runs without error.
  - No camera session (e.g. camera login never completed) and a failed camera-list fetch are both reported as a clean status in the output rather than raising and breaking the rest of the diagnostics download.

## 2026.7.9.1b0 (beta)

### Added
- **New: a diagnostics page.** Home Assistant's native diagnostics platform is now implemented (`diagnostics.py`) - a downloadable snapshot of everything the integration currently knows, available from **Settings → Devices & Services → Alarm.com → Download diagnostics** (whole account) or from any individual device's own page (that device only).
  - The whole-account dump includes config entry data, connection/websocket health, and a raw JSON:API dump of every resource across every controller (locks, sensors, thermostats, cameras, partitions, everything) - the same raw data the per-sensor "Debug" button already logs one device at a time, but comprehensive and available as one file instead of digging through logs device-by-device.
  - The per-device version is the same data, filtered to just that device - useful for reporting an issue with one sensor without needing to share the whole account's data.
  - **All known-sensitive fields are redacted before the data is ever assembled** - credentials, session tokens, and specifically the live camera stream tokens (`proxyUrl`, `janusToken`, `signallingServerToken`, `cameraAuthToken`, TURN credentials) using the same sensitive-field list built for the camera logging fix earlier. Covered by `tests/test_diagnostics.py`, including explicit regression tests asserting these specific tokens come back redacted, not just that the feature runs without error.
  - This closes the `diagnostics` item in `quality_scale.yaml`, previously `todo`.

## 2026.7.8.1b0 (beta)

### Fixed
- **`hub.py`: a genuine, previously-undiscovered runtime bug in the "all reconnect attempts exhausted" path.** `async_schedule_reload()` is a synchronous `@callback` that returns `None` and already schedules its own task internally - it was being wrapped in `async_create_task()` anyway, which would raise `TypeError` immediately after the reload had already correctly fired as a side effect. This would have hit every time Alarm.com connectivity failed enough times to exhaust all reconnect attempts - a real, reachable error path, not a hypothetical. Fixed: call it directly.
- **Arm/disarm code was never actually validated** (found while clearing a pre-commit lint backlog, not previously reported - this is the most important fix in this release): `alarm_control_panel.py`'s `control_fn` computed both the configured arm code and the user-entered code, but never compared them. Home Assistant core's `_attr_code_arm_required`/`_attr_code_format` mechanism only validates that an entered code matches the expected *format* (numeric vs. text) before this function is even called - it does not check the code against what's actually configured. Net effect: **anyone could arm or disarm by entering any correctly-formatted code, not necessarily the one you configured** - the "require a code" option looked like it was enforcing something it wasn't. Fixed: entering the wrong (or no) code now raises a validation error instead of silently succeeding. Covered by 4 new tests in `tests/test_alarm_control_panel.py`, including a regression test that specifically fails against the old (unfixed) behavior.
- **`lock.py` referenced an undefined name** (`CodeFormat`, `F821`): never imported, only survived because `from __future__ import annotations` makes type annotations lazy. `alarm_control_panel.py` already imports this correctly from `homeassistant.components.alarm_control_panel`; `lock.py` was just missing the same import. Not a live runtime bug (annotations are never evaluated), but a real static-analysis gap - fixed.

### Changed
- **`camera_api.py`: `_get` renamed to `get`, and a proper `owns_session` property added.** Both were being accessed from outside `AlarmCameraSession` already (by `__init__.py` and `camera.py`), so the leading underscore was misleading rather than enforcing real encapsulation. No behavior change, just properly public names for what were already effectively public interfaces.
- **`camera_api.py`: the three silent `except Exception: continue` blocks in session/ajax-key/MFA-cookie candidate extraction now log at debug level** instead of swallowing failures with zero trace. Still tries the next candidate on any failure (unchanged behavior) - just no longer invisible when everything fails.
- **`__init__.py`: extracted the pyalarmdotcomajax-location diagnostic check into its own sync function**, since it's pure path-string manipulation with no real async/await need - was flagged as doing blocking-style calls inside an async function.
- Minor control-flow clarity fixes in `hub.py` (moving a success-path `return` into an `else` block; `contextlib.suppress` instead of `try/except/pass` for a cancellation) - no behavior change.
- Removed one genuinely unused variable in `binary_sensor.py`.

### CI / tooling
- **This is the release where `pre-commit` actually completes a full run for the first time** - every previous run died at a Python-interpreter-discovery error before ever reaching the linters. Everything below was invisible until now, not new debt:
  - Fixed a real mypy config gap: `explicit_package_bases`/`mypy_path` were never set, causing "source file found twice under different module names" once mypy could actually run against the vendored package.
  - Fixed mypy's `python_version` setting (still `3.13`, causing a hard parse failure against Home Assistant's own 3.14-only syntax) and removed a stale external `pyalarmdotcomajax` dependency from the mypy hook's config, left over from before vendoring.
  - Fixed `codespell`'s exclusion path for vendored JSON:API files, silently broken by the `_pyalarmdotcomajax` rename.
  - Standardized on Python 3.14 throughout `.pre-commit-config.yaml` and its workflow, matching what `homeassistant>=2026.7.1` actually requires - previously mixed 3.13/3.14 pins were fighting each other.
  - Added scoped `ruff` ignores with documented reasoning: `S101`/`SLF001` for test files (assert and mock-attribute setup are normal there), `A002`/`A004`/`FBT001` for the vendored third-party library (not ours to restyle), and `E402` specifically for `__init__.py` (its `sys.path` shim must run before the imports that depend on it - intentional, not an oversight).
  - Deliberately, explicitly opted out of PEP 695 generic syntax modernization (`UP046`/`UP047`) for now - purely cosmetic, zero runtime difference, but converting 14 class declarations correctly needs live `mypy` verification this environment can't fully provide. Tracked as a real future PR, not left as unexplained lint noise.
  - **Added `custom_components/__init__.py` as a marker file.** Without it, mypy's directory-walk stopped at `alarmdotcom/` (which has its own `__init__.py`) while `explicit_package_bases`/`mypy_path` separately resolved the same files through `custom_components/` - two valid module names for one file, causing "Source file found twice" errors that kept resurfacing for whichever file happened to be checked. Zero effect on how Home Assistant actually loads the integration.
  - **Found the real, complete fix for the `_pyalarmdotcomajax`-resolves-to-`Any` gap**, via `mypy --verbose` rather than guessing: every file under `custom_components/alarmdotcom/` actually resolves as bare `alarmdotcom.X` for mypy's purposes (not `custom_components.alarmdotcom.X`, despite import statements elsewhere suggesting otherwise). Three earlier attempts at a global fix (changing `mypy_path`, changing import statements two different ways) were tried and rejected because each one reintroduced a worse, sometimes fatal, module-resolution error. The actual fix is one clearly-commented `[[tool.mypy.overrides]]` block in `pyproject.toml`, using the confirmed real module names, rather than either scattering `# type: ignore` everywhere or continuing to guess at global config changes. `mypy` now reports zero issues across the full codebase (down from 57 errors when this cleanup started).
  - Fixed several genuinely real type-safety gaps surfaced once `mypy` could actually check the codebase for the first time: a `SensorSubtype._missing_` classmethod with an imprecise `cls` type, `camera.py` annotating a field as the `callback` decorator instead of the real `CALLBACK_TYPE`, five `self.bridge` null-safety gaps in `config_flow.py` (now explicit, documented `assert` statements - the flow's own step ordering already guaranteed these were set, this just makes it provable), and a `binary_sensor.py` return type that didn't account for `None` entries it could legitimately return.
  - **Fixed `taplo-lint`'s intermittent network failures** - the actual cause was an inline `#:schema` directive in `.taplo.toml` forcing an external fetch to json.schemastore.org on every run, confirmed by reproducing the failure locally (where it manifested differently - a TLS cert error rather than CI's JSON-parsing mismatch - proving it really was an unreliable external dependency, not a config problem). Removed the directive and added `--no-schema` to the hook as defense-in-depth.
  - Fixed a real unused-variable bug in `scripts/sync_versions.py`, surfaced once `ruff` could run cleanly enough to reach it.
- Added `tests/test_alarm_control_panel.py` (4 tests covering the arm-code fix above).

## 2026.7.7.2b0 (beta)

### Fixed
- **Duplicate config entries were not prevented** (found while adding test coverage, not previously reported): `config_flow.py` set the unique ID for a system via `async_set_unique_id()`, but never actually called `_abort_if_unique_id_configured()` afterward. In practice this meant nothing stopped the same Alarm.com system from being added as a second, separate config entry - the unique ID was being set but never enforced. Fixed: adding a system that's already configured now correctly aborts with `already_configured`, the same as any other Home Assistant integration. Does not affect reauth (a matching unique ID during reauth is expected and still works normally).

### Added
- **First real automated test suite** (`tests/`), wired into CI via `.github/workflows/tests.yaml`:
  - `test_config_flow.py` - the initial login step, all three login failure modes (`cannot_connect`/`invalid_auth`/`unknown`), the `must_enable_2fa` abort, OTP method selection (including the auto-skip-when-only-authenticator-app-is-enabled case), OTP submission (including invalid code), the duplicate-system abort (see Fixed above), and both steps of the options flow.
  - `test_init.py` - the setup/unload lifecycle: successful setup, auth failure correctly triggering reauth, connection failure correctly triggering a retry (not a hard failure), and unload correctly closing both the hub and the camera session.
  - 17 tests, currently covering config flow comprehensively and the core setup/teardown lifecycle. Platform files (climate, sensors, camera, etc.), the bypass/unbypass services, and hub.py's websocket reconnect logic aren't covered yet.

## 2026.7.7.1b0 (beta)

### Changed
- **Vendored `pyalarmdotcomajax` renamed to `_pyalarmdotcomajax`** (`custom_components/alarmdotcom/_pyalarmdotcomajax/`), and every import updated to match. This is a deliberate, collision-proof name: no legitimate PyPI package can use a leading underscore, so this can never again share a name with any pip-installed package - including the leftover pip-installed `pyalarmdotcomajax` some of you will have from before `2026.7.6.1b0`. Previously, if the vendored copy were ever missing or misconfigured, Python could silently fall back to a stale pip-installed copy of the same name instead of failing - this is exactly what surfaced during beta testing of `2026.7.6.1b0`, where a leftover `2026.5.3` copy silently satisfied the import when the vendored folder was renamed away for testing. With the rename, that fallback is no longer possible: if `_pyalarmdotcomajax` isn't on the path, importing it can only raise `ModuleNotFoundError`, never silently resolve to the wrong thing.
- No functional/behavioral changes beyond the rename itself and the fixes below, carried over from unreleased work on top of `2026.7.6.1b0`:
  - Startup now logs which copy of the library loaded (version + file path), and warns (rather than silently continuing) if it's not the expected bundled copy.
  - Camera `get_stream_info` raw-response logging - which included live, unexpired session credentials (`janusToken`, `cameraAuthToken`, `signallingServerToken`, TURN credentials) and fired every 20-30 seconds per camera - is now off by default regardless of the integration's general debug-logging state. Opt in via `configuration.yaml`:
    ```yaml
    logger:
      logs:
        custom_components.alarmdotcom.camera_api.raw_responses: info    # redacted summary
        custom_components.alarmdotcom.camera_api.raw_responses: debug   # full raw response
    ```

### Beta notice
Continuing beta testing of the vendoring change from `2026.7.6.1b0`. Please report any errors on first startup (check **Settings → System → Logs** for anything mentioning `alarmdotcom` or `_pyalarmdotcomajax`) or anything that previously worked and now doesn't.

## 2026.7.6.1b0 (beta)

### Changed
- **`pyalarmdotcomajax` is now vendored directly in this repo** (`custom_components/alarmdotcom/pyalarmdotcomajax/`) instead of installed via a `git+` dependency in `manifest.json`. This eliminates the `git+` URL that blocked full HACS/hassfest compliance, and removes the need to coordinate version bumps across two separate repos for every fix. The library's own runtime dependencies (`mashumaro`, `phonenumbers`, `pyhumps`, `typer`) are now declared directly in this integration's `manifest.json`.
- No functional/behavioral changes from `2026.7.6` — this release is purely a packaging change. If you notice anything different at runtime (not just on first install/restart), please open an issue.

### Beta notice
This is a **pre-release** for testing the vendoring change specifically. Please report:
- Any errors on first startup after updating (check **Settings → System → Logs** for anything mentioning `alarmdotcom` or `pyalarmdotcomajax`)
- Anything that previously worked and now doesn't

If you don't need to help test this, wait for the next stable release instead.

### Known issue: leftover pip-installed `pyalarmdotcomajax`
Updating to this release does **not** remove the previous `pyalarmdotcomajax` package that was installed via the old `git+` dependency — Home Assistant's dependency installer only adds packages a `manifest.json` currently requires, it doesn't remove ones that used to be required. This leftover is harmless (the integration's own `sys.path` handling ensures the bundled copy is what actually loads), but if you want to confirm this or clean it up:
- On startup, check **Settings → System → Logs** for a line like `pyalarmdotcomajax <version> loaded from the bundled copy: ...`. If you instead see a **warning** saying it loaded from an unexpected location, something's wrong — please open an issue with that log line.
- To remove the leftover package (optional, cosmetic only): `pip uninstall pyalarmdotcomajax` from a shell with access to Home Assistant's Python environment.

## 2026.7.6

### Fixed
- **Black screen on iPhone/iPad/Safari with alarm-webrtc-card** (#38): The SDP offer from Alarm.com's WebRTC signaling can carry an H.264 `profile-level-id` that Apple's hardware decoder accepts without error but never actually renders — video stayed black with nothing surfaced anywhere in the pipeline, while Chrome and Android were unaffected. Root cause and initial fix identified by @Raul-7-7; the version shipped here generalizes it further based on mixed results reported in the thread: it matches *any* `profile-level-id` value (not just the one literal value seen on one test camera, which silently did nothing for other camera models), covers macOS Safari in addition to iOS (some users only saw the failure in Safari on Mac, not iOS), and patches both the legacy and Janus/proxy SDP code paths (the original fix only covered the legacy path). The offer is patched to `profile-level-id=42e01f` (Baseline Profile, Level 3.1) before `setRemoteDescription()`, which is the profile most consistently supported by Apple's decoders.
- **"Smart arming" seems to break the integration / state stops updating until reload** (#42): Not actually related to Smart Arming specifically — any state change could go unreflected in Home Assistant indefinitely (arm/disarm from the Alarm.com app, from HA itself, or from automations), correcting only after a full integration reload. Root cause was in `pyalarmdotcomajax`: the periodic 5-minute "safety net" poll (meant to catch state missed by a dropped WebSocket event) called `fetch_full_state()`, which silently did nothing on every call after the first — no error, no log line. Fixed in `pyalarmdotcomajax` 2026.7.6 with a new `refresh_all_resources()` method that actually re-fetches and re-publishes state every time it runs. Bumped dependency pin accordingly.

## 2026.7.5

### Fixed
- **OTP "Failed to Connect" still occurring after 2026.5.3 (reopened #21)**: The 2026.5.3 fix in `pyalarmdotcomajax` turned out to be a regression, not a fix — it checked for the MFA cookie before `trustTwoFactorDevice` ran, but Alarm.com reliably sets that cookie on the *trust* response, not the verify response. Since HA's config flow always provides a device name, this made the failure happen on every login. There was also a second, independent bug: aiohttp only exposes cookies from the last response in a redirect chain, so the cookie could be invisible even when present in the redirect history. Both fixed upstream in `pyalarmdotcomajax` 2026.7.5 (contributed by @jsight, confirmed independently by @lwimble). Bumped dependency pin accordingly.
- **Thermostat still shows only one temperature bar in auto mode** (#22): The 2026.5.3 fix corrected `target_temperature_high_fn`/`target_temperature_low_fn`, but `target_temperature_fn` (the single-setpoint attribute) was still inferring and returning a heat or cool setpoint while in `AUTO` state. Home Assistant's climate entity model treats `temperature` and the `target_temperature_high`/`target_temperature_low` pair as mutually exclusive — populating both at once caused the frontend to keep falling back to a single-setpoint control instead of the dual-bar range control. Fix: `target_temperature_fn` now returns `None` while in `AUTO` state, matching the high/low callbacks.
- **Bypassing sensors, resource ID undiscoverable** (#14): Bypass/unbypass services worked but required finding the Alarm.com resource ID via a Developer Tools -> Template lookup. The sensor entity now exposes `resource_id` as a plain attribute, and the bypass/unbypass service handlers now raise `ServiceValidationError`/`HomeAssistantError` instead of silently logging a warning and returning on failure.

### Dependency
- Updated `pyalarmdotcomajax` to `2026.7.5`, which fixes the OTP device-trust ordering regression and MFA/AFG cookie capture across redirects.

## 2026.5.3

### Fixed
- **Alarm panel state not updating on push events** (#20, #23): The alarm control panel entity was writing state updates to `self.alarm_state` — a plain instance attribute that Home Assistant never reads — instead of `self._attr_alarm_state`. Every websocket push event was silently discarded, so state only ever updated via the 5-minute polling fallback. Users would see delays of 10+ minutes or no update at all after arming/disarming at the keypad. Fix: corrected the attribute name in `update_state()`.
- **Thermostat shows only one temperature bar in auto mode** (#22): The `target_temperature_high_fn` and `target_temperature_low_fn` callbacks returned the cool and heat setpoints in all non-OFF states. Because both values were always non-`None`, Home Assistant rendered a range control even in HEAT/COOL mode — but with both bars collapsed to a single point, producing the "one yellow bar" symptom. Fix: high/low callbacks now return `None` unless the thermostat is in `AUTO` state, so HA renders a single-target slider in HEAT/COOL and a proper range control in AUTO/HEAT_COOL.
- **`supported_features` stale after mode change** (#22): `update_state()` was not refreshing `_attr_supported_features` on websocket events. If a thermostat switched from AUTO to HEAT/COOL at the panel, the `TARGET_TEMPERATURE_RANGE` flag would remain set in HA indefinitely. Fix: `supported_features` is now refreshed on every state update event.
- **OTP "Failed to Connect" on SMS and email** (#21): Handled by updated `pyalarmdotcomajax` dependency. The MFA cookie was being checked after the device-trust registration step rather than immediately after OTP verification, causing a spurious failure when Alarm.com set the cookie on the verify response.
- **`Task exception was never retrieved` log spam from imageSensors** (#23): On every websocket reconnect, the image sensor controller attempted a refresh and received a 423 (Not Authorized) from Alarm.com for accounts without that feature. The unhandled exception produced repeated errors in the HA log. Fixed in updated `pyalarmdotcomajax` — the base controller now catches 423 on reconnect refresh and logs it at DEBUG level only.

### Dependency
- Updated `pyalarmdotcomajax` to `2026.5.3`, which fixes OTP submission failures, makes device-trust registration best-effort, and silences repeated 423 log errors from unsupported resource types on reconnect.

---

## 2026.4.22

### Fixed
- Fixed thermostat entity writes so heat and cool setpoints can be updated together
- Fixed thermostat fan mode writes that used duration `0` for auto or indefinite modes
- Fixed arm night feature detection when Alarm.com returns nested arming option combinations
- Fixed controller resource parsing so one bad device payload no longer breaks an entire refresh
- Fixed sensor parsing when `open_closed_status` is returned as `null`
- Fixed thermostat parsing by using concrete enum types for thermostat state fields

### Improved
- Improved partition command errors so they report the command that failed
- Updated Home Assistant dependency pin to `pyalarmdotcomajax` `2026.4.22`

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
