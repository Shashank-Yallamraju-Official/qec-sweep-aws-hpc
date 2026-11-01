<script lang="ts">
  import type { Run } from './catalogue'
  import type { CellComparison } from './compare'
  import type { Ink, Series } from './curves'

  interface Props {
    cells: CellComparison[]
    a: Run
    b: Run
    colours: ReadonlyMap<string, 1 | 2>
  }

  let { cells, a, b, colours }: Props = $props()

  let host = $state<HTMLDivElement | null>(null)
  let width = $state(0)
  let failed = $state(false)
  let module = $state<typeof import('./curves') | null>(null)

  // The chart library arrives after the table has painted; the table stands alone until then.
  $effect(() => {
    import('./curves')
      .then((m) => (module = m))
      .catch(() => (failed = true))
  })

  $effect(() => {
    if (!host) return
    const observer = new ResizeObserver(([entry]) => {
      if (entry) width = Math.floor(entry.contentRect.width)
    })
    observer.observe(host)
    return () => observer.disconnect()
  })

  function token(name: string): string {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim()
  }

  function series(run: Run): Series {
    return { key: run.key, name: run.run, colour: token(`--run-${colours.get(run.key) ?? 1}`) }
  }

  $effect(() => {
    if (!host || !module || width === 0) return
    const ink: Ink = {
      text: token('--ink-2'),
      muted: token('--ink-3'),
      grid: token('--grid'),
      surface: token('--surface'),
    }
    const figure = module.curves(cells, series(a), series(b), width, ink)
    host.replaceChildren(figure)
    return () => figure.remove()
  })
</script>

<figure class="curves">
  <figcaption>
    <span class="legend">
      <span class="item"><span class="key" data-colour={colours.get(a.key)} aria-hidden="true"></span>{a.run}</span>
      <span class="item"><span class="key" data-colour={colours.get(b.key)} aria-hidden="true"></span>{b.run}</span>
      <span class="item"><span class="ring" aria-hidden="true"></span>intervals apart</span>
    </span>
    <span class="quiet">Logical error rate against physical error rate, one panel per distance; bands are the 95% intervals and a ring marks the judged point of a cell set apart. Cells with no observed error have no point.</span>
  </figcaption>
  <div class="host" bind:this={host} role="img" aria-label="Error-rate curves for both runs, one panel per distance; the table below holds every value">
    {#if failed}
      <p class="quiet">The chart could not be drawn; the table below has every value.</p>
    {/if}
  </div>
</figure>

<style>
  .curves {
    display: grid;
    gap: 0.75rem;
    margin: 0;
  }

  figcaption {
    display: grid;
    gap: 0.375rem;
  }

  .legend {
    display: flex;
    flex-wrap: wrap;
    gap: 0.5rem 1.25rem;
    font-variant-numeric: tabular-nums;
  }

  .item {
    display: inline-flex;
    gap: 0.5rem;
    align-items: center;
  }

  .key {
    width: 1.25rem;
    height: 3px;
    border-radius: 2px;
    background: var(--axis);
  }

  .key[data-colour='1'] {
    background: var(--run-1);
  }

  .key[data-colour='2'] {
    background: var(--run-2);
  }

  .ring {
    width: 0.875rem;
    height: 0.875rem;
    border: 1.5px solid var(--ink-2);
    border-radius: 50%;
  }

  .quiet {
    color: var(--ink-3);
    font-size: 0.9375rem;
  }

  .host {
    min-height: 12rem;
  }

  .host :global(svg) {
    display: block;
    overflow: visible;
  }

  .host :global([aria-label='tip']) {
    font-variant-numeric: tabular-nums;
  }
</style>
