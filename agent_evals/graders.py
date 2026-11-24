"""Graders: small functions that look at one trial and say pass, fail, or unknown.

Every grader has the same shape:

    grade(events, case, outcome, ctx) -> {"pass": True | False | None, "detail": "..."}

``pass: None`` means *unknown*: the grader could not decide (no judge configured,
the case did not say what to expect, ...). Unknown is counted on its own; it is
neither a pass nor a fail. Prefer code graders; use the model-judged ``rubric``
grader only for what code cannot check.

Add your own with the ``register`` decorator:

    from agent_evals.graders import register

    @register("no_emoji")
    def no_emoji(events, case, outcome, ctx):
        ...
"""

import fnmatch
import re

from . import transcript as T

GRADERS = {}


def register(name):
    def wrap(fn):
        GRADERS[name] = fn
        return fn
    return wrap


def _want(case, key):
    return (case.get("expect") or {}).get(key)


def _result(problems, ok_detail):
    return {"pass": not problems, "detail": "; ".join(problems) if problems else ok_detail}


def is_question(text):
    return text.rstrip().endswith("?")


@register("says")
def says(events, case, outcome, ctx):
    """expect.says: contains (all of), contains_any, not_contains, regex, asks_question, max_chars, any.
    Matching is case-insensitive over everything the agent said."""
    want = _want(case, "says")
    if not want:
        return {"pass": None, "detail": "case has no expect.says"}
    said = T.messages(events, "agent")
    joined = "\n".join(said).lower()
    bad = []
    if want.get("any") and not said:
        bad.append("agent said nothing")
    for w in want.get("contains") or []:
        if w.lower() not in joined:
            bad.append("missing %r" % w)
    any_of = want.get("contains_any") or []
    if any_of and not any(w.lower() in joined for w in any_of):
        bad.append("none of %r" % any_of)
    for w in want.get("not_contains") or []:
        if w.lower() in joined:
            bad.append("should not say %r" % w)
    if want.get("regex") and not any(re.search(want["regex"], s, re.I) for s in said):
        bad.append("no message matches /%s/" % want["regex"])
    if want.get("asks_question") and not any(is_question(s) for s in said):
        bad.append("never asked a question")
    limit = want.get("max_chars")
    if limit is not None:
        long_ones = [s for s in said if len(s) > limit]
        if long_ones:
            bad.append("%d message(s) longer than %d chars" % (len(long_ones), limit))
    return _result(bad, "said %d message(s)" % len(said))


@register("forbidden_tools")
def forbidden_tools(events, case, outcome, ctx):
    """expect.forbidden_tools: glob patterns over tool paths ('name' or 'name:target').
    A call counts even if it was a dry run: the agent *would* have done it."""
    pats = _want(case, "forbidden_tools")
    if not pats:
        return {"pass": None, "detail": "case has no expect.forbidden_tools"}
    if isinstance(pats, str):
        pats = [pats]
    paths = [T.tool_path(c) for c in T.tool_calls(events)]
    hits = ["%s ~ %s" % (p, pat) for p in paths for pat in pats if fnmatch.fnmatchcase(p, pat)]
    return _result(["forbidden call: " + h for h in hits], "%d tool call(s), none forbidden" % len(paths))


def _subset(want, got):
    if isinstance(want, dict):
        return isinstance(got, dict) and all(k in got and _subset(v, got[k]) for k, v in want.items())
    return want == got


@register("tool_args")
def tool_args(events, case, outcome, ctx):
    """expect.tool_args: list of {"name": ..., "args": {...}}; each must match at least one call
    (args compared as a subset, so extra arguments are fine)."""
    want = _want(case, "tool_args")
    if not want:
        return {"pass": None, "detail": "case has no expect.tool_args"}
    calls = T.tool_calls(events)
    bad = []
    for w in want:
        if not any(c["name"] == w.get("name") and _subset(w.get("args") or {}, c.get("args") or {}) for c in calls):
            bad.append("no call like %s %s" % (w.get("name"), w.get("args") or {}))
    return _result(bad, "all %d expected call(s) found" % len(want))


