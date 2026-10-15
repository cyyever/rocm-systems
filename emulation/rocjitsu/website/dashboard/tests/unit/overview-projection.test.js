import { expect, test } from 'vitest';
import { selectOverviewProjection } from '../../src/data/overviewProjection.js';

const filters = { targets: ['gfx950', 'gfx1250'], modes: ['single'], suites: ['gemm'] };
const catalog = (id, configurations) => ({ id, configurations, tests: ['a', 'b', 'c'].map((id) => ({ id, suite: id === 'c' ? 'fft' : 'gemm' })) });
function run(id, day, catalog, entries, { sha = id, completion = `${day}T12:00:00Z`, branch = 'develop' } = {}) {
  return { runId: id, branch, testCatalog: catalog.id, catalogId: catalog.id,
    commitTimestamp: `${day}T10:00:00Z`, timestamp: completion, provenance: { rocjitsuCommitSha: sha },
    configurations: Object.keys(entries).map((key) => { const [target, thread_policy] = key.split('/'); return { target, thread_policy }; }),
    tests: Object.entries(entries).flatMap(([key, durations]) => Object.entries(durations).map(([id, value]) => {
      const [target, mode] = key.split('/');
      return { testId: `${key}:${id}`, logicalTestId: id, target, mode, suite: id === 'c' ? 'fft' : 'gemm',
        status: value === null ? 'failed' : 'completed', durationSeconds: value };
    })) };
}
const data = (runs, catalogs) => ({ runs, catalogs: Object.fromEntries(catalogs.map((c) => [c.id, c])) });

test('daily cohorts intersect chosen catalogs per configuration before result eligibility; latest failure stays a gap', () => {
  const a = catalog('A', { 'gfx950/single': ['a', 'b'], 'gfx1250/single': ['b'] });
  const b = catalog('B', { 'gfx950/single': ['a', 'c'] });
  const c = catalog('C', { 'gfx950/single': ['a', 'b'], 'gfx1250/single': ['b'] });
  const runs = [run('one', '2026-01-01', a, { 'gfx950/single': { a: 4, b: 100 }, 'gfx1250/single': { b: 2 } }),
    run('two', '2026-01-02', b, { 'gfx950/single': { a: 2, c: 99 } }),
    run('three', '2026-01-03', c, { 'gfx950/single': { a: null, b: 3 }, 'gfx1250/single': { b: 1 } })];
  const model = selectOverviewProjection(data(runs, [a, b, c]), filters, { range: 'ALL' });
  expect(model.rows[0].cohortIds).toEqual(['b']); // Target ordering, not publication order.
  const row = model.rows.find((r) => r.target === 'gfx950');
  expect(row.cohortIds).toEqual(['a']);
  expect(row.points.map((p) => p.durationSeconds)).toEqual([4, 2, null]);
  expect(row.points.map((p) => p.speedup)).toEqual([1, 2, null]);
  expect(row.latest.completed).toBe(0);
  expect(row.latest.required).toBe(1);
  expect(row.latest.reason).toBe('failed');
  expect(model.rows[0].points[1].reason).toBe('configuration-absent');
  expect(model.rows[0].latest.speedup).toBe(2);
  expect(selectOverviewProjection(data(runs, [a, b, c]), { ...filters, targets: ['gfx950'] }).rows[0].cohortIds).toEqual(['a']);
});

test('daily picks one latest commit/attempt before configuration projection, including UTC boundaries and backfills', () => {
  const c = catalog('C', { 'gfx950/single': ['a'] });
  const older = run('older', '2026-01-01', c, { 'gfx950/single': { a: 1 } }, { completion: '2026-01-04T12:00:00Z' });
  const first = run('first', '2026-01-01', c, { 'gfx950/single': { a: 2 } });
  first.commitTimestamp = '2026-01-01T23:59:59Z';
  const failed = { ...first, runId: 'retry', timestamp: '2026-01-02T01:00:00Z', tests: first.tests.map((t) => ({ ...t, status: 'timeout', durationSeconds: null })) };
  const boundary = run('boundary', '2026-01-02', c, { 'gfx950/single': { a: 4 } });
  boundary.commitTimestamp = '2026-01-02T00:00:00Z';
  const side = run('side', '2026-02-01', c, { 'gfx950/single': { a: 99 } }, { branch: 'feature' });
  const model = selectOverviewProjection(data([side, boundary, first, older, failed], [c]), { ...filters, targets: ['gfx950'] });
  expect(model.slots.map((s) => s.run.runId)).toEqual(['retry', 'boundary']);
  expect(model.rows[0].points[0].reason).toBe('timeout');
  expect(model.rows[0].reference.runId).toBe('boundary');
  expect(model.anchorDay).toBe('2026-01-02');
});

test('equal commit timestamps choose SHA before completion and latest attempt within that commit', () => {
  const c = catalog('C', { 'gfx950/single': ['a'] });
  const runs = [
    run('b-first', '2026-01-01', c, { 'gfx950/single': { a: 2 } }, { sha: 'bbbb', completion: '2026-01-01T11:00:00Z' }),
    run('a-later', '2026-01-01', c, { 'gfx950/single': { a: 4 } }, { sha: 'aaaa', completion: '2026-01-01T12:00:00Z' }),
  ];
  const project = () => selectOverviewProjection(data(runs, [c]), { ...filters, targets: ['gfx950'] });
  expect(project().latestRun.runId).toBe('b-first');
  expect(project().rows[0].latest.durationSeconds).toBe(2);
  runs.push(run('b-retry', '2026-01-01', c, { 'gfx950/single': { a: 1 } }, { sha: 'bbbb', completion: '2026-01-01T11:30:00Z' }));
  expect(project().latestRun.runId).toBe('b-retry');
  expect(project().rows[0].latest.durationSeconds).toBe(1);
});

