import { readFileSync, readdirSync } from "node:fs";
import { join } from "node:path";
import { fileURLToPath } from "node:url";
import { gzipSync } from "node:zlib";

const limits = { initialJs: 190_000, initialCss: 12_000, chunkJs: 400_000 };
const gzipSize = (path) => gzipSync(readFileSync(path), { level: 9 }).length;

function htmlAssets(html) {
  const scripts = [];
  const styles = [];
  for (const [tag] of html.matchAll(/<(?:script|link)\b[^>]*>/gi)) {
    const attributes = new Map(
      [...tag.matchAll(/\s([\w-]+)\s*=\s*["']([^"']+)["']/g)].map(([, name, value]) => [name.toLowerCase(), value]),
    );
    const rel = attributes.get("rel")?.toLowerCase();
    const isScript = /^<script\b/iu.test(tag);
    const file = attributes.get(isScript ? "src" : "href")?.replace(/^\//, "");
    if (isScript && !file) throw new Error("index.html contains an inline script");
    if (!file) continue;
    if (isScript || rel === "modulepreload") scripts.push(file);
    if (rel === "stylesheet") styles.push(file);
  }
  return { scripts, styles };
}

function check(dist) {
  const read = (file) => readFileSync(join(dist, file), "utf8");
  const manifest = JSON.parse(read(".vite/manifest.json"));
  const markdown = new Set(JSON.parse(read(".vite/markdown-chunks.json")));
  const byFile = new Map(Object.values(manifest).map((chunk) => [chunk.file, chunk]));
  const { scripts, styles } = htmlAssets(read("index.html"));
  if (scripts.length === 0) throw new Error("index.html is missing its entry script");

  const initialJs = new Set();
  const initialCss = new Set(styles);
  for (const file of scripts) {
    if (initialJs.has(file)) continue;
    initialJs.add(file);
    const chunk = byFile.get(file);
    if (!chunk) throw new Error(`Missing manifest entry for ${file}`);
    for (const key of chunk.imports ?? []) {
      if (!manifest[key]) throw new Error(`Missing manifest entry for ${key}`);
      scripts.push(manifest[key].file);
    }
    for (const css of chunk.css ?? []) initialCss.add(css);
  }

  const problems = [];
  const total = (files) => [...files].reduce((size, file) => size + gzipSize(join(dist, file)), 0);
  const js = total(initialJs);
  const css = total(initialCss);
  if (js > limits.initialJs) problems.push(`initial JS is ${js} B gzip (limit ${limits.initialJs})`);
  if (css > limits.initialCss) problems.push(`initial CSS is ${css} B gzip (limit ${limits.initialCss})`);
  for (const file of initialJs) {
    if (markdown.has(file)) problems.push(`${file} loads react-markdown at startup`);
  }

  const chunks = readdirSync(dist, { recursive: true }).filter((file) => file.endsWith(".js"));
  let largest = 0;
  for (const file of chunks) {
    const size = gzipSize(join(dist, file));
    largest = Math.max(largest, size);
    if (size > limits.chunkJs) problems.push(`${file} is ${size} B gzip (limit ${limits.chunkJs})`);
  }

  if (problems.length > 0) throw new Error(problems.join("\n"));
  console.log(`budget ok: initial JS ${js} B, CSS ${css} B, largest of ${chunks.length} JS chunks ${largest} B (gzip)`);
}

try {
  const dist = process.argv[2] === "--dist" ? process.argv[3] : undefined;
  check(dist ?? fileURLToPath(new URL("../dist/", import.meta.url)));
} catch (error) {
  console.error(`budget: ${error.message}`);
  process.exitCode = 1;
}
