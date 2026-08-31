#!/usr/bin/env node
// ISI-3478 regression guard: doc pages are served at trailing-slash URLs
// (e.g. /docs/concepts/mcp-servers/), so an extension-less relative link like
// ./skills resolves one segment too deep -> /docs/concepts/mcp-servers/skills = 404.
// This toolchain (Starlight 0.36) does NOT auto-resolve relative .md links, so
// cross-page links must be root-absolute (/docs/...). Fail the build if a raw
// relative link to another doc page sneaks back in. Image assets are exempt —
// Astro's asset pipeline rewrites those.
import { readFileSync, readdirSync, statSync } from 'node:fs';
import { join } from 'node:path';

const ASSET = /\.(svg|png|jpe?g|gif|webp)([)#"?]|$)/i;
// markdown [text](./x) / [text](../x)  and  raw HTML href="./x" / href="../x"
const REL = /(?:\]\(|href=")(\.\.?\/[^)"\s]*)/g;

function walk(dir) {
  return readdirSync(dir).flatMap((e) => {
    const p = join(dir, e);
    return statSync(p).isDirectory() ? walk(p) : p.endsWith('.md') ? [p] : [];
  });
}

const offenders = [];
for (const file of walk('docs')) {
  const text = readFileSync(file, 'utf8');
  text.split('\n').forEach((line, i) => {
    for (const m of line.matchAll(REL)) {
      if (!ASSET.test(m[1])) offenders.push(`${file}:${i + 1}  ${m[1]}`);
    }
  });
}

if (offenders.length) {
  console.error(
    `\n✗ ${offenders.length} relative doc-page link(s) found — these 404 under trailing-slash URLs.\n` +
      `  Use root-absolute links instead, e.g. /docs/concepts/skills/ (see ISI-3478):\n`,
  );
  offenders.forEach((o) => console.error('    ' + o));
  process.exit(1);
}
console.log('✓ no raw relative doc-page links');
