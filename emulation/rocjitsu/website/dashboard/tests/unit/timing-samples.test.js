import { expect, test } from 'vitest';
import { validatePublishedResult, validatePublishedDashboardData } from '../../src/data/dashboardValidation.js';
import { createMaintainedPublication } from '../fixtures/maintainedDataset.js';

const completed = (samples) => ({ id: 'example', status: 'completed', error: null, timing_results_s: samples });

test.each([null, undefined, '123', {}, [0], [-1], [NaN], [Infinity], [true], ['2'], []].map((samples) => ({ samples })))(
  'rejects invalid completed timing samples $samples', ({ samples }) => {
    expect(() => validatePublishedResult(completed(samples))).toThrow(/timing_results_s/);
  },
);

test('rejects caller-supplied derived duration on new wire input', () => {
  expect(() => validatePublishedResult({ ...completed([1, 9, 2]), durationSeconds: 9 })).toThrow(/unsupported fields/);
});

test.each([
  [[1, 9, 2], 2],
  [[9, 1, 4, 2], 3],
  [[4], 4],
])('derives internal median without reordering source samples %j', (samples, duration) => {
  const source = createMaintainedPublication();
  source.runs[0].configurations[0].benchmark_results[0].timing_results_s = samples;
  const before = structuredClone(source);
  const { data, sourceData } = validatePublishedDashboardData(source);
  expect(data.runs[0].tests[0].durationSeconds).toBe(duration);
  expect(sourceData).toEqual(before); expect(source).toEqual(before);
});

test.each(['failed', 'timeout'])('preserves %s partial samples with internal null duration', (status) => {
  for (const timing_results_s of [[], [5, 2]]) {
    const source = createMaintainedPublication();
    const result = source.runs[0].configurations[0].benchmark_results[0];
    Object.assign(result, { status, error: 'Fictional failure', timing_results_s });
    expect(validatePublishedResult(result)).toEqual(result);
    const { data, sourceData } = validatePublishedDashboardData(source);
    expect(data.runs[0].tests[0]).toMatchObject({ status, durationSeconds: null, timing_results_s });
    expect(sourceData.runs[0].configurations[0].benchmark_results[0]).toEqual(result);
  }
  expect(() => validatePublishedResult({ id: 'example', status, error: null, timing_results_s: [0] })).toThrow(/timing_results_s/);
});

test('maintained publications retain sample arrays and reject omitted samples', () => {
  const source = createMaintainedPublication();
  const { data } = validatePublishedDashboardData(source);
  for (const run of data.allRuns) {
    const published = source.runs.find(({ id }) => id === run.runId);
    for (const result of run.tests) {
      const raw = published.configurations.find(({ target, thread_policy }) => target === result.target && thread_policy === result.mode).benchmark_results.find(({ id }) => id === result.logicalTestId);
      expect(result.timing_results_s).toEqual(raw.timing_results_s);
    }
  }
  delete source.runs[0].configurations[0].benchmark_results[0].timing_results_s;
  expect(() => validatePublishedDashboardData(source)).toThrow(/timing_results_s/);
});
