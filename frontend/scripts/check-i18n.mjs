// Fails when the interface is not fully bilingual:
//  1. visible English that is not wrapped in t()/tn()/N_() (JSX text, UI attributes, prose strings);
//  2. a t()/tn()/N_() literal with no Arabic entry in src/locales/ar, or with different {placeholders};
//  3. t()/tn() called at module level (it would freeze the language at import time; use N_ there);
//  4. a date, timestamp, month or language code shown as it came from the API: `.slice(0, 10)`,
//     `.slice(0, 16)`, `.slice(0, 7)` or `.toUpperCase()` on a value whose name says it is one
//     (published_at, created_at, at, day, week, month, date, lang, period.from ...). Use fmtDate,
//     fmtDateTime, fmtMonth, weekRange or langName instead.
// A line that legitimately holds English prose that is never shown (a CSS font string, a log line),
// or slices a date only to compare or key it, carries a trailing `// i18n-ok` comment. Brand and code
// tokens are listed in ALLOW.
//   node scripts/check-i18n.mjs                 all files
//   node scripts/check-i18n.mjs src/pages/X.jsx only these files (catalogue still checked in full)
import { readFileSync, readdirSync, statSync } from 'node:fs'
import { join, relative } from 'node:path'
import { parse } from '@babel/parser'
import traverseMod from '@babel/traverse'
import AR from '../src/locales/ar/index.js'

const traverse = traverseMod.default || traverseMod
const ROOT = new URL('..', import.meta.url).pathname.replace(/^\/([A-Za-z]:)/, '$1')
const SRC = join(ROOT, 'src')
const SKIP = [join(SRC, 'locales'), join(SRC, 'i18n.js')]

const files = []
const walk = (d) => readdirSync(d).forEach((f) => {
  const p = join(d, f)
  if (SKIP.some((s) => p.startsWith(s))) return
  if (statSync(p).isDirectory()) walk(p)
  else if (/\.(jsx|js)$/.test(f)) files.push(p)
})
walk(SRC)
const only = process.argv.slice(2).map((f) => join(ROOT, f.replace(/^frontend[\\/]/, '')))
const targets = only.length ? files.filter((f) => only.some((o) => f === o)) : files

