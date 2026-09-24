"""Bounded planning artifacts and human review records; no tracker transport."""
from __future__ import annotations

import copy
import hashlib
import json
import math
import re
import statistics
import unicodedata

VERSION = "0.1.2a1"
TEMPLATE_FIELDS = ("task_id", "title", "scope_item", "kind", "definition_of_done")
TASK_KINDS = ("design", "implement", "test", "review", "docs")
_KIND_ORDER = {"design": 0, "implement": 1, "test": 2, "review": 3, "docs": 3}


class DtsError(Exception):
    """Invalid planning input or exceeded resource limit."""


def _canonical(obj):
    def check(value, depth=0):
        if depth > 40:
            raise DtsError("JSON nesting exceeds 40 levels")
        if type(value) is dict:
            if any(type(k) is not str for k in value):
                raise DtsError("JSON keys must be strings")
            for v in value.values():
                check(v, depth + 1)
        elif type(value) is list:
            for v in value:
                check(v, depth + 1)
        elif type(value) not in (str, int, float, bool, type(None)):
            raise DtsError("only JSON values are supported")
    try:
        check(obj)
        payload = json.dumps(obj, sort_keys=True, separators=(",", ":"),
                             ensure_ascii=False, allow_nan=False)
        if len(payload.encode("utf-8")) > 16 * 1024 * 1024:
            raise DtsError("planning model exceeds 16 MiB")
        return payload
    except (TypeError, ValueError, UnicodeError, RecursionError, OverflowError) as exc:
        raise DtsError("invalid planning JSON") from exc


def _digest(obj):
    return "sha256:" + hashlib.sha256(_canonical(obj).encode("utf-8")).hexdigest()


def _text(value, field, limit=65536):
    if type(value) is not str or not value.strip() or len(value) > limit:
        raise DtsError(f"{field} must be a nonempty bounded string")
    if any(unicodedata.category(c).startswith("C") or c in "\u2028\u2029" for c in value):
        raise DtsError(f"{field} must be single-line text without control characters")
    return value


def _label(value, field):
    value = _text(value, field, 512)
    if value != value.strip():
        raise DtsError(f"{field} must not have surrounding whitespace")
    return value


def _list(value, field, limit):
    if type(value) is not list or len(value) > limit:
        raise DtsError(f"{field} must be a list with at most {limit} items")
    return value


def _labels(value, field, limit=1000):
    values = _list(value, field, limit)
    for item in values:
        _label(item, field)
    if len(set(values)) != len(values):
        raise DtsError(f"{field} contains duplicates")
    return list(values)


def _number(value, field, positive=False):
    if type(value) not in (int, float):
        raise DtsError(f"{field} must be a finite number")
    try:
        value = float(value)
    except (ValueError, OverflowError) as exc:
        raise DtsError(f"{field} must be a finite number") from exc
    if not math.isfinite(value) or not 0 <= value <= 1e6 or (positive and value == 0):
        raise DtsError(f"{field} must be {'positive' if positive else 'nonnegative'} and at most 1000000")
    return value


def _seal(raw, field):
    result = copy.deepcopy({k: v for k, v in raw.items() if k != field})
    result[field] = _digest(result)
    return result


def _verify(raw, field):
    if type(raw) is not dict or field not in raw:
        raise DtsError(f"missing {field}; use the public constructor")
    _canonical(raw)
    if raw[field] != _digest({k: v for k, v in raw.items() if k != field}):
        raise DtsError(f"{field} mismatch; regenerate the artifact")
    return copy.deepcopy(raw)


def capture_scope(raw):
    if type(raw) is not dict or "scope_digest" in raw:
        raise DtsError("scope must be a raw dictionary without a digest")
    _canonical(raw)
    _labels(raw.get("selected_scope"), "selected_scope")
    if not raw["selected_scope"]:
        raise DtsError("selected_scope must not be empty")
    for field in ("assumptions", "out_of_scope"):
        for item in _list(raw.get(field), field, 1000):
            _text(item, field, 4096)
    if set(raw["selected_scope"]) & set(raw["out_of_scope"]):
        raise DtsError("selected_scope overlaps out_of_scope")
    return _seal(raw, "scope_digest")


def _base_tasks(tasks):
    _list(tasks, "tasks", 1000)
    _canonical(tasks)
    ids, out = set(), []
    for task in tasks:
        if type(task) is not dict:
            raise DtsError("task must be a dictionary")
        for field in TEMPLATE_FIELDS:
            (_label if field in ("task_id", "scope_item", "kind") else _text)(task.get(field), field)
        if task["kind"] not in TASK_KINDS or task["task_id"] in ids:
            raise DtsError("unknown task kind or duplicate task_id")
        ids.add(task["task_id"])
        item = copy.deepcopy(task)
        item["depends_on"] = _labels(task.get("depends_on", []), "depends_on")
        if task["task_id"] in item["depends_on"]:
            raise DtsError("self dependency")
        out.append(item)
    for task in out:
        unknown = set(task["depends_on"]) - ids
        if unknown:
            raise DtsError(f"unknown dependencies: {sorted(unknown)}")
    if sum(len(t["depends_on"]) for t in out) > 10000:
        raise DtsError("dependency edge limit exceeded")
    return out


