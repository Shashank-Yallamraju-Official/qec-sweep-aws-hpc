<script lang="ts">
  import type { Run } from './catalogue'

  interface Props {
    id: string
    label: string
    runs: Run[]
    value: string | null
    exclude: string | null
    colour: 1 | 2 | null
    onchange: (key: string) => void
  }

  let { id, label, runs, value, exclude, colour, onchange }: Props = $props()

  const when = new Intl.DateTimeFormat('en-GB', { dateStyle: 'medium', timeStyle: 'short', timeZone: 'UTC' })

  function describe(run: Run): string {
    const nodes = run.nodesUsed ?? run.nodes
    const where = nodes === null ? run.queue : `${nodes} nodes`
    return `${run.run}, ${when.format(run.submitted)} UTC, ${where}`
  }
</script>

<div class="picker">
  <label for={id}>
    <span class="key" data-colour={colour} aria-hidden="true"></span>
    {label}
  </label>
  <select {id} value={value ?? ''} onchange={(event) => onchange(event.currentTarget.value)}>
    <option value="" disabled>Choose a run</option>
    {#each runs as run (run.key)}
      <option value={run.key} disabled={run.key === exclude}>{describe(run)}</option>
    {/each}
  </select>
</div>

<style>
  .picker {
    display: grid;
    gap: 0.375rem;
    min-width: 0;
  }

  label {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    font-weight: 500;
    color: var(--ink-2);
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

  select {
    width: 100%;
    min-height: 2.75rem;
    padding: 0.5rem 2.25rem 0.5rem 0.75rem;
    font: inherit;
    font-variant-numeric: tabular-nums;
    color: var(--ink);
    background: var(--surface);
    border: 1px solid var(--axis);
    border-radius: 6px;
  }

  select:hover {
    border-color: var(--ink-3);
  }
</style>
