"""Report: gates plus a one-page Markdown summary and a machine-readable results.json.

Gates (pending cases are run and reported but never gated):
  regression  every case passes all k trials (pass^k); up to `waivers` may miss
  safety      zero cases that are not pass^k - a fail, an unknown, or an error all block
  capability  no gate; watch the trend
"""

import json
import os


def _live(results, suite):
    return [r for r in results if r["suite"] == suite and not r.get("pending")]


def gates(results, waivers=0):
    reg = _live(results, "regression")
    saf = _live(results, "safety")
    cap = _live(results, "capability")
    reg_miss = [r["id"] for r in reg if not r["pass_k"]]
    saf_miss = [r["id"] for r in saf if not r["pass_k"]]
    out = {
        "regression": {"cases": len(reg), "missed": reg_miss, "waivers": waivers,
                       "ok": len(reg_miss) <= waivers},
        "safety": {"cases": len(saf), "violations": [r["id"] for r in saf if r["status"] in ("fail", "error")],
                   "unknown": [r["id"] for r in saf if r["status"] == "unknown"], "ok": not saf_miss},
        "capability": {"cases": len(cap), "pass_k": sum(1 for r in cap if r["pass_k"]), "gated": False},
    }
    out["ok"] = out["regression"]["ok"] and out["safety"]["ok"]
    return out


def _mark(r):
    return {"pass": "PASS", "fail": "FAIL", "unknown": "UNKNOWN", "error": "ERROR"}[r["status"]]


def _why(r, limit=3):
    seen = []
    for t in r["trials"]:
        if t["status"] != "ran":
            msg = "trial %d %s: %s" % (t["trial"], t["status"], t.get("error") or "")
            if msg not in seen:
                seen.append(msg)
            continue
        for g in t["graders"]:
            if g["pass"] is not True:
                msg = "%s: %s" % (g["name"], g["detail"])
                if msg not in seen:
                    seen.append(msg)
    return "; ".join(seen[:limit]) or "-"


def markdown(results, meta, gate):
    lines = ["# Eval summary", ""]
    lines.append("Agent: `%s` - cases: %d - started: %s" % (meta.get("agent"), len(results), meta.get("started")))
    lines.append("")
    reg, saf, cap = gate["regression"], gate["safety"], gate["capability"]
    lines.append("**Gates: %s**" % ("PASS" if gate["ok"] else "FAIL"))
    lines.append("")
    lines.append("- regression: %d/%d pass^k%s - %s" % (
        reg["cases"] - len(reg["missed"]), reg["cases"],
        " (waivers allowed: %d)" % reg["waivers"] if reg["waivers"] else "", "ok" if reg["ok"] else "FAIL"))
    lines.append("- safety: %d/%d pass^k - %d violation(s), %d unknown - %s" % (
        saf["cases"] - len(saf["violations"]) - len(saf["unknown"]), saf["cases"],
        len(saf["violations"]), len(saf["unknown"]), "ok" if saf["ok"] else "FAIL"))
    lines.append("- capability: %d/%d pass^k (not gated, watch the trend)" % (cap["pass_k"], cap["cases"]))
    trials = sum(len(r["trials"]) for r in results)
    t_pass = sum(r["n_pass"] for r in results)
    lines.append("- trials: %d run, %d passed, %d failed, %d unknown, %d errors" % (
        trials, t_pass, sum(r["n_fail"] for r in results), sum(r["n_unknown"] for r in results),
        sum(r["n_error"] for r in results)))

    missing = [r for r in results if not r["pass_k"] and not r.get("pending")]
    if missing:
        lines += ["", "## Not passing", ""]
        for r in missing:
            lines.append("- **%s** (%s, %s, %d/%d trials passed): %s" % (
                r["id"], r["suite"], _mark(r), r["n_pass"], r["k"], _why(r)))
    pend = [r for r in results if r.get("pending")]
    if pend:
        lines += ["", "## Pending (baseline only, not gated)", ""]
        for r in pend:
            lines.append("- %s: %s - now %s" % (r["id"], r["pending"], _mark(r)))

    lines += ["", "## All cases", "", "| id | suite | trials | pass | fail | unknown | error | pass^k | title |",
              "|---|---|---|---|---|---|---|---|---|"]
    for r in results:
        lines.append("| %s | %s | %d | %d | %d | %d | %d | %s | %s |" % (
            r["id"], r["suite"] + (" (pending)" if r.get("pending") else ""), r["k"], r["n_pass"], r["n_fail"],
            r["n_unknown"], r["n_error"], _mark(r), r["title"].replace("|", "/")))
    return "\n".join(lines) + "\n"


def write(out_dir, results, meta, waivers=0):
    """Write results.json and summary.md into out_dir; return the gates dict."""
    os.makedirs(out_dir, exist_ok=True)
    gate = gates(results, waivers)
    with open(os.path.join(out_dir, "results.json"), "w", encoding="utf-8") as f:
        json.dump({"meta": meta, "gates": gate, "results": results}, f, ensure_ascii=False, indent=1, sort_keys=True)
        f.write("\n")
    with open(os.path.join(out_dir, "summary.md"), "w", encoding="utf-8") as f:
        f.write(markdown(results, meta, gate))
    return gate
