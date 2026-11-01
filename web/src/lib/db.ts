// DuckDB in a worker, started on first use so the shell paints before the engine downloads.
// Parquet files are registered by URL and read with range requests; nothing is downloaded whole.
import type { AsyncDuckDB, AsyncDuckDBConnection } from '@duckdb/duckdb-wasm'

type Engine = { db: AsyncDuckDB; connection: AsyncDuckDBConnection; registered: Set<string> }

let engine: Promise<Engine> | undefined

async function start(): Promise<Engine> {
  const duckdb = await import('@duckdb/duckdb-wasm')
  const [mvpModule, mvpWorker, ehModule, ehWorker] = await Promise.all([
    import('@duckdb/duckdb-wasm/dist/duckdb-mvp.wasm?url'),
    import('@duckdb/duckdb-wasm/dist/duckdb-browser-mvp.worker.js?url'),
    import('@duckdb/duckdb-wasm/dist/duckdb-eh.wasm?url'),
    import('@duckdb/duckdb-wasm/dist/duckdb-browser-eh.worker.js?url'),
  ])
  const bundle = await duckdb.selectBundle({
    mvp: { mainModule: mvpModule.default, mainWorker: mvpWorker.default },
    eh: { mainModule: ehModule.default, mainWorker: ehWorker.default },
  })
  const worker = new Worker(bundle.mainWorker!, { type: 'module' })
  const db = new duckdb.AsyncDuckDB(new duckdb.VoidLogger(), worker)
  await db.instantiate(bundle.mainModule, bundle.pthreadWorker)
  return { db, connection: await db.connect(), registered: new Set() }
}

function running(): Promise<Engine> {
  engine ??= start().catch((error: unknown) => {
    engine = undefined
    throw error
  })
  return engine
}

/** The absolute URL of a file under the site's data directory. */
export function dataUrl(path: string): string {
  return new URL(`${import.meta.env.BASE_URL}data/${path}`, window.location.href).href
}

/** Make a data file queryable by name; registering twice is harmless. */
export async function register(name: string, path: string): Promise<void> {
  const { db, registered } = await running()
  if (registered.has(name)) return
  const duckdb = await import('@duckdb/duckdb-wasm')
  await db.registerFileURL(name, dataUrl(path), duckdb.DuckDBDataProtocol.HTTP, false)
  registered.add(name)
}

/** Milliseconds the last query took, engine start excluded: the number the metric wants. */
export let lastQueryMs = 0

/** Run one statement and return its rows as plain objects. */
export async function query<Row extends object>(sql: string): Promise<Row[]> {
  const { connection } = await running()
  const started = performance.now()
  const table = await connection.query(sql)
  lastQueryMs = performance.now() - started
  return table.toArray().map((row) => plain(row.toJSON()) as Row)
}

// Arrow hands back BigInt for 64-bit integers and Vector for lists; the site wants numbers and arrays.
function plain(row: Record<string, unknown>): Record<string, unknown> {
  const out: Record<string, unknown> = {}
  for (const [key, value] of Object.entries(row)) {
    if (typeof value === 'bigint') out[key] = Number(value)
    else if (value && typeof value === 'object' && 'toArray' in value) {
      out[key] = Array.from((value as { toArray(): unknown[] }).toArray())
    } else out[key] = value
  }
  return out
}
