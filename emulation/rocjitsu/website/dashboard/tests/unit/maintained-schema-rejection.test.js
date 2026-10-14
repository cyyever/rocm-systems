import { expect, test } from 'vitest';
import { loadDashboardDataFiles } from '../../src/data/dashboardData.js';
import { validatePublishedDashboardData } from '../../src/data/dashboardValidation.js';
import { createMaintainedPublication } from '../fixtures/maintainedDataset.js';

function publication() {
  const source = createMaintainedPublication();
  source.runs = source.runs.slice(0, 1);
  source.index.runFiles = source.index.runFiles.slice(0, 1);
  return source;
}

function legacyPublication(plugin = 'vanilla', version = 1) {
  const source = publication();
  const run = source.runs[0];
  run.schemaVersion = version;
  if (version === undefined) delete run.schemaVersion;
  run.plugin = { id: plugin, name: plugin };
  run.comparisonId = 'legacy-comparison';
  run.targets = run.configurations.map(({ target, results }) => ({ id: target, results }));
  delete run.configurations;
  const catalog = source.catalogs[run.testCatalog];
  catalog.targets = { gfx950: ['a'] };
  delete catalog.configurations;
  return source;
}

test.each(['vanilla', 'asan'])('retired %s measurements fail the full publication instead of disappearing or relabeling', (plugin) => {
  for (const version of [1, undefined]) {
    const source = legacyPublication(plugin, version);
    const before = structuredClone(source);
    expect(() => validatePublishedDashboardData(source)).toThrow(/legacy fields|unsupported schema version/);
    expect(source).toEqual(before);
  }
});

test('mixed maintained and historical side-branch input fails rather than partially displaying', () => {
  const source = publication();
  const historical = legacyPublication('asan').runs[0];
  historical.id = 'historical';
  historical.source.branch = 'feature/old';
  source.runs.push(historical);
  source.index.runFiles.push('runs/side-branches/historical.json');
  expect(() => validatePublishedDashboardData(source)).toThrow(/legacy fields/);
});

test.each([
  'runs/fictional-develop-00.json',
  'runs/side-branches/fictional-develop-00.json',
  'runs/side-branches/feature/fictional-develop-00.json',
  'runs/default-branch/../fictional-develop-00.json',
])('maintained load rejects flat, wrong-branch, nested or unsafe path %s', (path) => {
  const source = publication();
  source.index.runFiles = [path];
  expect(() => validatePublishedDashboardData(source)).toThrow(/filename|branch directory/);
});

test('maintained shared-catalog loads preserve configuration order and all parsed published fields', () => {
  const source = createMaintainedPublication();
  const before = structuredClone(source);
  const { data, sourceData } = validatePublishedDashboardData(source);
  for (const run of data.allRuns) {
    const published = source.runs.find(({ id }) => id === run.runId);
    expect(run.configurations).toEqual(published.configurations.map(({ target, thread_policy }) => ({ target, thread_policy })));
  }
  expect(sourceData).toEqual(before);
  expect(source).toEqual(before);
});

test('browser validates historical input instead of excluding it, without fetching metadata', async () => {
  const source = legacyPublication('asan');
  const bodies = { 'index.json': source.index, ...source.catalogs, [source.index.runFiles[0]]: source.runs[0] };
  const requests = [];
  await expect(loadDashboardDataFiles({
    indexUrl: 'https://example.test/data/index.json',
    retryDelaysMs: [],
    fetch: async (url) => {
      const path = new URL(url).pathname.slice('/data/'.length);
      requests.push(path);
      return { ok: Object.hasOwn(bodies, path), status: 404, text: async () => JSON.stringify(bodies[path]) };
    },
  })).rejects.toThrow(/legacy fields/);
  expect(requests).not.toContain('metadata.json');
});
