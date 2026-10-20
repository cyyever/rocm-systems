import { fixtureRunPath } from '../fixtures/runPath.js';
import { expect, test } from 'vitest';
import { selectAutomaticReference, selectPublishedBranches } from '../../src/data/branchSelectors.js';
import { validatePublishedDashboardData } from '../../src/data/dashboardValidation.js';
import { createMaintainedPublication } from '../fixtures/maintainedDataset.js';

test('normalizes current runs with explicit modes and keeps branch source envelopes', () => {
  const source = createMaintainedPublication();
  const { data, sourceData } = validatePublishedDashboardData(source);
  expect(data.schemaVersion).toBe(1);
  expect(sourceData.index).not.toHaveProperty('schemaVersion');
  for (const catalog of Object.values(sourceData.catalogs)) expect(catalog).not.toHaveProperty('schemaVersion');
  for (const run of sourceData.runs) expect(run.schemaVersion).toBe(1);
  expect(data.runs).toHaveLength(24);
  expect(data.allRuns).toHaveLength(44);
  expect(data).not.toHaveProperty('pluginRuns');
  expect(data.runs.every(({ branch }) => branch === 'develop')).toBe(true);
  expect(data.modes).toEqual(['single', 'default']);
  expect(data.latestCommitRun.runId).toBe('fictional-develop-23');
  expect(data.latestRun.runId).toBe('fictional-develop-21');
  expect(data.runs[0].tests[0].testId).toBe('gfx1250/single:a');
  expect(data.allRuns.at(-1).sourceBase).toBeUndefined();
  expect(sourceData).toEqual(source);
  for (const run of [...sourceData.runs, ...data.allRuns]) {
    expect(run).not.toHaveProperty('plugin');
    expect(run).not.toHaveProperty('comparisonId');
    expect(run).not.toHaveProperty('workflowUrl');
    if (run.execution) expect(run.execution).not.toHaveProperty('workflowUrl');
    for (const configuration of run.configurations) {
      expect(['single', 'default']).toContain(configuration.thread_policy);
      expect(configuration).not.toHaveProperty('mode');
      expect(configuration).not.toHaveProperty('threadCount');
    }
  }
  expect(data.runs.find(({ runId }) => runId === 'fictional-develop-14').tests[0].durationSeconds).toBe(source.runs[14].configurations[0].benchmark_results[0].timing_results_s[0]);
});

test.each([123, true, false, ['attempt-1']].map((id) => ({ id })))('rejects non-string attempt ID $id before normalization', ({ id }) => {
  const source = createMaintainedPublication();
  source.runs = [{ ...source.runs[0], id }];
  source.index.runFiles = [`runs/default-branch/${id}.json`];
  expect(() => validatePublishedDashboardData(source)).toThrow(/does not match the maintained schema-1 run contract/);
});

test('unsupported run version reports an explicit schema error', () => {
  const source = createMaintainedPublication();
  source.runs[0].schemaVersion = 99;
  expect(() => validatePublishedDashboardData(source)).toThrow(/schema.*99/i);
});

test('empty and branch-only snapshots remain valid', () => {
  const source = createMaintainedPublication();
  source.runs = []; source.index.runFiles = [];
  const { data } = validatePublishedDashboardData(source);
  expect(data.runs).toEqual([]);
  expect(data.latestRun).toBeNull();
  const branches = createMaintainedPublication();
  branches.runs = branches.runs.filter(({ source }) => source.branch !== 'develop');
  branches.index.runFiles = branches.runs.map(fixtureRunPath);
  expect(validatePublishedDashboardData(branches).data.allRuns).toHaveLength(20);
});

test('configuration targets must be declared strings, not coerced numbers', () => {
  const source = createMaintainedPublication();
  const run = source.runs[0];
  run.configurations = [run.configurations[0]];
  run.configurations[0].target = 123;
  source.catalogs[run.benchmark_catalog].membership = { '123:single': { single: ['a', 'b', 'c'] } };
  source.runs = [run]; source.index.runFiles = [fixtureRunPath(run)];
  expect(() => validatePublishedDashboardData(source)).toThrow(/configuration/);
});

test.each([
  { thread_policy: ['single'] },
  { thread_policy: ['default'] },
])('DATA-01 rejects coerced array thread_policy $thread_policy', ({ thread_policy }) => {
  const source = createMaintainedPublication();
  const run = source.runs[0];
  source.runs = [run]; source.index.runFiles = [fixtureRunPath(run)];
  run.configurations = [run.configurations[0]];
  Object.assign(run.configurations[0], { thread_policy });
  expect(() => validatePublishedDashboardData(source)).toThrow(/invalid.*configuration/i);
});

