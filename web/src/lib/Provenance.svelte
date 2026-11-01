<script lang="ts">
  import type { Run } from './catalogue'

  interface Props {
    runs: [Run, Run]
    labels: [string, string]
    colours: ReadonlyMap<string, 1 | 2>
    known: Run[]
    onparent: (parentKey: string, childKey: string) => void
  }

  let { runs, labels, colours, known, onparent }: Props = $props()

  const REPO = 'https://github.com/Shashank-Yallamraju-Official/qec-sweep-aws-hpc'
  const when = new Intl.DateTimeFormat('en-GB', { dateStyle: 'medium', timeStyle: 'medium', timeZone: 'UTC' })

  const sha = /^[0-9a-f]{7,40}$/

  function commitUrl(commit: string): string | null {
    return sha.test(commit) ? `${REPO}/commit/${commit}` : null
  }

  function configUrl(commit: string | null): string | null {
    return commit && sha.test(commit) ? `${REPO}/blob/${commit}/cluster/cluster.yaml` : null
  }

  function imageName(image: string): string {
    // oras://ghcr.io/owner/repo/sweep:tag -> sweep
    const path = image.replace(/^[a-z]+:\/\//, '').split(':')[0] ?? image
    return path.split('/').pop() ?? image
  }

  function imageUrl(image: string): string | null {
    const match = /ghcr\.io\/([^/]+)\/([^/]+)\/([^:]+)/.exec(image)
    if (!match) return null
    const [, owner, repo, name] = match
    return `https://github.com/${owner}/${repo}/pkgs/container/${repo}%2F${name}`
  }

  function duration(run: Run): string {
    if (!run.finished) return 'still running when catalogued'
    const minutes = (run.finished.getTime() - run.submitted.getTime()) / 60000
    return `${minutes.toFixed(1)} min`
  }

  function where(run: Run): string {
    const nodes = run.nodesUsed ?? run.nodes
    const parts = [run.queue]
    if (nodes !== null) parts.push(`${nodes} × ${run.instanceType ?? 'node'}`)
    return parts.join(', ')
  }

  function knownRun(key: string): Run | undefined {
    return known.find((run) => run.key === key)
  }
</script>

<section class="provenance" aria-label="Where each run came from">
  <h2>Where each run came from</h2>
  <p class="quiet">Every field below is read from the run's own record in the bucket. The address is the key; nothing here was typed in.</p>
  <div class="columns">
    {#each runs as run, i (run.key)}
      <article>
        <h3><span class="key" data-colour={colours.get(run.key)} aria-hidden="true"></span>{labels[i]}</h3>
        <dl>
          <dt>Address</dt>
          <dd class="mono break">{run.key}</dd>

          <dt>Submitted</dt>
          <dd>{when.format(run.submitted)} UTC, {duration(run)}</dd>

          <dt>Ran on</dt>
          <dd>{where(run)}</dd>

          <dt>Commit</dt>
          <dd class="mono">
            {#if run.commit}
              {@const url = commitUrl(run.commit)}
              {#if url}<a href={url} rel="noopener">{run.commit.slice(0, 12)}</a>{:else}{run.commit}{/if}
            {:else}
              <span class="quiet">not recorded</span>
            {/if}
          </dd>

          <dt>Image</dt>
          <dd>
            {#if run.image}
              {@const url = imageUrl(run.image)}
              {#if url}<a href={url} rel="noopener">{imageName(run.image)}</a>{:else}{imageName(run.image)}{/if}
              <span class="mono break digest">{run.imageDigest ?? 'digest not recorded'}</span>
            {:else}
              <span class="quiet">not recorded</span>
            {/if}
          </dd>

          <dt>Cluster configuration</dt>
          <dd class="mono break">
            {#if run.clusterConfigSha256}
              {@const url = configUrl(run.commit)}
              {#if url}<a href={url} rel="noopener">sha256:{run.clusterConfigSha256.slice(0, 12)}</a>{:else}sha256:{run.clusterConfigSha256.slice(0, 12)}{/if}
            {:else}
              <span class="quiet">not recorded</span>
            {/if}
          </dd>

          <dt>Slurm jobs</dt>
          <dd class="mono">
            {#if Object.keys(run.jobs).length}
              {Object.entries(run.jobs)
                .map(([name, id]) => `${name} ${id}`)
                .join(', ')}
            {:else}
              <span class="quiet">not recorded</span>
            {/if}
          </dd>

          <dt>Seed</dt>
          <dd class="mono">{run.seed ?? 'not recorded'}</dd>

          <dt>Made from</dt>
          <dd>
            {#if run.parents.length === 0}
              <span class="quiet">no parent run</span>
            {:else}
              <ul class="parents">
                {#each run.parents as parent (parent)}
                  {@const found = knownRun(parent)}
                  <li>
                    <span class="mono break">{parent}</span>
                    {#if found && !runs.some((shown) => shown.key === found.key)}
                      <button type="button" class="link" onclick={() => onparent(found.key, run.key)}>
                        judge against it
                      </button>
                    {:else if !found}
                      <span class="quiet">not in this snapshot</span>
                    {/if}
                  </li>
                {/each}
              </ul>
            {/if}
          </dd>
        </dl>
      </article>
    {/each}
  </div>
</section>

<style>
  .provenance {
    display: grid;
    gap: 1rem;
    padding-top: 1.5rem;
    border-top: 1px solid var(--grid);
  }

  h2 {
    font-size: 1.25rem;
    font-weight: 600;
    letter-spacing: -0.01em;
  }

  h3 {
    display: flex;
    gap: 0.5rem;
    align-items: center;
    font-size: 1rem;
    font-weight: 500;
    color: var(--ink-2);
  }

  .quiet {
    color: var(--ink-3);
  }

  .columns {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(min(100%, 22rem), 1fr));
    gap: 1.5rem 2.5rem;
  }

  article {
    display: grid;
    align-content: start;
    gap: 0.75rem;
    min-width: 0;
  }

  dl {
    display: grid;
    grid-template-columns: max-content minmax(0, 1fr);
    gap: 0.5rem 1rem;
    margin: 0;
  }

  dt {
    color: var(--ink-3);
  }

  dd {
    margin: 0;
    min-width: 0;
  }

  .mono {
    font-family: var(--mono);
    font-size: 0.875em;
  }

  .break {
    overflow-wrap: anywhere;
  }

  .digest {
    display: block;
    color: var(--ink-3);
  }

  .key {
    width: 1rem;
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

  .parents {
    display: grid;
    gap: 0.375rem;
    margin: 0;
    padding: 0;
    list-style: none;
  }

  .parents li {
    display: flex;
    flex-wrap: wrap;
    gap: 0.25rem 0.75rem;
    align-items: baseline;
  }

  .link {
    padding: 0;
    font: inherit;
    color: var(--ink);
    background: none;
    border: 0;
    text-decoration: underline;
    text-decoration-color: var(--axis);
    text-underline-offset: 0.15em;
    cursor: pointer;
  }

  .link:hover {
    text-decoration-color: currentColor;
  }
</style>
