import { readFileSync } from 'node:fs';
import { mkdtemp, mkdir, writeFile, rm } from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { expect, test } from 'vitest';
import { loadDashboardDataFiles } from '../../src/data/dashboardData.js';
import { validateDashboardDataDirectory } from '../../scripts/validate-dashboard-data.mjs';
import { processDashboardDataDirectory } from '../../scripts/process-dashboard-data.mjs';

function publicationBodies() {
  const text = readFileSync(new URL('../../docs/schema-1.md', import.meta.url), 'utf8');
  const [, index, catalog, run] = [...text.matchAll(/```json\n([\s\S]*?)\n```/g)].map(([, json]) => JSON.parse(json));
  return { 'index.json': JSON.stringify(index), [run.testCatalog]: JSON.stringify(catalog), [index.runFiles[0]]: JSON.stringify(run) };
}
const load = (bodies) => loadDashboardDataFiles({
  indexUrl: 'https://fixture.test/data/index.json',
  retryDelaysMs: [],
  fetch: async (url) => ({ ok: true, text: async () => bodies[new URL(url).pathname.slice('/data/'.length)] }),
});

test.each(['9007199254740993', '9.007199254740993e15', '1e-400'])('all text loaders reject unsupported numeric token %s', async (token) => {
  const bodies = publicationBodies();
  bodies['test-catalogs/example.json'] = bodies['test-catalogs/example.json'].replace('"problem":{', `"problem":{"unsafe":${token},`);
  await expect(load(bodies)).rejects.toThrow(/numeric/i);
  const directory = await mkdtemp(path.join(process.env.TMPDIR ?? os.tmpdir(), 'numeric-json-'));
  try {
    for (const [name, body] of Object.entries(bodies)) {
      await mkdir(path.dirname(path.join(directory, name)), { recursive: true });
      await writeFile(path.join(directory, name), body);
    }
    await expect(validateDashboardDataDirectory(directory)).rejects.toThrow(/numeric/i);
    await expect(processDashboardDataDirectory(directory)).rejects.toThrow(/numeric/i);
  } finally { await rm(directory, { recursive: true, force: true }); }
});

test('browser text boundary rejects duplicate decoded object keys', async () => {
  const bodies = publicationBodies();
  bodies['test-catalogs/example.json'] = bodies['test-catalogs/example.json'].replace('"gfx950/single":', '"gfx950\\u002fsingle":["gemm"],"gfx950/single":');
  await expect(load(bodies)).rejects.toThrow(/Duplicate JSON key/);
});

test('CLI and processor reject duplicate JSON declarations before normalization', async () => {
  const directory = await mkdtemp(path.join(process.env.TMPDIR ?? os.tmpdir(), 'maintained-json-'));
  try {
    const bodies = publicationBodies();
    bodies['index.json'] = bodies['index.json'].replace('"runFiles":', '"runFiles":[],"runFiles":');
    for (const [name, body] of Object.entries(bodies)) {
      await mkdir(path.dirname(path.join(directory, name)), { recursive: true });
      await writeFile(path.join(directory, name), body);
    }
    await expect(validateDashboardDataDirectory(directory)).rejects.toThrow(/Duplicate JSON key/);
    await expect(processDashboardDataDirectory(directory)).rejects.toThrow(/Duplicate JSON key/);
  } finally { await rm(directory, { recursive: true, force: true }); }
});

test.each([undefined, 2, 99, '1'])('browser rejects unsupported or missing version %s', async (version) => {
  const bodies = publicationBodies();
  const runPath = 'runs/default-branch/run-001.json';
  const run = JSON.parse(bodies[runPath]);
  if (version === undefined) delete run.schemaVersion;
  else run.schemaVersion = version;
  bodies[runPath] = JSON.stringify(run);
  await expect(load(bodies)).rejects.toThrow(/unsupported schema version/);
});

test.each(['vanilla', 'asan'])('browser rejects legacy plugin %s instead of hiding it', async (plugin) => {
  const bodies = publicationBodies();
  const runPath = 'runs/default-branch/run-001.json';
  const run = JSON.parse(bodies[runPath]);
  run.plugin = { id: plugin, name: plugin };
  bodies[runPath] = JSON.stringify(run);
  await expect(load(bodies)).rejects.toThrow(/legacy fields/);
});