@register("final_state")
def final_state(events, case, outcome, ctx):
    """expect.final_state: {key: value} that must hold in outcome["state"] after the trial,
    or the string "unchanged" (end state must equal the case's starting state).
    Judges what the world looks like, not what the agent claims."""
    want = _want(case, "final_state")
    if want is None:
        return {"pass": None, "detail": "case has no expect.final_state"}
    got = (outcome or {}).get("state")
    if not isinstance(got, dict):
        return {"pass": None, "detail": "agent returned no outcome.state"}
    if want == "unchanged":
        before = case.get("state") or {}
        changed = sorted(k for k in set(before) | set(got) if before.get(k) != got.get(k))
        return _result(["changed: " + ", ".join(changed)] if changed else [], "state unchanged")
    bad = ["%s is %r, expected %r" % (k, got.get(k), v) for k, v in want.items() if got.get(k) != v]
    return _result(bad, "%d key(s) as expected" % len(want))


@register("turns")
def turns(events, case, outcome, ctx):
    """expect.turns: max_messages (agent messages), max_questions, max_tool_calls."""
    want = _want(case, "turns")
    if not want:
        return {"pass": None, "detail": "case has no expect.turns"}
    said = T.messages(events, "agent")
    counts = {"max_messages": len(said), "max_questions": sum(1 for s in said if is_question(s)),
              "max_tool_calls": len(T.tool_calls(events))}
    bad = ["%s: %d > %d" % (k, counts[k], v) for k, v in want.items() if k in counts and counts[k] > v]
    return _result(bad, ", ".join("%s=%d" % kv for kv in sorted(counts.items())))


@register("latency")
def latency(events, case, outcome, ctx):
    """expect.latency: {"max_ms": N}. Uses outcome["ms_total"] if the agent reports it,
    otherwise the sum of the events' ms."""
    want = _want(case, "latency")
    if not want:
        return {"pass": None, "detail": "case has no expect.latency"}
    ms = (outcome or {}).get("ms_total")
    if not isinstance(ms, (int, float)):
        ms = T.total_ms(events)
    if not ms:
        return {"pass": None, "detail": "no timing in transcript"}
    return _result(["took %d ms > %d ms" % (ms, want["max_ms"])] if ms > want["max_ms"] else [], "took %d ms" % ms)


@register("rubric")
def rubric(events, case, outcome, ctx):
    """expect.rubric: {"criteria": ["...", ...], "min_score": 4}. Calls ctx["judge"](criterion, said_text)
    which returns a score 1-5 or None. No judge configured -> unknown, never a silent pass."""
    want = _want(case, "rubric")
    if not want or not want.get("criteria"):
        return {"pass": None, "detail": "case has no expect.rubric.criteria"}
    judge = (ctx or {}).get("judge")
    if judge is None:
        return {"pass": None, "detail": "no judge configured"}
    text = "\n".join(T.messages(events, "agent"))
    floor = want.get("min_score", 4)
    scores, bad, unknown = [], [], []
    for crit in want["criteria"]:
        s = judge(crit, text)
        scores.append("%s=%s" % (crit, s))
        if s is None:
            unknown.append(crit)
        elif s < floor:
            bad.append("%s scored %s < %s" % (crit, s, floor))
    if bad:
        return {"pass": False, "detail": "; ".join(bad)}
    if unknown:
        return {"pass": None, "detail": "judge could not score: " + ", ".join(unknown)}
    return {"pass": True, "detail": ", ".join(scores)}


def run_all(names, events, case, outcome, ctx=None):
    """Run several graders on one trial. An unknown name or a grader that crashes counts as a fail."""
    out = []
    for name in names:
        fn = GRADERS.get(name)
        if fn is None:
            r = {"pass": False, "detail": "no grader named %r" % name}
        else:
            try:
                r = dict(fn(events, case, outcome, ctx or {}))
            except Exception as e:  # a grader bug must not look like a pass
                r = {"pass": False, "detail": "grader crashed: %s: %s" % (type(e).__name__, e)}
        r["name"] = name
        out.append(r)
    return out


def combine(results):
    """One trial's verdict: any fail -> False; else any unknown -> None; all pass -> True; nothing -> None."""
    if not results:
        return None
    if any(r["pass"] is False for r in results):
        return False
    if any(r["pass"] is None for r in results):
        return None
    return True
