// Fails if a JSX component (<Capitalised ...>) is used in a file without being imported or
// defined there. Vite builds such files happily; they only crash in the browser.
//   node scripts/check-components.mjs
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join } from 'node:path'

const files = []
const walk = (d) => readdirSync(d).forEach((f) => {
  const p = join(d, f)
  if (statSync(p).isDirectory()) walk(p)
  else if (/\.(jsx|js)$/.test(f)) files.push(p)
})
walk(new URL('../src', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1'))

const BUILTIN = new Set(['Fragment'])
let bad = 0
for (const f of files) {
  const src = readFileSync(f, 'utf8')
  const used = new Set([...src.matchAll(/<([A-Z][A-Za-z0-9]*)[\s/>]/g)].map((m) => m[1]))
  const known = new Set([
    ...[...src.matchAll(/import\s+([A-Z][A-Za-z0-9]*)/g)].map((m) => m[1]),
    ...[...src.matchAll(/import\s*(?:[A-Za-z0-9_]+\s*,\s*)?\{([^}]*)\}/g)].flatMap((m) => m[1].split(',').map((x) => x.trim().split(/\s+as\s+/).pop())),
    ...[...src.matchAll(/(?:function|const|class)\s+([A-Z][A-Za-z0-9]*)/g)].map((m) => m[1]),
  ])
  for (const u of used) {
    if (!known.has(u) && !BUILTIN.has(u)) { console.error(`${f}: <${u}> is used but not imported or defined`); bad++ }
  }
}
if (bad) process.exit(1)
console.log(`component check ok (${files.length} files)`)
