# web

The comparison site: the catalogue and the comparison with a face, and no server behind it. A reader picks two runs, sees them judged cell by cell with 95% intervals, and follows each run's provenance to its commit, image digest and jobs. Published to GitHub Pages on every merge to `main`, over a fresh snapshot of the bucket.

## How it works

Vite and Svelte 5 in TypeScript. The page is a static shell painted from the HTML alone; DuckDB's WebAssembly build then starts in a worker and reads `data/runs.parquet` and `data/cells/<run>.parquet` with range requests. The join of two runs is one SQL statement; the verdict is the rule `results-compare` uses, in `src/lib/compare.ts`, and `src/lib/compare.test.ts` pins it. Observable Plot draws the curves after the table has painted. Colour belongs to a run, not to its slot, so swapping the two keeps each run's hue. The chosen runs live in the address, so a comparison is a link.

## Commands

```sh
npm ci
npm run data:fixture   # a small store of made-up runs under fixture/, snapshotted into public/data
npm run dev            # the site over that snapshot
npm run check          # svelte-check and tsc
npm test               # vitest: the verdict, the ratio, the selection
npm run build && npm run budget   # production build; fails past 150 kB gzip for the first script
npm run test:e2e       # Playwright drives the built site, desktop and phone
```

`scripts/snapshot.py <store> <out>` writes the files the site reads from a bucket or a directory; CI runs it against the bucket on merge, from the read-only runner. `scripts/fixture.py` writes the made-up store the tests use.

## Three things and no fourth

Pick two runs, compare them, trace them. Each is finished: loading, empty and error states; every control reachable by keyboard and named for a screen reader; one axis per panel; dark mode from the same tokens; a table twin for every chart. A fourth thing is not added until it can be finished to the same bar.
