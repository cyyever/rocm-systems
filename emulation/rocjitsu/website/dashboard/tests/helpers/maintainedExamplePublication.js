import { readFileSync } from 'node:fs';

export function readMaintainedExamplePublication() {
  const document = readFileSync(new URL('../../docs/schema-1.md', import.meta.url), 'utf8');
  const [, index, catalog, run] = [...document.matchAll(/```json\n([\s\S]*?)\n```/g)]
    .map(([, json]) => JSON.parse(json));
  return { index, runs: [run], catalogs: { [run.benchmark_catalog]: catalog } };
}
