# Maintained Fork

This repository is an actively maintained fork of the original **Alarm.com for Home Assistant** integration.

The goal of this fork is to maintain compatibility with modern Home Assistant releases while continuing development of the Alarm.com integration as the Home Assistant platform evolves.

Recent Home Assistant updates introduced architectural changes that affect older integrations. This fork adapts the integration to those changes and ensures continued functionality, including compliance with the Home Assistant device registry enforcement requirements introduced in Home Assistant 2025.12.

Repository and issue tracker:

https://github.com/ibasebcast/ha-alarmdotcom

The maintainer of this fork operates Alarm.com systems professionally and has access to multiple Alarm.com environments, allowing testing across a wider variety of devices and system configurations.

Community feedback, testing, and contributions are welcome.

---

# Maintainer

This integration is currently maintained by:

**Chris Pulliam**
GitHub: https://github.com/ibasebcast

The goal of this project is to ensure the Alarm.com ecosystem remains usable within Home Assistant as the platform evolves.

This fork exists to provide:

* Continued compatibility with new Home Assistant versions
* Expanded device support
* Improved reliability and error handling
* Long-term maintenance of the integration

---

# Overview

This custom component allows Home Assistant to interface with **Alarm.com** using the Alarm.com web platform.

The integration focuses primarily on Alarm.com security system functionality and requires an Alarm.com service package that includes security system support.

Because this integration communicates with Alarm.com cloud services, functionality may change if Alarm.com modifies their platform.

---

# Safety Notice

This integration is designed for **convenience and automation**, but it should **not be relied upon for safety-critical functions.**

Reasons include:

1. This integration communicates with Alarm.com using unofficial endpoints.
2. Alarm.com status updates may take time to propagate.
3. Home Assistant automations may introduce unintended behavior.
4. This code is community developed and may contain bugs.

For critical alerts such as:

* Break-ins
* Fire
* Carbon monoxide
* Water leaks
* Freeze warnings

You should rely on **Alarm.com's official monitoring services and mobile applications.**

Where possible, use **locally controlled Home Assistant integrations** for automation. Local integrations continue functioning during internet outages, while this integration requires cloud communication.

---

# Supported Devices

| Device Type  | Actions                               | Status | Low Battery | Malfunction | Notes                                                                     |
| ------------ | ------------------------------------- | ------ | ----------- | ----------- | ------------------------------------------------------------------------- |
| Alarm System | Arm Away, Arm Stay, Arm Night, Disarm | ✔      | ✔           | ✔           |                                                                           |
| Garage Door  | Open, Close                           | ✔      | ✔           | ✔           |                                                                           |
| Gate         | Open, Close                           | ✔      | ✔           | ✔           |                                                                           |
| Light        | On / Off / Brightness                 | ✔      | ✔           | ✔           | Supports auto-off timers - see below                                     |
| Lock         | Lock, Unlock                          | ✔      | ✔           | ✔           | Tracks who unlocked via keypad code - see below                          |
| Sensor       | None                                  | ✔      | ✔           | ✔           | Contact sensors will not report repeated changes within a 3 minute window |
| Thermostat   | Heat, Cool, Auto, Fan                 | ✔      | ✔           | ✔           | Fan-only mode runs for the maximum duration supported by Alarm.com        |
| Camera       | Live WebRTC stream, Snapshot          | ✔      | —           | —           | Requires the `www/alarm-webrtc-card.js` Lovelace card                    |

---

# Supported Sensor Types

| Sensor Type             | Description                    |
| ----------------------- | ------------------------------ |
| Contact                 | Doors and windows              |
| Freeze                  | Temperature threshold sensors  |
| Glass Break / Vibration | Standalone or panel-integrated |
| Motion                  | Motion detection sensors       |
| Vibration Contact       | Doors, safes, windows          |
| Water                   | Leak sensors                   |

Alarm.com may use different internal identifiers for some sensors.
If a supported sensor does not appear in Home Assistant, please open an issue.

