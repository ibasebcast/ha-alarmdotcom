# Changelog

All notable changes to this project will be documented in this file.

## Unreleased

* No changes yet.

## 2026.3.20.1

### Added

* Integrated Alarm.com camera support into the main `alarmdotcom` integration
* Added browser-style camera session handling for live view
* Added bundled `alarm-webrtc-card.js` frontend card
* Added best-effort snapshot retrieval for supported camera models

### Changed

* Camera entities are now discovered automatically during setup
* Updated installation instructions for first-time users
* Bumped integration version to `2026.3.20.1`

### Fixed

* Fixed camera session lifecycle handling inside the main hub
* Removed temporary camera debug noise from the packaged setup


## 2026.3.6

Initial maintained fork release.

This fork is maintained by **ibasebcast** to ensure continued compatibility with modern Home Assistant releases and to support ongoing development of the Alarm.com integration.

### Added

* Maintained fork to continue development and compatibility support

### Fixed

* Restored compatibility with recent Home Assistant versions
* Fixed light and switch entities becoming unavailable

### Changed

* Updated integration structure to comply with upcoming Home Assistant device registry requirements
* Improved stability and error handling