test('catalog switching preserves the full-history date window and deterministic daily tie-breaks', () => {
  const a = catalog('A', { 'gfx950/single': ['a'] });
  const b = catalog('B', { 'gfx950/single': ['a'] });
  const runs = [run('old', '2026-01-01', a, { 'gfx950/single': { a: 8 } }),
    run('z', '2026-01-20', b, { 'gfx950/single': { a: 2 } }, { sha: 'z' }),
    run('a', '2026-01-20', b, { 'gfx950/single': { a: 4 } }, { sha: 'a' }),
    run('zz', '2026-01-20', b, { 'gfx950/single': { a: 1 } }, { sha: 'z' })];
  const all = selectOverviewProjection(data(runs, [a, b]), filters, { range: '1M' });
  const scoped = selectOverviewProjection(data(runs, [a, b]), filters, { range: '1M', catalogId: 'A' });
  expect(scoped.dayKeys).toEqual(all.dayKeys);
  expect(all.latestRun.runId).toBe('zz');
  expect(scoped.latestRun.runId).toBe('old');
  expect(scoped.rows.find((r) => r.target === 'gfx950').latest.durationSeconds).toBe(8);
});

test('empty selections/intersections and invalid totals never become zero or a success fallback', () => {
  const a = catalog('A', { 'gfx950/single': ['a'] });
  const b = catalog('B', { 'gfx950/single': ['b'] });
  const runs = [run('one', '2026-01-01', a, { 'gfx950/single': { a: 2 } }),
    run('two', '2026-01-02', b, { 'gfx950/single': { b: 1 } })];
  const source = data(runs, [a, b]);
  expect(selectOverviewProjection(source, { ...filters, targets: [] }).rows).toEqual([]);
  expect(selectOverviewProjection(source, { ...filters, modes: [] }).rows).toEqual([]);
  const empty = selectOverviewProjection(source, filters).rows.find((r) => r.target === 'gfx950');
  expect(empty.cohortIds).toEqual([]);
  expect(empty.latest.durationSeconds).toBeNull();
  expect(empty.latest.reason).toBe('no-comparable-workloads');
  expect(selectOverviewProjection(source, { ...filters, suites: [] }).rows.every((r) => r.reference === null)).toBe(true);
  const c = catalog('C', { 'gfx950/single': ['a', 'b'] });
  const invalid = run('invalid', '2026-01-03', c, { 'gfx950/single': { a: 0, b: 2 } });
  expect(selectOverviewProjection(data([invalid], [c]), filters).rows.find((r) => r.target === 'gfx950').reference).toBeNull();
  invalid.tests.forEach((t) => { t.durationSeconds = 1e308; });
  const tiny = run('tiny', '2026-01-01', c, { 'gfx950/single': { a: 5e-324, b: 5e-324 } });
  const large = run('large', '2026-01-02', c, { 'gfx950/single': { a: 4e15, b: 4e15 } });
  expect(selectOverviewProjection(data([tiny, large], [c]), filters).rows.find((r) => r.target === 'gfx950').durationChangePercent).toBeNull();
  const overflow = selectOverviewProjection(data([invalid], [c]), filters).rows.find((r) => r.target === 'gfx950');
  expect(overflow.latest.reason).toBe('invalid-total');
  expect(overflow.latest.durationSeconds).toBeNull();
});

test('row order is policies first then deterministic targets and missing results retain required counts', () => {
  const c = catalog('C', { 'gfx950/single': ['a', 'b'], 'gfx950/default': ['a'] });
  const r = run('one', '2026-01-01', c, { 'gfx950/single': { a: 1 }, 'gfx950/default': { a: 2 } });
  const model = selectOverviewProjection(data([r], [c]), { ...filters, targets: ['gfx950', 'gfx1250'], modes: ['default', 'single'] });
  expect(model.rows.map((r) => r.key)).toEqual(['gfx1250/single', 'gfx950/single', 'gfx1250/default', 'gfx950/default']);
  expect(model.rows[1].latest).toMatchObject({ required: 2, completed: 1, reason: 'missing-result', durationSeconds: null });
  expect(model.rows[3].latest.durationSeconds).toBe(2);
});

test('weekly retains repeated SHA attempts without cap and calculates cohort before removing incomplete attempts', () => {
  const a = catalog('A', { 'gfx950/single': ['a', 'b'] });
  const b = catalog('B', { 'gfx950/single': ['a'] });
  const runs = Array.from({ length: 10 }, (_, i) => run(`attempt-${i}`, '2026-01-07', a,
    { 'gfx950/single': { a: 2, b: 5 } }, { sha: 'same', completion: `2026-01-07T12:00:${String(i).padStart(2, '0')}Z` }));
  runs.push(run('failed', '2026-01-07', b, { 'gfx950/single': { a: null } }));
  const model = selectOverviewProjection(data(runs, [a, b]), { ...filters, targets: ['gfx950'] }, { range: '1W' });
  expect(model.attempts).toHaveLength(11);
  expect(model.attempts.find((a) => a.runId === 'failed').eligible).toBe(false);
  expect(model.rows[0].cohortIds).toEqual(['a']);
  expect(model.slots.filter((s) => s.run)).toHaveLength(10);
  expect(model.rows[0].latest.runId).toBe('attempt-9');
  expect(model.endpointLabel).toBe('Latest eligible plotted run');
  expect(model.weeklyEligibility).toBe('selected-workloads-succeed');
});
