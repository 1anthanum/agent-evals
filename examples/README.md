# Examples

Everything here is made up.

- `toy_agent.py` - a pretend reading-room desk assistant: a few if-statements, four fake tools (`timer.set`, `catalog.search`, `loan.renew`, and `catalog.delete`, which it must never call), a three-book fake catalog. It has two planted weaknesses: timer lengths written in words, and a greeting that rambles on some trials.
- `cases/` - 10 cases: 5 regression (one of them `pending`), 2 safety, 3 capability.
- `sample-report/` - exactly what `python3 -m agent_evals run examples/cases --agent examples.toy_agent:agent --out examples/sample-report --started sample` writes. `tests/` checks it stays current.
