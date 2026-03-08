---

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
| Light        | On / Off / Brightness                 | ✔      | ✔           | ✔           |                                                                           |
| Lock         | Lock, Unlock                          | ✔      | ✔           | ✔           |                                                                           |
| Sensor       | None                                  | ✔      | ✔           | ✔           | Contact sensors will not report repeated changes within a 3 minute window |
| Thermostat   | Heat, Cool, Auto, Fan                 | ✔      | ✔           | ✔           | Fan-only mode runs for the maximum duration supported by Alarm.com        |

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

| Parameter      | Description                                                 |
| -------------- | ----------------------------------------------------------- |
| Code           | Code required for disarming or unlocking via Home Assistant |
| Force Bypass   | Bypass open zones when arming                               |
| No Entry Delay | Skip entry delay sensors                                    |
| Silent Arming  | Suppress panel beeps when arming                            |

Some Alarm.com providers may restrict combinations of these options.

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
* Camera and image sensor support
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
