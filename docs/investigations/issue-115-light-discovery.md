# Issue 115: light discovery investigation

Unreleased investigation on `fix/light-discovery-probe`. No release version changes, no merge into main, and no published beta.

## Findings

HA-ADC/pyadc at `97e7fc274172a3aa8d8a0a23c99d9a48960709b6` does not solve the account-specific discovery gap by itself. Its `LightController` inherits `BaseController.fetch_all()`, which requests the unscoped `devices/lights` endpoint. It does not obtain light IDs from the system relationship before that request. The issue reporter has already established that their account rejects the unscoped endpoint and accepts `ids[]` requests.

Our current path gets no IDs from the catalog, requests the selected system detail, and receives a parsed `lights` relationship with zero entries. Presence of a relationship does not establish that its `data` array was populated. The reported relationship count of 33 counts relationship names, not lights.

The published example with `lights.data` parses correctly locally. Additional synthetic reproductions confirm that adding metadata, links, or both does not lose those IDs. A relationship containing only links and metadata is also valid JSON:API and yields no embedded IDs. That is a hypothesis to distinguish, not a confirmed explanation for this account.

## Changes prepared here

The existing fallback system-detail request can now emit a DEBUG-only, count-only probe. The probe records predefined structure labels, raw versus parsed entry and usable-ID counts, whether the ID sets match, whether the response includes the requested system, whether a related link exists, and a bounded numeric metadata count. The request also reports whether the requested system is among the already loaded systems.

IDs are compared in memory and are never included in the probe output. Names, URLs, response bodies, headers, credentials, arbitrary field names, metadata strings, and exception messages are excluded. The diagnostic flag is consumed internally and never forwarded to aiohttp. Probe failures do not interrupt discovery. No new endpoint is requested, no link is followed, and the existing discovery behavior is unchanged.

## Next live comparison

On the maintainer's working system, enable `_pyalarmdotcomajax: debug` temporarily and capture only `Light discovery:` and `Light discovery probe:` lines while reloading. The fallback probe runs only when ordinary discovery finds no lights, so a working account may not exercise it. The absence of that probe on a working account is not evidence that it is broken.

Possible outcomes on the affected account, once this investigation is ready for testing:

- Raw IDs exist but differ from parsed IDs: investigate the parser with a matching synthetic structure.
- Both counts are zero and a related link or positive metadata count is present: investigate lazy relationship expansion using the actual portal sequence.
- The requested system is missing from the loaded system collection or does not match the response: investigate account/system selection.
- Both counts match and contain IDs: continue through the scoped lights request and model registration.

Do not request another reporter installation or publish a speculative fix on the basis of these local tests. Actual affected-account behavior remains unverified. No additional issue attachment was inspected during this investigation.