const ALLOW = new Set(['Desert Watch', 'EN', 'عربي'])
const UI_ATTRS = new Set(['placeholder', 'title', 'aria-label', 'alt', 'label', 'aria-description', 'summary', 'aria-valuetext'])
const SILENT_CALLS = /^(track|api|useApi|qs|fetch|flush|dwell|console\.\w+|localStorage\.\w+|sessionStorage\.\w+|document\.\w+|window\.\w+|\w+\.addEventListener|\w+\.querySelector(All)?|readPref|writePref|navigate|nav|URLSearchParams|RegExp|Intl\.\w+|\w+\.toLocale\w+|require)$/
// code-ish strings: CSS, colours, SVG paths, URLs, date patterns, identifiers, mime types
const TECH = /^(\s*|[#.][\w-]+|var\(--[\w-]+\)|.*\bvar\(--.*|.*\d+px\b.*|[\d\s.,%-]+|https?:\/\/\S+|\/\S*|%[-\w%\s:/.,]+|[MLHVCSQTAZmlhvcsqtaz\d\s.,-]+|\w+\/[\w.+-]+|translate\(.*|rotate\(.*|scale\(.*|rgba?\(.*|hsla?\(.*|\S+\.(js|jsx|json|svg|png|csv)|[\w.-]+@[\w.-]+)$/
const PROSE = /[A-Za-z]{2,}/
// a raw date or language code on its way to the screen: a date-ish or lang-ish name, then one of the
// slices that cut an ISO string to its day, minute or month, or the upper-casing of a language code
const RAW_VALUE = /(?:\b(?:at|day|date|week|month|lang|from|to|start|end|iso|stamp)|\w*(?:_at|_on|date|day|week|month|lang|published|created|updated|measured|last_ok|period|since)\w*)\??\.(?:slice\(0, ?(?:7|10|16)\)|toUpperCase\(\))/

const name = (callee) => {
  if (!callee) return ''
  if (callee.type === 'Identifier') return callee.name
  if (callee.type === 'MemberExpression') return `${name(callee.object)}.${callee.property.name || ''}`
  return ''
}
const placeholders = (s) => new Set([...String(s).matchAll(/\{(\w+)\}/g)].map((m) => m[1]))
const sameSet = (a, b) => a.size === b.size && [...a].every((x) => b.has(x))

const problems = []
const keys = new Map() // English key -> first place used
const say = (file, node, msg) => problems.push(`${relative(ROOT, file)}:${node.loc?.start.line ?? '?'}  ${msg}`)

for (const file of targets) {
  const src = readFileSync(file, 'utf8')
  const lines = src.split('\n')
  let ast
  try {
    ast = parse(src, { sourceType: 'module', plugins: ['jsx'] })
  } catch (e) {
    problems.push(`${relative(ROOT, file)}: cannot parse (${e.message})`)
    continue
  }
  const okLine = (node) => /i18n-ok/.test(lines[(node.loc?.start.line ?? 1) - 1] || '')
  lines.forEach((line, i) => {
    if (RAW_VALUE.test(line) && !/i18n-ok/.test(line)) {
      problems.push(`${relative(ROOT, file)}:${i + 1}  a date or language code shown raw: use fmtDate/fmtDateTime/fmtMonth/weekRange/langName, or mark the line // i18n-ok if it is only compared or keyed`)
    }
  })
  const inside = (path) => {
    // where this literal sits: a translation call, a silent call, a non-UI JSX attribute, a key...
    let p = path
    while (p.parentPath) {
      const parent = p.parentPath.node
      if (parent.type === 'CallExpression') {
        if (parent.callee.type === 'Import') return 'silent' // a dynamic import('./pages/X'): a module path, never shown
        const n = name(parent.callee)
        if (n === 't' || n === 'tn' || n === 'N_') return 'translated'
        if (SILENT_CALLS.test(n) || /\.(attr|style|classed|select|selectAll|append|on|call|join|raise|lower)$/.test(n)) return 'silent'
      }
      if (parent.type === 'NewExpression' && /^(Error|URL|RegExp|Date|Intl\.\w+)$/.test(name(parent.callee))) return 'silent'
      if (parent.type === 'JSXAttribute') return UI_ATTRS.has(parent.name.name) ? 'ui' : 'silent'
      if ((parent.type === 'ObjectProperty' || parent.type === 'ObjectMethod') && parent.key === p.node) return 'silent'
      if (parent.type === 'ImportDeclaration' || ((parent.type === 'ExportAllDeclaration' || parent.type === 'ExportNamedDeclaration') && parent.source === p.node)) return 'silent'
      if (parent.type === 'BinaryExpression' && /^(===|!==|==|!=|in)$/.test(parent.operator)) return 'silent'
      if (parent.type === 'SwitchCase' && parent.test === p.node) return 'silent'
      if (parent.type === 'MemberExpression' && parent.property === p.node) return 'silent'
      if (parent.type === 'TaggedTemplateExpression') return 'silent'
      p = p.parentPath
    }
    return 'free'
  }
  const checkText = (path, text, node, jsx = false) => {
    const s = text.replace(/\s+/g, ' ').trim()
    if (!s || !PROSE.test(s) || ALLOW.has(s) || okLine(node)) return
    const where = inside(path)
    if (where === 'translated' || where === 'silent') return
    if (!jsx && where !== 'ui') {
      if (TECH.test(s)) return
      if (/^[\w-]+$/.test(s) && !/^[A-Z][a-z]{2,}/.test(s)) return // a lower-case code word: a key, a class, an id
      if (!/[A-Za-z]{2,}[^A-Za-z{}$]+[A-Za-z]{2,}|^[A-Z][a-z]{2,}/.test(s)) return
    }
    say(file, node, `not translated: "${s.slice(0, 70)}"`)
  }
  traverse(ast, {
    JSXText(path) { checkText(path, path.node.value, path.node, true) },
    StringLiteral(path) {
      if (path.parent.type === 'JSXAttribute' && !UI_ATTRS.has(path.parent.name.name)) return
      if (path.parent.type === 'ImportDeclaration' || path.parent.type === 'ExportNamedDeclaration' || path.parent.type === 'ExportAllDeclaration') return
      if (path.parent.type === 'Directive' || path.parent.type === 'DirectiveLiteral') return
      checkText(path, path.node.value, path.node)
    },
    TemplateLiteral(path) {
      const text = path.node.quasis.map((q) => q.value.cooked).join(' ')
      checkText(path, text, path.node)
    },
    CallExpression(path) {
      const n = name(path.node.callee)
      if (n !== 't' && n !== 'tn' && n !== 'N_') return
      const args = path.node.arguments
      const lit = n === 'tn' ? [args[1], args[2]] : [args[0]]
      if (n !== 'N_' && !path.getFunctionParent()) say(file, path.node, `${n}() at module level: wrap the string in N_() there and call t() when rendering`)
      for (const a of lit) {
        if (!a) continue
        if (a.type === 'StringLiteral') { if (!keys.has(a.value)) keys.set(a.value, `${relative(ROOT, file)}:${a.loc.start.line}`) }
        else if (a.type === 'TemplateLiteral' && a.expressions.length === 0) { const v = a.quasis[0].value.cooked; if (!keys.has(v)) keys.set(v, `${relative(ROOT, file)}:${a.loc.start.line}`) }
        else if (a.type === 'TemplateLiteral') say(file, a, `${n}() with a template string: use {placeholders} and pass values, e.g. t('{n} articles', { n })`)
      }
      if (n === 'tn' && args[1]?.type === 'StringLiteral' && args[2]?.type === 'StringLiteral') {
        keys.delete(args[1].value) // the Arabic side only needs the 'other' form
        const one = placeholders(args[1].value), other = placeholders(args[2].value)
        if (![...one].every((x) => other.has(x))) say(file, path.node, `tn() forms use different placeholders`)
      }
    },
  })
}

// catalogue: every key used has Arabic, with the same placeholders
for (const [k, where] of keys) {
  const a = AR[k]
  if (a == null || a === '') { problems.push(`${where}  no Arabic for: "${k.slice(0, 80)}"`); continue }
  const en = placeholders(k)
  if (typeof a === 'string') {
    if (!sameSet(en, placeholders(a))) problems.push(`${where}  placeholders differ in Arabic for: "${k.slice(0, 60)}"`)
    if (!/[\u0600-\u06FF]/.test(a)) problems.push(`${where}  Arabic entry has no Arabic letters: "${k.slice(0, 60)}"`)
  } else if (typeof a === 'object') {
    if (!a.other) problems.push(`${where}  plural entry needs an 'other' form: "${k.slice(0, 60)}"`)
    for (const [form, v] of Object.entries(a)) {
      if (!['zero', 'one', 'two', 'few', 'many', 'other'].includes(form)) problems.push(`${where}  unknown plural form ${form}`)
      if (![...placeholders(v)].every((x) => en.has(x))) problems.push(`${where}  Arabic ${form} form uses a placeholder English does not: "${k.slice(0, 60)}"`)
    }
  }
}

if (!only.length) {
  const unused = Object.keys(AR).filter((k) => !keys.has(k))
  if (unused.length) console.warn(`i18n: ${unused.length} Arabic entries not used by any t()/tn()/N_() literal (fine if used through a variable)`)
}
if (problems.length) {
  console.error(problems.join('\n'))
  console.error(`\ni18n check failed: ${problems.length} problem(s) in ${targets.length} file(s)`)
  process.exit(1)
}
console.log(`i18n check ok (${targets.length} files, ${keys.size} strings, ${Object.keys(AR).length} Arabic entries)`)
