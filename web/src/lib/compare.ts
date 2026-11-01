// Two runs joined cell by cell, judged exactly as results-compare judges them.
import type { Run } from './catalogue'
import { lastQueryMs, query, register } from './db'

export type Verdict = 'within' | 'lower' | 'higher'

export interface Side {
  errors: number
  rate: number
  low: number
  high: number
}

export interface CellComparison {
  distance: number
  noise: number
  shots: number
  a: Side
  b: Side
  ratio: number | null
  verdict: Verdict
}

export interface Comparison {
  cells: CellComparison[]
  onlyA: number
  onlyB: number
  counts: Record<Verdict, number>
  queryMs: number
}

/**
 * Where the judged run stands against the reference on one cell.
 * Two 95% intervals that do not touch is a conservative test; a difference it calls holds.
 */
export function verdict(a: Side, b: Side): Verdict {
  if (b.high < a.low) return 'lower'
  if (b.low > a.high) return 'higher'
  return 'within'
}

/** The judged rate over the reference rate; undefined when the reference saw no error. */
export function ratio(a: Side, b: Side): number | null {
  return a.errors === 0 ? null : b.rate / a.rate
}

interface Row {
  distance: number
  noise: number
  shots: number
  errors_a: number | null
  rate_a: number | null
  low_a: number | null
  high_a: number | null
  errors_b: number | null
  rate_b: number | null
  low_b: number | null
  high_b: number | null
}

const CELL = 'cells/'

async function cells(run: Run): Promise<string> {
  const name = `${run.run}.parquet`
  await register(name, `${CELL}${name}`)
  return name
}

/** Join two runs on distance, noise and shots; cells on one side only are counted, not shown. */
export async function compareRuns(a: Run, b: Run): Promise<Comparison> {
  const [fileA, fileB] = await Promise.all([cells(a), cells(b)])
  const rows = await query<Row>(`
    select
      coalesce(a.distance, b.distance) as distance,
      coalesce(a.noise, b.noise) as noise,
      coalesce(a.shots, b.shots) as shots,
      a.errors as errors_a, a.logical_error_rate as rate_a, a.ci_low as low_a, a.ci_high as high_a,
      b.errors as errors_b, b.logical_error_rate as rate_b, b.ci_low as low_b, b.ci_high as high_b
    from '${fileA}' a
    full outer join '${fileB}' b using (distance, noise, shots)
    order by distance, noise
  `)
  const comparison: Comparison = {
    cells: [],
    onlyA: 0,
    onlyB: 0,
    counts: { within: 0, lower: 0, higher: 0 },
    queryMs: lastQueryMs,
  }
  for (const row of rows) {
    if (row.errors_a === null) comparison.onlyB += 1
    else if (row.errors_b === null) comparison.onlyA += 1
    else {
      const sideA = { errors: row.errors_a, rate: row.rate_a!, low: row.low_a!, high: row.high_a! }
      const sideB = { errors: row.errors_b, rate: row.rate_b!, low: row.low_b!, high: row.high_b! }
      const cell: CellComparison = {
        distance: row.distance,
        noise: row.noise,
        shots: row.shots,
        a: sideA,
        b: sideB,
        ratio: ratio(sideA, sideB),
        verdict: verdict(sideA, sideB),
      }
      comparison.cells.push(cell)
      comparison.counts[cell.verdict] += 1
    }
  }
  return comparison
}
