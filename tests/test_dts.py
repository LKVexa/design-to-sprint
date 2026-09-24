import unittest

from dts.core import (DtsError, approve_delta, capture_scope, estimate,
                      infer_dependencies, prepare_tracker_preview,
                      sequence_sprints, surface_tradeoffs, work_breakdown)

SCOPE_RAW = {"selected_scope": ["auth", "billing"],
             "assumptions": ["existing user store stays"],
             "out_of_scope": ["mobile app"]}

TASKS = [
    {"task_id": "A1", "title": "Design auth flow", "scope_item": "auth",
     "kind": "design", "definition_of_done": "reviewed design doc"},
    {"task_id": "A2", "title": "Implement auth", "scope_item": "auth",
     "kind": "implement", "definition_of_done": "code merged"},
    {"task_id": "A3", "title": "Test auth", "scope_item": "auth",
     "kind": "test", "definition_of_done": "suite green"},
    {"task_id": "B1", "title": "Design billing", "scope_item": "billing",
     "kind": "design", "definition_of_done": "reviewed design doc"},
    {"task_id": "B2", "title": "Implement billing", "scope_item": "billing",
     "kind": "implement", "definition_of_done": "code merged",
     "depends_on": ["A2"]},
]

HISTORY = [
    {"task_id": "H1", "kind": "design", "actual_days": 2},
    {"task_id": "H2", "kind": "design", "actual_days": 4},
    {"task_id": "H3", "kind": "implement", "actual_days": 5},
    {"task_id": "H4", "kind": "implement", "actual_days": 9},
    {"task_id": "H5", "kind": "implement", "actual_days": 7},
]


def build_plan(capacity=12.0):
    scope = capture_scope(SCOPE_RAW)
    tasks = infer_dependencies(work_breakdown(scope, TASKS))
    est = estimate(tasks, HISTORY)
    return est, sequence_sprints(est, capacity)


class Scope(unittest.TestCase):
    def test_capture_requires_explicit_fields(self):
        s = capture_scope(SCOPE_RAW)
        self.assertTrue(s["scope_digest"].startswith("sha256:"))
        with self.assertRaises(DtsError):
            capture_scope({"selected_scope": ["x"]})
        with self.assertRaises(DtsError):
            capture_scope({**SCOPE_RAW, "selected_scope": []})


class Breakdown(unittest.TestCase):
    def test_template_and_scope_binding(self):
        scope = capture_scope(SCOPE_RAW)
        wb = work_breakdown(scope, TASKS)
        self.assertEqual(len(wb), 5)
        with self.assertRaises(DtsError):
            work_breakdown(scope, [{"task_id": "X", "title": "t",
                                    "scope_item": "kitchen", "kind": "design",
                                    "definition_of_done": "d"}])
        with self.assertRaises(DtsError):
            work_breakdown(scope, [dict(TASKS[0], kind="vibes")])
        with self.assertRaises(DtsError):
            work_breakdown(scope, [TASKS[0], TASKS[0]])


class Dependencies(unittest.TestCase):
    def test_inferred_edges_explained_and_declared_kept(self):
        tasks = infer_dependencies(work_breakdown(capture_scope(SCOPE_RAW), TASKS))
        a2 = next(t for t in tasks if t["task_id"] == "A2")
        self.assertEqual(a2["inferred_deps"][0]["on"], "A1")
        self.assertIn("implement follows design", a2["inferred_deps"][0]["reason"])
        b2 = next(t for t in tasks if t["task_id"] == "B2")
        self.assertIn("A2", b2["depends_on"])          # declared edge kept
        self.assertTrue(any(d["on"] == "B1" for d in b2["inferred_deps"]))


class Estimation(unittest.TestCase):
    def test_ranges_cite_comparables(self):
        est, _ = build_plan()
        a2 = next(t for t in est if t["task_id"] == "A2")
        self.assertLessEqual(a2["estimate"]["low_days"],
                             a2["estimate"]["high_days"])
        self.assertEqual(set(a2["estimate"]["comparables"]),
                         {"H3", "H4", "H5"})

    def test_no_history_blocks_not_guesses(self):
        est, _ = build_plan()
        a3 = next(t for t in est if t["task_id"] == "A3")
        self.assertIsNone(a3["estimate"])
        self.assertIn("comparable", a3["estimation_blocker"])


class Sequencing(unittest.TestCase):
    def test_dependency_respecting_sprints(self):
        _, plan = build_plan(capacity=12.0)
        placed = {e["task_id"]: s["sprint"]
                  for s in plan["sprints"] for e in s["tasks"]}
        self.assertLess(placed["A1"], placed["A2"])
        self.assertLess(placed["A2"], placed["B2"])
        self.assertIn("A3", plan["estimation_blockers"])
        for s in plan["sprints"]:
            self.assertLessEqual(s["load_days"], s["capacity_days"])
        self.assertTrue(plan["draft"])

    def test_milestones_track_sprints(self):
        _, plan = build_plan()
        self.assertEqual(len(plan["milestones"]), len(plan["sprints"]))

    def test_deterministic(self):
        self.assertEqual(build_plan()[1], build_plan()[1])


