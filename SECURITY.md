# Security and planning boundaries

This library emits draft plans and tracker previews. It has no network or tracker
transport. Human review records do not authenticate the named person, establish
authorization or permit automatic execution. Every record identifies the exact
delta and explicitly states that identity is unverified.

Canonical hashes bind snapshots against accidental mismatches, not hostile
callers who can recompute them. Persist and authenticate records independently
in any real integration. Approval history is part of an in-memory returned
artifact, not an externally anchored audit log.

Task text and historical identifiers can contain sensitive information; no
redaction is supplied. Treat all content as untrusted text when displaying or
exporting. Input work, completion criteria, history quality, priority, resources
and capacity remain team judgments.

Historical quartiles are descriptive and do not imply prediction confidence.
The scheduler uses one capacity pool and cross-sprint dependencies; it does not
model individual availability, calendars or execution feasibility.

Count, size and numeric limits protect routine inputs, not hostile in-process
code or every resource-exhaustion scenario. Exposed services need request limits
and process isolation. No third-party runtime dependencies exist; no build-tool
vulnerability scan is claimed. Report defects privately using synthetic tasks.