https://github.com/ibasebcast/ha-alarmdotcom/issues

---

# Installation

## Install Using HACS (Recommended)

1. Open **HACS**
2. Navigate to **Integrations**
3. Click the **three-dot menu**
4. Select **Custom repositories**
5. Add the repository:

```
https://github.com/ibasebcast/ha-alarmdotcom
```

6. Select **Integration** as the category
7. Click **Add**
8. Install **Alarm.com**
9. Restart Home Assistant

After restarting:

**Settings → Devices & Services → Add Integration → Alarm.com**

## Removal

1. **Settings → Devices & Services → Alarm.com**
2. Click the three-dot menu on the integration card → **Delete**
3. If installed via HACS and you want to remove the integration's files as well (not just the config entry), go to **HACS → Integrations → Alarm.com → three-dot menu → Remove**
4. If you added the WebRTC Lovelace card (`www/alarm-webrtc-card.js`), remove it from your dashboard resources (**Settings → Dashboards → three-dot menu → Resources**) and delete the file from your `www/` folder

Removing the integration also removes its entities and the devices they were attached to. It does not affect your Alarm.com account itself or any settings configured directly through Alarm.com's own app or website.

---

# Configuration

When adding the integration you will be prompted for:

| Parameter         | Required | Description                                             |
| ----------------- | -------- | ------------------------------------------------------- |
| Username          | Yes      | Alarm.com account username                              |
| Password          | Yes      | Alarm.com account password                              |
| One-Time Password | Optional | Required if your account uses two-factor authentication |

---

# Integration Options

These settings can be modified later using the **Configure** button on the Alarm.com integration card.

