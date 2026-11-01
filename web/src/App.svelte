<script lang="ts">
  import { onMount } from 'svelte'
  import { loadRuns, type Run } from './lib/catalogue'

  type State = { kind: 'loading' } | { kind: 'error'; message: string } | { kind: 'ready'; runs: Run[] }

  let state = $state<State>({ kind: 'loading' })

  async function load() {
    state = { kind: 'loading' }
    try {
      state = { kind: 'ready', runs: await loadRuns() }
    } catch (error) {
      state = { kind: 'error', message: error instanceof Error ? error.message : String(error) }
    }
  }

  onMount(load)

  const when = new Intl.DateTimeFormat('en-GB', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'UTC' })
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
  <main aria-live="polite" aria-busy={state.kind === 'loading'}>
    {#if state.kind === 'loading'}
      <p class="quiet">Loading the catalogue.</p>
    {:else if state.kind === 'error'}
      <div class="notice" role="alert">
        <p>The catalogue could not be read: {state.message}</p>
        <button type="button" onclick={load}>Try again</button>
      </div>
    {:else if state.runs.length === 0}
      <p class="quiet">The snapshot holds no runs yet. The next merge to main publishes one.</p>
    {:else}
      <table>
        <caption class="visually-hidden">Runs in the catalogue</caption>
        <thead>
          <tr>
            <th scope="col">Run</th>
            <th scope="col">Kind</th>
            <th scope="col">Submitted</th>
            <th scope="col" class="num">Nodes</th>
            <th scope="col" class="num">Cells</th>
          </tr>
        </thead>
        <tbody>
          {#each state.runs as run (run.key)}
            <tr>
              <td class="mono">{run.run}</td>
              <td>{run.kind}</td>
              <td>{when.format(run.submitted)} UTC</td>
              <td class="num">{run.nodesUsed ?? run.nodes ?? ''}</td>
              <td class="num">{run.cells}</td>
            </tr>
          {/each}
        </tbody>
      </table>
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

  table {
    width: 100%;
    border-collapse: collapse;
    font-variant-numeric: tabular-nums;
  }

  th,
  td {
    padding: 0.5rem 0.75rem 0.5rem 0;
    text-align: left;
    border-bottom: 1px solid var(--grid);
  }

  th {
    font-weight: 500;
    color: var(--ink-2);
  }

  .num {
    text-align: right;
  }

  .mono {
    font-family: var(--mono);
    font-size: 0.9375em;
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
