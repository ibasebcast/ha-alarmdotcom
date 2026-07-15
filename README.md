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
# Data Updates

This integration's IoT class is cloud push, so when a change happens on alarm.com home assistant is notified about it. As a backup this integration also polls alarm.com for state changes every 5 minutes.

Because this integration is cloud push, that means every actions goes through alarm.com's cloud and an active internet connection is required for this integration to work.

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
-->
