// The catalogue as results-catalogue writes it: one row per run, read straight from the Parquet.
import { query, register } from './db'

export interface Run {
  key: string
  kind: string
  run: string
  submitted: Date
  finished: Date | null
  queue: string
  commit: string | null
  image: string | null
  imageDigest: string | null
  clusterConfigSha256: string | null
  instanceType: string | null
  nodes: number | null
  nodesUsed: number | null
  seed: number | null
  parents: string[]
  jobs: Record<string, number | string>
  parameters: Record<string, unknown>
  cells: number
}

interface Row {
  key: string
  kind: string
  run: string
  submitted: number
  finished: number | null
  queue: string
  commit: string | null
  image: string | null
  image_digest: string | null
  cluster_config_sha256: string | null
  instance_type: string | null
  nodes: number | null
  nodes_used: number | null
  seed: number | null
  parents: string[]
  jobs: string
  parameters: string
  cells: number
}

/** Every run in the snapshot, newest first. */
export async function loadRuns(): Promise<Run[]> {
  await register('runs.parquet', 'runs.parquet')
  const rows = await query<Row>(`select * from 'runs.parquet' order by submitted desc`)
  return rows.map(toRun)
}

function toRun(row: Row): Run {
  return {
    key: row.key,
    kind: row.kind,
    run: row.run,
    submitted: new Date(row.submitted),
    finished: row.finished === null ? null : new Date(row.finished),
    queue: row.queue,
    commit: row.commit,
    image: row.image,
    imageDigest: row.image_digest,
    clusterConfigSha256: row.cluster_config_sha256,
    instanceType: row.instance_type,
    nodes: row.nodes,
    nodesUsed: row.nodes_used,
    seed: row.seed,
    parents: row.parents ?? [],
    jobs: JSON.parse(row.jobs) as Record<string, number | string>,
    parameters: JSON.parse(row.parameters) as Record<string, unknown>,
    cells: row.cells,
  }
}