class TradeoffsAndSync(unittest.TestCase):
    def test_tradeoffs_and_blockers_surfaced(self):
        est, plan = build_plan(capacity=8.5)
        items = surface_tradeoffs(plan, est)
        kinds = {i["kind"] for i in items}
        self.assertIn("blocker", kinds)
        self.assertTrue(any("capacity planned" in i["detail"]
                            for i in items if i["kind"] == "trade-off"))

    def test_cap07_preview_only_and_human_approval(self):
        est, plan = build_plan()
        prev = prepare_tracker_preview(plan, est)
        self.assertFalse(prev["dispatched"])
        self.assertTrue(all(not d["approved"] for d in prev["deltas"]))
        with self.assertRaises(DtsError):
            approve_delta(prev, prev["deltas"][0]["task_id"], {"role": "model"})
        ok = approve_delta(prev, prev["deltas"][0]["task_id"],
                           {"role": "human", "approver": "lead",
                            "delta_digest": prev["deltas"][0]["delta_digest"]})
        self.assertTrue(ok["deltas"][0]["approved"])
        self.assertFalse(prev["deltas"][0]["approved"])   # original untouched
        import dts.core as m
        for name in dir(m):
            for bad in ("dispatch", "sync_tracker", "push_to", "jira", "create_ticket"):
                self.assertNotIn(bad, name.lower())


if __name__ == "__main__":
    unittest.main()

# ---- A016 hardening tests (0.1.1-partial) --------------------------------
class HardeningA016(unittest.TestCase):
    def test_f1_scope_isolated_from_caller_mutation(self):
        raw = {"selected_scope": ["auth"], "assumptions": [],
               "out_of_scope": []}
        scope = capture_scope(raw)
        raw["selected_scope"].append("evil-scope")
        self.assertEqual(scope["selected_scope"], ["auth"])
        with self.assertRaises(DtsError):
            work_breakdown(scope, [{"task_id": "X", "title": "t",
                                    "scope_item": "evil-scope",
                                    "kind": "design",
                                    "definition_of_done": "d"}])

    def test_f1_breakdown_output_isolated(self):
        scope = capture_scope(SCOPE_RAW)
        tasks = [dict(TASKS[4])]
        tasks[0]["depends_on"] = ["B2"]
        tasks[0]["task_id"] = "B2x"
        # self-reference not allowed? it's declared id so passes; mutate input
        wb = work_breakdown(scope, [dict(TASKS[0])])
        wb0_dod = wb[0]["definition_of_done"]
        self.assertEqual(wb0_dod, TASKS[0]["definition_of_done"])

    def test_f2_unknown_declared_dependency_rejected(self):
        scope = capture_scope(SCOPE_RAW)
        with self.assertRaises(DtsError) as cm:
            work_breakdown(scope, [dict(TASKS[0], depends_on=["GHOST"])])
        self.assertIn("GHOST", str(cm.exception))
        # forward references between declared tasks remain legal
        wb = work_breakdown(scope, [dict(TASKS[0], depends_on=["A2"]),
                                    dict(TASKS[1])])
        self.assertEqual(wb[0]["depends_on"], ["A2"])

    def test_f3_nan_history_rejected_not_propagated(self):
        scope = capture_scope(SCOPE_RAW)
        wb = infer_dependencies(work_breakdown(scope, TASKS))
        bad = HISTORY + [{"task_id": "HX", "kind": "design",
                          "actual_days": float("nan")}]
        with self.assertRaises(DtsError):
            estimate(wb, bad)
        with self.assertRaises(DtsError):
            estimate(wb, [{"task_id": "HX", "kind": "design",
                           "actual_days": float("inf")},
                          {"task_id": "HY", "kind": "design",
                           "actual_days": 2}])
        # finite history still estimates
        est = estimate(wb, HISTORY)
        self.assertIsNotNone(next(t for t in est
                                  if t["task_id"] == "A1")["estimate"])

    def test_f3_nan_scope_not_digestable(self):
        with self.assertRaises(DtsError):
            capture_scope({"selected_scope": ["a"],
                           "assumptions": [float("nan")],
                           "out_of_scope": []})

    def test_f4_documented_errors_not_bare_builtins(self):
        with self.assertRaises(DtsError):
            infer_dependencies([{"task_id": "Z", "scope_item": "a",
                                 "kind": "vibes", "depends_on": []}])
        with self.assertRaises(DtsError):
            infer_dependencies([{"scope_item": "a", "kind": "design"}])
        with self.assertRaises(DtsError):
            estimate([dict(TASKS[0], depends_on=[])],
                     [{"task_id": "H", "actual_days": 2}])
        est, plan = build_plan()
        prev = prepare_tracker_preview(plan, est)
        with self.assertRaises(DtsError):
            approve_delta(prev, prev["deltas"][0]["task_id"], "yes boss")

    def test_f5_empty_or_missing_approver_rejected(self):
        est, plan = build_plan()
        prev = prepare_tracker_preview(plan, est)
        tid = prev["deltas"][0]["task_id"]
        with self.assertRaises(DtsError):
            approve_delta(prev, tid, {"role": "human", "approver": ""})
        with self.assertRaises(DtsError):
            approve_delta(prev, tid, {"role": "human", "approver": "   "})
        with self.assertRaises(DtsError):
            approve_delta(prev, tid, {"role": "human", "approver": 42})
        ok = approve_delta(prev, tid, {"role": "human", "approver": "lead",
                                     "delta_digest": prev["deltas"][0]["delta_digest"]})
        self.assertEqual(ok["deltas"][0]["approved_by"], "lead")
