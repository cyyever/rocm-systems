import { fixtureCatalog, fixtureProvenance, fixtureSummary } from './inputFormat.js';
const CATALOG_PATH = 'test-catalogs/synthetic-core-v2.json';
const KEYS = ['gfx1250/single', 'gfx950/default'];
const catalog = fixtureCatalog('synthetic-core-v2', [
    { id: 'gemm-f16-1024', suite: 'Triton', name: 'Fictional GEMM FP16', operation: 'GEMM', problem: { operation: 'GEMM', m: 1024 } },
    { id: 'gemm-bf16-4096', suite: 'Triton', name: 'Fictional GEMM BF16', operation: 'GEMM', problem: { operation: 'GEMM', m: 4096 } },
  ], Object.fromEntries(KEYS.map((key) => [key, ['gemm-f16-1024', 'gemm-bf16-4096']])));
function syntheticRun(index) {
  const day = new Date(Date.UTC(2026, 0, 1) + index * 86400_000).toISOString();
  const id = `synthetic-run-${String(index).padStart(4, '0')}`;
  return { schemaVersion: 1, id, benchmark_catalog: CATALOG_PATH,
    source: { branch: 'develop', message: `Fictional queue test ${index}` },
    execution: { trigger: 'auto', machine_label: 'fictional-queue-node' },
    execution_summary: fixtureSummary(catalog.benchmark_suite, day),
    provenance: fixtureProvenance(index.toString(16).padStart(40, '0'), day),
    configurations: KEYS.map((key) => {
      const [target, mode] = key.split('/');
      return { target, thread_policy: mode, benchmark_results: catalog.membership[target][mode].map((testId, testIndex) => ({ id: testId, status: 'completed', timing_results_s: [1 + testIndex + index / 1000], error: null })) };
    }),
  };
}
// Request-queue stress data, generated in memory only; not shipped by Vite.
export function createSyntheticDataset(runCount = 500) {
  const runFiles = Array.from({ length: runCount }, (_, index) => `runs/default-branch/synthetic-run-${String(index).padStart(4, '0')}.json`);
  const bodies = new Map([
    ['https://dashboard.test/data/index.json', { generatedAt: '2027-06-01T00:00:00.000Z', runFiles }],
    [`https://dashboard.test/data/${CATALOG_PATH}`, catalog],
  ]);
  runFiles.forEach((runFile, index) => bodies.set(`https://dashboard.test/data/${runFile}`, syntheticRun(index)));
  return { runCount, runFiles, catalogPath: CATALOG_PATH, indexUrl: 'https://dashboard.test/data/index.json', bodies };
}
