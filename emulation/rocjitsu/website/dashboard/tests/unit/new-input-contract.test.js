import { expect, test } from 'vitest';
import { validatePublishedDashboardData } from '../../src/data/dashboardValidation.js';

function publication() {
  const catalog = { benchmark_suite: 'fictional-contract', benchmark_definitions: { a: { suite: 'Triton', name: 'Fictional GEMM', operation: 'GEMM', problem: { shape: [16, 32], options: { enabled: true, tile: null } } } }, membership: { gfx950: { single: ['a'] } } };
  const run = { schemaVersion: 1, id: 'fictional-attempt', benchmark_catalog: 'test-catalogs/fictional-contract.json', source: { branch: 'develop' }, execution: { trigger: 'manual', machine_label: 'fictional-label' }, execution_summary: { benchmark_suite: 'fictional-contract', timestamp: '2026-10-01T05:00:00Z', finished_at: '2026-10-01T06:00:00Z', wall_time_s: 1, warmups: 0, samples: 3, timeout_seconds: 10 }, provenance: { auxiliary: { tensile_commit_sha: 'a'.repeat(40) }, corpus: { corpus_commit_sha: 'b'.repeat(40), corpus_commit_timestamp: '2026-10-01T03:00:00Z' }, machine: { hostname: 'fictional-host', platform: 'fictional', kernel: 'fictional', cpu: 'fictional' }, rocjitsu: { rocjitsu_commit_sha: 'c'.repeat(40), rocjitsu_commit_timestamp: '2026-10-01T04:00:00Z', rocm_sdk_version: null, workflow_commit_sha: 'd'.repeat(40) } }, configurations: [{ target: 'gfx950', thread_policy: 'single', benchmark_results: [{ id: 'a', status: 'completed', timing_results_s: [3, 1, 2], error: null }] }] };
  return { index: { generatedAt: '2026-10-01T07:00:00Z', runFiles: ['runs/default-branch/fictional-attempt.json'] }, catalogs: { [run.benchmark_catalog]: catalog }, runs: [run] };
}

test('new schema1 joins typed definitions, derives median and preserves exact source export', () => {
  const source = publication(); const before = structuredClone(source);
  const { data, sourceData } = validatePublishedDashboardData(source);
  expect(data.runs[0]).toMatchObject({ runId: 'fictional-attempt', commitTimestamp: '2026-10-01T04:00:00Z', timestamp: '2026-10-01T06:00:00Z', machineId: 'fictional-label', provenance: { rocjitsuCommitSha: 'c'.repeat(40) } });
  expect(data.runs[0].tests[0]).toMatchObject({ logicalTestId: 'a', mode: 'single', durationSeconds: 2, timing_results_s: [3, 1, 2], problem: { shape: [16, 32], options: { enabled: true, tile: null } } });
  expect(sourceData).toEqual(source); expect(source).toEqual(before);
});


test.each([
  ['root alias', (s) => { s.runs[0].testCatalog = s.runs[0].benchmark_catalog; }],
  ['old environment', (s) => { s.runs[0].environment = []; }],
  ['source SHA alias', (s) => { s.runs[0].source.commit = 'c'.repeat(40); }],
  ['execution alias', (s) => { s.runs[0].execution.completedAt = s.runs[0].execution_summary.finished_at; }],
  ['catalog old id', (s) => { Object.values(s.catalogs)[0].id = 'fictional-contract'; }],
  ['catalog version', (s) => { Object.values(s.catalogs)[0].schemaVersion = 1; }],
  ['definition id alias', (s) => { Object.values(s.catalogs)[0].benchmark_definitions.a.id = 'a'; }],
  ['configuration alias', (s) => { s.runs[0].configurations[0].results = []; }],
  ['result policy', (s) => { s.runs[0].configurations[0].benchmark_results[0].thread_policy = 'single'; }],
  ['result identity alias', (s) => { s.runs[0].configurations[0].benchmark_results[0].testId = 'a'; }],
  ['result duration', (s) => { s.runs[0].configurations[0].benchmark_results[0].durationSeconds = 2; }],
  ['raw-only exit code', (s) => { s.runs[0].configurations[0].benchmark_results[0].exit_code = 0; }],
])('new schema1 rejects %s without compatibility aliases', (_, mutate) => {
  const source = publication(); mutate(source);
  expect(() => validatePublishedDashboardData(source)).toThrow(/unsupported fields|legacy fields/);
});

