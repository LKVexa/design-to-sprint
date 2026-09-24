import copy
import math
import unittest
from dts.core import (DtsError, approve_delta, capture_scope, estimate, infer_dependencies,
    prepare_tracker_preview, sequence_sprints, surface_tradeoffs, work_breakdown)
from tests.test_dts import SCOPE_RAW, TASKS, HISTORY, build_plan


def tasks(raw=None):
    return work_breakdown(capture_scope(SCOPE_RAW), TASKS if raw is None else raw)


class Regression(unittest.TestCase):
    def preview(self):
        estimated, plan = build_plan()
        return prepare_tracker_preview(plan, estimated)

    def test_invalid_scope_types(self):
        for value in (None, [], "scope"):
            with self.subTest(value=value), self.assertRaises(DtsError):
                capture_scope(value)

    def test_scope_fields_must_be_lists(self):
        for field in ("selected_scope", "assumptions", "out_of_scope"):
            with self.subTest(field=field), self.assertRaises(DtsError):
                capture_scope(dict(SCOPE_RAW, **{field: "auth"}))

    def test_duplicate_scope_rejected(self):
        with self.assertRaises(DtsError):
            capture_scope(dict(SCOPE_RAW, selected_scope=["auth", "auth"]))

    def test_scope_overlap_rejected(self):
        with self.assertRaises(DtsError):
            capture_scope(dict(SCOPE_RAW, out_of_scope=["auth"]))

    def test_tampered_scope_rejected(self):
        scope = capture_scope(SCOPE_RAW)
        scope["selected_scope"].append("injected")
        with self.assertRaises(DtsError):
            work_breakdown(scope, TASKS)

    def test_tampered_task_rejected_at_each_stage(self):
        raw = tasks()
        raw[0]["title"] = "changed"
        for fn in (lambda: infer_dependencies(raw), lambda: estimate(raw, HISTORY)):
            with self.assertRaises(DtsError):
                fn()

    def test_unknown_dependencies_rejected(self):
        with self.assertRaises(DtsError):
            tasks([dict(TASKS[0], depends_on=["missing"])])

    def test_dependency_string_rejected(self):
        with self.assertRaises(DtsError):
            tasks([dict(TASKS[0], depends_on="A1")])

    def test_self_dependency_rejected(self):
        with self.assertRaises(DtsError):
            tasks([dict(TASKS[0], depends_on=["A1"])])

    def test_duplicate_dependency_rejected(self):
        with self.assertRaises(DtsError):
            tasks([TASKS[0], dict(TASKS[1], depends_on=["A1", "A1"])])

    def test_invalid_task_shapes(self):
        for value in ([None], {}, "tasks", [dict(TASKS[0], task_id=[])],
                      [dict(TASKS[0], definition_of_done="")]):
            with self.subTest(value=value), self.assertRaises(DtsError):
                tasks(value)

    def test_inference_is_detached(self):
        raw = tasks()
        inferred = infer_dependencies(raw)
        inferred[0]["depends_on"].append("changed")
        self.assertEqual(raw[0]["depends_on"], [])

    def test_inference_idempotent(self):
        inferred = infer_dependencies(tasks())
        self.assertEqual(inferred, infer_dependencies(inferred))

    def test_mixed_scope_snapshots_rejected(self):
        a = tasks([TASKS[0]])
        scope = capture_scope(dict(SCOPE_RAW, assumptions=["new"]))
        b = work_breakdown(scope, [TASKS[1]])
        with self.assertRaises(DtsError):
            infer_dependencies(a + b)

    def test_inference_cycle_surfaces(self):
        raw = [dict(TASKS[0], depends_on=["A2"]), TASKS[1]]
        estimated = estimate(infer_dependencies(tasks(raw)), HISTORY)
        plan = sequence_sprints(estimated, 20)
        self.assertEqual(plan["dependency_cycles"], [["A1", "A2"]])
        self.assertEqual(plan["unplaced_tasks"], ["A1", "A2"])
        self.assertTrue(plan["unplaced_reasons"]["A1"]["cycle_member"])

    def test_cycle_downstream_not_marked_cycle_member(self):
        raw = [dict(TASKS[0], depends_on=["A2"]), TASKS[1],
               dict(TASKS[3], depends_on=["A2"])]
        plan = sequence_sprints(estimate(infer_dependencies(tasks(raw)), HISTORY), 20)
        self.assertEqual(plan["dependency_cycles"], [["A1", "A2"]])
        self.assertFalse(plan["unplaced_reasons"]["B1"]["cycle_member"])
        self.assertEqual(plan["unplaced_reasons"]["B1"]["pending_dependencies"], ["A2"])

    def test_duplicate_history_cannot_fake_two_comparables(self):
        with self.assertRaises(DtsError):
            estimate(tasks(), [HISTORY[0], HISTORY[0]])

    def test_history_validation(self):
        for history in (None, {}, [None], [dict(HISTORY[0], kind="unknown")],
                        [dict(HISTORY[0], actual_days=10 ** 1000)]):
            with self.subTest(history=history), self.assertRaises(DtsError):
                estimate(tasks(), history)

    def test_two_samples_cannot_extrapolate_negative_days(self):
        history = [dict(HISTORY[0], actual_days=0), dict(HISTORY[1], actual_days=4)]
        result = estimate(tasks([TASKS[0]]), history)[0]["estimate"]
        self.assertEqual((result["low_days"], result["high_days"]), (1, 3))

    def test_estimates_do_not_round_small_positive_cost_to_zero(self):
        history = [dict(HISTORY[0], actual_days=.001), dict(HISTORY[1], actual_days=.003)]
        result = estimate(tasks([TASKS[0]]), history)[0]["estimate"]
        self.assertGreater(result["high_days"], 0)

    def test_history_order_does_not_change_estimates(self):
        raw = tasks()
        self.assertEqual(estimate(raw, HISTORY), estimate(raw, list(reversed(HISTORY))))

    def test_reestimate_clears_stale_blocker(self):
        raw = estimate(tasks(), [])
        refreshed = estimate(raw, HISTORY)
        self.assertNotIn("estimation_blocker", refreshed[0])

    def test_invalid_capacity_rejected(self):
        estimated, _ = build_plan()
        for value in (0, -1, True, "12", float("nan"), float("inf"), 10 ** 1000):
            with self.subTest(value=value), self.assertRaises(DtsError):
                sequence_sprints(estimated, value)

    def test_invalid_sprint_limit_rejected(self):
        estimated, _ = build_plan()
        for value in (-1, True, 1.5, 261, None):
            with self.subTest(value=value), self.assertRaises(DtsError):
                sequence_sprints(estimated, 12, value)

    def test_zero_sprint_limit_is_explicit(self):
        estimated, _ = build_plan()
        plan = sequence_sprints(estimated, 12, 0)
        self.assertEqual(plan["sprints"], [])
        self.assertTrue(all(r["sprint_limit_reached"] for r in plan["unplaced_reasons"].values()))

    def test_estimate_change_cannot_bypass_task_digest(self):
        estimated, _ = build_plan()
        estimated[0]["estimate"]["high_days"] = 0
        with self.assertRaises(DtsError):
            sequence_sprints(estimated, 12)

    def test_unestimated_tasks_rejected(self):
        with self.assertRaises(DtsError):
            sequence_sprints(tasks(), 12)

    def test_oversized_work_reason(self):
        estimated, _ = build_plan()
        plan = sequence_sprints(estimated, 1)
        self.assertTrue(plan["unplaced_reasons"]["A1"]["exceeds_capacity"])

    def test_blocked_dependency_never_scheduled(self):
        raw = [dict(TASKS[0], depends_on=["A3"]), TASKS[2]]
        plan = sequence_sprints(estimate(tasks(raw), HISTORY), 12)
        self.assertIn("A1", plan["unplaced_tasks"])
        self.assertIn("A3", plan["estimation_blockers"])

    def test_plan_arithmetic_not_rounded(self):
        history = [dict(HISTORY[0], actual_days=.001), dict(HISTORY[1], actual_days=.003)]
        estimated = estimate(tasks([TASKS[0], TASKS[3]]), history)
        plan = sequence_sprints(estimated, .0049)
        self.assertEqual(len(plan["sprints"]), 2)
        for sprint in plan["sprints"]:
            self.assertEqual(sprint["load_days"], math.fsum(e["budgeted_days"] for e in sprint["tasks"]))

    def test_plan_mutation_rejected(self):
        estimated, plan = build_plan()
        plan["sprints"][0]["tasks"][0]["task_id"] = "other"
        for fn in (surface_tradeoffs, prepare_tracker_preview):
            with self.assertRaises(DtsError):
                fn(plan, estimated)

    def test_plan_cannot_mix_another_task_snapshot(self):
        estimated, plan = build_plan()
        different = estimate(infer_dependencies(tasks()), HISTORY[:-1])
        with self.assertRaises(DtsError):
            prepare_tracker_preview(plan, different)

    def test_preview_contains_reviewable_definition_and_dependencies(self):
        preview = self.preview()
        delta = next(d for d in preview["deltas"] if d["task_id"] == "A2")
        self.assertEqual(delta["definition_of_done"], "code merged")
        self.assertIn("A1", delta["dependencies"])
        self.assertTrue(delta["delta_digest"].startswith("sha256:"))
        self.assertFalse(delta["approved"])

    def test_approval_requires_exact_delta_digest(self):
        preview = self.preview()
        for value in (None, "sha256:wrong"):
            with self.subTest(value=value), self.assertRaises(DtsError):
                approve_delta(preview, "A1", {"role": "human", "approver": "lead", "delta_digest": value})

    def test_approval_cannot_follow_changed_content(self):
        preview = self.preview()
        approval = {"role": "human", "approver": "lead", "delta_digest": preview["deltas"][0]["delta_digest"]}
        preview["deltas"][0]["title"] = "new action"
        with self.assertRaises(DtsError):
            approve_delta(preview, "A1", approval)

    def test_approval_is_idempotent_unverified_and_preview_only(self):
        preview = self.preview()
        approval = {"role": "human", "approver": "lead", "delta_digest": preview["deltas"][0]["delta_digest"]}
        result = approve_delta(preview, "A1", approval)
        self.assertEqual(result, approve_delta(result, "A1", approval))
        self.assertFalse(result["dispatched"])
        self.assertFalse(result["deltas"][0]["approvals"][0]["identity_verified"])
        self.assertFalse(preview["deltas"][0]["approved"])

    def test_additional_review_preserves_prior_record(self):
        preview = self.preview()
        approval = {"role": "human", "approver": "lead", "delta_digest": preview["deltas"][0]["delta_digest"]}
        first = approve_delta(preview, "A1", approval)
        second = approve_delta(first, "A1", dict(approval, approver="reviewer"))
        self.assertEqual([r["approver"] for r in second["deltas"][0]["approvals"]], ["lead", "reviewer"])

    def test_empty_work_produces_empty_preview(self):
        estimated = estimate(tasks([]), HISTORY)
        preview = prepare_tracker_preview(sequence_sprints(estimated, 12), estimated)
        self.assertEqual(preview["deltas"], [])

    def test_control_character_in_task_rejected(self):
        with self.assertRaises(DtsError):
            tasks([dict(TASKS[0], title="misleading\u202etext")])

    def test_json_cycle_rejected(self):
        cycle = []
        cycle.append(cycle)
        with self.assertRaises(DtsError):
            capture_scope(dict(SCOPE_RAW, extra=cycle))

    def test_task_count_limit(self):
        with self.assertRaises(DtsError):
            tasks([dict(TASKS[0], task_id=str(i)) for i in range(1001)])

    def test_returned_estimate_is_detached(self):
        raw = infer_dependencies(tasks())
        estimated = estimate(raw, HISTORY)
        estimated[0]["inferred_deps"].append({"on": "injected"})
        self.assertEqual(raw[0]["inferred_deps"], [])

    def test_cycles_match_mutual_reachability(self):
        import itertools
        identifiers = ("A1", "A2", "A3")
        edges = list(itertools.permutations(identifiers, 2))
        for mask in range(64):
            adjacency = {key: set() for key in identifiers}
            for i, (a, b) in enumerate(edges):
                if mask & (1 << i):
                    adjacency[a].add(b)
            def reaches(start, target):
                seen, stack = {start}, list(adjacency[start])
                while stack:
                    node = stack.pop()
                    if node == target:
                        return True
                    if node not in seen:
                        seen.add(node)
                        stack.extend(adjacency[node])
                return False
            raw = [dict(TASKS[0], task_id=key, depends_on=sorted(adjacency[key])) for key in identifiers]
            plan = sequence_sprints(estimate(tasks(raw), HISTORY), 20)
            expected = set()
            for a, b in itertools.combinations(identifiers, 2):
                if reaches(a, b) and reaches(b, a):
                    expected.update((a, b))
            self.assertEqual({key for group in plan["dependency_cycles"] for key in group}, expected)
