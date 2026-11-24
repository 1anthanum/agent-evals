"""Command line.

    python -m agent_evals list  CASES_DIR
    python -m agent_evals check CASES_DIR
    python -m agent_evals run   CASES_DIR --agent module:function [--k N] [--suite S] [--ids a,b]
                                [--out DIR] [--waivers N] [--keep-transcripts] [--started TEXT]

Exit codes for `run`: 0 gates pass, 1 gates fail, 2 bad cases or usage.
"""

import argparse
import datetime
import os
import sys

from . import __version__
from . import cases as C
from . import report as R
from . import runner
from . import transcript as T


def _load(folder):
    try:
        return C.load_dir(folder)
    except C.CaseError as e:
        print("bad cases: %s" % e, file=sys.stderr)
        return None


def cmd_list(args):
    cases = _load(args.cases)
    if cases is None:
        return 2
    for c in C.select(cases, args.suite, args.ids):
        print("%-24s %-11s k=%d  %s%s" % (c["id"], c["suite"], c["k"], c.get("title", ""),
                                          "  [pending: %s]" % c["pending"] if c.get("pending") else ""))
    return 0


def cmd_check(args):
    cases = _load(args.cases)
    if cases is None:
        return 2
    from .graders import GRADERS
    unknown = sorted({g for c in cases for g in c["graders"] if g not in GRADERS})
    if unknown:
        print("cases use graders that are not registered: %s" % ", ".join(unknown), file=sys.stderr)
        return 2
    print("%d case(s) OK" % len(cases))
    return 0


def cmd_run(args):
    cases = _load(args.cases)
    if cases is None:
        return 2
    if args.k is not None and args.k < 1:
        print("--k must be >= 1", file=sys.stderr)
        return 2
    picked = C.select(cases, args.suite, args.ids)
    if not picked:
        print("no cases selected", file=sys.stderr)
        return 2
    if os.getcwd() not in sys.path:
        sys.path.insert(0, os.getcwd())          # so --agent can name a module in the current folder
    try:
        agent = runner.load_agent(args.agent)
    except (ImportError, AttributeError, ValueError) as e:
        print("cannot load agent: %s" % e, file=sys.stderr)
        return 2
    keep = None
    if args.keep_transcripts:
        tdir = os.path.join(args.out, "transcripts")
        os.makedirs(tdir, exist_ok=True)

        def keep(cid, n, events):
            T.write_jsonl(os.path.join(tdir, "%s_t%d.jsonl" % (cid, n)), events)
    started = args.started or datetime.datetime.now().isoformat(timespec="seconds")
    results = runner.run_all(picked, agent, args.k, {}, keep)
    meta = {"tool": "agent-evals %s" % __version__, "agent": args.agent, "started": started,
            "k_override": args.k, "suite": args.suite, "ids": args.ids}
    gate = R.write(args.out, results, meta, args.waivers)
    for r in results:
        print("%-8s %-24s %-11s %d/%d%s" % (r["status"].upper(), r["id"], r["suite"], r["n_pass"], r["k"],
                                            "  (pending)" if r.get("pending") else ""))
    print("gates: %s -> %s" % ("PASS" if gate["ok"] else "FAIL", os.path.join(args.out, "summary.md")))
    return 0 if gate["ok"] else 1


def main(argv=None):
    ap = argparse.ArgumentParser(prog="agent_evals", description="Small, file-based evals for AI agents.")
    ap.add_argument("--version", action="version", version="agent-evals %s" % __version__)
    sub = ap.add_subparsers(dest="cmd")
    for name in ("list", "check", "run"):
        p = sub.add_parser(name)
        p.add_argument("cases", help="folder of *.json case files")
        p.add_argument("--suite", default="all", choices=("all",) + C.SUITES)
        p.add_argument("--ids", help="comma-separated case ids")
        if name == "run":
            p.add_argument("--agent", required=True, help="module:function to evaluate")
            p.add_argument("--k", type=int, help="trials per case (overrides each case's k)")
            p.add_argument("--out", default="runs/latest", help="where summary.md and results.json go")
            p.add_argument("--waivers", type=int, default=0, help="regression cases allowed to miss")
            p.add_argument("--keep-transcripts", action="store_true", help="also write every trial's transcript")
            p.add_argument("--started", help="fixed timestamp text for reproducible reports")
    args = ap.parse_args(argv)
    if args.cmd is None:
        ap.print_help()
        return 2
    return {"list": cmd_list, "check": cmd_check, "run": cmd_run}[args.cmd](args)
