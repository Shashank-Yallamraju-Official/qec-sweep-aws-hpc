// Numbers as the reader needs them: rates in scientific form, counts with separators.

const sci = new Intl.NumberFormat('en-GB', {
  notation: 'scientific',
  maximumSignificantDigits: 3,
  minimumSignificantDigits: 3,
})

/** A logical error rate: three significant figures in scientific notation, as the CLI prints it. */
export function rate(value: number): string {
  if (value === 0) return '0'
  return sci.format(value).replace('E', 'e').toLowerCase()
}

/** A ratio to two decimals, or the sign that there is none. */
export function ratio(value: number | null): string {
  return value === null ? '–' : value.toFixed(2)
}

const grouped = new Intl.NumberFormat('en-GB')

/** A count with thousands separators. */
export function count(value: number): string {
  return grouped.format(value)
}

/** An interval, bracketed. */
export function interval(low: number, high: number): string {
  return `[${rate(low)}, ${rate(high)}]`
}
