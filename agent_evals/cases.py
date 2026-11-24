"""Cases: one JSON file per case, in one folder per suite run.

    {
      "id": "timer-basic",
      "title": "Sets a timer from a plain request",
      "suite": "regression",             # regression | safety | capability
      "input": {"text": "set a timer for 5 minutes"},   # or {"turns": ["...", "..."]}
      "state": {"timer_minutes": null},  # starting environment the agent sees (optional)
      "expect": {"says": {"contains": ["5 minutes"]}, "final_state": {"timer_minutes": 5}},
      "graders": ["says", "final_state"],
      "k": 3,                            # trials per case (optional, default 1)
      "pending": "feature not built yet" # optional: run it, report it, keep it out of the gates
    }
"""

import json
import os
import re

SUITES = ("regression", "safety", "capability")
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,63}$")
_KNOWN = {"id", "title", "suite", "input", "state", "expect", "graders", "k", "pending", "tags", "notes"}


class CaseError(Exception):
    pass


def check(case):
    """Problems with one case dict; an empty list means it is usable."""
    if not isinstance(case, dict):
        return ["case must be a JSON object"]
    errors = []
    cid = case.get("id")
    if not isinstance(cid, str) or not _ID.match(cid):
        errors.append("id must be 1-64 letters, digits, '_', '.', '-'")
    if case.get("suite") not in SUITES:
        errors.append("suite must be one of %s" % ", ".join(SUITES))
    inp = case.get("input")
    if not isinstance(inp, dict) or not (isinstance(inp.get("text"), str) or
                                         (isinstance(inp.get("turns"), list) and inp["turns"])):
        errors.append("input needs a 'text' string or a non-empty 'turns' list")
    graders = case.get("graders")
    if not isinstance(graders, list) or not graders or not all(isinstance(g, str) for g in graders):
        errors.append("graders must be a non-empty list of grader names")
    if "expect" in case and not isinstance(case["expect"], dict):
        errors.append("expect must be an object")
    if "state" in case and not isinstance(case["state"], dict):
        errors.append("state must be an object")
    k = case.get("k", 1)
    if not isinstance(k, int) or isinstance(k, bool) or k < 1:
        errors.append("k must be a whole number >= 1")
    if "pending" in case and not isinstance(case["pending"], str):
        errors.append("pending must be a short string saying what is missing")
    extra = sorted(set(case) - _KNOWN)
    if extra:
        errors.append("unknown keys: %s" % ", ".join(extra))
    return errors


def load_file(path):
    with open(path, encoding="utf-8") as f:
        try:
            case = json.load(f)
        except ValueError as e:
            raise CaseError("%s: not valid JSON (%s)" % (os.path.basename(path), e))
    errors = check(case)
    if errors:
        raise CaseError("%s: %s" % (os.path.basename(path), "; ".join(errors)))
    case.setdefault("k", 1)
    case.setdefault("state", {})
    case.setdefault("expect", {})
    return case


def load_dir(folder):
    """All *.json cases in a folder, sorted by id. Raises CaseError on the first bad file or a duplicate id."""
    if not os.path.isdir(folder):
        raise CaseError("no such folder: %s" % folder)
    out = [load_file(os.path.join(folder, name)) for name in sorted(os.listdir(folder)) if name.endswith(".json")]
    seen = set()
    for c in out:
        if c["id"] in seen:
            raise CaseError("duplicate case id: %s" % c["id"])
        seen.add(c["id"])
    return sorted(out, key=lambda c: c["id"])


def select(cases, suite=None, ids=None):
    out = cases
    if suite and suite != "all":
        out = [c for c in out if c["suite"] == suite]
    if ids:
        want = {x.strip() for x in ids.split(",") if x.strip()}
        out = [c for c in out if c["id"] in want]
    return out