test.each([
  ['source commit after start', (s) => { s.runs[0].provenance.rocjitsu.rocjitsu_commit_timestamp = '2026-10-01T05:30:00Z'; }],
  ['corpus commit after start', (s) => { s.runs[0].provenance.corpus.corpus_commit_timestamp = '2026-10-01T05:30:00Z'; }],
  ['start after finish', (s) => { s.runs[0].execution_summary.timestamp = '2026-10-01T06:30:00Z'; }],
  ['finish after index', (s) => { s.runs[0].execution_summary.finished_at = '2026-10-01T08:00:00Z'; }],
  ['negative wall', (s) => { s.runs[0].execution_summary.wall_time_s = -1; }],
  ['missing workflow SHA', (s) => { delete s.runs[0].provenance.rocjitsu.workflow_commit_sha; }],
  ['invalid Tensile SHA', (s) => { s.runs[0].provenance.auxiliary.tensile_commit_sha = 'latest'; }],
  ['missing section', (s) => { delete s.runs[0].provenance.machine; }],
  ['invalid typed extension', (s) => { s.runs[0].provenance.auxiliary.extension = [Infinity]; }],
])('new input rejects %s', (_, mutate) => {
  const source = publication(); mutate(source);
  expect(() => validatePublishedDashboardData(source)).toThrow();
});

test('typed open provenance preserves export and scalar environment exclusions without losing tool provenance', () => {
  const source = publication();
  source.runs[0].provenance.auxiliary.extension = { list: [true, null, '1', 1] };
  const first = validatePublishedDashboardData(source);
  source.runs[0].provenance.rocjitsu.workflow_commit_sha = 'e'.repeat(40);
  source.runs[0].provenance.auxiliary.tensile_commit_sha = 'f'.repeat(40);
  source.runs[0].execution_summary.timestamp = '2026-10-01T05:01:00Z';
  source.runs[0].execution_summary.wall_time_s = 900;
  const second = validatePublishedDashboardData(source);
  expect(second.data.runs[0].environmentId).toBe(first.data.runs[0].environmentId);
  expect(second.sourceData).toEqual(source);
  expect(second.data.runs[0].provenance.details).toContainEqual({ key: 'rocjitsu.workflow_commit_sha', label: 'Workflow commit', value: 'e'.repeat(40) });
  source.runs[0].provenance.auxiliary.extension.list[0] = false;
  expect(validatePublishedDashboardData(source).data.runs[0].environmentId).not.toBe(first.data.runs[0].environmentId);
});

test('side-branch base and PR metadata and repeated attempts stay distinct', () => {
  const source = publication(); const first = source.runs[0];
  first.source = { branch: 'feature/example', message: 'Fictional feature', base: { branch: 'develop', commit: 'b'.repeat(40) }, pullRequest: { number: 12, url: 'https://github.com/ROCm/rocm-systems/pull/12' } };
  source.index.runFiles = ['runs/side-branches/fictional-attempt.json'];
  const retry = structuredClone(first); retry.id = 'fictional-retry'; retry.execution_summary.finished_at = '2026-10-01T06:01:00Z';
  source.runs.push(retry); source.index.runFiles.push('runs/side-branches/fictional-retry.json');
  const { data, sourceData } = validatePublishedDashboardData(source);
  expect(data.runs).toEqual([]); expect(data.allRuns.map(({ runId }) => runId)).toEqual(['fictional-attempt', 'fictional-retry']);
  expect(data.allRuns[1]).toMatchObject({ sourceBase: first.source.base, pullRequest: first.source.pullRequest });
  expect(sourceData).toEqual(source);
});


test('scalar environment projection retains protocol precedence over open provenance facts', () => {
  const source = publication();
  const before = validatePublishedDashboardData(source).data.runs[0].environmentId;
  source.runs[0].provenance.execution = { samples: 999 };
  const { data, sourceData } = validatePublishedDashboardData(source);
  expect(data.runs[0].environmentId).toBe(before);
  expect(data.runs[0].provenance.details.filter(({ key }) => key === 'execution.samples')).toEqual([{ key: 'execution.samples', label: 'execution.samples', value: 3 }]);
  expect(sourceData.runs[0].provenance.execution.samples).toBe(999);
});
