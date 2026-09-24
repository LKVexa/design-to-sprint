# Design-to-Sprint

**0.1.2a1 — experimental partial candidate, JY-S019-P001**

A deterministic planning library that validates a selected scope and task
breakdown, infers explainable dependencies, estimates historical ranges and
proposes capacity-bounded sprints. Tracker output is a preview only; no tracker
client, synchronization or dispatch capability exists.

## Install and use

Python 3.10 or newer; no third-party runtime dependencies.

~~~sh
python -m pip install .
python -m unittest discover -s tests -t .
~~~

~~~python
from dts.core import (capture_scope, work_breakdown, infer_dependencies, estimate,
                      sequence_sprints, prepare_tracker_preview, approve_delta)

scope = capture_scope({"selected_scope": ["auth"], "assumptions": [],
                       "out_of_scope": []})
tasks = work_breakdown(scope, [{
    "task_id": "A1", "title": "Design auth flow", "scope_item": "auth",
    "kind": "design", "definition_of_done": "reviewed design document",
}])
tasks = estimate(infer_dependencies(tasks), [
    {"task_id": "H1", "kind": "design", "actual_days": 2},
    {"task_id": "H2", "kind": "design", "actual_days": 4},
])
plan = sequence_sprints(tasks, capacity_days=10)
preview = prepare_tracker_preview(plan, tasks)
delta = preview["deltas"][0]
reviewed = approve_delta(preview, delta["task_id"], {
    "role": "human", "approver": "team-lead", "delta_digest": delta["delta_digest"],
})
assert reviewed["dispatched"] is False
~~~

## Planning behavior

Scope lists, assumptions and out-of-scope items must be explicit. Exact overlap
between selected and excluded scope labels is rejected. Tasks are caller
declarations, not generated work. Required fields are task_id, title, scope_item,
kind and definition_of_done. Kinds are design/implement/test/review/docs.

Declared dependencies remain intact. Inference adds previous-stage tasks within
the same scope item: implement follows design, test follows implement, and
review/docs follow test. Inferred edges are labeled and explained. Missing stages
are not invented. Conflicting declarations can create cycles; these surface in
dependency_cycles and specific unplaced-task reasons.

Estimates use at least two distinct same-kind historical task IDs. Inclusive
p25..p75 interpolation stays within the observed range, with no extrapolated
negative values or early rounding. This range is descriptive, not a confidence
interval or a delivery guarantee. Kind alone is a weak comparability heuristic;
the team must select appropriate history and consistent units. History digests
and comparable IDs identify the evidence used. No manual-estimate override API
is supplied.

Greedy packing uses high-end estimates, alphabetical task-ID priority, and a
single capacity pool. Dependencies must finish in earlier sprints. There is no
within-sprint scheduling, resource calendar, skills matching or optimality claim.
Estimation gaps, cycles, pending dependencies, oversized tasks and exhausted
sprint limits remain visible. Zero-duration historical work is allowed; zero
sprint count requests no placement. Capacity must be positive.

## Integrity and human review

Scope, task, plan, delta and preview artifacts carry canonical content digests.
Consumers verify them. Trade-off and preview creation recompute the plan against
the supplied estimated tasks, preventing accidental mixing of snapshots.
Use each pipeline constructor in order; regenerate downstream artifacts after
changing source scope, tasks or history. All returned structures are detached.

Each preview delta includes scope, kind, definition of done, dependencies,
sprint, budget and task/plan provenance for human review. approve_delta requires
the exact delta_digest, appends an attributed review record, preserves prior
records and returns a new preview. Repeated identical reviews are idempotent.
Records explicitly state identity_verified=false. An approved flag is a recorded
caller assertion, not authenticated identity, authorization or permission to
send. No preview is dispatched by this library.

Content hashes are not signatures and do not defeat a caller rewriting data and
recomputing hashes. They also do not anonymize predictable content. A real tracker
integration would need separate identity, authorization and execution controls.

## Limits and compatibility

At most 1,000 tasks/scope labels, 10,000 combined declared/inferred dependency
edges, 10,000 historical entries, 260 sprints and 100 reviews per delta. Labels
are at most 512 characters, task text 65,536, and scope notes 4,096. JSON depth
is at most 40 and each model is limited to 16 MiB. Durations/capacity must be
finite and at most 1,000,000 days. Invalid inputs raise DtsError.

Version 0.1.1-partial -> 0.1.2a1 requires regenerated artifacts and exact digest
references in approval records. Estimates use inclusive quartiles and full
precision, so ranges and packing may change. Duplicate historical IDs no longer
count as independent observations. Arbitrary manually constructed estimates are
not part of the supported pipeline.

60 tests include 17 inherited checks and 43 regressions. Two approval fixtures
now cite exact delta digests; the utilization fixture reflects corrected quartiles.
Source and installed-wheel results: [CHECK_RUNS](docs/CHECK_RUNS.json).
See [AUDIT](docs/AUDIT.md) and [SECURITY](SECURITY.md). CI covers Linux Python
3.10/3.12/3.14 and Windows Python 3.12.

The original 2,412-card program, gates G00–G07, live integration and product-wide
verification scenarios remain unimplemented. No production readiness is claimed.

## License

Copyright 2026 **RUSSELL PHILIP SMITHSON**.
[Apache License 2.0](LICENSE), with [NOTICE](NOTICE).
No third-party code is vendored.
