"""Tests for agent-evals. Run from the repo root: python -m unittest discover -s tests"""

import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from agent_evals import cases as C  # noqa: E402
from agent_evals import cli  # noqa: E402
from agent_evals import graders as G  # noqa: E402
from agent_evals import report as R  # noqa: E402
from agent_evals import runner  # noqa: E402
from agent_evals import transcript as T  # noqa: E402

EXAMPLES = os.path.join(ROOT, "examples", "cases")
SAMPLE = os.path.join(ROOT, "examples", "sample-report")


def case(**kw):
    base = {"id": "c1", "suite": "regression", "input": {"text": "hi"}, "graders": ["says"], "k": 1,
            "state": {}, "expect": {}}
    base.update(kw)
    return base


def said(*texts):
    return [{"role": "agent", "kind": "message", "text": t} for t in texts]


def call(name, **args):
    return {"role": "agent", "kind": "tool_call", "name": name, "args": args}


def quiet(fn, *a):
    out, err = io.StringIO(), io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        rc = fn(*a)
    return rc, out.getvalue(), err.getvalue()


class TestCases(unittest.TestCase):
    def test_examples_load_sorted(self):
        cs = C.load_dir(EXAMPLES)
        self.assertEqual(len(cs), 10)
        self.assertEqual([c["id"] for c in cs], sorted(c["id"] for c in cs))

    def test_check_reports_each_problem(self):
        errs = C.check({"id": "bad id!", "suite": "nope", "input": {}, "graders": [], "k": 0, "extra": 1})
        self.assertEqual(len(errs), 6)

    def test_duplicate_id_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            for name in ("a.json", "b.json"):
                with open(os.path.join(d, name), "w") as f:
                    json.dump(case(id="same"), f)
            with self.assertRaises(C.CaseError):
                C.load_dir(d)

    def test_defaults_filled(self):
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "a.json"), "w") as f:
                json.dump({"id": "a", "suite": "safety", "input": {"turns": ["x"]}, "graders": ["says"]}, f)
            c = C.load_dir(d)[0]
        self.assertEqual((c["k"], c["state"], c["expect"]), (1, {}, {}))


class TestTranscript(unittest.TestCase):
    def test_valid(self):
        self.assertEqual(T.validate(said("ok") + [call("x.y")]), [])

    def test_invalid(self):
        errs = T.validate([{"role": "robot", "kind": "message"}, {"role": "agent", "kind": "tool_call"}, "x"])
        self.assertEqual(len(errs), 3)
        self.assertTrue(T.validate("not a list"))

    def test_tool_path(self):
        self.assertEqual(T.tool_path(call("loan.renew", target="L-1")), "loan.renew:L-1")
        self.assertEqual(T.tool_path(call("timer.set", minutes=5)), "timer.set")


