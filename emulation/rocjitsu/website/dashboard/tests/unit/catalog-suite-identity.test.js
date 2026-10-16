import { expect, test } from 'vitest';
import { createMaintainedPublication } from '../fixtures/maintainedDataset.js';
import { validatePublishedDashboardData } from '../../src/data/dashboardValidation.js';

test.each(['missing', 'mismatched', 'duplicate', 'nonstring'])('suite identity rejects %s metadata', (change) => {
  const publication = createMaintainedPublication();
  for (const run of publication.runs) {
    const id = publication.catalogs[run.testCatalog].id;
    run.environment = run.environment.filter(({ key }) => key !== 'execution.benchmark_suite');
    if (change !== 'missing') run.environment.push({ key: 'execution.benchmark_suite', label: 'Suite', value: change === 'nonstring' ? [id] : change === 'mismatched' ? 'Other' : id });
    if (change === 'duplicate') run.environment.push({ key: 'execution.benchmark_suite', label: 'Suite', value: id });
  }
  expect(() => validatePublishedDashboardData(publication)).toThrow();
});
