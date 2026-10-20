import { expect, test } from 'vitest';
import { createMaintainedPublication } from '../fixtures/maintainedDataset.js';
import { validatePublishedDashboardData } from '../../src/data/dashboardValidation.js';
import { parsePublishedJson } from '../../src/data/publishedJson.js';

test.each(['missing', 'mismatched', 'nonstring'])('suite identity rejects %s metadata', (change) => {
  const publication = createMaintainedPublication();
  for (const run of publication.runs) {
    const id = publication.catalogs[run.benchmark_catalog].benchmark_suite;
    if (change === 'missing') delete run.execution_summary.benchmark_suite;
    else run.execution_summary.benchmark_suite = change === 'nonstring' ? [id] : 'Other';
  }
  expect(() => validatePublishedDashboardData(publication)).toThrow(/benchmark_suite/);
});

test('strict JSON boundary rejects duplicate suite identity before it can shadow the declaration', () => {
  expect(() => parsePublishedJson('{"benchmark_suite":"first","benchmark_suite":"second"}')).toThrow(/Duplicate JSON key/);
});
