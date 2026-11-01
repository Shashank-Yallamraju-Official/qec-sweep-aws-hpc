<script lang="ts">
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
  <main>
    <p class="quiet">No runs loaded yet.</p>
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
</style>
