# QEC sweep on AWS HPC

Read docs/design.md and docs/plan.md before starting a stage. The plan lists every commit in order.

## Working
- One branch per stage, `stage-NN-<scope>`, merged by rebase through a pull request. Never commit on main.
- Commits follow docs/plan.md. The only unplanned commits are fixes, scoped to the directory they touch.
- `uv run pre-commit run --all-files` and `uv run pytest` pass before every commit; the hooks refuse otherwise.
- Run /code-review on the branch before opening its pull request.

## Code
- A name says what the thing is for. If a name needs a comment, rename it.
- Every public module, class and function outside tests has a Google-style docstring that says what it is for; ruff enforces it. No comment that restates the code. A comment says why, or it goes.
- One concern per module. A function fits on one screen.
- Interfaces are typed and narrow. A dataclass over a dict with known keys.
- Prose lives in docs/design.md, docs/plan.md and the final README. Nowhere else.
- British spelling in prose and messages.

## Commit messages
`<type>(<scope>): <subject>`, first line at most 60 characters, imperative, lowercase, no full stop.
Body only when the diff cannot say why. No trailers. tools/check_commit.py is the rule; the hook runs it.
