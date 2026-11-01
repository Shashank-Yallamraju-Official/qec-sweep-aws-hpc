// The threshold plot as small multiples, one panel per distance, two runs per panel:
// logical error rate against physical error rate, log-log, each line inside its 95% band.
import * as Plot from '@observablehq/plot'
import type { CellComparison } from './compare'

export interface Series {
  key: string
  name: string
  colour: string
}

interface Point {
  distance: number
  noise: number
  rate: number
  low: number
  high: number
  run: string
  apart: boolean
}

export interface Ink {
  text: string
  muted: string
  grid: string
  surface: string
}

// A cell with no observed error has no point on a log axis, as in the CLI's plot.
function points(cells: CellComparison[], a: Series, b: Series): Point[] {
  const out: Point[] = []
  for (const cell of cells) {
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
      })
    }
  }
  return out
}

/** Build the figure; the caller owns the element and replaces it on each change. */
export function curves(
  cells: CellComparison[],
  a: Series,
  b: Series,
  width: number,
  ink: Ink,
): HTMLElement | SVGSVGElement {
  const data = points(cells, a, b)
  const names = new Map([
    [a.key, a.name],
    [b.key, b.name],
  ])
  const panels = new Set(data.map((d) => d.distance)).size || 1
  const columns = width < 560 ? 1 : width < 900 ? 2 : Math.min(panels, 5)
  const panelWidth = Math.floor(width / columns)
  const floor = Math.min(...data.map((d) => d.low), 1e-5)
  const ceiling = Math.min(1, Math.max(...data.map((d) => d.high), 1e-4) * 1.6)
  return Plot.plot({
    width,
    height: Math.ceil(panels / columns) * Math.max(180, Math.min(260, panelWidth * 0.9)) + 40,
    marginLeft: 48,
    marginRight: 12,
    marginBottom: 36,
    style: { background: 'transparent', color: ink.text, fontFamily: 'inherit', fontSize: '12px' },
    fx: { axis: null, padding: 0.12 },
    x: { type: 'log', label: 'physical error rate p', tickFormat: '~g', grid: false },
    y: { type: 'log', label: 'logical error rate', tickFormat: '.0e', grid: true, domain: [floor * 0.7, ceiling] },
    color: { domain: [a.key, b.key], range: [a.colour, b.colour] },
    marks: [
      Plot.frame({ stroke: ink.grid }),
      Plot.text(
        data,
        Plot.selectFirst({
          fx: 'distance',
          text: (d: Point) => `d = ${d.distance}`,
          frameAnchor: 'top-left',
          dx: 8,
          dy: 8,
          fill: ink.text,
          fontWeight: 500,
        }),
      ),
      Plot.areaY(data, {
        fx: 'distance',
        x: 'noise',
        y1: 'low',
        y2: 'high',
        fill: 'run',
        fillOpacity: 0.12,
        curve: 'monotone-x',
      }),
      Plot.lineY(data, {
        fx: 'distance',
        x: 'noise',
        y: 'rate',
        stroke: 'run',
        strokeWidth: 2,
        curve: 'monotone-x',
      }),
      Plot.dot(data, {
        fx: 'distance',
        x: 'noise',
        y: 'rate',
        fill: 'run',
        r: 4,
        stroke: ink.surface,
        strokeWidth: 2,
      }),
      // One ring per cell set apart, around the judged run's point, in ink rather than a run's hue.
      Plot.dot(
        data.filter((d) => d.apart && d.run === b.key),
        { fx: 'distance', x: 'noise', y: 'rate', r: 7.5, fill: 'none', stroke: ink.text, strokeWidth: 1.25 },
      ),
      Plot.ruleX(data, Plot.pointerX({ fx: 'distance', x: 'noise', stroke: ink.muted, strokeWidth: 1 })),
      Plot.tip(
        data,
        Plot.pointerX({
          fx: 'distance',
          x: 'noise',
          y: 'rate',
          title: (d: Point) =>
            `${names.get(d.run)}\np = ${d.noise}\n${d.rate.toExponential(2)}  [${d.low.toExponential(2)}, ${d.high.toExponential(2)}]${d.apart ? '\nintervals apart' : ''}`,
          fill: ink.surface,
          stroke: ink.grid,
        }),
      ),
    ],
  })
}
