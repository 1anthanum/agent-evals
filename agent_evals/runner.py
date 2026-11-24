"""Runner: run each case k times against an agent and grade every trial.

An *agent* is any callable you point the runner at:

    def agent(inp, state, trial):
        # inp:   the case's "input" dict ({"text": ...} or {"turns": [...]})
        # state: a fresh deep copy of the case's "state" - mutate it to show what changed
        # trial: 1..k, so a seeded fake can vary between trials
        return {"events": [...], "outcome": {"state": state}}

Wrap your real system (an HTTP call, a CLI, a test double) in a function like this.
"""

import copy
import importlib

from . import graders as G
from . import transcript as T


def load_agent(spec):
    """'package.module:attr' -> the callable."""
    mod_name, _, attr = spec.partition(":")
    if not mod_name or not attr:
        raise ValueError("agent must look like module:function, got %r" % spec)
    fn = getattr(importlib.import_module(mod_name), attr)
    if not callable(fn):
        raise ValueError("%s is not callable" % spec)
    return fn


def run_trial(case, agent, n, ctx=None):
    rec = {"trial": n, "status": "ran", "verdict": None, "graders": [], "error": None}
    try:
        got = agent(copy.deepcopy(case["input"]), copy.deepcopy(case.get("state") or {}), n)
        events = (got or {}).get("events")
        outcome = (got or {}).get("outcome") or {}
    except Exception as e:  # the agent failing is a result, not a crash of the run
        rec.update(status="error", error="%s: %s" % (type(e).__name__, e))
        return rec, []
    problems = T.validate(events)
    if problems:
        rec.update(status="bad_transcript", error="; ".join(problems[:3]))
        return rec, events if isinstance(events, list) else []
    rec["graders"] = G.run_all(case["graders"], events, case, outcome, ctx)
    rec["verdict"] = G.combine(rec["graders"])
    rec["ms"] = outcome.get("ms_total") if isinstance(outcome.get("ms_total"), (int, float)) else T.total_ms(events)
    return rec, events


def run_case(case, agent, k=None, ctx=None, keep=None):
    """Run one case k times. keep(case_id, trial, events) is called with each transcript if given."""
    k = k or case.get("k", 1)
    trials = []
    for n in range(1, k + 1):
        rec, events = run_trial(case, agent, n, ctx)
        if keep is not None and events:
            keep(case["id"], n, events)
        trials.append(rec)
    ran = [t for t in trials if t["status"] == "ran"]
    n_pass = sum(1 for t in ran if t["verdict"] is True)
    n_fail = sum(1 for t in ran if t["verdict"] is False)
    n_unknown = sum(1 for t in ran if t["verdict"] is None)
    errors = len(trials) - len(ran)
    if errors:
        status = "error"
    elif n_fail:
        status = "fail"
    elif n_unknown:
        status = "unknown"
    else:
        status = "pass"
    return {"id": case["id"], "title": case.get("title", ""), "suite": case["suite"], "pending": case.get("pending"),
            "k": k, "n_pass": n_pass, "n_fail": n_fail, "n_unknown": n_unknown, "n_error": errors,
            "pass_k": status == "pass", "status": status, "trials": trials}


def run_all(cases, agent, k=None, ctx=None, keep=None):
    return [run_case(c, agent, k, ctx, keep) for c in cases]
