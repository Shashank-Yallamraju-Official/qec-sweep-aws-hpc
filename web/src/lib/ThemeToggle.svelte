<script lang="ts">
  import { applyTheme, storedTheme, type Theme } from './theme'

  let theme = $state<Theme>(storedTheme())

  const options: { value: Theme; label: string }[] = [
    { value: 'system', label: 'System' },
    { value: 'light', label: 'Light' },
    { value: 'dark', label: 'Dark' },
  ]

  function pick(next: Theme) {
    theme = next
    applyTheme(next)
  }
</script>

<fieldset class="toggle">
  <legend class="visually-hidden">Colour theme</legend>
  {#each options as option (option.value)}
    <label class:on={theme === option.value}>
      <input
        type="radio"
        name="theme"
        value={option.value}
        checked={theme === option.value}
        onchange={() => pick(option.value)}
      />
      {option.label}
    </label>
  {/each}
</fieldset>

<style>
  .toggle {
    display: inline-flex;
    gap: 2px;
    margin: 0;
    padding: 2px;
    border: 1px solid var(--axis);
    border-radius: 8px;
    background: var(--surface);
  }

  label {
    position: relative;
    display: inline-flex;
    align-items: center;
    min-height: 2.25rem;
    padding: 0 0.75rem;
    font-size: 0.9375rem;
    color: var(--ink-2);
    border-radius: 6px;
    cursor: pointer;
  }

  label.on {
    color: var(--ink);
    background: var(--page);
    box-shadow: inset 0 0 0 1px var(--ring);
  }

  label:hover:not(.on) {
    color: var(--ink);
  }

  input {
    position: absolute;
    inset: 0;
    width: 100%;
    height: 100%;
    margin: 0;
    opacity: 0;
    cursor: pointer;
  }

  label:has(input:focus-visible) {
    outline: 2px solid var(--focus);
    outline-offset: 1px;
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
