# Maintained Fork

This repository is an actively maintained fork of the original **Alarm.com for Home Assistant** integration.

The goal of this fork is to maintain compatibility with modern Home Assistant releases while continuing development of the Alarm.com integration as the Home Assistant platform evolves.

Recent Home Assistant updates introduced architectural changes that affect older integrations. This fork adapts the integration to those changes and ensures continued functionality, including compliance with the Home Assistant device registry enforcement requirements introduced in Home Assistant 2025.12.

Repository and issue tracker:

https://github.com/ibasebcast/ha-alarmdotcom

Community feedback, testing, and contributions are welcome.

---

# Overview

This custom integration allows Home Assistant to interface with [**Alarm.com**](https://Alarm.com) using the Alarm.com web platform.

The integration focuses primarily on Alarm.com security system functionality and requires an Alarm.com service package that includes security system support.

Because this integration communicates with Alarm.com cloud services, functionality may change if Alarm.com modifies their platform.

---
> [!WARNING]
> # Safety Notice
>
>This integration is designed for **convenience and automation**, but it should **not be relied upon for safety-critical functions.**
>
>Reasons include:
>
>1. This integration communicates with Alarm.com using unofficial endpoints.
>2. Alarm.com status updates may take time to propagate.
>3. Home Assistant automations may introduce unintended behavior.
>4. This code is community developed and may contain bugs.
>
>For critical alerts such as:
>
>* Break-ins
>* Fire
>* Carbon monoxide
>* Water leaks
>* Freeze warnings
>
>You should rely on **Alarm.com's official monitoring services and mobile applications.**
>
>Where possible, use **locally controlled Home Assistant integrations** for automation. Local integrations continue functioning during internet outages, while this integration requires cloud communication.

> [!TIP]
> Some alarm.com devices use Z-Wave, so if you have a Z-Wave dongle then you can move the devices from alarm.com to Home Assistant's [native Z-Wave integration](https://www.home-assistant.io/integrations/zwave_js/)
---

# How to install and setup the integration

## Installation

### Install Using HACS (Recommended)

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

## Prerequisites
Before setting up this integration you need the following

1. An active alarm.com account
2. Know the login for the alarm.com and be able to fill the One-Time Password
3. Have a device connected to alarm.com

## Setup

When adding the integration you will be prompted for:

| Parameter         | Required | Description                                             |
| ----------------- | -------- | ------------------------------------------------------- |
| Username          | Yes      | Alarm.com account username                              |
| Password          | Yes      | Alarm.com account password                              |
| One-Time Password | Maybe    | Required if your account uses two-factor authentication |

---

# Integration Options

These settings can be modified later using the **Configure** button on the Alarm.com integration card.

| Parameter      | Description                                                 |
| -------------- | ----------------------------------------------------------- |
| Code           | Code required for disarming or unlocking via Home Assistant |
| Force Bypass   | Bypass open zones when arming                               |
| No Entry Delay | Skip entry delay sensors                                    |
| Silent Arming  | Suppress panel beeps when arming                            |

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

# Supported Devices

| Device Type  | Actions                               | Status | Low Battery | Malfunction | Notes                                                                     |
| ------------ | ------------------------------------- | ------ | ----------- | ----------- | ------------------------------------------------------------------------- |
| Alarm System | Arm Away, Arm Stay, Arm Night, Disarm | ✔      | ✔           | ✔           |                                                                           |
| Garage Door  | Open, Close                           | ✔      | ✔           | ✔           | See MyQ / Security+ 3.0 note below                                       |
| Gate         | Open, Close                           | ✔      | ✔           | ✔           | See MyQ note below                                                        |
| Light        | On / Off / Brightness                 | ✔      | ✔           | ✔           |                                                                           |
| Lock         | Lock, Unlock                          | ✔      | ✔           | ✔           |                                                                           |
| Sensor       | None                                  | ✔      | ✔           | ✔           | Contact sensors will not report repeated changes within a 3 minute window |
| Thermostat   | Heat, Cool, Auto, Fan                 | ✔      | ✔           | ✔           | Fan-only mode runs for the maximum duration supported by Alarm.com        |
| Camera       | Live WebRTC stream, Snapshot          | ✔      | -           |-           | Requires the `www/alarm-webrtc-card.js` Lovelace card                    |

> [!NOTE]
> **Garage Doors (MyQ):** MyQ garage doors don't natively integrate with Home Assistant, but they do through Alarm.com, making this integration useful if that's what you have. A dedicated local solution like [RATGDO](https://paulwieland.github.io/ratgdo/) is generally preferable for local control.
>
>  However, if your opener uses **Security+ 3.0** (newer Chamberlain and LiftMaster models), no local solution currently supports it. This integration may be your only path to Home Assistant control.
>
> **Gates (MyQ):** MyQ gates use Security+ 2.0 with dry-contact wiring, there is no Security+ 3.0 gate. RATGDO and similar adapters can work with them, see the [RATGDO wiring guide](https://ratcloud.llc/pages/wiring) for specifics.

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

## Removing This Integration

Removing this integration is the same as most HACS integrations:

- Go to **Settings** → **Devices & Services**
- Find the **Alarm.com** integration card
- Click the **three-dot menu** on the card and select **Delete**
- Repeat for any additional Alarm.com entries
- Go to HACS, select the three-dot menu for this integration, then select **Remove**.
- Then restart Home Assistant to clear the cache

---

# Development Status

This integration is under active maintenance.

Recent improvements include:

* Restored compatibility with modern Home Assistant releases
* Fixed entities becoming unavailable
* Updated device registry usage to comply with upcoming Home Assistant requirements
* Improved websocket connection reliability

---

# Project Roadmap

Planned areas of development include:

* Expanded device coverage across the Alarm.com ecosystem
* Improved websocket reliability and reconnection handling
* Expanded automation and scene support
* Additional device diagnostics and status reporting
* Continued compatibility updates for new Home Assistant releases
* Maybe submission of this custom integration as a core integration

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
* Diagnostics of your alarm.com config entry

---

# Maintainer

This integration is currently maintained by:

**Chris Pulliam**
GitHub: https://github.com/ibasebcast

The maintainer of this fork operates Alarm.com systems professionally and has access to multiple Alarm.com environments, allowing testing across a wider variety of devices and system configurations.

The goal of this project is to ensure the Alarm.com ecosystem remains usable within Home Assistant as the platform evolves.

This fork exists to provide:

* Continued compatibility with new Home Assistant versions
* Expanded device support
* Improved reliability and error handling
* Long-term maintenance of the integration

---

# License

This project is licensed under the MIT License.

See the **LICENSE** file for details.

<!--
  DEVELOPER NOTE: What needs to happen before submitting this as a HA core integration.

  ## What to exclude from the initial PR

  HA's submission guidelines for new integrations require a focused first PR:

  - Limit to a single platform (see rollout order below)
  - Remove all custom service actions: bypass_sensor, unbypass_sensor,
    set_auto_off, cancel_auto_off
  - Remove diagnostics.py
  - Remove reauthentication and reconfiguration flows
  - Remove dynamic-devices and stale-devices logic
    (cleanup_orphaned_entities_and_devices in util.py)

  Once the initial PR is accepted, add features and additional platforms back
  one PR at a time.

  ## Camera platform blocker

  The camera platform cannot ship in a core integration PR in its current form.
  It requires a custom Lovelace card (www/alarm-webrtc-card.js) that cannot be
  bundled with a core integration, HA core only ships frontend components that
  are merged into the separate HA frontend repository.

  Options before camera can go into a core PR:

  (a) Exclude camera.py from the initial PR entirely and resubmit as a
      follow-up after the base integration is accepted. Simplest path.

  (b) Still-image-only redesign: return snapshots only from the camera entity,
      which works with HA's built-in Picture Entity card. No custom card needed,
      but streaming would be lost.

  (c) Implement async_handle_async_webrtc_offer() so the stream works with
      HA's built-in WebRTC camera card that ships with HA core. This is the
      correct long-term path and would make camera fully first-class. If this
      is done before the core PR, camera priority moves to 3rd or 4th.

  ## Recommended platform rollout order

  Add one platform per PR after the initial alarm_control_panel PR is accepted.

  1.  alarm_control_panel  - core product; the alarm is the whole point
  2.  binary_sensor        - doors, windows, motion; immediate automation value
  3.  lock                 - security-adjacent, high demand
  4.  cover                - garage doors and gates (indirect MyQ path)
  5.  sensor               - battery summaries and trouble-condition reporting
  6.  button               - panel debug and test actions
  7.  light                - Alarm.com-connected lights
  8.  climate              - thermostats; similar reasoning to lights
  9.  valve                - less common Alarm.com device type
  10. camera               - important for security but blocked on custom card
                             (see above; moves to 3rd–4th if card issue resolved)
                             
 ## Also check the quality_scale.yaml for other notes                          
-->
