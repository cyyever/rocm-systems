import { fixtureRunPath } from './runPath.js';
import { CONFIGURATION_KEYS } from './maintainedDataset.js';

// Separate fictional wire publication: never replace the default browser fixtures.
export function createOverviewContractPublication() {
  const definitions = [
    { id: 'a', suite: 'Triton', name: 'Fictional typed GEMM', operation: 'GEMM', problem: { shape: [16, 32], tuning: { enabled: true, tile: null } } },
    { id: 'b', suite: 'Llama', name: 'Fictional decode', operation: 'decode', problem: { tokens: 128 } },
    { id: 'c', suite: 'Triton', name: 'Fictional string shape', operation: 'GEMM', problem: { shape: '[16,32]' } },
    { id: 'd', suite: 'Triton', name: 'Fictional later workload', operation: 'GEMM', problem: { shape: [32, 32] } },
  ];
  const memberships = {
    old: Object.fromEntries(CONFIGURATION_KEYS.map((key) => [key, ['a', 'b']])),
    middle: {
      'gfx950/single': ['a', 'c'],
      'gfx950/default': ['b', 'c'],
      'gfx1250/default': ['a', 'b', 'c'],
    },
    current: {
      'gfx950/single': ['a', 'd'],
      'gfx950/default': ['c', 'd'],
      'gfx1250/single': ['a', 'b', 'd'],
      'gfx1250/default': ['a', 'b', 'd'],
    },
  };
  const catalogs = Object.fromEntries(Object.entries(memberships).map(([period, configurations]) => {
    const id = `fictional-contract-${period}`;
    const members = new Set(Object.values(configurations).flat());
    return [`test-catalogs/${id}.json`, { id, configurations,
      tests: definitions.filter((test) => members.has(test.id)) }];
  }));
  const attempts = [
    ['old-1', 'old', 1, 6, 10], ['old-2', 'old', 2, 6, 9],
    ['middle-4', 'middle', 4, 6, 8], ['middle-5', 'middle', 5, 6, 7],
    ['current-first', 'current', 6, 7, 6], ['current-retry', 'current', 6, 8, 5],
    ['current-failed', 'current', 6, 9, 4],
  ];
  const runs = attempts.map(([attempt, period, day, hour, seconds]) => {
    const id = `fictional-contract-${attempt}`;
    const testCatalog = `test-catalogs/fictional-contract-${period}.json`;
    const stamp = (time) => `2026-10-${String(day).padStart(2, '0')}T${String(time).padStart(2, '0')}:00:00.000Z`;
    return {
      schemaVersion: 1, id, testCatalog,
      source: { branch: 'develop', commit: String(day).repeat(40), committedAt: stamp(4), message: `FICTIONAL contract commit ${day}` },
      execution: { completedAt: stamp(hour), trigger: 'manual', machine: 'fictional-contract-node' },
      environment: [{ key: 'execution.benchmark_suite', label: 'execution.benchmark_suite', value: catalogs[testCatalog].id }],
      configurations: Object.entries(catalogs[testCatalog].configurations).map(([key, members]) => {
        const [target, thread_policy] = key.split('/');
        return { target, thread_policy, results: members.map((testId) => {
          const failed = attempt === 'current-failed' && key === 'gfx1250/single' && testId === 'b';
          const durationSeconds = failed ? null : testId === 'a' ? seconds : { b: 100, c: 200, d: 300 }[testId];
          return { testId, thread_policy, status: failed ? 'failed' : 'completed',
            timing_results_s: failed ? [] : [durationSeconds], durationSeconds,
            error: failed ? 'Fictional required decode failed' : null };
        }) };
      }),
    };
  });
  return { index: { generatedAt: '2026-10-06T12:00:00.000Z', runFiles: runs.map(fixtureRunPath) }, catalogs, runs };
}
