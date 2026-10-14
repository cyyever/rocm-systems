import { expect, test } from 'vitest';
import { validatePublishedDashboardData } from '../../src/data/dashboardValidation.js';
import { selectRecentRunAttempts, selectRecentRunSummaries, selectBenchmarkSeries, selectBenchmarkCatalog, selectRunComparison } from '../../src/data/selectors.js';
import { createMaintainedPublication } from '../fixtures/maintainedDataset.js';

const data = validatePublishedDashboardData(createMaintainedPublication()).data;
const filters = { targets: ['gfx1250', 'gfx950'], suites: data.suites, modes: ['single', 'default'] };
const run = (id) => data.runs.find(({ runId }) => runId === `fictional-develop-${id}`);



test('policy-specific benchmark histories keep positive measurements and missing configurations as gaps', () => {
  const series = selectBenchmarkSeries(data, filters, 'a').series;
  expect(series.map(({ key, target, mode }) => ({ key, target, mode }))).toEqual([
    { key: 'gfx1250/single', target: 'gfx1250', mode: 'single' }, { key: 'gfx1250/default', target: 'gfx1250', mode: 'default' },
    { key: 'gfx950/single', target: 'gfx950', mode: 'single' }, { key: 'gfx950/default', target: 'gfx950', mode: 'default' },
  ]);
  expect(series[3].points[12]).toBeNull();
  expect(series[0].points[14].value).toBeGreaterThan(0);
  expect(selectBenchmarkSeries(data, { ...filters, modes: [] }, 'a').series).toEqual([]);
  expect(selectBenchmarkSeries(data, { ...filters, suites: [] }, 'a').series.every(({ points }) => points.every((p) => p === null))).toBe(true);
  expect(selectBenchmarkCatalog(data, { ...filters, modes: [] }).available).toEqual([]);
});

test('recent history includes only the latest 20 canonical executions and preserves failure denominators', () => {
  const recent = selectRecentRunSummaries(selectRecentRunAttempts(data).slice(0, 20), filters);
  expect(recent).toHaveLength(20);
  expect(recent[0].run.runId).toBe('fictional-develop-21');
  expect(recent.every(({ run }) => run.branch === 'develop')).toBe(true);
  const failure = selectRecentRunSummaries(selectRecentRunAttempts(data), filters).find(({ run }) => run.runId === 'fictional-develop-08');
  expect(failure.completed).toBeLessThan(failure.total);
  expect(failure.duration).toBeNull();
});

test('zero baseline is measured and matched but its percentage is unavailable', () => {
  const scope = { targets: ['gfx1250'], modes: ['single'], suites: ['Triton'] };
  const baseline = structuredClone(run('14'));
  baseline.tests.find((test) => test.target === 'gfx1250' && test.mode === 'single' && test.logicalTestId === 'a').durationSeconds = 0;
  const result = selectRunComparison(run('15'), baseline, scope);
  const zero = result.comparable.find(({ baselineTest }) => baselineTest.logicalTestId === 'a');
  expect(zero.delta).toBeNull();
  expect(zero.deltaSeconds).toBe(run('15').tests[0].durationSeconds);
  expect(result.notComparable).toHaveLength(0);
  expect(result.counts.unavailable).toBe(1);
});
