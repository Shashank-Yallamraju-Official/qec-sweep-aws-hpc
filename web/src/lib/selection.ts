// Which two runs are chosen, kept in the URL so a comparison is a link.
import type { Run } from './catalogue'

export interface Selection {
  a: string | null
  b: string | null
}

/** The runs named in the address, by run name, resolved against the catalogue. */
export function fromUrl(runs: Run[], search: string): Selection {
  const params = new URLSearchParams(search)
  const find = (name: string | null) => runs.find((run) => run.run === name)?.key ?? null
  return { a: find(params.get('a')), b: find(params.get('b')) }
}

/** The address for a selection: run names, not keys, so the link stays short and readable. */
export function toSearch(runs: Run[], selection: Selection): string {
  const params = new URLSearchParams()
  const name = (key: string | null) => runs.find((run) => run.key === key)?.run
  const a = name(selection.a)
  const b = name(selection.b)
  if (a) params.set('a', a)
  if (b) params.set('b', b)
  const search = params.toString()
  return search ? `?${search}` : ''
}

/** With nothing chosen, the two newest comparable runs: the newest is judged against the one before. */
export function defaults(runs: Run[]): Selection {
  const [newest, previous] = runs
  return { a: previous?.key ?? null, b: newest?.key ?? null }
}

/**
 * Colour belongs to a run, not to its slot: swapping A and B keeps each run's hue.
 * A newly chosen run takes whichever of the two hues the other chosen run is not wearing.
 */
export function assignColours(
  colours: ReadonlyMap<string, 1 | 2>,
  selection: Selection,
): Map<string, 1 | 2> {
  const next = new Map<string, 1 | 2>()
  const chosen = [selection.a, selection.b].filter((key): key is string => key !== null)
  for (const key of chosen) {
    const kept = colours.get(key)
    if (kept !== undefined) next.set(key, kept)
  }
  for (const key of chosen) {
    if (next.has(key)) continue
    const taken = new Set(next.values())
    next.set(key, taken.has(1) ? 2 : 1)
  }
  return next
}
