# agent-evals

Small, file-based evals for AI agents: one JSON file per case, graders that are plain functions, every case run k times, and a one-page Markdown report with pass/fail gates. Standard library only, Python 3.9+.

> v0.1. Rewritten from scratch out of a private eval harness used on a personal assistant project; the examples here are all made up.

## Why

Most agent bugs show up as "it worked when I tried it". This kit makes the trying repeatable:

- **Cases are files.** Inputs, starting state, and what to expect live in JSON you can review in a diff.
- **Graders check the world, not the words.** `final_state` looks at what the agent actually changed; `forbidden_tools` flags a call even when it was a dry run.
- **Unknown is its own answer.** A grader that cannot decide (no judge configured, nothing to compare) returns unknown instead of a quiet pass.
- **pass^k, not pass@1.** A case passes only if all k trials pass, so a flaky agent cannot pass by luck.
- **Gates you can wire into CI.** Regression must all pass, safety must have zero misses, capability is reported but not gated. The exit code says which.

## Quick start

```bash
git clone <this repo> agent-evals && cd agent-evals
python3 -m unittest discover -s tests                  # 25 tests, no network, no installs
python3 -m agent_evals check examples/cases            # validate the 10 example cases
python3 -m agent_evals run examples/cases --agent examples.toy_agent:agent --out runs/demo
```

Optional: `pip install .` gives you an `agent-evals` command instead of `python3 -m agent_evals`.

`runs/demo/summary.md` is the report; `runs/demo/results.json` has every trial and every grader's verdict. A copy of the report the command above produces is in [`examples/sample-report/`](examples/sample-report/summary.md) (the tests check that it is current). It shows the gates passing while the made-up agent still fails two capability cases and leaves one unknown:

```
**Gates: PASS**
- regression: 4/4 pass^k - ok
- safety: 2/2 pass^k - 0 violation(s), 0 unknown - ok
- capability: 0/3 pass^k (not gated, watch the trend)
- trials: 24 run, 17 passed, 6 failed, 1 unknown, 0 errors
```

## A case

```json
{
  "id": "renew-ambiguous",
  "title": "Asks which book when two are on loan, and does nothing yet",
  "suite": "regression",
  "input": {"text": "Please renew my book"},
  "state": {"loans": {"L-1": "The Quiet Orchard", "L-2": "A Field Guide to Clouds"}},
  "expect": {
    "says": {"asks_question": true},
    "turns": {"max_questions": 1, "max_tool_calls": 0},
    "final_state": "unchanged"
  },
  "graders": ["says", "turns", "final_state"],
  "k": 3
}
```

| key | meaning |
|---|---|
| `id` | letters, digits, `_ . -`; unique in the folder |
| `suite` | `regression` (must keep working) · `safety` (must never happen) · `capability` (what you are working toward) |
| `input` | `{"text": ...}` or `{"turns": [...]}` - passed to your agent as is |
| `state` | starting world; each trial gets a fresh copy |
| `expect` | one entry per grader (below) |
| `graders` | which graders to run; all must pass for the trial to pass |
| `k` | trials per case (default 1; `--k` overrides) |
| `pending` | optional note: the feature is not built yet - run and report it, keep it out of the gates |

## Graders

| name | `expect` key | passes when |
|---|---|---|
| `says` | `says`: `contains`, `contains_any`, `not_contains`, `regex`, `asks_question`, `max_chars`, `any` | what the agent said fits (case-insensitive) |
| `forbidden_tools` | `forbidden_tools`: glob patterns over `name` / `name:target` | no tool call matches, dry runs included |
| `tool_args` | `tool_args`: `[{"name", "args"}]` | each expected call happened (args matched as a subset) |
| `final_state` | `final_state`: `{key: value}` or `"unchanged"` | the agent's returned `outcome.state` matches |
| `turns` | `turns`: `max_messages`, `max_questions`, `max_tool_calls` | counts stay under the limits |
| `latency` | `latency`: `{"max_ms"}` | `outcome.ms_total`, or the sum of event `ms`, is under the limit |
| `rubric` | `rubric`: `{"criteria", "min_score"}` | your judge scores every criterion at least `min_score` (1-5); no judge means unknown |

A grader that crashes, or a name that is not registered, counts as a fail. Write your own:

```python
from agent_evals.graders import register

@register("no_exclamations")
def no_exclamations(events, case, outcome, ctx):
    said = [e.get("text") or "" for e in events if e["role"] == "agent" and e["kind"] == "message"]
    loud = [s for s in said if "!" in s]
    return {"pass": not loud, "detail": "%d loud message(s)" % len(loud)}
```

Import that module from your agent module (or anywhere that runs before the cases) and list `"no_exclamations"` in a case's `graders`.

## Plugging in your agent

The runner calls any function `agent(inp, state, trial)` and expects back a transcript and an outcome:

```python
def agent(inp, state, trial):
    reply = my_system.handle(inp["text"])          # your real call goes here
    events = [
        {"role": "user", "kind": "message", "text": inp["text"]},
        {"role": "agent", "kind": "message", "text": reply.text, "ms": reply.ms},
    ]
    return {"events": events, "outcome": {"state": state}}
```

Events are dicts with `role` (`user` · `agent` · `tool` · `system`), `kind` (`message` · `tool_call` · `tool_result` · `note`), and optional `text`, `name`, `args`, `ms`. A transcript that does not fit this shape is reported as `bad_transcript`, not graded. See [`examples/toy_agent.py`](examples/toy_agent.py) for a complete fake agent with tools and state.

## Gates and exit codes

| suite | gate |
|---|---|
| regression | every case pass^k (`--waivers N` lets N miss) |
| safety | zero cases short of pass^k - a fail, an unknown, or an error all block |
| capability | none; reported so you can watch the trend |

`pending` cases are never gated. `run` exits `0` when the gates pass, `1` when they fail, `2` for bad cases or a bad `--agent`.

## Not in v0.1

- No model judge ships with it: `rubric` calls a `judge(criterion, text)` you supply in code; on the command line it is always unknown.
- Cases are JSON only; trials run one after another in one process.
- The report is Markdown + JSON; no HTML, no charts, no history across runs.

## License

MIT - see [LICENSE](LICENSE). No third-party code, models, or data.
