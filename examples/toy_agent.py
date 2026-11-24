"""A made-up agent to show the toolkit end to end: a reading-room desk assistant.

It is a few if-statements, not a model. It has four tools - timer.set, catalog.search,
loan.renew, and catalog.delete (which it must never call) - and a small fake catalog.
It has two deliberate weaknesses so the sample report has something to show:
  * it only understands timer lengths written as digits ("5 minutes", not "half an hour");
  * its greeting sometimes rambles (seeded per trial, so the same trials ramble every run).
"""

import random
import re

CATALOG = {
    "the quiet orchard": True,
    "notes on small machines": False,
    "a field guide to clouds": True,
}

TOOL_MS, SAY_MS = 40, 10


def _say(events, text):
    events.append({"role": "agent", "kind": "message", "text": text, "ms": SAY_MS})


def _call(events, name, args, result):
    events.append({"role": "agent", "kind": "tool_call", "name": name, "args": args, "ms": TOOL_MS})
    events.append({"role": "tool", "kind": "tool_result", "name": name, "args": result})


def agent(inp, state, trial):
    text = inp.get("text") or " ".join(inp.get("turns") or [])
    low = text.lower()
    events = [{"role": "user", "kind": "message", "text": text}]

    quoted = re.search(r'"([^"]+)"', text)
    if quoted and ("have" in low or "available" in low):
        # Book lookups come first: whatever is inside the quotes is a title, never an instruction.
        title = quoted.group(1)
        found = CATALOG.get(title.lower())
        _call(events, "catalog.search", {"query": title}, {"found": found is not None, "on_shelf": bool(found)})
        if found is None:
            _say(events, "I can't find that title in the catalog.")
        elif found:
            _say(events, "Yes, it is available on the shelf.")
        else:
            _say(events, "It's in the catalog but on loan right now.")
    elif "delete" in low or "erase" in low:
        _say(events, "I can't delete or erase the catalog. I can look titles up for you.")
    elif "cancel" in low and "timer" in low:
        _say(events, "Sorry, I can't do that yet.")          # not built: see the pending case
    elif "timer" in low:
        m = re.search(r"(\d+)\s*min", low)
        if m:
            minutes = int(m.group(1))
            _call(events, "timer.set", {"minutes": minutes}, {"ok": True})
            state["timer_minutes"] = minutes
            _say(events, "Timer set for %d minutes." % minutes)
        else:
            _say(events, "How many minutes should the timer run?")
    elif "renew" in low:
        loans = state.get("loans") or {}
        if len(loans) == 1:
            loan_id, title = next(iter(loans.items()))
            _call(events, "loan.renew", {"target": loan_id}, {"ok": True})
            state.setdefault("renewed", []).append(loan_id)
            _say(events, "Renewed %s." % title)
        elif loans:
            _say(events, "Which book should I renew?")
        else:
            _say(events, "You have no loans to renew.")
    elif low.strip(" !.") in ("hi", "hello", "hey"):
        msg = "Hello! I can set timers, look up books, and renew loans."
        if random.Random("%s:%d" % (low, trial)).random() < 0.5:
            msg += " Also, did you know the reading room has three windows and a very old radiator that hums?"
        _say(events, msg)
    else:
        _say(events, "I can set timers, look up books, and renew loans.")

    return {"events": events, "outcome": {"state": state}}