class TestGraders(unittest.TestCase):
    def g(self, name, events, expect, outcome=None, state=None, ctx=None):
        return G.GRADERS[name](events, case(expect=expect, state=state or {}), outcome or {}, ctx or {})

    def test_says(self):
        ev = said("Timer set for 5 minutes.")
        self.assertTrue(self.g("says", ev, {"says": {"contains": ["5 MINUTES"]}})["pass"])
        self.assertFalse(self.g("says", ev, {"says": {"not_contains": ["timer"]}})["pass"])
        self.assertFalse(self.g("says", ev, {"says": {"asks_question": True}})["pass"])
        self.assertFalse(self.g("says", ev, {"says": {"max_chars": 10}})["pass"])
        self.assertTrue(self.g("says", ev, {"says": {"regex": r"\d+ minutes"}})["pass"])
        self.assertIsNone(self.g("says", ev, {})["pass"])

    def test_forbidden_tools_counts_dry_runs(self):
        ev = [call("catalog.delete", dry_run=True)]
        r = self.g("forbidden_tools", ev, {"forbidden_tools": ["catalog.delete*"]})
        self.assertFalse(r["pass"])
        self.assertTrue(self.g("forbidden_tools", [call("catalog.search")], {"forbidden_tools": "catalog.delete*"})["pass"])

    def test_tool_args_subset(self):
        ev = [call("timer.set", minutes=5, label="tea")]
        self.assertTrue(self.g("tool_args", ev, {"tool_args": [{"name": "timer.set", "args": {"minutes": 5}}]})["pass"])
        self.assertFalse(self.g("tool_args", ev, {"tool_args": [{"name": "timer.set", "args": {"minutes": 6}}]})["pass"])

    def test_final_state(self):
        self.assertTrue(self.g("final_state", [], {"final_state": {"a": 1}}, {"state": {"a": 1, "b": 2}})["pass"])
        self.assertFalse(self.g("final_state", [], {"final_state": "unchanged"}, {"state": {"a": 2}}, {"a": 1})["pass"])
        self.assertTrue(self.g("final_state", [], {"final_state": "unchanged"}, {"state": {"a": 1}}, {"a": 1})["pass"])
        self.assertIsNone(self.g("final_state", [], {"final_state": {"a": 1}}, {})["pass"])

    def test_turns_and_latency(self):
        ev = said("Which one?", "Or this?") + [dict(call("x"), ms=900)]
        self.assertFalse(self.g("turns", ev, {"turns": {"max_questions": 1}})["pass"])
        self.assertFalse(self.g("latency", ev, {"latency": {"max_ms": 500}})["pass"])
        self.assertTrue(self.g("latency", ev, {"latency": {"max_ms": 500}}, {"ms_total": 100})["pass"])
        self.assertIsNone(self.g("latency", said("x"), {"latency": {"max_ms": 500}})["pass"])

    def test_rubric_without_judge_is_unknown(self):
        exp = {"rubric": {"criteria": ["friendly"]}}
        self.assertIsNone(self.g("rubric", said("hello"), exp)["pass"])
        self.assertTrue(self.g("rubric", said("hello"), exp, ctx={"judge": lambda c, t: 5})["pass"])
        self.assertFalse(self.g("rubric", said("hello"), exp, ctx={"judge": lambda c, t: 2})["pass"])
        self.assertIsNone(self.g("rubric", said("hello"), exp, ctx={"judge": lambda c, t: None})["pass"])

    def test_unknown_name_and_crash_fail(self):
        @G.register("_boom")
        def boom(*a):
            raise RuntimeError("bug")
        try:
            rs = G.run_all(["nope", "_boom"], [], case(), {})
        finally:
            G.GRADERS.pop("_boom")
        self.assertEqual([r["pass"] for r in rs], [False, False])
        self.assertIn("crashed", rs[1]["detail"])

    def test_combine(self):
        self.assertIs(G.combine([{"pass": True}, {"pass": None}]), None)
        self.assertIs(G.combine([{"pass": None}, {"pass": False}]), False)
        self.assertIs(G.combine([{"pass": True}]), True)
        self.assertIs(G.combine([]), None)


class TestRunner(unittest.TestCase):
    def test_pass_k_needs_every_trial(self):
        def flaky(inp, state, trial):
            return {"events": said("ok" if trial != 2 else "no"), "outcome": {}}
        r = runner.run_case(case(expect={"says": {"contains": ["ok"]}}, k=3), flaky)
        self.assertEqual((r["n_pass"], r["n_fail"], r["pass_k"], r["status"]), (2, 1, False, "fail"))

    def test_agent_error_and_bad_transcript(self):
        def broken(inp, state, trial):
            raise ValueError("down")
        r = runner.run_case(case(k=2), broken)
        self.assertEqual((r["status"], r["n_error"]), ("error", 2))
        r = runner.run_case(case(), lambda i, s, t: {"events": [{"role": "agent"}]})
        self.assertEqual(r["trials"][0]["status"], "bad_transcript")

    def test_state_is_fresh_each_trial(self):
        seen = []

        def mutate(inp, state, trial):
            seen.append(dict(state))
            state["n"] = state.get("n", 0) + 1
            return {"events": said("x"), "outcome": {"state": state}}
        c = case(state={"n": 0}, k=3)
        runner.run_case(c, mutate)
        self.assertEqual(seen, [{"n": 0}] * 3)
        self.assertEqual(c["state"], {"n": 0})

    def test_load_agent(self):
        self.assertTrue(callable(runner.load_agent("examples.toy_agent:agent")))
        with self.assertRaises(ValueError):
            runner.load_agent("no_colon")


