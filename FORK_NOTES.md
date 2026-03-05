# Fork notes

This repo is a fork of the upstream Alarm.com Home Assistant integration.

## What was changed in this fork

- Fixed Device Registry `via_device` handling so Home Assistant 2025.12+ will not break when enforcing that `via_device` must reference an existing device.
- Updated manifest and constants to use fork owned links (links are preconfigured for https://github.com/ibasebcast/ha-alarmdotcom).

## Publish steps (GitHub)

1) Create a new GitHub repo, example name: `ha-alarmdotcom`

2) Replace placeholders:

- `custom_components/alarmdotcom/const.py`
  - `ISSUE_URL`

- `custom_components/alarmdotcom/manifest.json`
  - `documentation`
  - `issue_tracker`
  - `codeowners`

3) Initialize git and push

```bash
git init
git add .
git commit -m "Initial fork"
git branch -M main
git remote add origin https://github.com/<YOUR_GITHUB_USERNAME>/ha-alarmdotcom.git
git push -u origin main
```

## HACS install (custom repository)

- HACS, Integrations, three dots menu, Custom repositories
- Add your repository URL
- Category: Integration

Then install and restart Home Assistant.

## Releases

This repo includes a GitHub Actions workflow that publishes a GitHub Release when you push a tag that starts with `v`.

Example:

```bash
git tag v4.0.1-ibasebcast.1
git push origin v4.0.1-ibasebcast.1
```

If you want HACS to track releases, keep the `manifest.json` version aligned with your tag naming.
