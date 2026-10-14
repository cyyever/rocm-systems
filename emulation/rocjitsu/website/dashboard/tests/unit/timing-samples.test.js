import { expect, test } from 'vitest';
import { validatePublishedResult, validatePublishedDashboardData } from '../../src/data/dashboardValidation.js';
import { createMaintainedPublication } from '../fixtures/maintainedDataset.js';

const completed = (samples, durationSeconds = 2) => ({
  testId: 'example', status: 'completed', durationSeconds, error: null, timing_results_s: samples,
});

test.each([null, undefined, '123', {}, [0], [-1], [NaN], [Infinity], [true], ['2'], []].map((samples) => ({ samples })))(
  'rejects invalid completed timing samples $samples', ({ samples }) => {
    expect(() => validatePublishedResult(completed(samples))).toThrow(/timing_results_s/);
  },
);

test('rejects a duration that disagrees with the sample median', () => {
  expect(() => validatePublishedResult(completed([1, 9, 2], 9))).toThrow(/median/);
});

test.each([
  [[1, 9, 2], 2],
  [[9, 1, 4, 2], 3],
  [[4], 4],
])('accepts median duration without reordering samples %j', (samples, duration) => {
  const result = completed(samples, duration);
  const before = structuredClone(result);
  expect(validatePublishedResult(result)).toEqual(before);
});

test.each(['failed', 'timeout'])('preserves %s partial samples with null duration', (status) => {
  for (const timing_results_s of [[], [5, 2]]) {
    const result = { testId: 'example', status, durationSeconds: null, error: null, timing_results_s };
    expect(validatePublishedResult(result)).toEqual(result);
  }
  expect(() => validatePublishedResult({ testId: 'example', status, durationSeconds: null, error: null, timing_results_s: [0] })).toThrow(/timing_results_s/);
});

test('maintained publications retain sample arrays and reject omitted samples', () => {
  const source = createMaintainedPublication();
  const { data } = validatePublishedDashboardData(source);
  for (const run of data.allRuns) {
    const published = source.runs.find(({ id }) => id === run.runId);
    for (const result of run.tests) {
      const raw = published.configurations.find(({ target, thread_policy }) => target === result.target && thread_policy === result.mode).results.find(({ testId }) => testId === result.logicalTestId);
      expect(result.timing_results_s).toEqual(raw.timing_results_s);
    }
  }
  delete source.runs[0].configurations[0].results[0].timing_results_s;
  expect(() => validatePublishedDashboardData(source)).toThrow(/must contain timing_results_s/);
});