test('DATA-02 result extensions cannot override authoritative definitions or hide failure', () => {
  for (const id of ['fictional-develop-00', 'fictional-develop-08']) {
    const source = createMaintainedPublication();
    const run = source.runs.find((run) => run.id === id);
    source.runs = [run]; source.index.runFiles = [fixtureRunPath(run)];
    run.configurations[0].benchmark_results[0].suite = 'not-a-catalog-suite';
    expect(() => validatePublishedDashboardData(source)).toThrow(/unsupported fields/);
  }
});

test('rejects array source.commit SHA in published input', () => {
  const source = createMaintainedPublication();
  const run = source.runs.find(({ id }) => id === 'fictional-branch-01');
  source.runs = [run]; source.index.runFiles = [fixtureRunPath(run)];
  run.provenance.rocjitsu.rocjitsu_commit_sha = [run.provenance.rocjitsu.rocjitsu_commit_sha];
  expect(() => validatePublishedDashboardData(source)).toThrow(/invalid provenance/);
});

test('rejects array source.base.commit SHA in published input', () => {
  const source = createMaintainedPublication();
  const run = source.runs.find(({ id }) => id === 'fictional-branch-01');
  source.runs = [run]; source.index.runFiles = [fixtureRunPath(run)];
  run.source.base.commit = [run.source.base.commit];
  expect(() => validatePublishedDashboardData(source)).toThrow(/Run fictional-branch-01 has an invalid source base/);
});

test.each(['source.commit', 'source.base.commit'].flatMap((field) =>
  ['uppercase', 'mixed-case'].map((casing) => ({ field, casing }))))('rejects $casing $field before reference selection', ({ field, casing }) => {
  const source = createMaintainedPublication();
  source.runs = source.runs.filter(({ id }) => ['fictional-branch-01', 'fictional-develop-20', 'fictional-develop-21'].includes(id));
  source.index.runFiles = source.runs.map(fixtureRunPath);
  const branch = source.runs.find(({ id }) => id === 'fictional-branch-01');
  const normalized = validatePublishedDashboardData(source).data;
  const candidate = normalized.allRuns.find(({ runId }) => runId === branch.id);
  expect(selectAutomaticReference(normalized, candidate)).toMatchObject({ reason: 'exact-base', run: { runId: 'fictional-develop-20' } });
  expect(selectAutomaticReference(normalized, { ...candidate, sourceBase: undefined })).toMatchObject({ reason: 'earlier-develop', run: { runId: 'fictional-develop-21' } });
  const identity = field === 'source.base.commit' ? branch.source.base : branch.provenance.rocjitsu;
  const key = field === 'source.base.commit' ? 'commit' : 'rocjitsu_commit_sha';
  identity[key] = casing === 'uppercase' ? identity[key].toUpperCase() : identity[key].replace(/[a-f]/, (letter) => letter.toUpperCase());
  const invalidSha = identity[key];
  expect(() => validatePublishedDashboardData(source)).toThrow(field === 'source.commit' ? /invalid provenance/ : /invalid source base/);
  expect(identity[key]).toBe(invalidSha);
});

test('preserves canonical lowercase full SHAs for branch search and exact base', () => {
  const source = createMaintainedPublication();
  source.runs = source.runs.filter(({ id }) => ['fictional-branch-01', 'fictional-develop-20', 'fictional-develop-21'].includes(id));
  source.index.runFiles = source.runs.map(fixtureRunPath);
  const branch = source.runs.find(({ id }) => id === 'fictional-branch-01');
  expect(branch.provenance.rocjitsu.rocjitsu_commit_sha).toMatch(/^[0-9a-f]{40}$/);
  const { data } = validatePublishedDashboardData(source);
  const candidate = data.allRuns.find(({ runId }) => runId === branch.id);
  expect(candidate.provenance.rocjitsuCommitSha).toBe(branch.provenance.rocjitsu.rocjitsu_commit_sha);
  expect(candidate.sourceBase).toEqual(branch.source.base);
  expect(selectPublishedBranches(data, { query: branch.provenance.rocjitsu.rocjitsu_commit_sha.toLowerCase() }).map(({ latestRun }) => latestRun.runId)).toEqual([branch.id]);
  expect(selectPublishedBranches(data, { query: 'nonmatching-query' })).toEqual([]);
  expect(selectAutomaticReference(data, candidate)).toMatchObject({ reason: 'exact-base', run: { runId: 'fictional-develop-20' } });
});
