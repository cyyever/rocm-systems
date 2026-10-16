import { fixtureRunPath } from './runPath.js';
// Fictional deterministic maintained-schema measurements. Test/fixtures mode ONLY.
import { mkdir, readdir, rm, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath, pathToFileURL } from 'node:url';

export const CONFIGURATION_KEYS = ['gfx1250/single', 'gfx1250/default', 'gfx950/single', 'gfx950/default'];
const definitions = [
  ['a', 'Triton', 'Fictional GEMM', { operation: 'GEMM', m: 1024 }],
  ['b', 'Llama', 'Fictional decode', { tokens: 128 }],
  ['c', 'Triton', 'Fictional retired workload', { size: 64 }],
  ['d', 'Triton', 'Fictional added workload D', { size: 256 }],
  ['e', 'Llama', 'Fictional added workload E', { size: 512 }],
].map(([id, suite, name, problem]) => ({ id, suite, name, operation: problem.operation ?? 'Fictional computation', problem }));
const sha = (index) => `${index.toString(16).padStart(4, '0')}f1c7`.repeat(5);
const iso = (day, hour = 6, minute = 0) => new Date(Date.UTC(2026, 8, 11 + day, hour, minute)).toISOString();
const catalogFor = (current) => ({
  id: current ? 'fictional-current' : 'fictional-old',
  tests: structuredClone(definitions.filter(({ id }) => (current ? ['a', 'b', 'd', 'e'] : ['a', 'b', 'c']).includes(id))),
  configurations: Object.fromEntries(CONFIGURATION_KEYS.map((key) => [key,
    current ? (key === 'gfx950/default' ? ['a', 'b', 'd'] : ['a', 'b', 'd', 'e']) : ['a', 'b', 'c'],
  ])),
});

export function createMaintainedPublication() {
  const catalogs = Object.fromEntries([false, true].map((current) => {
    const catalog = catalogFor(current);
    return [`test-catalogs/${catalog.id}.json`, catalog];
  }));
  const canonical = Array.from({ length: 24 }, (_, index) => {
    const current = index >= 8;
    const testCatalog = `test-catalogs/fictional-${current ? 'current' : 'old'}.json`;
    const id = `fictional-develop-${String(index).padStart(2, '0')}`;
    return {
      schemaVersion: 1, id, testCatalog,
      source: { branch: 'develop', commit: sha(index + 1), committedAt: iso(index, 4), message: `FICTIONAL develop measurement ${index}` },
      execution: { completedAt: index === 21 ? '2026-10-05T10:00:00.000Z' : iso(index), trigger: index === 21 ? 'manual' : 'auto', machine: index < 16 ? 'fictional-node-a' : 'fictional-node-b' },
      environment: [{ key: 'sdk', label: 'Fictional SDK', value: index < 16 ? 'test-a' : 'test-b' }, { key: 'enabled', label: 'Feature enabled', value: true }, { key: 'cores', label: 'CPU cores', value: 32 }],
      configurations: CONFIGURATION_KEYS.filter((key) => !(index === 12 && key === 'gfx950/default')).map((key, configIndex) => {
        const [target, policy] = key.split('/');
        return { target, thread_policy: policy,
          results: catalogs[testCatalog].configurations[key].map((testId, testIndex) => {
            const status = (index === 8 && policy === 'single' && testId === 'd') || (index === 9 && policy === 'single' && testId === 'e') ? 'failed'
              : index === 8 && testId === 'e' ? 'timeout' : 'completed';
            const durationSeconds = status !== 'completed' ? null : Number((20 + testIndex * 10 + configIndex * 5 - index * 0.2).toFixed(2));
            return { testId, thread_policy: policy, status, timing_results_s: status === 'completed' ? [durationSeconds] : [], durationSeconds, error: status === 'completed' ? null : 'Fictional diagnostic' };
          }) };
      }),
    };
  });
  const branches = Array.from({ length: 20 }, (_, index) => {
    const run = structuredClone(canonical[23]);
    run.id = `fictional-branch-${String(index + 1).padStart(2, '0')}`;
    run.source = { branch: `fictional/optimization-${String(index + 1).padStart(2, '0')}`, commit: sha(100 + index), committedAt: '2026-10-05T09:00:00.000Z', message: `FICTIONAL branch ${index + 1}`,
      ...(index % 2 === 0 ? { base: { branch: 'develop', commit: canonical[20].source.commit }, pullRequest: { number: 1000 + index } } : {}),
    };
    run.execution.completedAt = `2026-10-05T11:${String(index).padStart(2, '0')}:00.000Z`;
    run.execution.trigger = 'manual';
    run.execution.machine = 'fictional-branch-node';
    run.environment[0].value = 'test-branch';
    if (index === 1) run.configurations = run.configurations.filter(({ thread_policy }) => thread_policy === 'single');
    if (index === 2) Object.assign(run.configurations[0].results[0], { status: 'failed', timing_results_s: [], durationSeconds: null, error: 'Fictional branch failure' });
    for (const config of run.configurations) for (const result of config.results) {
      if (result.status === 'completed') {
        result.durationSeconds = Number((result.durationSeconds * (0.9 + index / 100)).toFixed(2));
        result.timing_results_s = [result.durationSeconds];
      }
    }
    return run;
  });
  const runs = [...canonical, ...branches];
  // Configuration absence requires an equally sparse catalog, not one-sided
  // group omission. Preserve the base catalogs for fully populated attempts.
  for (const run of runs) {
    const original = catalogs[run.testCatalog];
    if (run.configurations.length === Object.keys(original.configurations).length) continue;
    const catalog = structuredClone(original);
    catalog.id = `${original.id}-${run.id}`;
    catalog.configurations = Object.fromEntries(run.configurations.map(({ target, thread_policy }) => {
      const key = `${target}/${thread_policy}`;
      return [key, original.configurations[key]];
    }));
    run.testCatalog = `test-catalogs/${catalog.id}.json`;
    catalogs[run.testCatalog] = catalog;
  }
  for (const run of runs) run.environment.push({ key: 'execution.benchmark_suite', label: 'execution.benchmark_suite', value: catalogs[run.testCatalog].id });
  return {
    index: { generatedAt: '2026-10-05T12:00:00.000Z', runFiles: runs.map(fixtureRunPath) },
    catalogs, runs,
  };
}

export async function writeMaintainedFixtureDirectory(directory) {
  return writeFixturePublication(directory, createMaintainedPublication());
}

export async function writeFixturePublication(directory, publication) {
  await mkdir(directory, { recursive: true });
  // This function deliberately targets test data only; never point it at published data.
  for (const entry of await readdir(directory)) await rm(path.join(directory, entry), { recursive: true, force: true });
  const files = { 'index.json': publication.index, ...publication.catalogs,
    ...Object.fromEntries(publication.runs.map((run, index) => [publication.index.runFiles[index], run])), };
  for (const [name, value] of Object.entries(files)) {
    await mkdir(path.dirname(path.join(directory, name)), { recursive: true });
    await writeFile(path.join(directory, name), `${JSON.stringify(value, null, 2)}\n`);
  }
  return publication;
}

if (process.argv[1] && import.meta.url === pathToFileURL(path.resolve(process.argv[1])).href) {
  await writeMaintainedFixtureDirectory(fileURLToPath(new URL('./data/', import.meta.url)));
  console.log('Wrote fictional maintained-schema test fixtures (24 develop, 20 branches).');
}
