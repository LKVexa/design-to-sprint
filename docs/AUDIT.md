# Audit and hardening — 0.1.2a1

Date: 2026-09-23. Source: JY-S019-P001 / 0.1.1-partial / run-0001 / product.
Reviewed scope, breakdown, dependency inference, estimation, sequencing,
trade-offs, preview and approval code. Original source remains separate.

## Repaired findings

- Loose collection/type validation accepted strings as scope/dependency lists
  and leaked built-in exceptions. Bounded JSON/schema validation now rejects
  malformed shapes, duplicate/self/unknown edges and contradictory scope.
- Stale or mixed artifact contents passed downstream unchecked. Scope/task/plan/
  preview validation now verifies digests, with plan recomputation before review
  outputs. Nested inference and estimate outputs are detached snapshots.
- Exclusive quartiles extrapolated beyond tiny samples, producing negative
  estimates; rounding could hide small positive costs. Inclusive quantiles and
  unrounded costs keep descriptive ranges within observed samples.
- Duplicate history IDs falsely satisfied the two-comparable minimum. History
  IDs are unique, kinds validate, evidence is digest-bound and order-independent.
- Invalid capacities and limits could silently misplan or divide by zero.
  Positive finite capacity and bounded integer sprint limits now validate.
- Cycles and blocked descendants had only generic unplaced explanations.
  Iterative component analysis identifies cycle members separately from pending
  dependents; capacity and sprint-limit causes are explicit.
- Tracker previews omitted completion criteria/dependencies and approvals did
  not bind exact reviewed content. Deltas now carry complete planning context
  and a digest; reviews cite that digest, retain prior attribution, and explicitly
  remain identity-unverified, non-dispatched records.

## Verification and release

17 inherited tests passed before changes. 60 source and installed-wheel tests
pass afterward, including 43 regressions. Cycle checks compare all 64 directed
graphs on three vertices (without self-edges) against mutual reachability.
Two approval fixtures cite delta digests and one capacity fixture changed for
the corrected inclusive quartiles. Historical check evidence is retained.

Version 0.1.1-partial -> 0.1.2a1. Regenerate the entire pipeline; estimates and
packing may change and approval records require exact delta digests. CI covers
Linux Python 3.10/3.12/3.14 and Windows Python 3.12.

Added packaging, pinned-action CI, README, security documentation and Apache 2.0
LICENSE/NOTICE naming RUSSELL PHILIP SMITHSON. No third-party runtime dependencies
require upgrades. No build-tool vulnerability scan or production readiness is
claimed. The original gates and full workflow program remain unimplemented.
