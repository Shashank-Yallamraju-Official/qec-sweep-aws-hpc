# tools

The scripts that measure the project and keep its rules, none of which run on the cluster.

| Command | Reads | Says |
| --- | --- | --- |
| `uv run python -m tools.cost_report <run>` | a run's record and the Pricing API | node-hours and dollars, while cells ran and once the idle tail is billed |
| `uv run python -m tools.loop_report <run>` | a run's record, its cells and GitHub | how long the commit took to become the first cell on the cluster, in three phases |
| `uv run python -m tools.loop_plot --before <run> --after <run>` | two of the above | loop time and cost per sweep, side by side |
| `uv run python -m tools.process_report [--stage N]` | the hook event log | active minutes, edits, rejected edits and commit attempts per planned commit |
| `uv run python tools/check_commit.py <message file>` | a commit message | whether it follows the format in `CLAUDE.md`; the commit hook runs it |
| `uv run python -m tools.loop_figure` | the marks under `docs/figures/marks` | the README's figure, `docs/figures/loop-light.svg` and `loop-dark.svg`, with the marks embedded |

Each report prints the addresses it read, so a number in the write-up walks back to a record. The marks are GitHub's Invertocat, under GitHub's logo guidelines, and two AWS Architecture Icons, under their terms for architecture diagrams. `<run>` is `s3://bucket/<kind>/<run>` or a directory laid out the same way.

## Where it fits

The measured numbers in [the plan](../docs/plan.md) come from these; the figures they draw sit under `plots/` in the bucket. Test with `uv run pytest tests/tools`.
