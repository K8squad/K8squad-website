// Sync source docs into the Starlight content collection.
//
// Source of truth is `docs/` at the repo root (owned by the Content Writer).
// Starlight reads its content collection from `src/content/docs/`. We mirror
// `docs/**` -> `src/content/docs/docs/**` so doc pages live under the `/docs`
// URL prefix, leaving `/` free for the custom landing page (src/pages/index.astro).
//
// The only transform: Docusaurus-style `sidebar_position: N` frontmatter is
// rewritten to Starlight's `sidebar: { order: N }` so the intended ordering is
// preserved. Everything else (including colocated ./images/*.png) is copied verbatim.
//
// ponytail: whole-tree copy on every build (not incremental). Doc tree is tiny
// (~30 files); if it grows large, switch to an mtime-gated rsync-style copy.

import { cp, rm, readdir, readFile, writeFile, stat } from 'node:fs/promises';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = dirname(fileURLToPath(import.meta.url)) + '/..';
const SRC = join(root, 'docs');
const DEST = join(root, 'src/content/docs/docs');

async function walk(dir) {
  const out = [];
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    const p = join(dir, entry.name);
    if (entry.isDirectory()) out.push(...(await walk(p)));
    else out.push(p);
  }
  return out;
}

// Rewrite `sidebar_position: N` -> `sidebar:\n  order: N` inside the leading
// YAML frontmatter block only. Idempotent: skips files that already declare
// a `sidebar:` key.
function convertFrontmatter(text) {
  if (!text.startsWith('---')) return text;
  const end = text.indexOf('\n---', 3);
  if (end === -1) return text;
  const fm = text.slice(0, end);
  const rest = text.slice(end);
  if (/^sidebar:/m.test(fm)) return text;
  const m = fm.match(/^sidebar_position:\s*(\d+)\s*$/m);
  if (!m) return text;
  const converted = fm.replace(/^sidebar_position:\s*\d+\s*$/m, `sidebar:\n  order: ${m[1]}`);
  return converted + rest;
}

await rm(DEST, { recursive: true, force: true });
await cp(SRC, DEST, { recursive: true });

for (const file of await walk(DEST)) {
  if (!/\.mdx?$/.test(file)) continue;
  const original = await readFile(file, 'utf8');
  const converted = convertFrontmatter(original);
  if (converted !== original) await writeFile(file, converted);
}

const count = (await walk(DEST)).length;
console.log(`[sync-content] mirrored docs/ -> src/content/docs/docs/ (${count} files)`);

// Self-check: destination must be non-empty and every markdown file must carry a
// title (Starlight requires it). Fail the build loudly rather than shipping blanks.
const mdFiles = (await walk(DEST)).filter((f) => /\.mdx?$/.test(f));
if (mdFiles.length === 0) throw new Error('[sync-content] no markdown synced — refusing to build an empty docs tree');
for (const f of mdFiles) {
  const t = await readFile(f, 'utf8');
  if (!/^title:\s*\S/m.test(t.slice(0, t.indexOf('\n---', 3) + 4 || 400))) {
    throw new Error(`[sync-content] ${f} is missing a 'title:' frontmatter field (Starlight requires it)`);
  }
}
