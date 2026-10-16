#!/usr/bin/env node
// Parse every ```mermaid block of the tracked Markdown sources with the mermaid library of the docs site.
//
//   node scripts/docs-mermaid-check.mjs [FILE.md ...]     (default: the tracked pages of the site, docs/ and
//                                                           packages/*/docs/, without the copies docs-sync.sh makes)
//
// Needs `npm ci` in docs/ (mermaid and dompurify from docs/node_modules). The site renders diagrams in the browser,
// so a broken one only shows as an error box on the page; this check finds it before the deploy.
// Exit: 0 every diagram parses, 1 at least one does not (each is printed as FILE #N: error).
import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const modules = join(root, 'docs', 'node_modules');

// mermaid.parse needs no layout, but its module touches a browser at import time: give it the least that loads.
globalThis.window = globalThis;
globalThis.addEventListener = () => {};
globalThis.document = { createElement: () => ({ style: {} }), querySelector: () => null, addEventListener: () => {} };
const purify = (await import(pathToFileURL(join(modules, 'dompurify', 'dist', 'purify.es.mjs')).href)).default;
Object.assign(purify, { addHook: () => {}, removeHook: () => {}, removeHooks: () => {}, sanitize: (x) => x });
const { default: mermaid } = await import(pathToFileURL(join(modules, 'mermaid', 'dist', 'mermaid.core.mjs')).href);
mermaid.initialize({ startOnLoad: false });

function sources() {
  const copies = /^docs\/(analyst|brain|core|harness|maind|orch|planner|skiller)\//;
  const site = [':(glob)docs/**/*.md', ':(glob)packages/*/docs/**/*.md'];  // what the site renders; -z: names stay unquoted
  return execFileSync('git', ['ls-files', '-z', '--', ...site], { cwd: root, encoding: 'utf8' })
    .split('\0').filter((path) => path && !copies.test(path) && !path.includes('node_modules'));
}

const files = process.argv.length > 2 ? process.argv.slice(2) : sources();
let total = 0;
let bad = 0;
for (const file of files) {
  const text = readFileSync(join(root, file), 'utf8');
  const blocks = [...text.matchAll(/```mermaid\n([\s\S]*?)```/g)].map((match) => match[1]);
  for (const [index, block] of blocks.entries()) {
    total += 1;
    try {
      await mermaid.parse(block);
    } catch (error) {
      bad += 1;
      console.log(`${file} #${index + 1}: ${String(error.message || error).split('\n').slice(0, 3).join(' | ')}`);
    }
  }
}
console.log(`mermaid: ${total} diagram(s), ${bad} invalid`);
process.exit(bad ? 1 : 0);