def work_breakdown(scope, tasks):
    scope = _verify(scope, "scope_digest")
    if capture_scope({k: v for k, v in scope.items() if k != "scope_digest"}) != scope:
        raise DtsError("invalid scope")
    out = []
    reserved = {"scope_digest", "task_digest", "stage", "estimate", "estimation_blocker", "inferred_deps"}
    for task in _base_tasks(tasks):
        if reserved & set(task):
            raise DtsError("work_breakdown requires raw task declarations")
        if task["scope_item"] not in scope["selected_scope"]:
            raise DtsError("task is outside selected scope")
        out.append(_seal(dict(task, scope_digest=scope["scope_digest"],
                              stage="breakdown", inferred_deps=[]), "task_digest"))
    return sorted(out, key=lambda t: t["task_id"])


def _tasks(tasks, estimated=False):
    out = _base_tasks(tasks)
    ids = {t["task_id"] for t in out}
    scope_digests = set()
    edge_count = 0
    for task in out:
        _verify(task, "task_digest")
        scope_digest = task.get("scope_digest")
        if type(scope_digest) is not str or not re.fullmatch(r"sha256:[0-9a-f]{64}", scope_digest):
            raise DtsError("invalid scope digest")
        scope_digests.add(scope_digest)
        if task.get("stage") not in ("breakdown", "inferred", "estimated"):
            raise DtsError("invalid task stage")
        seen = set(task["depends_on"])
        for dependency in _list(task.get("inferred_deps"), "inferred_deps", 1000):
            if type(dependency) is not dict:
                raise DtsError("invalid inferred dependency")
            identifier = _label(dependency.get("on"), "inferred dependency")
            _text(dependency.get("reason"), "dependency reason")
            if identifier not in ids or identifier == task["task_id"] or identifier in seen:
                raise DtsError("unknown, self or duplicate inferred dependency")
            seen.add(identifier)
        edge_count += len(seen)
        if estimated:
            if task["stage"] != "estimated" or "estimate" not in task:
                raise DtsError("use estimate before sequencing")
            estimate_value = task["estimate"]
            if estimate_value is None:
                _text(task.get("estimation_blocker"), "estimation_blocker")
            else:
                if type(estimate_value) is not dict:
                    raise DtsError("invalid estimate")
                low = _number(estimate_value.get("low_days"), "low_days")
                high = _number(estimate_value.get("high_days"), "high_days")
                if low > high:
                    raise DtsError("estimate bounds inverted")
                _labels(estimate_value.get("comparables"), "comparables", 10000)
                _text(estimate_value.get("basis"), "estimate basis")
    if len(scope_digests) > 1 or edge_count > 10000:
        raise DtsError("mixed scope snapshots or excessive dependency edges")
    return sorted(out, key=lambda t: t["task_id"])


def infer_dependencies(tasks):
    tasks = _tasks(tasks)
    out = []
    for task in tasks:
        inferred = []
        for other in tasks:
            if (other["scope_item"] == task["scope_item"] and
                _KIND_ORDER[other["kind"]] == _KIND_ORDER[task["kind"]] - 1 and
                other["task_id"] not in task["depends_on"]):
                inferred.append({"on": other["task_id"], "inferred": True,
                    "reason": f"{task['kind']} follows {other['kind']} within scope item {task['scope_item']!r}"})
        raw = {k: v for k, v in task.items() if k not in ("estimate", "estimation_blocker")}
        out.append(_seal(dict(raw, inferred_deps=inferred, stage="inferred"), "task_digest"))
    return _tasks(out)


def _all_deps(task):
    return sorted(task["depends_on"] + [d["on"] for d in task["inferred_deps"]])


