# Issue 115: light discovery request context

## Evidence

The reporter's b1 probe shows an empty raw lights relationship, an empty parsed relationship, a declared count of zero, and a matching requested/returned system ID. Their browser instead returns four entries under `relationships.lights.data` from the same endpoint family, then successfully requests lights using `ids[]`.

This rules out loss of IDs during parsing of the sampled response. It does not prove that the browser and integration use the same system ID, login permissions, query parameters, or request context.

## Code review

`AvailableSystemsController.active_system_id` chooses the resource marked `is_selected`. Fallback light discovery uses that ID in the system-detail URL. Neither that call nor the common header builder explicitly supplied `context-id`. The access-management path already supplies system context per request.

## Candidate change

Send the selected system's `context-id` header on fallback system-detail, ID-scoped light, and unscoped light requests. Preserve existing selection, endpoint order, ID validation, parsing, and normal controller discovery. Keep headers local to these requests rather than changing session defaults. No new raw response, identifier, or header logging is introduced.

This is an unconfirmed candidate fix, not evidence that missing context causes the reporter's issue. No version bump or release is included.

## Remaining account comparison

Ask the reporter to compare the portal's system ID and login with HA locally. For the working system-detail request, report whether `context-id` is present and matches the URL system ID, and whether query parameters exist (names only). Do not request cookies, tokens, full headers, or an unredacted network export. If context is absent in the working browser request too, revisit this hypothesis before requesting a new install.

## Regression coverage

Tests exercise empty and populated system-detail responses, scoped and unscoped light followups, provider-specific type labels, and preservation of context alongside the AJAX authentication header.
