// The bundle budget. Runs after `vite build` (npm run build) and fails when the JavaScript a reader
// downloads before the first screen renders is larger than the budget: the entry chunk index.html loads
// plus any chunk it modulepreloads. Everything else (the pages behind React.lazy, the charts, the world
// atlas, the Arabic catalogue) is fetched on demand and is listed but not counted.
//   node scripts/check-bundle.mjs                 dist/ next to this folder, budget 300 KB
//   node scripts/check-bundle.mjs <dist> --budget=320
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'

const args = process.argv.slice(2)
const dir = args.find((a) => !a.startsWith('--')) || new URL('../dist', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1')
const BUDGET_KB = +(args.find((a) => a.startsWith('--budget='))?.split('=')[1] || 300)

let html
try { html = readFileSync(join(dir, 'index.html'), 'utf8') } catch { console.error(`bundle check: no index.html in ${dir} (run vite build first)`); process.exit(1) }
const entry = [...html.matchAll(/<script[^>]+type="module"[^>]+src="\/?([^"]+\.js)"/g)].map((m) => m[1])
const preload = [...html.matchAll(/<link[^>]+rel="modulepreload"[^>]+href="\/?([^"]+\.js)"/g)].map((m) => m[1])
if (!entry.length) { console.error('bundle check: index.html loads no module script'); process.exit(1) }
const upFront = new Set([...entry, ...preload])
const kb = (p) => statSync(join(dir, p)).size / 1024

const assets = readdirSync(join(dir, 'assets')).filter((f) => f.endsWith('.js'))
  .map((f) => ({ path: `assets/${f}`, kb: kb(`assets/${f}`) })).sort((a, b) => b.kb - a.kb)
for (const a of assets) console.log(`${a.kb.toFixed(1).padStart(8)} KB  ${a.path}${upFront.has(a.path) ? (entry.includes(a.path) ? '  (entry)' : '  (preloaded)') : ''}`)
const total = [...upFront].reduce((n, p) => n + kb(p), 0)
if (total > BUDGET_KB) {
  console.error(`bundle check failed: ${total.toFixed(1)} KB loads before the first screen (budget ${BUDGET_KB} KB). Lazy-load the page or library that grew.`)
  process.exit(1)
}
console.log(`bundle check ok: ${total.toFixed(1)} KB before the first screen, budget ${BUDGET_KB} KB (${assets.length} chunks in all)`)