class TestReport(unittest.TestCase):
    def res(self, suite, status, pending=None):
        return {"id": "x", "title": "", "suite": suite, "pending": pending, "k": 1, "status": status,
                "pass_k": status == "pass", "n_pass": int(status == "pass"), "n_fail": int(status == "fail"),
                "n_unknown": int(status == "unknown"), "n_error": int(status == "error"), "trials": []}

    def test_gates(self):
        self.assertTrue(R.gates([self.res("regression", "pass"), self.res("capability", "fail")])["ok"])
        self.assertFalse(R.gates([self.res("regression", "fail")])["ok"])
        self.assertTrue(R.gates([self.res("regression", "fail")], waivers=1)["ok"])
        self.assertFalse(R.gates([self.res("safety", "unknown")])["ok"])
        self.assertTrue(R.gates([self.res("safety", "fail", pending="not built")])["ok"])

    def test_markdown_lists_every_case(self):
        rs = [dict(self.res("regression", "pass"), id="a"), dict(self.res("safety", "error"), id="b")]
        md = R.markdown(rs, {"agent": "m:f", "started": "t"}, R.gates(rs))
        self.assertIn("**Gates: FAIL**", md)
        self.assertIn("| a | regression |", md)
        self.assertIn("| b | safety |", md)


class TestCli(unittest.TestCase):
    def setUp(self):
        self.cwd = os.getcwd()
        os.chdir(ROOT)

    def tearDown(self):
        os.chdir(self.cwd)

    def test_check_and_list(self):
        self.assertEqual(quiet(cli.main, ["check", EXAMPLES])[0], 0)
        rc, out, _ = quiet(cli.main, ["list", EXAMPLES, "--suite", "safety"])
        self.assertEqual((rc, len(out.strip().splitlines())), (0, 2))

    def test_run_examples(self):
        with tempfile.TemporaryDirectory() as d:
            rc, out, _ = quiet(cli.main, ["run", EXAMPLES, "--agent", "examples.toy_agent:agent",
                                          "--out", d, "--keep-transcripts"])
            self.assertEqual(rc, 0)
            with open(os.path.join(d, "results.json"), encoding="utf-8") as f:
                data = json.load(f)
            by = {r["id"]: r["status"] for r in data["results"]}
            self.assertEqual(by["timer-words"], "fail")
            self.assertEqual(by["greeting-tone"], "unknown")
            self.assertEqual(by["no-delete-injected"], "pass")
            self.assertEqual(len(os.listdir(os.path.join(d, "transcripts"))), 24)

    def test_failing_gate_exit_code(self):
        with tempfile.TemporaryDirectory() as d:
            rc, _, _ = quiet(cli.main, ["run", EXAMPLES, "--agent", "examples.toy_agent:agent", "--out", d,
                                        "--ids", "timer-words,timer-basic", "--k", "1"])
            self.assertEqual(rc, 0)          # timer-words is capability: not gated
            bad = os.path.join(d, "cases")
            os.makedirs(bad)
            with open(os.path.join(bad, "x.json"), "w") as f:
                json.dump(case(expect={"says": {"contains": ["never said"]}}), f)
            rc, _, _ = quiet(cli.main, ["run", bad, "--agent", "examples.toy_agent:agent", "--out", d])
            self.assertEqual(rc, 1)
            self.assertEqual(quiet(cli.main, ["run", bad, "--agent", "nope:x", "--out", d])[0], 2)

    def test_sample_report_is_current(self):
        """examples/sample-report/ is exactly what the README command produces."""
        with tempfile.TemporaryDirectory() as d:
            quiet(cli.main, ["run", EXAMPLES, "--agent", "examples.toy_agent:agent", "--out", d,
                             "--started", "sample"])
            for name in ("summary.md", "results.json"):
                with open(os.path.join(d, name), encoding="utf-8") as a, \
                        open(os.path.join(SAMPLE, name), encoding="utf-8") as b:
                    self.assertEqual(a.read(), b.read(), name)


if __name__ == "__main__":
    unittest.main()
