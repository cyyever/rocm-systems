import { expect, test } from 'vitest';
import { validatePublishedDashboardData, validatePublishedResult } from '../../src/data/dashboardValidation.js';
import { createMaintainedPublication } from '../fixtures/maintainedDataset.js';

const invalidCases = [
  ['unsafe repository', (s) => { s.siteConfig = { repository: 'javascript:alert(1)', isBeta: true, canonicalBranch: 'develop' }; }, /repository URL/],
  ['credential URL', (s) => { s.siteConfig = { repository: 'https://name:secret@example.test/', isBeta: true, canonicalBranch: 'develop' }; }, /repository URL/],
  ['noncanonical site branch', (s) => { s.siteConfig = { repository: 'https://example.test/repo', isBeta: true, canonicalBranch: 'main' }; }, /canonicalBranch/],
  ['impossible calendar day', (s) => { s.index.generatedAt = '2026-02-30T12:00:00Z'; }, /ISO/],
  ['unsafe run path', (s) => { s.index.runFiles[0] = 'runs/../../escape.json'; }, /filename/],
  ['duplicate file', (s) => { s.index.runFiles[1] = s.index.runFiles[0]; }, /Duplicate/],
  ['filename identity mismatch', (s) => { s.runs[0].id = 'different'; }, /filename/],
  ['duplicate run identity across directories', (s) => { s.runs[24].id = s.runs[0].id; s.index.runFiles[24] = `runs/side-branches/${s.runs[0].id}.json`; }, /Duplicate run ID/],
  ['absent catalogs', (s) => { delete s.catalogs; }, /catalog/],
  ['empty catalogs', (s) => { s.catalogs = {}; }, /catalog/],
  ['missing referenced catalog', (s) => { delete s.catalogs[s.runs[0].benchmark_catalog]; }, /catalog/],
  ['missing catalog with omitted workload', (s) => { delete s.catalogs[s.runs[0].benchmark_catalog]; s.runs[0].configurations[0].benchmark_results.pop(); }, /catalog/],
  ['unsafe catalog path', (s) => { s.runs[0].benchmark_catalog = '../escape.json'; }, /catalog/],
  ['catalog identity mismatch', (s) => { s.catalogs[s.runs[0].benchmark_catalog].benchmark_suite = 'different'; }, /catalog/],
  ['invalid configuration key', (s) => { s.catalogs[s.runs[0].benchmark_catalog].membership.gfx1250.unknown = ['a']; }, /invalid configuration/],
  ['invalid workload definition', (s) => { s.catalogs[s.runs[0].benchmark_catalog].benchmark_definitions.a.problem = null; }, /invalid or duplicate test definition/],
  ['omitted workload', (s) => { s.runs[0].configurations[0].benchmark_results.pop(); }, /exactly one result/],
  ['duplicate result', (s) => { const r = s.runs[0].configurations[0].benchmark_results; r.push(r[0]); }, /exactly one result/],
  ['unknown workload', (s) => { s.runs[0].configurations[0].benchmark_results[0].id = 'unknown'; }, /exactly one result/],
  ['duplicate configuration', (s) => { s.runs[0].configurations.push(s.runs[0].configurations[0]); }, /duplicate configuration/],
  ['missing explicit mode', (s) => { delete s.runs[0].configurations[0].thread_policy; }, /configuration/],
  ['negative duration', (s) => { s.runs[0].configurations[0].benchmark_results[0].timing_results_s = [-1]; }, /positive/],
  ['completed error', (s) => { s.runs[0].configurations[0].benchmark_results[0].error = 'invalid'; }, /cannot contain an error/],
  ['forbidden derived duration', (s) => { s.runs[0].configurations[0].benchmark_results[0].durationSeconds = null; }, /unsupported fields/],
  ['future execution', (s) => { s.runs[0].execution_summary.finished_at = '2026-10-06T00:00:00Z'; }, /publication/],
  ['commit after completion', (s) => { s.runs[0].provenance.rocjitsu.rocjitsu_commit_timestamp = '2026-10-06T00:00:00Z'; }, /committed/],
  ['invalid base SHA', (s) => { s.runs[0].source.base = { branch: 'develop', commit: 'abcd' }; }, /source base/],
  ['unsafe PR URL', (s) => { s.runs[0].source.pullRequest = { number: 1, url: 'https://evil.test/pull/1' }; }, /pullRequest/],
  ['old environment wrappers', (s) => { s.runs[0].environment = []; }, /legacy fields/],
  ['changed reused workload', (s) => { s.catalogs['test-catalogs/fictional-current.json'].benchmark_definitions.a.problem.m = 999; }, /defined differently/],
  ['conflicting commit time', (s) => { s.runs[1].provenance.rocjitsu.rocjitsu_commit_sha = s.runs[0].provenance.rocjitsu.rocjitsu_commit_sha; }, /conflicting committedAt/],
];

test.each(invalidCases)('maintained schema 1 rejects %s', (_, mutate, expected) => {
  const source = createMaintainedPublication(); mutate(source);
  expect(() => validatePublishedDashboardData(source)).toThrow(expected);
});

test('independent branch machines and scalar environment projection remain disclosed', () => {
  const source = createMaintainedPublication();
  const { data } = validatePublishedDashboardData(source);
  expect(data.allRuns.at(-1).machineId).toBe('fictional-branch-node');
  expect(data.allRuns.at(-1).provenance.details).toContainEqual({ key: 'auxiliary.sdk', label: 'auxiliary.sdk', value: 'test-branch' });
  expect(data.runs.some((run) => data.backfillRunIds.has(run.runId))).toBe(true);
  expect(data.allRuns).toHaveLength(44);
});

test('result status/error distinction rejects zero and preserves failure/timeout diagnostics', () => {
  expect(() => validatePublishedResult({ id: 'zero', status: 'completed', timing_results_s: [0], error: null })).toThrow(/positive/);
  for (const status of ['failed', 'timeout']) expect(validatePublishedResult({ id: status, status, timing_results_s: [], error: 'diagnostic' }).status).toBe(status);
  expect(() => validatePublishedResult({ id: 'missing', status: 'completed', error: null })).toThrow(/timing_results_s/);
  expect(() => validatePublishedResult({ id: 'bad', status: 'failed', timing_results_s: [], error: '' })).toThrow(/non-empty/);
  expect(() => validatePublishedResult({ id: 'bad', status: 'completed', timing_results_s: [Infinity], error: null })).toThrow(/finite/);
});
