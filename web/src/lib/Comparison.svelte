<script lang="ts">
  import type { Run } from './catalogue'
  import type { Comparison } from './compare'
  import Curves from './Curves.svelte'
  import { count, interval, rate, ratio } from './format'

  interface Props {
    comparison: Comparison
    a: Run
    b: Run
    colours: ReadonlyMap<string, 1 | 2>
    stale: boolean
  }

  let { comparison, a, b, colours, stale }: Props = $props()

  let apartOnly = $state(false)

  const shown = $derived(apartOnly ? comparison.cells.filter((c) => c.verdict !== 'within') : comparison.cells)
  const apart = $derived(comparison.counts.lower + comparison.counts.higher)

  function headline(): string {
    const total = comparison.cells.length
    if (total === 0) return 'The two runs share no cell.'
    if (apart === 0) return `Within the intervals on every one of ${total} cells.`
    const parts = []
    if (comparison.counts.lower) parts.push(`lower on ${comparison.counts.lower}`)
    if (comparison.counts.higher) parts.push(`higher on ${comparison.counts.higher}`)
    return `The judged run is ${parts.join(' and ')} of ${total} cells, within the intervals on the rest.`
  }

  function aside(): string {
    const notes = []
    if (comparison.onlyA) notes.push(`${comparison.onlyA} cells only in the reference`)
    if (comparison.onlyB) notes.push(`${comparison.onlyB} cells only in the judged run`)
    return notes.join('; ')
  }
</script>

<section class="comparison" class:stale aria-label="Comparison" aria-busy={stale}>
  <p class="headline" role="status">{headline()}</p>
  {#if aside()}
    <p class="quiet">{aside()}</p>
  {/if}

  {#if comparison.cells.length > 0}
    <Curves cells={comparison.cells} {a} {b} {colours} />

    <div class="controls">
      <label class="toggle">
        <input type="checkbox" bind:checked={apartOnly} disabled={apart === 0} />
        Only the cells set apart
      </label>
      <p class="quiet">{count(comparison.cells.length)} cells joined in {comparison.queryMs.toFixed(0)} ms</p>
    </div>

    <div class="scroll">
      <table>
        <caption class="visually-hidden">Logical error rate per cell for both runs, with intervals and verdict</caption>
        <thead>
          <tr>
            <th scope="col" class="num">d</th>
            <th scope="col" class="num">p</th>
            <th scope="col">
              <span class="key" data-colour={colours.get(a.key)} aria-hidden="true"></span>
              Reference
            </th>
            <th scope="col">
              <span class="key" data-colour={colours.get(b.key)} aria-hidden="true"></span>
              Judged
            </th>
            <th scope="col" class="num">Ratio</th>
            <th scope="col">Verdict</th>
          </tr>
        </thead>
        <tbody>
          {#each shown as cell (`${cell.distance}-${cell.noise}-${cell.shots}`)}
            <tr>
              <td class="num">{cell.distance}</td>
              <td class="num">{cell.noise}</td>
              <td>
                <strong>{rate(cell.a.rate)}</strong>
                <span class="interval">{interval(cell.a.low, cell.a.high)}</span>
              </td>
              <td>
                <strong>{rate(cell.b.rate)}</strong>
                <span class="interval">{interval(cell.b.low, cell.b.high)}</span>
              </td>
              <td class="num">{ratio(cell.ratio)}</td>
              <td>
                <span class="verdict" data-verdict={cell.verdict}>
                  {#if cell.verdict === 'lower'}
                    <svg viewBox="0 0 12 12" width="12" height="12" aria-hidden="true"><path d="M6 2v8m0 0L2.5 6.5M6 10l3.5-3.5" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" /></svg>
                  {:else if cell.verdict === 'higher'}
                    <svg viewBox="0 0 12 12" width="12" height="12" aria-hidden="true"><path d="M6 10V2m0 0L2.5 5.5M6 2l3.5 3.5" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" /></svg>
                  {:else}
                    <svg viewBox="0 0 12 12" width="12" height="12" aria-hidden="true"><path d="M2 6h8" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" /></svg>
                  {/if}
                  {cell.verdict}
                </span>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
</section>

<style>
  .comparison {
    display: grid;
    gap: 1rem;
    transition: opacity 150ms ease;
  }

  .stale {
    opacity: 0.5;
  }

  .headline {
    max-width: 40ch;
    font-size: clamp(1.25rem, 2.5vw, 1.625rem);
    font-weight: 500;
    letter-spacing: -0.01em;
    line-height: 1.25;
    text-wrap: balance;
  }

  .quiet {
    color: var(--ink-3);
  }

  .controls {
    display: flex;
    flex-wrap: wrap;
    justify-content: space-between;
    gap: 0.5rem 1.5rem;
    align-items: baseline;
  }

  .toggle {
    display: inline-flex;
    gap: 0.5rem;
    align-items: center;
    min-height: 2.75rem;
    cursor: pointer;
  }

  .toggle input {
    width: 1.125rem;
    height: 1.125rem;
    margin: 0;
    accent-color: var(--focus);
  }

  .scroll {
    overflow-x: auto;
  }

  table {
    width: 100%;
    border-collapse: collapse;
    font-variant-numeric: tabular-nums;
  }

  th,
  td {
    padding: 0.5rem 1rem 0.5rem 0;
    text-align: left;
    vertical-align: baseline;
    border-bottom: 1px solid var(--grid);
    white-space: nowrap;
  }

  th {
    font-weight: 500;
    color: var(--ink-2);
  }

  .num {
    text-align: right;
  }

  .key {
    display: inline-block;
    width: 1rem;
    height: 3px;
    margin-right: 0.375rem;
    vertical-align: middle;
    border-radius: 2px;
    background: var(--axis);
  }

  .key[data-colour='1'] {
    background: var(--run-1);
  }

  .key[data-colour='2'] {
    background: var(--run-2);
  }

  .interval {
    margin-left: 0.375rem;
    color: var(--ink-3);
    font-size: 0.875em;
  }

  .verdict {
    display: inline-flex;
    gap: 0.375rem;
    align-items: center;
    color: var(--ink-2);
  }

  .verdict[data-verdict='lower'] {
    color: var(--good);
  }

  .verdict[data-verdict='higher'] {
    color: var(--serious);
  }

  .visually-hidden {
    position: absolute;
    width: 1px;
    height: 1px;
    overflow: hidden;
    clip: rect(0 0 0 0);
    white-space: nowrap;
  }
</style>