| Parameter                | Description                                                 |
| ------------------------- | ----------------------------------------------------------- |
| Code                      | Code required for disarming or unlocking via Home Assistant |
| Force Bypass              | Bypass open zones when arming                               |
| No Entry Delay            | Skip entry delay sensors                                    |
| Silent Arming             | Suppress panel beeps when arming                             |
| Activity Poll Interval    | See [Polling Intervals](#polling-intervals) below            |
| Full State Poll Interval  | See [Polling Intervals](#polling-intervals) below            |

Some Alarm.com providers may restrict combinations of these options.

---

# Services

This integration exposes the following services, callable from **Developer Tools → Actions**, automations, or scripts.

| Service                       | Purpose                                                          | Target                        |
| ------------------------------ | ----------------------------------------------------------------- | ------------------------------ |
| `alarmdotcom.bypass_sensor`    | Bypass a supported sensor (e.g. a door left open) for the current arm period | `resource_id` field (see the sensor entity's `resource_id` attribute), optional `partition_id` |
| `alarmdotcom.unbypass_sensor`  | Remove a bypass from a sensor                                    | Same as above                 |
| `alarmdotcom.set_auto_off`     | Schedule one or more lights to turn off after a duration - see [Auto-Off Timers](#auto-off-timers) below | Standard entity target picker, restricted to this integration's lights |
| `alarmdotcom.cancel_auto_off`  | Cancel a pending auto-off timer                                  | Same as above                 |

`bypass_sensor`/`unbypass_sensor` take a `resource_id`, not an `entity_id` - find this in the sensor entity's own `resource_id` attribute (Settings → Devices & Services → Alarm.com → the sensor entity → Attributes). `set_auto_off`/`cancel_auto_off` use Home Assistant's standard entity target selector instead, since they operate on lights specifically and Home Assistant already has a rich picker for that.

---

---

# Camera Support

This integration includes WebRTC live-streaming support for Alarm.com cameras.

## Setup

1. Copy `www/alarm-webrtc-card.js` from this repository to your Home Assistant `www/` folder.
2. Add it as a Lovelace resource:
   - Go to **Settings → Dashboards → Resources**
   - Click **Add Resource**
   - URL: `/local/alarm-webrtc-card.js`
   - Type: **JavaScript module**
3. Add the card to any Lovelace dashboard:

```yaml
type: custom:alarm-webrtc-card
entity: camera.your_camera_name
```

## How it works

When the card loads it calls the `camera.turn_on` service which fetches a fresh set of WebRTC tokens from Alarm.com. Tokens are refreshed automatically every 30 minutes in the background so the stream is always ready. If a token expires before the next scheduled refresh the card requests new tokens automatically.

Still image snapshots are also available, which means the camera will display a thumbnail in the Home Assistant media browser and picture-glance dashboard cards.

---

# Auto-Off Timers

Any light can be scheduled to turn off automatically after a duration, using the `alarmdotcom.set_auto_off` service - useful for things like "turn on for 30 minutes" without building a full automation for every light.

This is deliberately more capable than a plain automation using a "wait, then turn off" action:

* **Survives a Home Assistant restart.** The scheduled off-time is persisted. If Home Assistant was offline when a timer was due, the light turns off immediately on startup instead of the timer being silently lost; a timer still in the future is rescheduled for its exact remaining time.
* **The scheduled off-time is visible.** Every light with a pending timer shows it directly in its own `auto_off_at` attribute - no separate helper entity needed to check "how much time is left."
* **A summary sensor** ("Active Auto-Off Timers", found on the account's System device) shows how many timers are currently pending account-wide, with a `timers` attribute listing each affected light and its scheduled off-time.
* If a light is turned off some other way before its timer fires - manually, from the Alarm.com app, from an unrelated automation - the timer clears itself automatically.

**Example: turn on a light for one hour**

```yaml
action: alarmdotcom.set_auto_off
target:
  entity_id: light.front_porch
data:
  duration:
    hours: 1
```

**Example: automatically time out any of a group of lights whenever they're turned on**

```yaml
alias: Auto-off lights after 1 hour
triggers:
  - trigger: state
    entity_id:
      - light.front_porch
      - light.back_porch
      - light.garage
    to: "on"
actions:
  - action: alarmdotcom.set_auto_off
    target:
      entity_id: "{{ trigger.entity_id }}"
    data:
      duration:
        hours: 1
mode: queued
```

To cancel a pending timer early, call `alarmdotcom.cancel_auto_off` with the same target.

---

# Lock Unlock Attribution

Lock entities expose three additional attributes: `last_unlocked_by`, `last_unlock_method`, and `last_unlocked_at`.

This is sourced from Alarm.com's own activity history, polled roughly every 15 seconds - a genuinely separate data path from this integration's live state updates, since "who unlocked this" isn't part of the lock's ongoing state, only its history.

**Prerequisite:** the Alarm.com account/login used by this integration needs the **"Activity" read-only permission** enabled, or these attributes will never populate at all. Confirmed by a real user - this isn't documented anywhere by Alarm.com itself, so it's easy to miss if the integration's account was set up before this feature existed, or was scoped narrowly on purpose.

**Important limitation, confirmed directly from Alarm.com's own data, not a gap in this integration:** Alarm.com only attributes a keypad-code unlock to a specific person. Unlocking from the Alarm.com app, the web portal, or manually at the door is **not** attributed to anyone - `last_unlocked_by` correctly shows as unset for those, since Alarm.com itself doesn't know who performed them. Lights and switches have no equivalent - Alarm.com does not attribute those to a user at all under any circumstance.

**`last_unlocked_by` doesn't necessarily reflect the most recent unlock, and that's also not a bug.** Not every unlock method generates its own distinct, loggable Alarm.com event for every lock model - a manual/inside turn may not be logged at all on some hardware. When that happens, `last_unlocked_by` simply keeps showing whoever the last *keypad* unlock was attributed to, even after a more recent manual or remote unlock, since there's no newer event for the poller to ever see. **`last_unlock_method`** exists specifically to sidestep this: it reports `"keypad"`, `"manual"`, or `"remote"` for whatever the most recently *tracked* unlock actually was, so an automation can gate on "was this actually a keypad entry" directly, rather than relying on a name that might be stale.

**Example: a welcome-home announcement that varies by person, gated on method to avoid the staleness pitfall above**

```yaml
alias: Welcome home TTS
triggers:
  - trigger: state
    entity_id: lock.front_door
    attribute: last_unlocked_by
conditions:
  - condition: template
    value_template: "{{ trigger.to_state.attributes.last_unlock_method == 'keypad' }}"
actions:
  - action: tts.speak
    target:
      entity_id: tts.google_translate
    data:
      media_player_entity_id: media_player.living_room_speaker
      message: "Welcome home, {{ trigger.to_state.attributes.last_unlocked_by }}."
```

---

# Activity Feed

Beyond lock unlock attribution, this integration also fires a curated event on Home Assistant's event bus for other significant Alarm.com activity - arm/disarm, lock/unlock, and camera motion triggers - and keeps a short rolling list of the most recent ones on a **"Recent Activity"** sensor (found on the account's System device).

This uses the same underlying poll as lock unlock attribution - nothing extra to configure, no additional load on Alarm.com's servers.

**What's included by default**, and why the list is deliberately curated rather than exhaustive: real captured activity data showed roughly one event every 2-3 minutes during ordinary use, much of it genuinely noisy for automation purposes - every light interaction fires twice (a command event and a state-change event), motion and button presses fire constantly. Alarm.com does not attribute any of those to a specific person either (see [Lock Unlock Attribution](#lock-unlock-attribution) above), so they carry less unique automation value than the events below:

* System armed (any mode) or disarmed
* A lock locked or unlocked
* A camera detected motion/a person
* A garage door opened or closed

Garage door events specifically are cross-referenced against this account's known garage door devices (the same ones the garage door cover entity is built from) before being included - this is what lets them in while ordinary window/door sensors, which share the exact same event data shape, stay excluded as noise.

**Example: catch any curated event in an automation**

```yaml
alias: Log all significant Alarm.com activity
triggers:
  - trigger: event
    event_type: alarmdotcom_activity
actions:
  - action: logbook.log
    data:
      name: Alarm.com
      message: "{{ trigger.event.data.description }}"
```

Filter by `trigger.event.data.event_type_name` (e.g. `ArmedStay`, `DoorUnlocked`, `VideoCameraTriggered`) if you only want to react to specific kinds of activity.

---

# Polling Intervals

Two things are polled on a timer rather than arriving live over the websocket, and both are configurable via the **Configure** button on the Alarm.com integration card:

| Setting                       | Default    | What it affects                                                              |
| ------------------------------ | ---------- | ------------------------------------------------------------------------------ |
| Activity poll interval         | 15 seconds | How quickly lock unlock attribution and the activity feed reflect real events |
| Full state poll interval       | 5 minutes  | A safety net that re-syncs everything in case a websocket event was ever missed |

The activity poll interval in particular is worth understanding before turning it down further: it hits an entirely undocumented Alarm.com endpoint with no confirmed rate-limit information. The default of 15 seconds is a deliberate tradeoff for a prompt welcome-home automation experience, not a guarantee it's safe at any value - if you ever run into problems, this is the first thing worth dialing back up.

---

# Development Status

This integration is under active maintenance. **Version `2026.7.14.6`** is the current beta release. See `CHANGELOG.md` for the complete, detailed history - the highlights since the last stable release (`2026.7.9.3`):

### New features

* **Auto-off timers for lights** - see [Auto-Off Timers](#auto-off-timers) above. Survives Home Assistant restarts and exposes the scheduled off-time as an entity attribute, unlike a plain "wait then turn off" automation.
* **Lock unlock attribution** - see [Lock Unlock Attribution](#lock-unlock-attribution) above. `last_unlocked_by`/`last_unlock_method`/`last_unlocked_at` attributes on lock entities, sourced from Alarm.com's own activity history (an entirely undocumented endpoint, reverse-engineered and verified against real captured data before being relied on). Keypad-code unlocks are the only ones Alarm.com attributes to a name - `last_unlock_method` (added after real user feedback) reports the method itself (`keypad`/`manual`/`remote`) independent of whether a name is attached, since `last_unlocked_by` alone can remain stuck showing an earlier keypad user after a later, unattributed unlock.
* **A general activity feed** - see [Activity Feed](#activity-feed) above. A curated Home Assistant event (`alarmdotcom_activity`) fires for other significant activity (arm/disarm, lock/unlock, camera motion), plus a "Recent Activity" sensor with a short rolling history - built on the same poller as lock unlock attribution, no extra load added.
* **Configurable polling intervals** - see [Polling Intervals](#polling-intervals) above. Both the activity poll (default 15s) and the full-state safety-net poll (default 5min) can now be tuned via the **Configure** button, rather than being fixed constants - useful for dialing back the activity poll specifically, since it hits an undocumented endpoint with no confirmed rate limit.

### Fixed

* **`bypass_sensor`/`unbypass_sensor` crashed** (`'PartitionController' object has no attribute 'values'`) when called without an explicit `partition_id` - the auto-resolve-partition logic incorrectly treated a controller as dict-like when it's actually iterable directly, matching every other controller in this integration. There was previously no test coverage for either service at all; both are now covered, using a mock deliberately shaped like the real (iterable, not dict-like) controller so this exact class of bug can't slip through unnoticed again.

### Under the hood

* `AlarmBridge.get_activity_history()` - the first data source in this integration with no persistent state and no live websocket delivery; it has to be actively polled rather than subscribed to, which is a genuinely different architecture from every device platform this integration otherwise models. The poller (`ActivityFeedTracker`, originally `LockActivityTracker` before it grew beyond just locks) now also drives the general activity feed and reads its own interval from the options flow.
* **Garage door disambiguation for the activity feed** - garage door open/close now appears in the curated activity feed, cross-referenced against known garage door devices so ordinary window/door sensors (which share identical event data with a garage door) stay correctly excluded.
* Continued expansion of the automated test suite alongside every change above - 106 tests as of this release, `mypy`/`ruff` both clean.

<details>
<summary>Highlights from the <code>2026.7.9.3</code> stable release (click to expand)</summary>

### Security fix

**Arm/disarm code enforcement was silently broken.** If you configured a code to require for arming/disarming, entering *any* correctly-formatted code - not necessarily the one you set - would still successfully arm or disarm. This is now fixed and covered by automated regression tests. If you rely on the code requirement, you should update as soon as practical.

### New features

* **A diagnostics page** (Settings → Devices & Services → Alarm.com → Download diagnostics) - a downloadable snapshot of everything the integration knows about your account or a specific device, with all credentials and session tokens automatically redacted. Useful for troubleshooting and for attaching to bug reports without needing to dig through logs or worry about leaking a live camera token.
* **Account-wide low/critical battery count sensors** - two new entities that track how many devices currently report low or critical battery, with the specific device names available as an attribute, so you don't have to check every sensor individually.

### Bug fixes

* Two real bugs found while adding test coverage: duplicate config entries were never actually prevented, and a crash could occur in the reconnect-recovery path after enough failed connection attempts.
* Camera diagnostics were silently missing all camera data due to cameras using a different internal discovery path than every other device type - now fixed and verified against a real account with real cameras.
* Live camera session tokens were being written to Home Assistant's logs whenever debug logging was enabled - this is now off by default and opt-in only, and separately redacted anywhere else this data surfaces.
* Carried-forward fixes from `2026.7.6`: the iPhone/iPad/Safari black-screen camera issue, and a bug where entity state could silently stop updating until a full integration reload.

### Under the hood

* **Vendored the `pyalarmdotcomajax` API client directly into this repository** (see "Architecture Note" below) - this was previously a real HACS compliance blocker and a source of duplicated bug reports across two repos.
* **A real, automated test suite** now runs in CI on every push and pull request, covering config flow, setup/unload lifecycle, the arm-code security fix, diagnostics (including the redaction itself), and the new battery sensors.
* `mypy` now reports zero type errors across the entire codebase, for the first time - `ruff`, `codespell`, and `taplo` all pass cleanly as well.
* A preemptive fix for a Home Assistant deprecation that becomes a hard error in December 2026 (a config-entry reload pattern used during reauthentication), verified directly against Home Assistant's own source code before shipping.

</details>

---

# Architecture Note: Vendored `pyalarmdotcomajax`

As of `2026.7.6.1b0`, the `pyalarmdotcomajax` Alarm.com API client lives directly in this repository, instead of being installed separately via a `git+` URL in `manifest.json`. As of `2026.7.7.1b0`, it's vendored under the deliberately collision-proof name `_pyalarmdotcomajax` at `custom_components/alarmdotcom/_pyalarmdotcomajax/` (see below for why the name changed).

**Why:** `pyalarmdotcomajax` was previously a separate repository ([ibasebcast/pyalarmdotcomajax](https://github.com/ibasebcast/pyalarmdotcomajax)) that this integration depended on via a `git+` dependency. In practice, the two repos were never really independent — nearly every bug fix required a version bump in `pyalarmdotcomajax`, then a matching dependency-pin bump here, then a release of both. Bugs also frequently got reported in both repos as duplicates, since from a user's perspective it's one integration. On top of the coordination overhead, a `git+` dependency in `manifest.json` is a HACS/hassfest compliance issue, since HACS/hassfest strongly prefer plain PyPI-resolvable requirements.

**What changed:**
- The library's code (and its git history) now lives under `custom_components/alarmdotcom/_pyalarmdotcomajax/`. It's imported as `_pyalarmdotcomajax` (leading underscore), not `pyalarmdotcomajax`, deliberately: no legitimate PyPI package can use a leading underscore, so this name can never collide with a stray pip-installed `pyalarmdotcomajax` (e.g. one left over from before this vendoring change). Without that, a missing or broken vendored copy could silently fall back to a stale pip-installed copy instead of failing loudly - which is exactly what happened during beta testing of `2026.7.6.1b0`.
- `manifest.json` no longer has a `git+` requirement; it now lists the library's actual runtime dependencies directly (`mashumaro`, `phonenumbers`, `pyhumps`, `typer`, `beautifulsoup4`), which were previously pulled in transitively.
- The library's internal code is otherwise unchanged and still uses absolute imports internally (e.g. `from _pyalarmdotcomajax.controllers.users import ...`, updated from the original `pyalarmdotcomajax.` prefix as part of the rename). This integration's `__init__.py` adds the vendored directory to `sys.path` before anything imports it, so those imports keep resolving without needing every file in the library rewritten to relative imports.
- No functional/runtime behavior changes are intended by this move — it's a packaging change only.

**What this means going forward:**
- Bug reports and contributions related to the Alarm.com API client now belong in this repository, not a separate one.
- The standalone `pyalarmdotcomajax` repository is no longer the source of truth for this integration; see that repository's own README for its current status.

---

# Project Roadmap

Planned areas of development include:

* Expanded device coverage across the Alarm.com ecosystem
* Improved websocket reliability and reconnection handling
* Expanded automation and scene support
* Additional device diagnostics and status reporting
* Continued compatibility updates for new Home Assistant releases

Community testing and feedback help guide development priorities.

---

# Contributing

Issues and pull requests are welcome.

Please report bugs or feature requests here:

https://github.com/ibasebcast/ha-alarmdotcom/issues

When reporting issues include:

* Home Assistant version
* Integration version
* Relevant Home Assistant logs

---

# License

This project is licensed under the MIT License.

See the **LICENSE** file for details.
