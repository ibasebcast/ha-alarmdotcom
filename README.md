# Alarm.com for Home Assistant

A maintained Home Assistant custom integration for Alarm.com with support for:

- Alarm panel control
- Contact, motion, water, freeze, and other sensors
- Locks, lights, covers, valves, and thermostats
- Diagnostic entities
- Camera entities with Alarm.com web-session based live-view support

This integration uses `pyalarmdotcomajax` for the core Alarm.com system integration and a browser-style Alarm.com web session for camera access, because Alarm.com's public-facing video API behavior is inconsistent across accounts and camera models.

## Installation

### HACS

1. Open **HACS**.
2. Go to **Integrations**.
3. Open the menu in the top right and choose **Custom repositories**.
4. Add your repository URL:

```text
https://github.com/ibasebcast/ha-alarmdotcom
```

5. Select **Integration** as the category.
6. Install **Alarm.com**.
7. Restart Home Assistant.

### Manual

1. Copy `custom_components/alarmdotcom` into your Home Assistant `config/custom_components/` folder.
2. Copy `www/alarm-webrtc-card.js` into your Home Assistant `config/www/` folder.
3. Restart Home Assistant.

## First-time setup

1. Go to **Settings → Devices & Services**.
2. Click **Add Integration**.
3. Search for **Alarm.com**.
4. Enter your Alarm.com username and password.
5. If your account uses two-factor authentication, complete the OTP flow.

After setup, Home Assistant should create your Alarm.com entities automatically.

## Cameras

Camera entities are discovered automatically from your Alarm.com account. They will appear as normal Home Assistant camera entities.

### Start a live session

A live stream session is established when the camera is turned on. You can do that from **Developer Tools → Actions**:

```yaml
action: camera.turn_on
target:
  entity_id: camera.front_door
```

You can stop the cached live session with:

```yaml
action: camera.turn_off
target:
  entity_id: camera.front_door
```

### Lovelace card

This repository includes `www/alarm-webrtc-card.js`.

Add it in **Settings → Dashboards → Resources** as:

```text
URL: /local/alarm-webrtc-card.js
Type: JavaScript Module
```

Then add a manual card like this:

```yaml
type: custom:alarm-webrtc-card
entity: camera.front_door
name: Front Door
```

### Snapshot support

Snapshot support is included as a best-effort fallback. Alarm.com uses inconsistent snapshot endpoints across some accounts and camera models, so live view is the primary supported camera mode.

## Notes

- Cameras use an Alarm.com web session instead of relying only on the generic video API.
- Some camera models and account configurations may still behave differently because Alarm.com changes server behavior without notice.
- If your camera entities appear but live view does not start, remove and re-add the dashboard resource for the custom card, then restart Home Assistant.

## Troubleshooting

### Cameras do not show up

- Restart Home Assistant after initial setup.
- Confirm your Alarm.com account can see cameras in the Alarm.com website.
- Check the Home Assistant logs for `Failed to fetch Alarm.com camera list`.

### OTP or authentication issues

- Reconfigure the integration from **Settings → Devices & Services**.
- Make sure your Alarm.com account can log in through the website.

## Supported devices

| Device Type  | Supported |
| --- | --- |
| Alarm Panel | Yes |
| Sensors | Yes |
| Locks | Yes |
| Lights | Yes |
| Garage Doors / Covers | Yes |
| Thermostats | Yes |
| Cameras | Yes |

## Disclaimer

This is an unofficial integration and is not affiliated with Alarm.com. Alarm.com can change their web platform or APIs at any time, which may require updates to this integration.
