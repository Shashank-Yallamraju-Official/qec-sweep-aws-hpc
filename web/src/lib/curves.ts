// The threshold plot as small multiples, one panel per distance, two runs per panel:
// logical error rate against physical error rate, log-log, each line inside its 95% band.
import * as Plot from '@observablehq/plot'
import type { CellComparison } from './compare'

export interface Series {
  key: string
  name: string
  colour: string
}

export interface Ink {
  text: string
  muted: string
  grid: string
  surface: string
}

interface Point {
  distance: number
  noise: number
  rate: number
  low: number
  high: number
  run: string
  apart: boolean
  column: number
  row: number
}

interface Layout {
  columns: number
  rows: number
  height: number
  floor: number
  ceiling: number
}

// A cell with no observed error has no point on a log axis, as in the CLI's plot.
function points(cells: CellComparison[], a: Series, b: Series, columns: number): Point[] {
  const distances = [...new Set(cells.map((c) => c.distance))].sort((x, y) => x - y)
  const out: Point[] = []
  for (const cell of cells) {
    const panel = distances.indexOf(cell.distance)
    const apart = cell.verdict !== 'within'
    for (const [side, series] of [
      [cell.a, a],
      [cell.b, b],
    ] as const) {
      if (side.errors === 0) continue
      out.push({
        distance: cell.distance,
        noise: cell.noise,
        rate: side.rate,
        low: Math.max(side.low, side.rate / 10),
        high: side.high,
        run: series.key,
        apart,
        column: panel % columns,
        row: Math.floor(panel / columns),
      })
    }
  }
  return out
}

/** Panels wrap into rows as the width shrinks; Plot lays facets out on a grid of column and row. */
export function layout(cells: CellComparison[], width: number): Layout {
  const panels = new Set(cells.map((c) => c.distance)).size || 1
  const columns = width < 560 ? 1 : width < 900 ? 2 : Math.min(panels, 5)
  const rows = Math.ceil(panels / columns)
  const panelWidth = Math.floor(width / columns)
  const rates = cells.flatMap((c) => [c.a, c.b]).filter((s) => s.errors > 0)
  const floor = Math.min(...rates.map((s) => Math.max(s.low, s.rate / 10)), 1e-5)
  const ceiling = Math.min(1, Math.max(...rates.map((s) => s.high), 1e-4) * 1.6)
  return {
    columns,
    rows,
    height: rows * Math.max(180, Math.min(260, panelWidth * 0.9)) + 40,
    floor: floor * 0.7,
    ceiling,
  }
}

function tipText(point: Point, names: Map<string, string>): string {
  const interval = `[${point.low.toExponential(2)}, ${point.high.toExponential(2)}]`
  const apart = point.apart ? '\nintervals apart' : ''
  return `${names.get(point.run)}\np = ${point.noise}\n${point.rate.toExponential(2)}  ${interval}${apart}`
}

/** Build the figure; the caller owns the element and replaces it on each change. */
export function curves(
  cells: CellComparison[],
  a: Series,
  b: Series,
  width: number,
  ink: Ink,
): HTMLElement | SVGSVGElement {
  const frame = layout(cells, width)
  const data = points(cells, a, b, frame.columns)
  const names = new Map([
    [a.key, a.name],
    [b.key, b.name],
  ])
  const facet = { fx: 'column', fy: 'row' } as const
  const curve = { ...facet, x: 'noise', curve: 'monotone-x' } as const
  return Plot.plot({
    width,
    height: frame.height,
    marginLeft: 48,
    marginRight: 12,
    marginBottom: 36,
    style: { background: 'transparent', color: ink.text, fontFamily: 'inherit', fontSize: '12px' },
    fx: { axis: null, padding: 0.12 },
    fy: { axis: null, padding: 0.15 },
    x: { type: 'log', label: 'physical error rate p', ticks: [1e-3, 3e-3, 1e-2], tickFormat: '~g' },
    y: {
      type: 'log',
      label: 'logical error rate',
      tickFormat: '.0e',
      grid: true,
      domain: [frame.floor, frame.ceiling],
    },
    color: { domain: [a.key, b.key], range: [a.colour, b.colour] },
    marks: [
      Plot.frame({ stroke: ink.grid }),
      Plot.text(
        data,
        Plot.selectFirst({
          ...facet,
          text: (d: Point) => `d = ${d.distance}`,
          frameAnchor: 'top-left',
          dx: 8,
          dy: 8,
          fill: ink.text,
          fontWeight: 500,
        }),
      ),
      Plot.areaY(data, { ...curve, y1: 'low', y2: 'high', fill: 'run', fillOpacity: 0.12 }),
      Plot.lineY(data, { ...curve, y: 'rate', stroke: 'run', strokeWidth: 2 }),
      Plot.dot(data, { ...facet, x: 'noise', y: 'rate', fill: 'run', r: 4, stroke: ink.surface, strokeWidth: 2 }),
      // One ring per cell set apart, around the judged run's point, in ink rather than a run's hue.
      Plot.dot(
        data.filter((d) => d.apart && d.run === b.key),
        { ...facet, x: 'noise', y: 'rate', r: 7.5, fill: 'none', stroke: ink.text, strokeWidth: 1.25 },
      ),
      Plot.ruleX(data, Plot.pointerX({ ...facet, x: 'noise', stroke: ink.muted, strokeWidth: 1 })),
      Plot.tip(
        data,
        Plot.pointerX({
          ...facet,
          x: 'noise',
          y: 'rate',
          title: (d: Point) => tipText(d, names),
          fill: ink.surface,
          stroke: ink.grid,
        }),
      ),
    ],
  })
}
