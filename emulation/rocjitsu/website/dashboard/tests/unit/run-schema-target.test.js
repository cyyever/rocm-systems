import { expect, test } from 'vitest';
import { CURRENT_RUN_SCHEMA_VERSION, runSchemaVersion } from '../../src/data/runSchema.js';
import { createMaintainedPublication } from '../fixtures/maintainedDataset.js';
import { validatePublishedDashboardData } from '../../src/data/dashboardValidation.js';

test('bundled metadata and supported publication agree on maintained schema 1', () => {
  expect(CURRENT_RUN_SCHEMA_VERSION).toBe(1);
  expect(validatePublishedDashboardData(createMaintainedPublication()).data.schemaVersion).toBe(1);
});

test.each([undefined, null, 0, 2, 3, 99, '1'])('missing or unsupported wire version %s is never upgraded', (schemaVersion) => {
  const run = { id: 'unsupported', schemaVersion, configurations: [] };
  if (schemaVersion === undefined) delete run.schemaVersion;
  expect(() => runSchemaVersion(run)).toThrow(/unsupported schema version/);
});

test.each(['targets', 'plugin', 'comparisonId'])('version 1 cannot conceal retired %s fields', (field) => {
  expect(() => runSchemaVersion({ id: 'legacy', schemaVersion: 1, [field]: {} })).toThrow(/legacy fields/);
});
