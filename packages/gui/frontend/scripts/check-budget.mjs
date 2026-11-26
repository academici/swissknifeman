// Performance budget of the built frontend (`npm run build` first): reads dist/index.html, follows the initial scripts
// and styles (script tags, stylesheet and modulepreload links, static imports between chunks) and checks
//   initial JS (gzip) <= 190 kB, initial CSS (gzip) <= 12 kB, every JS chunk (gzip) <= 400 kB,
//   and that the initial scripts carry no xterm: the terminal loads in a chunk of its own, on the /terminal page only.
// kB = 1000 bytes. `--dist DIR` checks another folder (tests); exit 1 with one line per violation.
import { existsSync, readFileSync, readdirSync } from "node:fs";
import { dirname, join, normalize } from "node:path";
import { fileURLToPath } from "node:url";
import { gzipSync } from "node:zlib";

export const BUDGET = {
  initialJs: 190_000,
  initialCss: 12_000,
  chunkJs: 400_000,
};

const gz = (buffer) => gzipSync(buffer, { level: 9 }).length;

/** Asset paths named by index.html: [{ file, kind }] with kind js|css, in document order. */
export function initialAssets(html) {
  const found = [];
  for (const tag of html.match(/<(?:script|link)\b[^>]*>/gi) ?? []) {
    const attr = (name) => tag.match(new RegExp(`\\b${name}\\s*=\\s*"([^"]*)"`, "i"))?.[1];
    if (/^<script/i.test(tag) && attr("src")) found.push({ file: attr("src"), kind: "js" });
    else if (/^<link/i.test(tag) && attr("href")) {
      const rel = (attr("rel") ?? "").toLowerCase();
      if (rel === "stylesheet") found.push({ file: attr("href"), kind: "css" });
      else if (rel === "modulepreload") found.push({ file: attr("href"), kind: "js" });
    }
  }
  return found;
}

/** Static imports of a chunk (`import{..}from"./x.js"`, `import"./x.js"`); dynamic `import("./x.js")` does not count. */
export function staticImports(source) {
  return [...source.matchAll(/(?:\bfrom\s*|\bimport\s*)"(\.{1,2}\/[^"]+\.js)"/g)].map((match) => match[1]);
}

/** The source without what only names another chunk: dynamic import specifiers and the Vite dependency map. */
export function withoutChunkReferences(source) {
  return source
    .replace(/import\(\s*["'`][^"'`]*["'`]\s*\)/g, "import()")
    .replace(/__vite__mapDeps\(\[[^\]]*\]\)/g, "")
    .replace(/m\.f\s*=\s*\[[^\]]*\]/g, "");
}

export function check(dist) {
  const problems = [];
  const indexPath = join(dist, "index.html");
  if (!existsSync(indexPath)) return { problems: [`${indexPath} does not exist; run \`npm run build\` first`], report: {} };
  const html = readFileSync(indexPath, "utf8");
  const resolveAsset = (from, ref) => normalize(ref.startsWith("/") ? join(dist, ref) : join(dirname(from), ref));

  const queue = initialAssets(html).map(({ file, kind }) => ({ path: resolveAsset(indexPath, file), kind }));
  const seen = new Map();
  while (queue.length > 0) {
    const { path, kind } = queue.shift();
    if (seen.has(path)) continue;
    if (!existsSync(path)) {
      problems.push(`${path}: named by the initial page but missing`);
      continue;
    }
    const buffer = readFileSync(path);
    seen.set(path, { kind, raw: buffer.length, gzip: gz(buffer) });
    if (kind === "js") {
      const source = buffer.toString("utf8");
      for (const ref of staticImports(source)) queue.push({ path: resolveAsset(path, ref), kind: "js" });
      if (/xterm/i.test(withoutChunkReferences(source))) problems.push(`${path}: the initial script contains xterm`);
    }
    if (/xterm/i.test(path.split("/").pop() ?? "")) problems.push(`${path}: an xterm file is loaded at start`);
  }

  let js = 0;
  let css = 0;
  for (const entry of seen.values()) entry.kind === "js" ? (js += entry.gzip) : (css += entry.gzip);
  if (js > BUDGET.initialJs) problems.push(`initial JS is ${js} bytes gzip, the budget is ${BUDGET.initialJs}`);
  if (css > BUDGET.initialCss) problems.push(`initial CSS is ${css} bytes gzip, the budget is ${BUDGET.initialCss}`);

  const assets = join(dist, "assets");
  const chunks = existsSync(assets) ? readdirSync(assets).filter((name) => name.endsWith(".js")).sort() : [];
  for (const name of chunks) {
    const size = gz(readFileSync(join(assets, name)));
    if (size > BUDGET.chunkJs) problems.push(`assets/${name} is ${size} bytes gzip, the budget per chunk is ${BUDGET.chunkJs}`);
  }
  return { problems, report: { initialJs: js, initialCss: css, initialFiles: seen.size, chunks: chunks.length } };
}

if (process.argv[1] && fileURLToPath(import.meta.url) === normalize(process.argv[1])) {
  const at = process.argv.indexOf("--dist");
  const dist = at > 0 && process.argv[at + 1] ? process.argv[at + 1] : join(dirname(fileURLToPath(import.meta.url)), "..", "dist");
  const { problems, report } = check(dist);
  if (problems.length > 0) {
    for (const problem of problems) console.error(`budget: ${problem}`);
    process.exit(1);
  }
  console.log(
    `budget ok: initial JS ${report.initialJs} B gzip (<= ${BUDGET.initialJs}), CSS ${report.initialCss} B (<= ${BUDGET.initialCss}), ` +
      `${report.chunks} chunk(s) each <= ${BUDGET.chunkJs}`,
  );
}