def estimate(tasks, history):
    tasks = _tasks(tasks)
    _list(history, "history", 10000)
    _canonical(history)
    by_kind, seen = {}, set()
    for item in history:
        if type(item) is not dict:
            raise DtsError("history item must be a dictionary")
        identity = _label(item.get("task_id"), "history task_id")
        if identity in seen or item.get("kind") not in TASK_KINDS:
            raise DtsError("duplicate history task_id or unknown history kind")
        seen.add(identity)
        days = _number(item.get("actual_days"), "actual_days")
        by_kind.setdefault(item["kind"], []).append(dict(item, actual_days=days))
    out = []
    for task in tasks:
        comparables = sorted(by_kind.get(task["kind"], []), key=lambda h: h["task_id"])
        raw = {k: v for k, v in task.items() if k not in ("estimate", "estimation_blocker")}
        if len(comparables) < 2:
            raw.update(estimate=None, estimation_blocker=f"fewer than 2 comparable {task['kind']!r} tasks in history")
        else:
            quartiles = statistics.quantiles(sorted(h["actual_days"] for h in comparables),
                                             n=4, method="inclusive")
            raw["estimate"] = {"low_days": quartiles[0], "high_days": quartiles[2],
                "comparables": [h["task_id"] for h in comparables],
                "history_digest": _digest(comparables),
                "basis": f"inclusive p25..p75 of {len(comparables)} historical {task['kind']} tasks"}
        out.append(_seal(dict(raw, stage="estimated"), "task_digest"))
    _canonical(out)
    return out


def _cycles(tasks):
    adjacency = {t["task_id"]: _all_deps(t) for t in tasks}
    reverse = {key: [] for key in adjacency}
    for key, neighbors in adjacency.items():
        for neighbor in neighbors:
            reverse[neighbor].append(key)
    seen, order = set(), []
    for root in sorted(adjacency):
        if root in seen:
            continue
        stack = [(root, False)]
        while stack:
            node, expanded = stack.pop()
            if expanded:
                order.append(node)
            elif node not in seen:
                seen.add(node)
                stack.append((node, True))
                stack.extend((v, False) for v in reversed(adjacency[node]) if v not in seen)
    seen, result = set(), []
    for root in reversed(order):
        if root in seen:
            continue
        group, stack = [], [root]
        seen.add(root)
        while stack:
            node = stack.pop()
            group.append(node)
            for neighbor in reverse[node]:
                if neighbor not in seen:
                    seen.add(neighbor)
                    stack.append(neighbor)
        if len(group) > 1:
            result.append(sorted(group))
    return sorted(result)


def sequence_sprints(tasks, capacity_days, sprint_count_limit=26):
    tasks = _tasks(tasks, estimated=True)
    capacity = _number(capacity_days, "capacity_days", positive=True)
    if type(sprint_count_limit) is not int or not 0 <= sprint_count_limit <= 260:
        raise DtsError("sprint_count_limit must be an integer in 0..260")
    ready = {t["task_id"]: t for t in tasks if t["estimate"] is not None}
    blocked = [t["task_id"] for t in tasks if t["estimate"] is None]
    placed, sprints = {}, []
    while ready and len(sprints) < sprint_count_limit:
        entries, costs = [], []
        for identity in sorted(ready):
            task = ready[identity]
            if any(dep not in placed for dep in _all_deps(task)):
                continue
            cost = task["estimate"]["high_days"]
            if math.fsum(costs + [cost]) <= capacity:
                entries.append({"task_id": identity, "budgeted_days": cost})
                costs.append(cost)
        if not entries:
            break
        index = len(sprints) + 1
        for entry in entries:
            placed[entry["task_id"]] = index
            del ready[entry["task_id"]]
        sprints.append({"sprint": index, "tasks": entries, "load_days": math.fsum(costs),
                        "capacity_days": capacity})
    cycles = _cycles(tasks)
    cyclic = {identity for group in cycles for identity in group}
    reasons = {}
    for identity, task in sorted(ready.items()):
        pending = [d for d in _all_deps(task) if d not in placed]
        reasons[identity] = {"cycle_member": identity in cyclic,
            "pending_dependencies": pending,
            "exceeds_capacity": task["estimate"]["high_days"] > capacity,
            "sprint_limit_reached": len(sprints) >= sprint_count_limit}
    return _seal({"sprints": sprints, "unplaced_tasks": sorted(ready),
        "estimation_blockers": blocked, "dependency_cycles": cycles, "unplaced_reasons": reasons,
        "capacity_days": capacity, "sprint_count_limit": sprint_count_limit,
        "tasks_digest": _digest(tasks),
        "milestones": [{"milestone": f"M{s['sprint']}", "after_sprint": s["sprint"],
                        "delivers": [e["task_id"] for e in s["tasks"]]} for s in sprints],
        "draft": True, "human_decision_required": True,
        "note": "proposed sequence only; capacity and priorities are team decisions; dependencies complete in earlier sprints"},
        "plan_digest")


def _plan(plan, tasks):
    plan = _verify(plan, "plan_digest")
    if "capacity_days" not in plan or "sprint_count_limit" not in plan:
        raise DtsError("invalid plan")
    expected = sequence_sprints(tasks, plan["capacity_days"], plan["sprint_count_limit"])
    if expected != plan:
        raise DtsError("plan does not match these estimated tasks")
    return expected


