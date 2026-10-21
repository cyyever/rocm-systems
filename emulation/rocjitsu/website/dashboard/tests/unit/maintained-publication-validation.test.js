import { expect, test } from 'vitest';
import { validatePublishedDashboardData } from '../../src/data/dashboardValidation.js';
import { readMaintainedExamplePublication } from '../helpers/maintainedExamplePublication.js';

test('documentation publication setup returns fresh independent nested objects on every call', () => {
  const first = readMaintainedExamplePublication();
  const second = readMaintainedExamplePublication();
  expect(first).toEqual(second);
  expect(first.index).not.toBe(second.index);
  expect(first.runs[0]).not.toBe(second.runs[0]);
  const catalog = first.runs[0].benchmark_catalog;
  expect(first.catalogs[catalog]).not.toBe(second.catalogs[catalog]);
  first.runs[0].configurations[0].benchmark_results.pop();
  first.index.runFiles.length = 0;
  delete first.catalogs[catalog].benchmark_definitions.gemm;
  expect(readMaintainedExamplePublication()).toEqual(second);
});

test('maintained publication preserves literal policies, typed definitions and published export', () => {
  const source = readMaintainedExamplePublication();
  const before = structuredClone(source);
  const { data, sourceData } = validatePublishedDashboardData(source);
  expect(data.schemaVersion).toBe(1);
  expect(data.runs[0].configurations).toEqual([
    { target: 'gfx950', thread_policy: 'single' },
    { target: 'gfx950', thread_policy: 'default' },
  ]);
  expect(data.runs[0].tests[0].problem).toEqual({ shape: [16, 16, 16], options: { transpose: false }, note: null });
  expect(data.runs[0].tests[1]).toMatchObject({ mode: 'default', status: 'timeout', durationSeconds: null, timing_results_s: [5] });
  expect(sourceData).toEqual(before);
  expect(source).toEqual(before);
});

function repeatedPublication(left, right) {
  const source = readMaintainedExamplePublication();
  const catalog = source.catalogs[source.runs[0].benchmark_catalog];
  Object.values(catalog.benchmark_definitions)[0].problem = { value: left };
  const secondCatalog = structuredClone(catalog);
  secondCatalog.benchmark_suite = 'second';
  Object.values(secondCatalog.benchmark_definitions)[0].problem = { value: right };
  const secondRun = structuredClone(source.runs[0]);
  secondRun.id = 'run-002';
  secondRun.benchmark_catalog = 'test-catalogs/second.json';
  secondRun.execution_summary.benchmark_suite = secondCatalog.benchmark_suite;
  source.catalogs[secondRun.benchmark_catalog] = secondCatalog;
  source.runs.push(secondRun);
  source.index.runFiles.push('runs/default-branch/run-002.json');
  return source;
}

test('recursive typed identity ignores nested object order across catalogs', () => {
  const left = { a: [1, { z: null, b: true }], c: 'value' };
  const right = { c: 'value', a: [1, { b: true, z: null }] };
  expect(validatePublishedDashboardData(repeatedPublication(left, right)).data.allRuns).toHaveLength(2);
});

test.each([
  [[1, 2], '[1,2]'],
  [{ a: 1 }, '{"a":1}'],
  [null, 'null'],
  [[1, 2], [2, 1]],
  [true, 'true'],
])('typed identity rejects incompatible values %#', (left, right) => {
  expect(() => validatePublishedDashboardData(repeatedPublication(left, right))).toThrow(/defined differently/);
});

test.each([
  ['catalog-only key', (s) => { s.runs[0].configurations.pop(); }],
  ['run-only group', (s) => { delete s.catalogs[s.runs[0].benchmark_catalog].membership.gfx950.default; }],
  ['empty group', (s) => { s.runs[0].configurations[0].benchmark_results = []; }],
  ['duplicate group', (s) => { s.runs[0].configurations.push(s.runs[0].configurations[0]); }],
  ['duplicate result', (s) => { s.runs[0].configurations[0].benchmark_results.push(s.runs[0].configurations[0].benchmark_results[0]); }],
  ['empty membership', (s) => { s.catalogs[s.runs[0].benchmark_catalog].membership.gfx950.single = []; }],
  ['policy mismatch', (s) => { s.runs[0].configurations[0].benchmark_results[0].thread_policy = 'default'; }],
  ['missing operation', (s) => { delete s.catalogs[s.runs[0].benchmark_catalog].benchmark_definitions.gemm.operation; }],
  ['missing samples', (s) => { delete s.runs[0].configurations[0].benchmark_results[0].timing_results_s; }],
  ['missing failure samples', (s) => { delete s.runs[0].configurations[1].benchmark_results[0].timing_results_s; }],
  ['zero duration', (s) => { s.runs[0].configurations[0].benchmark_results[0].durationSeconds = 0; }],
  ['nonfinite problem', (s) => { s.catalogs[s.runs[0].benchmark_catalog].benchmark_definitions.gemm.problem = { nested: [Infinity] }; }],
])('maintained validation rejects %s', (_, mutate) => {
  const source = readMaintainedExamplePublication();
  mutate(source);
  expect(() => validatePublishedDashboardData(source)).toThrow();
});

test.each([
  ['dot run ID', (s) => { s.runs[0].id = '.'; s.index.runFiles[0] = 'runs/default-branch/..json'; }],
  ['same source/base branch', (s) => { s.runs[0].source.base = { branch: 'develop', commit: 'b'.repeat(40) }; }],
  ['PR without source base', (s) => { s.runs[0].source.pullRequest = { number: 1 }; }],
  ['PR URL query', (s) => { s.runs[0].source.base = { branch: 'main', commit: 'b'.repeat(40) }; s.runs[0].source.pullRequest = { number: 1, url: 'https://github.com/ROCm/rocm-systems/pull/1?x=1' }; }],
])('maintained source contract rejects %s', (_, mutate) => {
  const source = readMaintainedExamplePublication();
  mutate(source);
  expect(() => validatePublishedDashboardData(source)).toThrow();
});
