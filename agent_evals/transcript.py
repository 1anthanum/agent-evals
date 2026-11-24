"""Transcripts: the one record format every grader reads.

A transcript is a list of events (plain dicts). One event is one thing that
happened during a trial:

    {"role": "user",  "kind": "message",   "text": "set a timer for 5 minutes"}
    {"role": "agent", "kind": "tool_call", "name": "timer.set", "args": {"minutes": 5}, "ms": 40}
    {"role": "tool",  "kind": "tool_result", "name": "timer.set", "args": {"ok": true}}
    {"role": "agent", "kind": "message",   "text": "Timer set for 5 minutes.", "ms": 12}

Required keys: role, kind. Optional: text (str), name (str, tool calls/results),
args (dict), ms (number, how long this step took). Unknown keys are allowed and
ignored by the built-in graders.
"""

import json

ROLES = ("user", "agent", "tool", "system")
KINDS = ("message", "tool_call", "tool_result", "note")


def validate(events):
    """Return a list of problems; an empty list means the transcript is usable."""
    if not isinstance(events, list):
        return ["transcript must be a list of events, got %s" % type(events).__name__]
    errors = []
    for i, ev in enumerate(events):
        where = "event %d" % i
        if not isinstance(ev, dict):
            errors.append("%s: not an object" % where)
            continue
        if ev.get("role") not in ROLES:
            errors.append("%s: role must be one of %s" % (where, ", ".join(ROLES)))
        if ev.get("kind") not in KINDS:
            errors.append("%s: kind must be one of %s" % (where, ", ".join(KINDS)))
        if "text" in ev and ev["text"] is not None and not isinstance(ev["text"], str):
            errors.append("%s: text must be a string" % where)
        if "args" in ev and not isinstance(ev["args"], dict):
            errors.append("%s: args must be an object" % where)
        if "ms" in ev and ev["ms"] is not None and not isinstance(ev["ms"], (int, float)):
            errors.append("%s: ms must be a number" % where)
        if ev.get("kind") in ("tool_call", "tool_result") and not isinstance(ev.get("name"), str):
            errors.append("%s: %s needs a name" % (where, ev.get("kind")))
    return errors


def messages(events, role="agent"):
    """Texts of the messages sent by one role, in order."""
    return [ev.get("text") or "" for ev in events if ev.get("role") == role and ev.get("kind") == "message"]


def tool_calls(events):
    return [ev for ev in events if ev.get("kind") == "tool_call"]


def tool_path(call):
    """'name' or 'name:target' when the call has args.target - what forbidden_tools patterns match."""
    target = (call.get("args") or {}).get("target")
    return call["name"] if target in (None, "") else "%s:%s" % (call["name"], target)


def total_ms(events):
    return sum(ev["ms"] for ev in events if isinstance(ev.get("ms"), (int, float)))


def write_jsonl(path, events):
    with open(path, "w", encoding="utf-8") as f:
        for ev in events:
            f.write(json.dumps(ev, ensure_ascii=False, sort_keys=True) + "\n")


def read_jsonl(path):
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]