def surface_tradeoffs(plan, tasks):
    plan = _plan(plan, tasks)
    items = [{"kind": "blocker", "subject": tid,
              "detail": "fewer than two distinct same-kind historical tasks; add comparable history"}
             for tid in plan["estimation_blockers"]]
    for tid in plan["unplaced_tasks"]:
        items.append({"kind": "blocker", "subject": tid, "evidence": plan["unplaced_reasons"][tid],
                      "detail": "review dependency cycles, pending dependencies, capacity and sprint limit"})
    for sprint in plan["sprints"]:
        utilization = sprint["load_days"] / sprint["capacity_days"]
        if utilization > .9:
            items.append({"kind": "trade-off", "subject": f"sprint {sprint['sprint']}",
                "detail": f"{round(utilization * 100)}% capacity planned — limited slack; consider lowering scope"})
    return items


def _delta_digest(delta):
    return _digest({k: v for k, v in delta.items()
                    if k not in ("delta_digest", "approved", "approved_by", "approvals")})


def prepare_tracker_preview(plan, tasks):
    tasks = _tasks(tasks, estimated=True)
    plan = _plan(plan, tasks)
    sprint_of = {e["task_id"]: s["sprint"] for s in plan["sprints"] for e in s["tasks"]}
    deltas = []
    for task in tasks:
        if task["task_id"] in sprint_of:
            delta = {k: task[k] for k in TEMPLATE_FIELDS}
            delta.update(op="create_or_update", sprint=sprint_of[task["task_id"]],
                         dependencies=_all_deps(task), budgeted_days=task["estimate"]["high_days"],
                         task_digest=task["task_digest"], plan_digest=plan["plan_digest"],
                         approved=False, approvals=[])
            delta["delta_digest"] = _delta_digest(delta)
            deltas.append(delta)
    return _seal({"schema": "dts/tracker-preview/v1", "dts_version": VERSION,
                  "plan_digest": plan["plan_digest"], "deltas": deltas, "dispatched": False,
                  "rule": "human review records only; identity is unverified and no tracker API exists"},
                 "preview_digest")


def approve_delta(preview, task_id, approval):
    preview = _verify(preview, "preview_digest")
    _label(task_id, "task_id")
    if preview.get("schema") != "dts/tracker-preview/v1" or preview.get("dispatched") is not False:
        raise DtsError("invalid preview")
    if type(approval) is not dict or approval.get("role") != "human":
        raise DtsError("a human review record is required")
    approver = _label(approval.get("approver"), "approver")
    seen, selected = set(), None
    for delta in _list(preview.get("deltas"), "deltas", 1000):
        if type(delta) is not dict:
            raise DtsError("invalid delta")
        identity = _label(delta.get("task_id"), "delta task_id")
        for field in TEMPLATE_FIELDS:
            (_label if field in ("task_id", "scope_item", "kind") else _text)(delta.get(field), field)
        if delta["kind"] not in TASK_KINDS or delta.get("op") != "create_or_update":
            raise DtsError("invalid delta kind or operation")
        if type(delta.get("sprint")) is not int or not 1 <= delta["sprint"] <= 260:
            raise DtsError("invalid delta sprint")
        _number(delta.get("budgeted_days"), "budgeted_days")
        _labels(delta.get("dependencies"), "dependencies")
        for field in ("task_digest", "plan_digest"):
            if type(delta.get(field)) is not str or not re.fullmatch(r"sha256:[0-9a-f]{64}", delta[field]):
                raise DtsError("invalid delta provenance")
        if delta["plan_digest"] != preview.get("plan_digest"):
            raise DtsError("mixed plan provenance")
        if identity in seen or delta.get("delta_digest") != _delta_digest(delta):
            raise DtsError("duplicate or changed delta")
        seen.add(identity)
        records = _list(delta.get("approvals"), "approvals", 100)
        if delta.get("approved") is not bool(records):
            raise DtsError("invalid approval state")
        for record in records:
            if (type(record) is not dict or record.get("role") != "human" or
                record.get("delta_digest") != delta["delta_digest"] or
                record.get("identity_verified") is not False):
                raise DtsError("invalid prior review record")
            _label(record.get("approver"), "prior approver")
        if records and delta.get("approved_by") != records[-1]["approver"]:
            raise DtsError("review attribution mismatch")
        if identity == task_id:
            selected = delta
    if selected is None:
        raise DtsError("no matching delta")
    if approval.get("delta_digest") != selected["delta_digest"]:
        raise DtsError("approval must cite the exact delta_digest")
    record = {"role": "human", "approver": approver,
              "delta_digest": selected["delta_digest"], "identity_verified": False}
    if record not in selected["approvals"]:
        if len(selected["approvals"]) >= 100:
            raise DtsError("review record limit reached")
        selected["approvals"].append(record)
        selected.update(approved=True, approved_by=approver)
    return _seal(preview, "preview_digest")
