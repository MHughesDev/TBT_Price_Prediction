# Rules for editing this repo

The person who owns this repo reads every line. **Readability is the goal.** Less is better.

## Code
- Every file opens with a short docstring: what it does, what it reads, what it writes.
- Use plain, full names: `train`, `test`, `bucket`, `price`, `weight`. No single letters.
- Keep settings as literal lists and dicts at the top of the file.
- A comment says **why**, never what. Each hard-won gotcha gets one short comment where it matters.
- No classes, frameworks, config files, or generated metadata unless they are clearly needed.
- A new idea to test becomes a new file in `methods/`, not an option flag in an existing one.
- Before you add code, try to delete some.

## Docs
- Short sentences. Tables for numbers.
- Each fact lives in **one** place. Results live only in `results/SCOREBOARD.md`, which `score.py` writes.
- No changelogs, correspondence or history in docs. Git keeps history.

## Judging methods
- Dollars decide. A method wins only when `score.py` says so: the whole 95% interval above $0.
- Never compare numbers from different test sets. Re-run `backtest.py` for every method you compare.
