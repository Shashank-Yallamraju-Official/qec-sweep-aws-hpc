// Fails the build when the first script grows past its budget. The first script is the one
// index.html loads; everything else (the query engine, the chart library) arrives after paint.
import { readFileSync, readdirSync } from 'node:fs'
import { join } from 'node:path'
import { brotliCompressSync, gzipSync } from 'node:zlib'

const DIST = new URL('../dist/', import.meta.url).pathname
const BUDGET_KB = 150

const html = readFileSync(join(DIST, 'index.html'), 'utf8')
const entry = /<script[^>]+type="module"[^>]+src="([^"]+)"/.exec(html)?.[1]
if (!entry) {
  console.error('budget: index.html loads no module script')
  process.exit(2)
}

const kb = (bytes) => (bytes / 1024).toFixed(1)
const compressed = (path) => {
  const bytes = readFileSync(path)
  return { raw: bytes.length, gzip: gzipSync(bytes).length, brotli: brotliCompressSync(bytes).length }
}

// The src carries the deploy's base path; the file itself sits under dist/assets whatever that is.
const first = compressed(join(DIST, 'assets', entry.split('/').pop()))
console.log(`first script ${entry}: ${kb(first.raw)} kB, ${kb(first.gzip)} kB gzip, ${kb(first.brotli)} kB brotli`)

const assets = join(DIST, 'assets')
for (const file of readdirSync(assets).filter((f) => f.endsWith('.js') && !entry.endsWith(f)).sort()) {
  const size = compressed(join(assets, file))
  console.log(`  later: ${file}: ${kb(size.gzip)} kB gzip`)
}

if (first.gzip > BUDGET_KB * 1024) {
  console.error(`budget: the first script is ${kb(first.gzip)} kB gzip; the budget is ${BUDGET_KB} kB`)
  process.exit(1)
}
console.log(`budget: ${kb(first.gzip)} kB of ${BUDGET_KB} kB`)
