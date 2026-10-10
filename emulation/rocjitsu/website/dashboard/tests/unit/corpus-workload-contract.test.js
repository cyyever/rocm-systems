import { expect, test } from 'vitest';
import { validatePublishedDashboardData } from '../../src/data/dashboardValidation.js';
import { selectBenchmarkSeries } from '../../src/data/selectors.js';
import { createSchema2Publication } from '../fixtures/schema2Dataset.js';

function publication() {
  const source = createSchema2Publication();
  for (const catalog of Object.values(source.catalogs)) {
    for (const test of catalog.tests) test.operation = 'Matrix multiplication followed by reduction';
  }
  return source;
}

test('preserves literal workload IDs, operation, ordered samples and sparse target/policy configurations', () => {
  const source = publication();
  const run = source.runs[12];
  for (const configuration of run.configurations) {
    for (const result of configuration.results) Object.assign(result, { timing_results_s: [0.03, 0.01, 0.02], durationSeconds: 0.02 });
  }
  const before = structuredClone(source);
  const { data, sourceData } = validatePublishedDashboardData(source);
  const normalized = data.runs.find(({ runId }) => runId === run.id);
  expect(normalized.configurations).toHaveLength(3);
  expect(normalized.tests.every((result) => result.operation === 'Matrix multiplication followed by reduction'
    && result.logicalTestId === result.id && result.testId === `${result.target}:${result.mode}:${result.id}`
    && result.timing_results_s.join(',') === '0.03,0.01,0.02' && result.durationSeconds === 0.02)).toBe(true);
  const series = selectBenchmarkSeries(data, { targets: ['gfx950'], suites: data.suites, modes: ['ST', 'MT'] }, 'a');
  expect(series.series.map(({ key }) => key)).toEqual(['gfx950:ST', 'gfx950:MT']);
  expect(series.series[0].points[12].value).toBe(0.02);
  expect(series.series[1].points[12]).toBeNull();
  expect(sourceData.runs).toEqual(before.runs);
  expect(source).toEqual(before);
});

test.each(['', ' ', null, 7, {}, []].map((operation) => ({ operation })))('rejects an explicitly invalid operation $operation', ({ operation }) => {
  const source = publication();
  Object.values(source.catalogs)[0].tests[0].operation = operation;
  expect(() => validatePublishedDashboardData(source)).toThrow(/invalid.*definition/);
});

test('rejects conflicting operations for the same corpus workload ID', () => {
  const source = publication();
  source.catalogs['test-catalogs/fictional-current.json'].tests[0].operation = 'Different computation';
  expect(() => validatePublishedDashboardData(source)).toThrow(/defined differently/);
});

test('historical catalogs may omit operation without inventing metadata on old results', () => {
  const source = publication();
  for (const test of source.catalogs['test-catalogs/fictional-old.json'].tests) delete test.operation;
  const { data } = validatePublishedDashboardData(source);
  expect(data.runs[0].tests[0]).not.toHaveProperty('operation');
  expect(data.testCatalog.find(({ id }) => id === 'a').operation).toBe('Matrix multiplication followed by reduction');
  source.runs.reverse();
  source.index.runFiles.reverse();
  expect(validatePublishedDashboardData(source).data.testCatalog.find(({ id }) => id === 'a').operation).toBe('Matrix multiplication followed by reduction');
});
