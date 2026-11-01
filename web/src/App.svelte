<script lang="ts">
  import { onMount } from 'svelte'
  import { loadRuns, type Run } from './lib/catalogue'
  import RunPicker from './lib/RunPicker.svelte'
  import ComparisonView from './lib/Comparison.svelte'
  import { compareRuns, type Comparison } from './lib/compare'
  import { assignColours, defaults, fromUrl, toSearch, type Selection } from './lib/selection'

  type State = { kind: 'loading' } | { kind: 'error'; message: string } | { kind: 'ready'; runs: Run[] }
  type Judged = { comparison: Comparison; a: Run; b: Run }

  let catalogue = $state<State>({ kind: 'loading' })
  let selection = $state<Selection>({ a: null, b: null })
  let colours = $state<Map<string, 1 | 2>>(new Map())
  let judged = $state<Judged | null>(null)
  let judging = $state(false)
  let judgeError = $state<string | null>(null)

  const comparable = $derived(catalogue.kind === 'ready' ? catalogue.runs.filter((run) => run.cells > 0) : [])
  const runA = $derived(comparable.find((run) => run.key === selection.a) ?? null)
  const runB = $derived(comparable.find((run) => run.key === selection.b) ?? null)

  // The previous comparison stays on screen, dimmed, while the next one is queried.
  $effect(() => {
    const a = runA
    const b = runB
    if (!a || !b) {
      judged = null
      return
    }
    let current = true
    judging = true
    judgeError = null
    compareRuns(a, b)
      .then((comparison) => {
        if (current) judged = { comparison, a, b }
      })
      .catch((error: unknown) => {
        if (current) judgeError = error instanceof Error ? error.message : String(error)
      })
      .finally(() => {
        if (current) judging = false
      })
    return () => {
      current = false
    }
  })

  async function load() {
    catalogue = { kind: 'loading' }
    try {
      const runs = await loadRuns()
      catalogue = { kind: 'ready', runs }
      const pickable = runs.filter((run) => run.cells > 0)
      const named = fromUrl(pickable, window.location.search)
      choose(named.a || named.b ? named : defaults(pickable), false)
    } catch (error) {
      catalogue = { kind: 'error', message: error instanceof Error ? error.message : String(error) }
    }
  }

  function choose(next: Selection, push = true) {
    selection = next
    colours = assignColours(colours, next)
    const url = `${window.location.pathname}${toSearch(comparable, next)}`
    if (push) history.pushState(null, '', url)
    else history.replaceState(null, '', url)
  }

  function swap() {
    choose({ a: selection.b, b: selection.a })
  }

  onMount(() => {
    void load()
    const back = () => choose(fromUrl(comparable, window.location.search), false)
    window.addEventListener('popstate', back)
    return () => window.removeEventListener('popstate', back)
  })
</script>

<div class="page">
  <header class="masthead">
    <h1>Compare two runs</h1>
    <p class="standfirst">
      Pick two runs of the decoder sweep. Each cell is judged on its 95% intervals: a difference
      counts only where they do not touch. Every run traces back to the commit, image and jobs
      that produced it.
    </p>
  </header>
  <main aria-busy={catalogue.kind === 'loading'}>
    {#if catalogue.kind === 'loading'}
      <p class="quiet" role="status">Loading the catalogue.</p>
    {:else if catalogue.kind === 'error'}
      <div class="notice" role="alert">
        <p>The catalogue could not be read: {catalogue.message}</p>
        <button type="button" class="button" onclick={load}>Try again</button>
      </div>
    {:else if comparable.length === 0}
      <p class="quiet">The snapshot holds no sweep with cells yet. The next merge to main publishes one.</p>
    {:else}
      <section class="pickers" aria-label="Runs to compare">
        <RunPicker
          id="run-a"
          label="Reference"
          runs={comparable}
          value={selection.a}
          exclude={selection.b}
          colour={selection.a ? (colours.get(selection.a) ?? null) : null}
          onchange={(key) => choose({ a: key, b: selection.b })}
        />
        <button type="button" class="button swap" onclick={swap} disabled={!runA || !runB} aria-label="Swap the two runs">
          <svg viewBox="0 0 20 20" width="20" height="20" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round">
            <path d="M4 7h12m0 0-3-3m3 3-3 3M16 13H4m0 0 3-3m-3 3 3 3" />
          </svg>
        </button>
        <RunPicker
          id="run-b"
          label="Judged"
          runs={comparable}
          value={selection.b}
          exclude={selection.a}
          colour={selection.b ? (colours.get(selection.b) ?? null) : null}
          onchange={(key) => choose({ a: selection.a, b: key })}
        />
      </section>
      {#if !runA || !runB}
        <p class="quiet">Choose a reference and a run to judge against it.</p>
      {:else if judgeError}
        <div class="notice" role="alert">
          <p>The cells could not be read: {judgeError}</p>
          <button type="button" class="button" onclick={() => choose({ ...selection })}>Try again</button>
        </div>
      {:else if judged}
        <ComparisonView comparison={judged.comparison} a={judged.a} b={judged.b} {colours} stale={judging} />
      {:else}
        <p class="quiet" role="status">Joining the two runs cell by cell.</p>
      {/if}
    {/if}
  </main>
</div>

<style>
  .page {
    max-width: var(--measure);
    margin-inline: auto;
    padding: clamp(1.5rem, 5vw, 3.5rem) var(--gutter) 4rem;
  }

  .masthead {
    display: grid;
    gap: 0.75rem;
    padding-bottom: 1.5rem;
    border-bottom: 1px solid var(--grid);
  }

  h1 {
    font-size: clamp(1.75rem, 4vw, 2.5rem);
    font-weight: 600;
    letter-spacing: -0.02em;
    line-height: 1.1;
  }

  .standfirst {
    max-width: 60ch;
    color: var(--ink-2);
  }

  main {
    display: grid;
    gap: 1.5rem;
    padding-top: 1.5rem;
  }

  .quiet {
    color: var(--ink-3);
  }

  .notice {
    display: grid;
    gap: 0.75rem;
    justify-items: start;
  }

  .pickers {
    display: grid;
    grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr);
    gap: 1rem;
    align-items: end;
  }

  @media (max-width: 40rem) {
    .pickers {
      grid-template-columns: 1fr;
    }

    .swap {
      justify-self: center;
      transform: rotate(90deg);
    }
  }

  .button {
    min-height: 2.75rem;
    padding: 0.5rem 0.875rem;
    font: inherit;
    color: var(--ink);
    background: var(--surface);
    border: 1px solid var(--axis);
    border-radius: 6px;
    cursor: pointer;
  }

  .button:hover:not(:disabled) {
    border-color: var(--ink-3);
  }

  .button:disabled {
    color: var(--ink-3);
    cursor: default;
  }

  .swap {
    display: grid;
    place-items: center;
    width: 2.75rem;
    padding: 0;
  }
</style>
