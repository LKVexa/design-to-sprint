# 0.1.2a1 — 2026-09-23

- Validate and bind scope, tasks, plans, deltas and previews to content digests.
- Use inclusive historical quartiles and preserve small positive planning costs.
- Reject duplicate history evidence and invalid capacity/limit inputs.
- Surface cycle membership, blocked dependencies and capacity/limit causes.
- Require exact delta references in preserved, identity-unverified review records.
- Add 43 regressions, packaging, CI, README and Apache 2.0 LICENSE/NOTICE.
- Compatibility: regenerate pipeline artifacts and approval records.

# Changelog — Design-to-Sprint (DTS), JY-S019-P001

## 0.1.1-partial — 2026-09-14 (A016 audit & hardening, run-0001)

Baseline fingerprint: build-0001 product.zip
sha256 34a299ba99b46b5c3463c3b9cf23b1542dbdac3f7aff94e97c47291341938798
(7963 bytes), baseline version 0.1.0-partial. All findings below were
reproduced on the unmodified baseline before fixing.

### Fixes (all reproduced on baseline)

- **A016-F1 — scope/tamper aliasing.** Observed: `capture_scope` returned
  a dict sharing mutable lists with the caller's input; appending to the
  input's `selected_scope` after digesting changed the scope while
  `scope_digest` stayed stale, and `work_breakdown` then accepted tasks
  bound to the post-digest injected scope item. Expected: the digested
  scope is an isolated snapshot. Fix: deep-copy the input before
  digesting; `work_breakdown` also deep-copies task rows.
- **A016-F2 — unknown declared dependencies silently dropped.** Observed:
  a task with `depends_on: ["GHOST"]` (no such task) was scheduled into
  sprint 1 with no blocker — the sequencer's filter silently ignored ids
  outside the plan. Expected: an unresolvable declared dependency is an
  error. Fix: `work_breakdown` validates every `depends_on` id against
  the declared task set (forward references between declared tasks
  remain legal) and raises `DtsError` naming the unknown ids.
- **A016-F3 — NaN propagation / non-strict canonicalization.** Observed:
  a history row with `actual_days = NaN` produced `low_days/high_days =
  nan` estimates ("never a guess" violated) and the task then vanished
  from sprints without any blocker; NaN values in scope were digested
  via non-strict JSON (`NaN` literal). Fix: `estimate` rejects
  non-finite or negative `actual_days` with `DtsError`; `_digest` uses
  `allow_nan=False` and wraps failures in `DtsError`.
- **A016-F4 — error-contract leaks.** Observed: bare `KeyError` from
  `estimate` on a history row missing `kind`, bare `KeyError` from
  `infer_dependencies` on missing/unknown fields, bare `AttributeError`
  from `approve_delta` on a non-dict approval. Expected: documented
  `DtsError`. Fix: explicit input validation in all three entry points.
- **A016-F5 — hollow approval records accepted.** Observed:
  `approve_delta` accepted `approver: ""` (and non-string approvers),
  marking a tracker delta approved with an empty approver identity.
  Fix: approver must be a non-empty, non-whitespace string.

### Compatibility

Repairs only; no public API added or removed — patch bump
0.1.0-partial -> 0.1.1-partial. Previously-accepted invalid inputs
(unknown dependency ids, NaN history, malformed approvals) now raise
`DtsError`; valid inputs behave identically. CAP-07 remains
preview-only: nothing dispatches.

### Rollback

Restore build-0001 `product.zip`
(sha256 34a299ba99b46b5c3463c3b9cf23b1542dbdac3f7aff94e97c47291341938798).
No data formats changed; rollback is a file swap.
